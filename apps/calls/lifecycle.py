from threading import Timer

from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .choices import CallStatus
from .constants import CALL_RING_TIMEOUT
from .models import Call


CALL_TIMERS = {}


def schedule_ring_timeout(call_id):
    """
    Automatically mark a ringing call as missed after timeout.
    """

    timer = Timer(
        CALL_RING_TIMEOUT,
        timeout_call,
        args=[call_id],
    )

    CALL_TIMERS[call_id] = timer

    timer.start()


def cancel_ring_timeout(call_id):
    """
    Cancel timeout when call is answered/rejected/etc.
    """

    timer = CALL_TIMERS.pop(
        call_id,
        None,
    )

    if timer:
        timer.cancel()


def timeout_call(call_id):

    try:

        call = Call.objects.get(pk=call_id)

    except Call.DoesNotExist:

        return

    if call.status != CallStatus.RINGING:
        return

    call.status = CallStatus.MISSED

    call.ended_at = timezone.now()

    call.save(
        update_fields=[
            "status",
            "ended_at",
        ],
    )


    channel_layer = get_channel_layer()

    async_to_sync(
        channel_layer.group_send,
    )(
        f"call_{call.room_id}",
        {
            "type": "call.event",
            "event": "missed_call",
            "payload": {
                "call_id": call.id,
            },
        },
    )
    
    cancel_ring_timeout(
        call.id,
    )

    CALL_TIMERS.pop(
        call_id,
        None,
    )


def leave_call(
    call,
    user,
):
    """
    Mark a participant as having left the call.
    """

    participant = call.participants.filter(
        user=user,
    ).first()

    if participant is None:
        return

    if participant.left_at:
        return

    participant.left_at = timezone.now()

    participant.save(
        update_fields=[
            "left_at",
        ]
    )

    remaining = call.participants.filter(
        left_at__isnull=True,
    ).count()

    if remaining <= 1:

        call.end()