"""
Group calls (WhatsApp style, mesh WebRTC).

Every member of the group gets a ``CallParticipant`` row when the call
starts (state RINGING; the caller is JOINED). People then join, decline,
miss (ring timeout) or leave independently:

* declining only affects the person who declines;
* anyone in the group can join while the call is ongoing (late join or
  rejoin after leaving), up to ``MAX_GROUP_CALL_PARTICIPANTS`` at once;
* leaving does not end the call until at most one person is left in it;
* the ring timeout marks the call missed only for people who never joined.

All state lives in the database (several server processes may serve the
same call). Changes are broadcast on the ``call_<room>`` channel-layer group
(``member_joined`` / ``member_left`` / ``member_declined`` / ``member_missed``
/ ``call_ended``) and as ``calls.updated`` inbox nudges.

WebRTC pairing rule (enforced by the clients, validated by the consumer):
the participant who joins later sends the offer to everyone already in the
call, so two peers never offer to each other at the same time (no glare).
"""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone

from .choices import CallStatus, ParticipantState
from .constants import MAX_GROUP_CALL_PARTICIPANTS
from .models import Call, CallParticipant

ACTIVE = (CallStatus.RINGING, CallStatus.ONGOING)


class GroupCallError(Exception):
    """A request that cannot be honoured; ``status`` is the HTTP code."""

    def __init__(self, detail, status=400):
        super().__init__(detail)
        self.detail = detail
        self.status = status


def _send_group(room_id, event, payload):
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(
        f"call_{room_id}",
        {"type": "call.event", "event": event, "payload": payload},
    )


def _send_user(user_id, event, payload):
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(
        f"user_call_{user_id}",
        {"type": "call.event", "event": event, "payload": payload},
    )


def present_qs(call):
    """Participants who are in the call right now."""
    return call.participants.filter(state=ParticipantState.JOINED, left_at__isnull=True)


def participant_states(call):
    """``[{user, state, is_muted}]`` for every invited member (small: <= group size)."""
    return [
        {"user": row["user_id"], "state": row["state"], "is_muted": row["is_muted"]}
        for row in call.participants.values("user_id", "state", "is_muted").order_by("id")
    ]


def start_group_call(room, user, call_type):
    """Create the call, ring every other member (caller is already in it)."""
    from apps.chat.models import Participant

    now = timezone.now()
    member_ids = list(Participant.objects.filter(room=room).values_list("user_id", flat=True))
    with transaction.atomic():
        call = Call.objects.create(room=room, caller=user, call_type=call_type, is_group=True)
        CallParticipant.objects.bulk_create(
            [
                CallParticipant(
                    call=call,
                    user_id=member_id,
                    state=ParticipantState.JOINED if member_id == user.id else ParticipantState.RINGING,
                    answered_at=now if member_id == user.id else None,
                )
                for member_id in member_ids
            ]
        )

    from .lifecycle import schedule_ring_timeout

    schedule_ring_timeout(call.id)

    payload = {
        "call_id": call.id,
        "caller": user.id,
        "room": room.id,
        "call_type": call_type,
        "is_group": True,
    }
    for member_id in member_ids:
        if member_id != user.id:
            _send_user(member_id, "incoming_call", payload)
    # Web Push "Incoming group call" for members with no open tab.
    from apps.notifications.push import notify_incoming_call
    notify_incoming_call(call, member_ids)
    return call


def join_group_call(call, user):
    """
    Join (accept, late join or rejoin). Returns the user ids already in the
    call: the joiner sends a WebRTC offer to each of them.
    """
    from apps.chat.models import Participant

    from .utils import has_active_call

    with transaction.atomic():
        call = Call.objects.select_for_update().get(pk=call.pk)
        if call.status not in ACTIVE or call.ended_at:
            raise GroupCallError("This call has ended.", 400)
        if not Participant.objects.filter(room_id=call.room_id, user=user).exists():
            raise GroupCallError("You are not a participant of this group.", 403)
        row, _ = CallParticipant.objects.get_or_create(call=call, user=user)
        if row.state == ParticipantState.JOINED and row.left_at is None:
            # Already in (e.g. a retried request): just report who is there.
            return list(present_qs(call).exclude(user=user).values_list("user_id", flat=True))
        if has_active_call(user, exclude_call_id=call.id):
            raise GroupCallError("You are already in another call.", 409)
        if present_qs(call).count() >= MAX_GROUP_CALL_PARTICIPANTS:
            raise GroupCallError(
                f"This call is full. Group calls can have up to {MAX_GROUP_CALL_PARTICIPANTS} people.",
                409,
            )
        now = timezone.now()
        row.state = ParticipantState.JOINED
        row.left_at = None
        row.is_muted = False
        row.is_on_hold = False
        if row.answered_at is None:
            row.answered_at = now
        row.save(update_fields=["state", "left_at", "is_muted", "is_on_hold", "answered_at"])
        if call.status == CallStatus.RINGING:
            call.status = CallStatus.ONGOING
            call.answered_at = now
            call.save(update_fields=["status", "answered_at"])
        others = list(present_qs(call).exclude(user=user).values_list("user_id", flat=True))

    _send_group(call.room_id, "member_joined", {"call_id": call.id, "user": user.id})
    from .events import notify_calls_changed

    notify_calls_changed(call, "joined")
    return others


