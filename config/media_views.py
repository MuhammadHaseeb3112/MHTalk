"""
Development media server with HTTP Range support.

Django's built-in ``static.serve`` ignores the ``Range`` header. Browsers
need ranges to play and seek videos and voice notes: phone recordings keep
their index ("moov atom") at the end of the file, so without ranges Chrome
shows a black frame and the video never starts. In production the web server
(nginx, a CDN or object storage) serves media and handles ranges itself.
"""

import mimetypes
import os
import re

from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse
from django.utils._os import safe_join
from django.utils.http import http_date

RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
CHUNK = 64 * 1024


def _stream(path, start, length):
    with open(path, "rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining > 0:
            data = handle.read(min(CHUNK, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data


# MEDIA_ROOT/private/ holds view once media. It is never served by URL: the
# only way to read it is the authenticated, one-time view-once endpoint.
PRIVATE_PREFIX = "private"


def is_private_media_path(path):
    """True for "private/..." however it is spelled (./, //, \\, %2F, case)."""
    from urllib.parse import unquote

    normalized = unquote(str(path or "")).replace("\\", "/")
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    return bool(parts) and parts[0].lower() == PRIVATE_PREFIX


def serve_media(request, path, document_root=None):
    if is_private_media_path(path):
        raise Http404("Not found")
    try:
        full_path = safe_join(str(document_root), path)
    except Exception as exc:  # path traversal attempt
        raise Http404("Not found") from exc
    if not os.path.isfile(full_path):
        raise Http404("Not found")

    size = os.path.getsize(full_path)
    content_type, encoding = mimetypes.guess_type(full_path)
    content_type = content_type or "application/octet-stream"
    modified = http_date(os.path.getmtime(full_path))

    match = RANGE_RE.match(request.headers.get("Range", "").strip())
    if not match or (not match.group(1) and not match.group(2)):
        response = FileResponse(open(full_path, "rb"), content_type=content_type)
        response["Accept-Ranges"] = "bytes"
        response["Last-Modified"] = modified
        if encoding:
            response["Content-Encoding"] = encoding
        return response

    first, last = match.group(1), match.group(2)
    if first:
        start = int(first)
        end = min(int(last), size - 1) if last else size - 1
    else:  # suffix range: the last N bytes
        start = max(0, size - int(last))
        end = size - 1
    if start >= size or start > end:
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{size}"
        return response

    length = end - start + 1
    response = StreamingHttpResponse(_stream(full_path, start, length), status=206, content_type=content_type)
    response["Content-Length"] = str(length)
    response["Content-Range"] = f"bytes {start}-{end}/{size}"
    response["Accept-Ranges"] = "bytes"
    response["Last-Modified"] = modified
    return response
