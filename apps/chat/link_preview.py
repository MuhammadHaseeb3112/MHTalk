"""
Link previews (Open Graph / Twitter cards / <title>) fetched server-side.

Fetching arbitrary URLs from the server is a classic SSRF hole, so every hop
is checked before connecting:

* only ``http`` / ``https`` URLs, no credentials in the URL;
* the host name is resolved once and **every** resolved address must be a
  public unicast address (private, loopback, link-local, multicast, reserved,
  shared/CGNAT, unspecified and IPv4-mapped variants are refused);
* the connection is made to the vetted IP itself (the Host header / TLS SNI
  still carry the name), so a DNS answer cannot change between the check and
  the connect (DNS rebinding);
* redirects are followed manually (max 3) and each target is re-validated;
* 4 s overall deadline, at most ~512 KB read, ``text/html`` only.

Results (including "no preview") are cached in the Django cache for a day so
the composer, the sender and every recipient share one fetch. Tests can allow
loopback with ``MHTALK_LINK_PREVIEW_ALLOW_LOOPBACK = True`` to hit a local
``http.server``; it is never enabled in real settings.
"""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import re
import socket
import ssl
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from django.conf import settings
from django.core.cache import cache

MAX_REDIRECTS = 3
TIMEOUT_SECONDS = 4.0
MAX_BYTES = 512 * 1024
CACHE_SECONDS = 24 * 60 * 60
NEGATIVE_CACHE_SECONDS = 60 * 60
USER_AGENT = "MHTalkLinkPreview/1.0 (+https://github.com/; like WhatsApp)"

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
TRAILING_PUNCTUATION = ".,:;!?)]}'\""


class PreviewError(Exception):
    """The URL is not allowed or could not be previewed."""


# ---------------------------------------------------------------- URL helpers

def extract_first_url(text):
    """First http(s) URL in a message, without trailing punctuation."""
    match = URL_RE.search(str(text or ""))
    if not match:
        return None
    url = match.group(0).rstrip(TRAILING_PUNCTUATION)
    return url if len(url) <= 2048 else None


def _check_scheme_and_host(url):
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise PreviewError("Only http and https links can be previewed.")
    if parts.username or parts.password:
        raise PreviewError("Links with credentials are not previewed.")
    host = parts.hostname
    if not host:
        raise PreviewError("The link has no host.")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise PreviewError("Invalid port.") from exc
    return parts, host, port


# ---------------------------------------------------------------- SSRF guard

def _allow_loopback():
    return bool(getattr(settings, "MHTALK_LINK_PREVIEW_ALLOW_LOOPBACK", False))


def is_public_ip(value, allow_loopback=False):
    """True only for globally routable unicast addresses."""
    try:
        ip = ipaddress.ip_address(str(value).split("%", 1)[0])
    except ValueError:
        return False
    # ::ffff:10.0.0.1, 64:ff9b::/96 (NAT64) and 6to4 wrap an IPv4 address: judge the inner one.
    if ip.version == 6:
        if ip.ipv4_mapped is not None:
            return is_public_ip(ip.ipv4_mapped, allow_loopback)
        if ip.sixtofour is not None:
            return is_public_ip(ip.sixtofour, allow_loopback)
        if ip in ipaddress.ip_network("64:ff9b::/96"):
            return is_public_ip(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF), allow_loopback)
    if allow_loopback and ip.is_loopback:
        return True
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or not ip.is_global
    ):
        return False
    return True


