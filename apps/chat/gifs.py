"""
GIF search for the emoji panel's "GIF" tab (GIPHY, like WhatsApp).

The browser asks our server; the server adds the API key (never sent to the
browser) and returns only what the picker needs. Configure in .env:

    GIPHY_API_KEY=...   # free key from https://developers.giphy.com/dashboard/

Without a key the endpoint answers 503 and the tab explains how to turn it on.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

GIPHY_URL = "https://api.giphy.com/v1/gifs/{endpoint}"


def _slim(item):
    images = item.get("images") or {}
    small = images.get("fixed_width") or {}
    full = images.get("original") or {}
    still = images.get("fixed_width_still") or {}
    mp4 = full.get("mp4") or small.get("mp4")
    if not mp4:
        return None
    return {
        "id": item.get("id"),
        "title": (item.get("title") or "")[:120],
        "mp4": mp4,
        "preview": small.get("mp4") or mp4,
        "still": still.get("url") or small.get("url") or "",
        "width": int(full.get("width") or small.get("width") or 0) or None,
        "height": int(full.get("height") or small.get("height") or 0) or None,
    }


class GifSearchAPIView(APIView):
    """GET ?q=… (empty = trending). Returns up to 24 GIFs."""

    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Search GIFs (GIPHY)", tags=["Chat"])
    def get(self, request):
        key = (getattr(settings, "GIPHY_API_KEY", "") or "").strip()
        if not key:
            return Response(
                {"detail": "GIFs aren't set up yet. Add a free GIPHY key as GIPHY_API_KEY in .env and restart."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        query = (request.query_params.get("q") or "").strip()[:60]
        offset = max(0, min(int(request.query_params.get("offset") or 0), 500))
        cache_key = f"gifs:{query.lower()}:{offset}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)
        params = {"api_key": key, "limit": 24, "offset": offset, "rating": "pg-13", "bundle": "messaging_non_clips"}
        if query:
            params["q"] = query
        url = GIPHY_URL.format(endpoint="search" if query else "trending") + "?" + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310 (fixed https URL)
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            logger.warning("GIF search failed: %s", error)
            return Response({"detail": "Couldn't load GIFs right now."}, status=status.HTTP_502_BAD_GATEWAY)
        results = [slim for slim in (_slim(item) for item in payload.get("data") or []) if slim]
        data = {"results": results}
        cache.set(cache_key, data, 600)
        return Response(data)


class RecentStickersAPIView(APIView):
    """
    Stickers sent or received in your chats (newest first), so the Sticker
    tab shows the same stickers on every device, like WhatsApp's "Recent".
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Recent stickers", tags=["Chat"])
    def get(self, request):
        from .choices import MessageType
        from .models import Attachment

        rows = (
            Attachment.objects.filter(
                message__message_type=MessageType.STICKER,
                message__is_deleted=False,
                message__room__participants__user=request.user,
            )
            .exclude(message__deleted_for_users__user=request.user)
            .order_by("-message__created_at")
            .values_list("file", "file_size", "file_name")[:200]
        )
        seen = set()
        items = []
        for file, size, name in rows:
            key = (name, size)
            if not file or key in seen:
                continue
            seen.add(key)
            items.append(file if file.startswith("http") else settings.MEDIA_URL + file)
            if len(items) >= 40:
                break
        return Response({"results": items})
