"""
Helpers for the WhatsApp message features: polls, @mentions, disappearing
messages, view once media, link previews and locations.

Views, serializers and the WebSocket consumer share these so every path
validates and broadcasts the same way.
"""

import json
import math

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from rest_framework import serializers

from .choices import DISAPPEARING_CHOICES, SYSTEM_PREFIX, MessageType, RoomType
from .models import Message, MessageMention, Participant, Poll, PollOption, PollVote

POLL_MIN_OPTIONS = 2
POLL_MAX_OPTIONS = 12
POLL_QUESTION_MAX = 255
POLL_OPTION_MAX = 100


# ==========================================================
# Realtime
# ==========================================================

def broadcast_message_patch(room_id, message_id, patch, inbox_user_ids=()):
    """
    Push a partial update of one message (``patch`` is merged into the
    client's copy) to everyone viewing the room, plus the inbox sockets of
    ``inbox_user_ids`` (e.g. the sender, whose chat may not be open).
    The patch must not contain per-user data: it is the same for everyone.
    """
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    event = {"room_id": int(room_id), "message_id": int(message_id), "patch": patch}
    async_to_sync(channel_layer.group_send)(f"chat_{room_id}", {"type": "message.patch", **event})
    for user_id in set(inbox_user_ids or ()):
        async_to_sync(channel_layer.group_send)(f"chat_inbox_{user_id}", {"type": "inbox.message_patch", **event})


# ==========================================================
# Polls
# ==========================================================

def validate_poll_content(content):
    """Validate ``{"question", "options": [...], "allow_multiple"}``; returns a clean dict."""
    if not isinstance(content, dict):
        raise serializers.ValidationError({"content": "A poll must be a JSON object."})
    question = str(content.get("question") or "").strip()
    if not question:
        raise serializers.ValidationError({"content": "The poll needs a question."})
    if len(question) > POLL_QUESTION_MAX:
        raise serializers.ValidationError({"content": f"The question must be {POLL_QUESTION_MAX} characters or fewer."})
    raw_options = content.get("options")
    if not isinstance(raw_options, list):
        raise serializers.ValidationError({"content": "Poll options must be a list."})
    options = []
    for raw in raw_options:
        text = str(raw.get("text") if isinstance(raw, dict) else raw or "").strip()
        if not text:
            continue
        if len(text) > POLL_OPTION_MAX:
            raise serializers.ValidationError({"content": f"Options must be {POLL_OPTION_MAX} characters or fewer."})
        if text.lower() in (option.lower() for option in options):
            raise serializers.ValidationError({"content": "Poll options must be different."})
        options.append(text)
    if not POLL_MIN_OPTIONS <= len(options) <= POLL_MAX_OPTIONS:
        raise serializers.ValidationError(
            {"content": f"A poll needs between {POLL_MIN_OPTIONS} and {POLL_MAX_OPTIONS} options."}
        )
    allow_multiple = content.get("allow_multiple", False)
    if isinstance(allow_multiple, str):
        allow_multiple = allow_multiple.lower() in ("true", "1", "on")
    return {"question": question, "options": options, "allow_multiple": bool(allow_multiple)}


def create_poll(message, poll_data):
    poll = Poll.objects.create(
        message=message,
        question=poll_data["question"],
        allow_multiple=poll_data["allow_multiple"],
    )
    PollOption.objects.bulk_create(
        [PollOption(poll=poll, text=text, position=index) for index, text in enumerate(poll_data["options"])]
    )
    return poll


def poll_payload(poll):
    """Poll state shared by every viewer (each client derives "my vote")."""
    if poll is None:
        return None
    options = []
    voters = set()
    for option in poll.options.all():
        option_voters = [vote.user_id for vote in option.votes.all()]
        voters.update(option_voters)
        options.append({
            "id": option.id,
            "text": option.text,
            "voters": option_voters,
            "count": len(option_voters),
        })
    return {
        "id": poll.id,
        "question": poll.question,
        "allow_multiple": poll.allow_multiple,
        "options": options,
        "total_voters": len(voters),
    }


def load_poll(message_id):
    return (
        Poll.objects.filter(message_id=message_id)
        .prefetch_related("options__votes")
        .first()
    )


