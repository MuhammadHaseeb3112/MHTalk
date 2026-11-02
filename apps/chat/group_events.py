"""
Group system messages ("Alice changed this group's settings…", "Bob joined
using this group's invite link", "Carol left").

They follow the same convention as call cards (apps/calls/events.py): a TEXT
message whose content is a ``__WHATSUP_…__:`` prefix plus a JSON payload, so
they flow through the normal message list, chat list preview and sockets.
The client renders them as centred pills. The payload's ``text`` contains an
``{actor}`` placeholder the client replaces with "You" or the actor's name.

System messages never count as unread and cannot be edited, forwarded,
pinned or deleted for everyone.
"""

import json

from .choices import MessageType
from .models import Message

GROUP_EVENT_PREFIX = "__WHATSUP_GROUP_EVENT__:"

PERMISSION_TEXT = {
    "send_messages_admins_only": (
        "{actor} changed this group's settings to allow all members to send messages",
        "{actor} changed this group's settings to allow only admins to send messages",
    ),
    "edit_info_admins_only": (
        "{actor} changed this group's settings to allow all members to edit this group's settings",
        "{actor} changed this group's settings to allow only admins to edit this group's settings",
    ),
    "add_members_admins_only": (
        "{actor} changed this group's settings to allow all members to add others to this group",
        "{actor} changed this group's settings to allow only admins to add others to this group",
    ),
}


def actor_display_name(user):
    profile = getattr(user, "profile", None)
    name = (getattr(profile, "display_name", "") or "").strip()
    return name or user.phone_number


def is_group_event(message):
    return str(getattr(message, "content", "") or "").startswith(GROUP_EVENT_PREFIX)


def create_group_event(room, actor, event, text, **extra):
    """Persist a system message in ``room`` (no broadcast)."""
    payload = {
        "kind": "group_event",
        "event": event,
        "actor_id": actor.pk,
        "actor_name": actor_display_name(actor),
        "text": text,
        **extra,
    }
    return Message.objects.create(
        room_id=getattr(room, "pk", room),
        sender=actor,
        message_type=MessageType.TEXT,
        content=GROUP_EVENT_PREFIX + json.dumps(payload, separators=(",", ":")),
    )


def post_group_event(room, actor, event, text, request=None, **extra):
    """Persist a system message and push it to every member live."""
    from .utils import broadcast_message, get_message_with_relations

    message = create_group_event(room, actor, event, text, **extra)
    broadcast_message(get_message_with_relations(message.pk), request)
    return message
