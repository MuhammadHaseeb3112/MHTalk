"""
Group permission checks (Group info > Group permissions), shared by every
REST view and WebSocket path so the rules live in one place.

    can_edit_group_info(user, room)   name, icon, description, disappearing timer
    can_send_message(user, room)      text, media, voice, forwards (not reactions)
    can_add_members(user, room)       add people / see and share the invite link

Private chats: both members may always edit/send, except that nobody can
send to an account that was deleted.
"""

from .choices import RoomType
from .models import Participant

ONLY_ADMINS_CAN_SEND = "Only admins can send messages to this group."
DELETED_ACCOUNT_PEER = "You can't send messages to a deleted account."
NOT_A_PARTICIPANT = "You are not a participant of this room."


def _membership(user, room):
    user_id = getattr(user, "pk", user)
    room_id = getattr(room, "pk", room)
    if not user_id or not room_id:
        return None
    # ``user__is_active``: a deleted account keeps its private-chat rows but
    # can no longer act in them (even from a socket opened before deletion).
    return (
        Participant.objects.filter(room_id=room_id, user_id=user_id, user__is_active=True)
        .only("id", "is_admin")
        .first()
    )


def _room(room):
    from .models import ChatRoom

    if isinstance(room, ChatRoom):
        return room
    return ChatRoom.objects.filter(pk=room).first()


def is_group_admin(user, room):
    membership = _membership(user, room)
    return bool(membership and membership.is_admin)


def can_edit_group_info(user, room):
    room = _room(room)
    if room is None:
        return False
    membership = _membership(user, room)
    if membership is None:
        return False
    if room.room_type != RoomType.GROUP:
        return True
    return membership.is_admin or not room.edit_info_admins_only


def send_message_error(user, room):
    """``None`` when ``user`` may post in ``room``; otherwise the reason."""
    room = _room(room)
    if room is None:
        return NOT_A_PARTICIPANT
    membership = _membership(user, room)
    if membership is None:
        return NOT_A_PARTICIPANT
    if room.room_type == RoomType.GROUP:
        if room.send_messages_admins_only and not membership.is_admin:
            return ONLY_ADMINS_CAN_SEND
        return None
    peer_deleted = (
        Participant.objects.filter(room_id=room.pk, user__is_deleted=True)
        .exclude(user_id=getattr(user, "pk", user))
        .exists()
    )
    return DELETED_ACCOUNT_PEER if peer_deleted else None


def can_send_message(user, room):
    return send_message_error(user, room) is None


def can_add_members(user, room):
    room = _room(room)
    if room is None or room.room_type != RoomType.GROUP:
        return False
    membership = _membership(user, room)
    if membership is None:
        return False
    return membership.is_admin or not room.add_members_admins_only


def group_permissions(room):
    """Serialized group permission settings (``True`` = only admins)."""
    return {
        "edit_info_admins_only": bool(room.edit_info_admins_only),
        "send_messages_admins_only": bool(room.send_messages_admins_only),
        "add_members_admins_only": bool(room.add_members_admins_only),
    }
