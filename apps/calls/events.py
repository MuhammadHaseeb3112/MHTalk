"""
Call side effects shared by the REST views, the signaling consumer and the
ring-timeout timer: the chat "call card" message and live inbox nudges.
"""

import json

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone

from django.db.models import Q

from .choices import CallStatus, ParticipantState

CALL_EVENT_PREFIX = "__WHATSUP_CALL_EVENT__:"

# Statuses that produce a call card in the conversation.
FINAL_STATUSES = (
    CallStatus.ENDED,
    CallStatus.MISSED,
    CallStatus.REJECTED,
    CallStatus.CANCELLED,
    CallStatus.BUSY,
)


def call_event_payload(call):
    payload = {
        "kind": "call_event",
        "call_id": call.id,
        "room_id": call.room_id,
        "call_type": call.call_type,
        "status": call.status,
        "duration": int(call.duration or 0),
        "caller_id": call.caller_id,
        "started_at": call.started_at.isoformat() if call.started_at else None,
        "answered_at": call.answered_at.isoformat() if call.answered_at else None,
        "ended_at": call.ended_at.isoformat() if call.ended_at else None,
    }
    if call.is_group:
        # One card is shared by the whole group; each viewer works out
        # "joined" vs "missed" from the list of people who joined.
        joined = sorted(call.participants.filter(answered_at__isnull=False).values_list("user_id", flat=True))
        payload["is_group"] = True
        payload["joined_ids"] = joined
        payload["joined_count"] = len(joined)
        payload["declined_ids"] = sorted(
            call.participants.filter(state=ParticipantState.DECLINED).values_list("user_id", flat=True)
        )
    return payload


def ensure_call_message(call):
    """
    Create (or update) the single chat message that represents a finished
    call. Returns ``(message, created)``. Retries return the same row thanks
    to the ``client_message_id`` idempotency key.
    """
    from apps.chat.models import Message

    if call.status not in FINAL_STATUSES:
        return None, False

    content = CALL_EVENT_PREFIX + json.dumps(call_event_payload(call), separators=(",", ":"))
    with transaction.atomic():
        message, created = Message.objects.get_or_create(
            room_id=call.room_id,
            sender_id=call.caller_id,
            client_message_id=f"call-event-{call.id}",
            defaults={"message_type": "TEXT", "content": content},
        )
        if not created and message.content != content:
            message.content = content
            message.save(update_fields=["content", "updated_at"])
    return message, created


def publish_call_message(call, request=None):
    """Persist the call card and push it to the room and every inbox."""
    from apps.chat.utils import broadcast_message, broadcast_room_changed, get_message_with_relations

    message, created = ensure_call_message(call)
    if message is None:
        return None
    if created:
        broadcast_message(get_message_with_relations(message.id), request)
    else:
        broadcast_room_changed(call.room_id, "call_updated")
    return message


def notify_calls_changed(call, action="updated"):
    """Tell every participant to refresh call history / the missed badge."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    user_ids = list(call.participants.values_list("user_id", flat=True))
    for user_id in user_ids:
        async_to_sync(channel_layer.group_send)(
            f"chat_inbox_{user_id}",
            {
                "type": "inbox.call_changed",
                "call_id": call.id,
                "room_id": call.room_id,
                "status": call.status,
                "action": action,
            },
        )


MISSABLE_STATUSES = (CallStatus.MISSED, CallStatus.CANCELLED, CallStatus.ENDED, CallStatus.REJECTED)


def is_missed_for(call, user_id):
    """
    A call counts as missed for someone who did not place or answer it.
    Group calls: someone who never joined and did not decline it (uses the
    prefetched participants, no extra query when they are prefetched).
    """
    if call.caller_id == user_id:
        return False
    if call.is_group:
        if call.status not in MISSABLE_STATUSES:
            return False
        row = next((p for p in call.participants.all() if p.user_id == user_id), None)
        return bool(row and row.answered_at is None and row.state != ParticipantState.DECLINED)
    if call.answered_at:
        return False
    return call.status in (CallStatus.MISSED, CallStatus.CANCELLED, CallStatus.ENDED)


def _missed_rows(user):
    from .models import CallParticipant

    one_to_one = Q(
        call__is_group=False,
        call__answered_at__isnull=True,
        call__status__in=(CallStatus.MISSED, CallStatus.CANCELLED, CallStatus.ENDED),
    )
    group = Q(call__is_group=True, answered_at__isnull=True, call__status__in=MISSABLE_STATUSES) & ~Q(
        state=ParticipantState.DECLINED
    )
    return CallParticipant.objects.filter(one_to_one | group, user=user, missed_seen_at__isnull=True).exclude(
        call__caller=user
    )


def mark_missed_calls_seen(user):
    return _missed_rows(user).update(missed_seen_at=timezone.now())


def unseen_missed_count(user):
    return _missed_rows(user).count()
