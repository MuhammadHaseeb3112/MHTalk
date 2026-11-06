"""
REST endpoints for polls, disappearing messages, view once media and link
previews. Every endpoint checks chat membership first.
"""

import json
import mimetypes

from django.db import IntegrityError, transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .choices import MessageType
from .features import (
    broadcast_message_patch,
    can_change_disappearing,
    cast_poll_vote,
    live_location_active,
    set_disappearing_timer,
    validate_location_content,
)
from .link_preview import extract_first_url, get_link_preview
from .models import ChatRoom, DeletedMessage, Message, Participant, ViewOnceOpen
from .serializers import MessageSerializer
from .utils import (
    broadcast_message,
    broadcast_receipts,
    broadcast_room_changed,
    get_message_with_relations,
    persist_receipts_bulk,
)


def _member_message(request, message_id):
    """A message in one of the user's chats that is still visible to them."""
    message = get_object_or_404(
        Message.objects.select_related("room"),
        pk=message_id,
        room__participants__user=request.user,
        room__is_active=True,
    )
    if DeletedMessage.objects.filter(message=message, user=request.user).exists():
        raise Http404("Not found")
    return message


class PollVoteAPIView(APIView):
    """
    Set the caller's answer for a poll: ``{"option_ids": [..]}`` replaces the
    previous answer, ``[]`` removes it. Everyone in the chat gets the new
    counts live (``patch`` socket event with the poll state).
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Vote in a poll",
        request={"type": "object", "properties": {"option_ids": {"type": "array", "items": {"type": "integer"}}}},
        tags=["Chat"],
    )
    def post(self, request, message_id):
        message = _member_message(request, message_id)
        if message.message_type != MessageType.POLL or message.is_deleted:
            return Response({"detail": "This message is not a poll."}, status=status.HTTP_400_BAD_REQUEST)
        option_ids = request.data.get("option_ids", [])
        if not isinstance(option_ids, list):
            return Response({"option_ids": ["Provide a list of option ids."]}, status=status.HTTP_400_BAD_REQUEST)
        poll = cast_poll_vote(message, request.user, option_ids)
        broadcast_message_patch(message.room_id, message.id, {"poll": poll})
        return Response({"message_id": message.id, "poll": poll})


class LiveLocationAPIView(APIView):
    """
    The sender of a live location moves it (``{"latitude", "longitude",
    "accuracy"?}``) or stops sharing (``{"stop": true}``). Everyone in the
    chat gets the new position live (``patch`` socket event).
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Update or stop a live location",
        request={
            "type": "object",
            "properties": {
                "latitude": {"type": "number"},
                "longitude": {"type": "number"},
                "accuracy": {"type": "number"},
                "stop": {"type": "boolean"},
            },
        },
        tags=["Chat"],
    )
    def post(self, request, message_id):
        message = _member_message(request, message_id)
        if message.message_type != MessageType.LOCATION or message.is_deleted:
            return Response({"detail": "This message is not a location."}, status=status.HTTP_400_BAD_REQUEST)
        if message.sender_id != request.user.id:
            return Response({"detail": "Only the sender can update a live location."}, status=status.HTTP_403_FORBIDDEN)
        with transaction.atomic():
            message = Message.objects.select_for_update().get(pk=message.pk)
            try:
                content = json.loads(message.content or "{}")
            except ValueError:
                content = {}
            if not isinstance(content, dict) or not content.get("live"):
                return Response({"detail": "This location is not live."}, status=status.HTTP_400_BAD_REQUEST)
            if request.data.get("stop") is True:
                content["stopped"] = True
                content["live_until"] = timezone.now().isoformat()
            else:
                if not live_location_active(content):
                    return Response({"detail": "Live location has ended."}, status=status.HTTP_400_BAD_REQUEST)
                moved = validate_location_content(
                    {
                        "latitude": request.data.get("latitude"),
                        "longitude": request.data.get("longitude"),
                        "accuracy": request.data.get("accuracy"),
                    }
                )
                content.update({key: moved[key] for key in ("latitude", "longitude")})
                if "accuracy" in moved:
                    content["accuracy"] = moved["accuracy"]
            content["updated_at"] = timezone.now().isoformat()
            message.content = json.dumps(content)
            message.save(update_fields=["content"])
        broadcast_message_patch(message.room_id, message.id, {"content": content}, inbox_user_ids=[request.user.id])
        return Response({"message_id": message.id, "content": content})


