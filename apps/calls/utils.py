from django.db.models import Q

from .choices import CallStatus, ParticipantState
from .models import Call
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


ACTIVE_CALL_STATUSES = (
    CallStatus.RINGING,
    CallStatus.ONGOING,
)


def _repair_stale_finished_calls():
    """Repair legacy rows where ended_at was set but status stayed active."""
    Call.objects.filter(
        status__in=ACTIVE_CALL_STATUSES,
        ended_at__isnull=False,
    ).update(status=CallStatus.ENDED)


def has_active_call(user, exclude_call_id=None):
    """
    Is ``user`` busy? A one-to-one call counts while it rings or runs. A group
    call only counts while the user is actually in it: ringing members of a
    group call they ignore stay free to make and take other calls.
    """
    _repair_stale_finished_calls()
    queryset = Call.objects.filter(
        Q(is_group=False, participants__user=user)
        | Q(
            is_group=True,
            participants__user=user,
            participants__state=ParticipantState.JOINED,
            participants__left_at__isnull=True,
        ),
        status__in=ACTIVE_CALL_STATUSES,
        ended_at__isnull=True,
    )
    if exclude_call_id is not None:
        queryset = queryset.exclude(pk=exclude_call_id)
    return queryset.exists()


def active_room_call(room):
    """The ringing/ongoing call of a room, if any."""
    _repair_stale_finished_calls()
    return Call.objects.filter(
        room=room,
        status__in=ACTIVE_CALL_STATUSES,
        ended_at__isnull=True,
    ).first()


def room_has_active_call(room):
    _repair_stale_finished_calls()
    return Call.objects.filter(
        room=room,
        status__in=ACTIVE_CALL_STATUSES,
        ended_at__isnull=True,
    ).exists()



def broadcast_call_event(
    room_id,
    event,
    payload,
):
    """
    Broadcast a call event to all websocket clients
    connected to the call room.
    """

    channel_layer = get_channel_layer()

    async_to_sync(
        channel_layer.group_send
    )(
        f"call_{room_id}",
        {
            "type": "call.event",
            "event": event,
            "payload": payload,
        },
    )