def resolve_public_ip(host, port):
    """Resolve ``host`` and return one vetted address (all answers must be public)."""
    allow_loopback = _allow_loopback()
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError) as exc:
        raise PreviewError("The link's host could not be resolved.") from exc
    addresses = []
    for family, _type, _proto, _canon, sockaddr in infos:
        if family not in (socket.AF_INET, socket.AF_INET6):
            continue
        addresses.append(sockaddr[0])
    if not addresses:
        raise PreviewError("The link's host could not be resolved.")
    # If any answer points inside the network the host is refused outright,
    # otherwise an attacker could mix one public and one private record.
    for address in addresses:
        if not is_public_ip(address, allow_loopback):
            raise PreviewError("Links to private or local addresses are not previewed.")
    return addresses[0]


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """HTTP connection to an already-vetted IP (Host header keeps the name)."""

    def __init__(self, host, port, ip, timeout):
        super().__init__(host, port, timeout=timeout)
        self._ip = ip

    def connect(self):
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS to a vetted IP with SNI + certificate checks for the real name."""

    def __init__(self, host, port, ip, timeout):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


# ---------------------------------------------------------------- fetching

def _remaining(deadline):
    left = deadline - time.monotonic()
    if left <= 0:
        raise PreviewError("The site took too long to answer.")
    return left


def _set_read_timeout(response, seconds):
    """Shrink the socket timeout to what is left of the overall deadline."""
    raw = getattr(getattr(response, "fp", None), "raw", None)
    sock = getattr(raw, "_sock", None)
    if sock is not None:
        try:
            sock.settimeout(seconds)
        except OSError:
            pass


def fetch_html(url):
    """Fetch ``url`` with the SSRF guard. Returns ``(final_url, html_text)``."""
    deadline = time.monotonic() + TIMEOUT_SECONDS
    current = url
    for _hop in range(MAX_REDIRECTS + 1):
        parts, host, port = _check_scheme_and_host(current)
        ip = resolve_public_ip(host, port)
        connection_class = _PinnedHTTPSConnection if parts.scheme == "https" else _PinnedHTTPConnection
        connection = connection_class(host, port, ip, timeout=_remaining(deadline))
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        try:
            connection.request(
                "GET",
                path,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
                    "Accept-Language": "en",
                    "Accept-Encoding": "identity",
                },
            )
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    raise PreviewError("Redirect without a target.")
                current = urljoin(current, location.strip())
                continue
            if response.status != 200:
                raise PreviewError(f"The site answered {response.status}.")
            content_type = (response.getheader("Content-Type") or "").lower()
            mime = content_type.split(";", 1)[0].strip()
            if mime not in ("text/html", "application/xhtml+xml"):
                raise PreviewError("The link is not a web page.")
            charset = "utf-8"
            match = re.search(r"charset=([\w.-]+)", content_type)
            if match:
                charset = match.group(1)
            chunks = []
            total = 0
            while total < MAX_BYTES:
                _set_read_timeout(response, _remaining(deadline))
                chunk = response.read(min(65536, MAX_BYTES - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            body = b"".join(chunks)
            try:
                text = body.decode(charset, errors="replace")
            except LookupError:
                text = body.decode("utf-8", errors="replace")
            return current, text
        except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
            raise PreviewError("The site could not be reached.") from exc
        finally:
            connection.close()
    raise PreviewError("Too many redirects.")


# ---------------------------------------------------------------- parsing

class _MetaParser(HTMLParser):
    """Collects <meta> tags and the <title> text from the document head."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.title = ""
        self._in_title = False
        self.done = False

    def handle_starttag(self, tag, attrs):
        if self.done:
            return
        attributes = {key.lower(): (value or "") for key, value in attrs}
        if tag == "meta":
            key = (attributes.get("property") or attributes.get("name") or "").strip().lower()
            content = attributes.get("content", "").strip()
            if key and content and key not in self.meta:
                self.meta[key] = content
        elif tag == "title":
            self._in_title = True
        elif tag == "body" and self.meta:
            # Everything useful lives in <head>; stop early.
            self.done = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "head":
            self.done = True

    def handle_data(self, data):
        if self._in_title and len(self.title) < 500:
            self.title += data


def _clean(value, limit):
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    return value[:limit]


def parse_preview(html, base_url):
    """Build the preview dict from HTML (Open Graph > Twitter > <title>)."""
    parser = _MetaParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # malformed markup: keep what was collected
        pass
    meta = parser.meta
    title = meta.get("og:title") or meta.get("twitter:title") or parser.title
    description = meta.get("og:description") or meta.get("twitter:description") or meta.get("description")
    site_name = meta.get("og:site_name") or meta.get("application-name") or (urlsplit(base_url).hostname or "")
    image = meta.get("og:image:secure_url") or meta.get("og:image") or meta.get("twitter:image") or meta.get("twitter:image:src")
    if image:
        image = urljoin(base_url, image.strip())
        if urlsplit(image).scheme not in ("http", "https"):
            image = ""
    preview = {
        "url": base_url,
        "title": _clean(title, 200),
        "description": _clean(description, 300),
        "site_name": _clean(site_name, 100),
        "image": (image or "")[:1000],
    }
    if not preview["title"] and not preview["description"]:
        return None
    return preview


# ---------------------------------------------------------------- public API

def _cache_key(url):
    return "linkpreview:v1:" + hashlib.sha256(url.encode("utf-8", "ignore")).hexdigest()


def cached_preview(url):
    """(found, preview) from the cache without touching the network."""
    value = cache.get(_cache_key(url))
    if value is None:
        return False, None
    return True, (value or None)


def get_link_preview(url, use_network=True):
    """
    Preview dict for ``url`` or None. Cached for a day (failures for an hour).
    With ``use_network=False`` only the cache is consulted.
    """
    if not url:
        return None
    found, preview = cached_preview(url)
    if found or not use_network:
        return preview
    try:
        _check_scheme_and_host(url)
        final_url, html = fetch_html(url)
        preview = parse_preview(html, final_url)
        if preview:
            # Keep the link the user wrote; the card opens it.
            preview["url"] = url
    except PreviewError:
        preview = None
    cache.set(_cache_key(url), preview or {}, CACHE_SECONDS if preview else NEGATIVE_CACHE_SECONDS)
    return preview
