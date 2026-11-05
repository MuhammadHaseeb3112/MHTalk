"""
Replies to a status with anything (photo, video, voice, GIF, sticker,
document, location...): the message goes to the private chat with the status
owner and carries a small snapshot of the status (``Message.status_ref``),
which the chat shows as a "Name · Status" card above it, like WhatsApp.
"""

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import Contact
from apps.chat.choices import RoomType
from apps.chat.models import Participant

from .models import Status


def status_snapshot(status_obj):
    media_url = ""
    if status_obj.media:
        try:
            media_url = status_obj.media.url
        except (ValueError, AttributeError):
            media_url = ""
    return {
        "status_id": status_obj.id,
        "status_type": status_obj.status_type,
        "status_text": (status_obj.content or "").strip()[:180],
        "status_media": media_url,
        "status_bg": getattr(status_obj, "background_color", "") or "",
        "status_fg": getattr(status_obj, "text_color", "") or "",
        "owner_id": status_obj.user_id,
        "status_created_at": status_obj.created_at.isoformat(),
    }


def viewer_can_see(status_obj, user):
    from .views import ContactsStatusAPIView

    contact_ids = set(Contact.objects.filter(owner=user).values_list("contact_user_id", flat=True))
    contact_ids.update(
        Participant.objects.filter(
            room__room_type=RoomType.PRIVATE,
            room__is_active=True,
            room__participants__user=user,
        )
        .exclude(user=user)
        .values_list("user_id", flat=True)
    )
    return ContactsStatusAPIView().can_view_status(status_obj, user, contact_ids)


def status_ref_for(request, room):
    """The snapshot for ``status_id`` in the request, or None. Raises when invalid."""
    raw = request.data.get("status_id") if hasattr(request, "data") else None
    if raw in (None, "", "null"):
        return None
    try:
        status_id = int(raw)
    except (TypeError, ValueError) as error:
        raise ValidationError({"status_id": "Invalid status."}) from error
    status_obj = (
        Status.objects.select_related("user")
        .filter(pk=status_id, is_deleted=False, expires_at__gt=timezone.now())
        .first()
    )
    if status_obj is None:
        raise ValidationError({"status_id": "This status is no longer available."})
    if status_obj.user_id == request.user.id or not viewer_can_see(status_obj, request.user):
        raise PermissionDenied("You can't reply to this status.")
    is_their_chat = (
        room.room_type == RoomType.PRIVATE
        and Participant.objects.filter(room=room, user_id=status_obj.user_id).exists()
    )
    if not is_their_chat:
        raise ValidationError({"status_id": "Status replies go to the private chat with its owner."})
    return status_snapshot(status_obj)