class DisappearingMessagesAPIView(APIView):
    """
    Turn disappearing messages on (24 hours / 7 days / 90 days) or off for a
    chat: ``{"seconds": 604800}``. Posts the system notice to the chat.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Set disappearing messages timer",
        request={"type": "object", "properties": {"seconds": {"type": "integer", "enum": [0, 86400, 604800, 7776000]}}},
        tags=["Chat"],
    )
    def post(self, request, pk):
        room = get_object_or_404(ChatRoom, pk=pk, participants__user=request.user, is_active=True)
        if not can_change_disappearing(room, request.user):
            return Response(
                {"detail": "Only admins can change this group's settings."},
                status=status.HTTP_403_FORBIDDEN,
            )
        raw = request.data.get("seconds")
        if isinstance(raw, bool) or not str(raw).strip().isdigit():
            return Response({"seconds": ["Choose Off, 24 hours, 7 days or 90 days."]}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            room = ChatRoom.objects.select_for_update().get(pk=room.pk)
            notice = set_disappearing_timer(room, request.user, int(raw))
        data = None
        if notice is not None:
            notice = get_message_with_relations(notice.id)
            broadcast_message(notice, request)
            broadcast_room_changed(room.id, "disappearing")
            data = MessageSerializer(notice, context={"request": request}).data
        return Response({"room": room.id, "disappearing_seconds": room.disappearing_seconds, "message": data})


class ViewOnceMediaAPIView(APIView):
    """
    The only way to get a view once photo, video or voice message. Each recipient may download
    it exactly once (the open is recorded before the first byte is sent);
    the sender can't reopen it either. Files live under MEDIA_ROOT/private/,
    which the web server refuses to serve.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Open view once media (once)", tags=["Chat"])
    def get(self, request, message_id):
        message = _member_message(request, message_id)
        if not message.is_view_once or message.is_deleted:
            raise Http404("Not found")
        if message.sender_id == request.user.id:
            return Response({"detail": "You can't open view once media you sent."}, status=status.HTTP_403_FORBIDDEN)
        joined = Participant.objects.filter(room_id=message.room_id, user=request.user).values_list("joined_at", flat=True).first()
        if joined is None or joined > message.created_at:
            raise Http404("Not found")
        attachment = message.attachments.first()
        voice = getattr(message, "voice_note", None) if attachment is None else None
        stored = attachment.file if attachment is not None else (voice.audio if voice is not None else None)
        if not stored:
            return Response({"detail": "This media is no longer available."}, status=status.HTTP_410_GONE)
        if attachment is not None:
            mime_type = attachment.mime_type
        else:
            # ".webm" guesses as video/webm; a voice note is always audio.
            guessed = mimetypes.guess_type(stored.name)[0] or "audio/webm"
            mime_type = guessed if guessed.startswith("audio/") else "audio/" + guessed.split("/", 1)[-1]
        try:
            handle = stored.open("rb")
        except (FileNotFoundError, OSError):
            return Response({"detail": "This media is no longer available."}, status=status.HTTP_410_GONE)
        try:
            with transaction.atomic():
                ViewOnceOpen.objects.create(message=message, user=request.user)
        except IntegrityError:
            handle.close()
            return Response({"detail": "You already opened this view once media."}, status=status.HTTP_410_GONE)

        opened_by = list(ViewOnceOpen.objects.filter(message=message).values_list("user_id", flat=True))
        transaction.on_commit(lambda: _after_open(message, request.user, opened_by))

        response = FileResponse(handle, content_type=mime_type or "application/octet-stream")
        response["Cache-Control"] = "no-store, private"
        response["Content-Disposition"] = "inline"
        response["X-Content-Type-Options"] = "nosniff"
        return response


def _after_open(message, user, opened_by):
    # Opening counts as reading it (blue ticks), and the sender's bubble
    # switches to "Opened".
    broadcast_receipts(persist_receipts_bulk([message.id], user.id, "read"))
    broadcast_message_patch(
        message.room_id,
        message.id,
        {"view_once_opened_by": opened_by},
        inbox_user_ids=[message.sender_id, user.id],
    )


class LinkPreviewAPIView(APIView):
    """
    ``GET ?url=`` → ``{"preview": {title, description, site_name, image, url}}``
    (or ``null``). Used by the composer while typing; fetched server-side
    with SSRF protection and cached for a day.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "link_preview"

    @extend_schema(summary="Link preview metadata", tags=["Chat"])
    def get(self, request):
        raw = str(request.query_params.get("url") or "").strip()
        url = extract_first_url(raw)
        if not url:
            return Response({"url": ["Provide an http or https link."]}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"preview": get_link_preview(url)})