def decline_group_call(call, user):
    """Decline for yourself only. The call ends if nobody else can still join."""
    with transaction.atomic():
        call = Call.objects.select_for_update().get(pk=call.pk)
        if call.status not in ACTIVE:
            raise GroupCallError("Call already finished.", 400)
        updated = call.participants.filter(user=user, state=ParticipantState.RINGING).update(
            state=ParticipantState.DECLINED
        )
        if not updated:
            return call
        # Nobody joined and everybody declined/missed: the caller is alone.
        nobody_left_to_ring = not call.participants.filter(state=ParticipantState.RINGING).exists()
        give_up = call.status == CallStatus.RINGING and nobody_left_to_ring

    _send_group(call.room_id, "member_declined", {"call_id": call.id, "user": user.id})
    if give_up:
        end_group_call(call, status=CallStatus.REJECTED, action="rejected")
    else:
        from .events import notify_calls_changed

        notify_calls_changed(call, "declined")
    return call


def leave_group_call(call, user):
    """Leave; the call ends for everyone once at most one person remains."""
    with transaction.atomic():
        call = Call.objects.select_for_update().get(pk=call.pk)
        if call.status not in ACTIVE:
            return call
        updated = call.participants.filter(
            user=user, state=ParticipantState.JOINED, left_at__isnull=True
        ).update(state=ParticipantState.LEFT, left_at=timezone.now(), is_on_hold=False)
        if not updated:
            return call
        remaining = present_qs(call).count()
        # Before anyone answered only the caller is in the call (remaining 0
        # once they leave); after that, one person alone ends the call.
        finish = remaining == 0 or (remaining <= 1 and call.answered_at is not None)

    _send_group(call.room_id, "member_left", {"call_id": call.id, "user": user.id})
    if finish:
        end_group_call(call)
    else:
        from .events import notify_calls_changed

        notify_calls_changed(call, "left")
    return call


def end_group_call(call, status=CallStatus.ENDED, action="ended"):
    """Finish the call for everyone and write the chat call card."""
    from .events import notify_calls_changed, publish_call_message
    from .lifecycle import cancel_ring_timeout

    with transaction.atomic():
        call = Call.objects.select_for_update().get(pk=call.pk)
        if call.status not in ACTIVE:
            return call
        call.end()
        if status != CallStatus.ENDED:
            call.status = status
            call.save(update_fields=["status"])
        now = timezone.now()
        call.participants.filter(state=ParticipantState.RINGING).update(state=ParticipantState.MISSED)
        call.participants.filter(state=ParticipantState.JOINED, left_at__isnull=True).update(
            state=ParticipantState.LEFT, left_at=now
        )
    cancel_ring_timeout(call.id)

    _send_group(
        call.room_id,
        "call_ended",
        {
            "call_id": call.id,
            "room_id": call.room_id,
            "status": call.status,
            "duration": call.duration,
            "ended_at": call.ended_at.isoformat() if call.ended_at else None,
        },
    )
    publish_call_message(call)
    notify_calls_changed(call, action)
    return call


def group_ring_timeout(call):
    """
    Ring timeout. Nobody joined: the whole call becomes missed. Otherwise
    the call goes on and only the people still ringing stop ringing (they
    can still join from the chat's "Join" banner).
    """
    if call.status == CallStatus.RINGING:
        end_group_call(call, status=CallStatus.MISSED, action="missed")
        _send_group(call.room_id, "missed_call", {"call_id": call.id, "status": CallStatus.MISSED})
        return
    if call.status != CallStatus.ONGOING:
        return
    ringing = list(call.participants.filter(state=ParticipantState.RINGING).values_list("user_id", flat=True))
    if not ringing:
        return
    call.participants.filter(user_id__in=ringing, state=ParticipantState.RINGING).update(state=ParticipantState.MISSED)
    for user_id in ringing:
        _send_group(call.room_id, "member_missed", {"call_id": call.id, "user": user_id})
    from .events import notify_calls_changed

    notify_calls_changed(call, "ring_timeout")


def can_signal(call_id, sender_id, target_id):
    """
    Offer / answer / ICE may only flow between two people of the same active
    call. In a group call both must currently be in it (joined, not left).
    """
    call = Call.objects.filter(pk=call_id, status__in=ACTIVE, ended_at__isnull=True).only("id", "is_group").first()
    if call is None:
        return False
    rows = call.participants.filter(user_id__in=(sender_id, target_id))
    if call.is_group:
        rows = rows.filter(state=ParticipantState.JOINED, left_at__isnull=True)
    return rows.count() == 2