def cast_poll_vote(message, user, option_ids):
    """
    Replace ``user``'s answer with ``option_ids`` (empty = remove the vote).
    Raises ValidationError for foreign options or several answers in a
    single-answer poll. Returns the fresh poll payload.
    """
    poll = Poll.objects.filter(message=message).first()
    if poll is None:
        raise serializers.ValidationError({"detail": "This message is not a poll."})
    wanted = []
    for value in option_ids or []:
        if isinstance(value, bool):
            raise serializers.ValidationError({"option_ids": "Invalid option."})
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError({"option_ids": "Invalid option."}) from exc
        if number not in wanted:
            wanted.append(number)
    valid = set(PollOption.objects.filter(poll=poll, pk__in=wanted).values_list("pk", flat=True))
    if len(valid) != len(wanted):
        raise serializers.ValidationError({"option_ids": "Option does not belong to this poll."})
    if not poll.allow_multiple and len(wanted) > 1:
        raise serializers.ValidationError({"option_ids": "This poll allows only one answer."})
    with transaction.atomic():
        PollVote.objects.filter(option__poll=poll, user=user).exclude(option_id__in=wanted).delete()
        PollVote.objects.bulk_create(
            [PollVote(option_id=option_id, user=user) for option_id in wanted],
            ignore_conflicts=True,
        )
    return poll_payload(load_poll(message.id))


def copy_poll(original, new_message):
    """Forwarding a poll creates a fresh poll with the same options and no votes."""
    poll = getattr(original, "poll", None) if original.message_type == MessageType.POLL else None
    if poll is None:
        return
    create_poll(new_message, {
        "question": poll.question,
        "allow_multiple": poll.allow_multiple,
        "options": [option.text for option in poll.options.all()],
    })


# ==========================================================
# Mentions
# ==========================================================

def validate_mentions(room, raw_ids):
    """Mentioned ids must be members of a group; returns the clean id list."""
    from .views import parse_id_list

    ids = parse_id_list(raw_ids)
    if not ids:
        return []
    if room.room_type != RoomType.GROUP:
        raise serializers.ValidationError({"mentions": "Mentions are only available in groups."})
    if len(ids) > 256:
        raise serializers.ValidationError({"mentions": "Too many mentions."})
    members = set(Participant.objects.filter(room=room, user_id__in=ids).values_list("user_id", flat=True))
    if members != set(ids):
        raise serializers.ValidationError({"mentions": "You can only mention members of this group."})
    return ids


def save_mentions(message, user_ids):
    if user_ids:
        MessageMention.objects.bulk_create(
            [MessageMention(message=message, user_id=user_id) for user_id in user_ids],
            ignore_conflicts=True,
        )


# ==========================================================
# Disappearing messages
# ==========================================================

def disappearing_label(seconds):
    return {86400: "24 hours", 604800: "7 days", 7776000: "90 days"}.get(int(seconds or 0), "Off")


def can_change_disappearing(room, user):
    """
    Who may change a chat's disappearing-messages timer: both people in a
    private chat; in groups the "Edit group info" permission decides (only
    admins when the group restricts it). Single check for every caller.
    """
    from .permissions import can_edit_group_info

    return can_edit_group_info(user, room)


def system_content(kind, **payload):
    return SYSTEM_PREFIX + json.dumps({"kind": kind, **payload}, separators=(",", ":"))


def set_disappearing_timer(room, user, seconds):
    """Change the timer and post the "turned on/off disappearing messages" notice."""
    seconds = int(seconds)
    if seconds not in DISAPPEARING_CHOICES:
        raise serializers.ValidationError({"seconds": "Choose Off, 24 hours, 7 days or 90 days."})
    if room.disappearing_seconds == seconds:
        return None
    room.disappearing_seconds = seconds
    room.save(update_fields=["disappearing_seconds", "updated_at"])
    return Message.objects.create(
        room=room,
        sender=user,
        message_type=MessageType.TEXT,
        content=system_content("disappearing", seconds=seconds, actor_id=user.id),
    )


# ==========================================================
# Location
# ==========================================================

def validate_location_content(content):
    """
    ``{"latitude", "longitude", "address"?, "name"?}``. ``address`` used to be
    required; it is optional now (a shared "current location" has none) but
    older clients that send it keep working.
    """
    if not isinstance(content, dict):
        raise serializers.ValidationError({"content": "Location must be a JSON object."})
    for field in ("latitude", "longitude"):
        if field not in content:
            raise serializers.ValidationError({"content": f"{field} is required."})
    try:
        latitude = float(content["latitude"])
        longitude = float(content["longitude"])
    except (TypeError, ValueError) as exc:
        raise serializers.ValidationError({"content": "Latitude and longitude must be numbers."}) from exc
    if not (math.isfinite(latitude) and math.isfinite(longitude)) or not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise serializers.ValidationError({"content": "Coordinates are out of range."})
    clean = {
        "latitude": round(latitude, 7),
        "longitude": round(longitude, 7),
        "address": str(content.get("address") or "").strip()[:255],
    }
    name = str(content.get("name") or "").strip()[:120]
    if name:
        clean["name"] = name
    accuracy = content.get("accuracy")
    if isinstance(accuracy, (int, float)) and not isinstance(accuracy, bool) and math.isfinite(accuracy) and accuracy >= 0:
        clean["accuracy"] = round(float(accuracy), 1)
    return clean
