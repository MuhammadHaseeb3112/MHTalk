from threading import Timer

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

from .choices import CallStatus
from .constants import CALL_RING_TIMEOUT
from .models import Call

# In-process timers are suitable for local development, but not a multi-worker production
# deployment. For production, use Celery or another shared task queue for ring timeouts.
CALL_TIMERS = {}


def schedule_ring_timeout(call_id):
    cancel_ring_timeout(call_id)
    timer = Timer(CALL_RING_TIMEOUT, timeout_call, args=[call_id])
    timer.daemon = True
    CALL_TIMERS[call_id] = timer
    timer.start()


def cancel_ring_timeout(call_id):
    timer = CALL_TIMERS.pop(call_id, None)
    if timer:
        timer.cancel()


def timeout_call(call_id):
    try:
        call = Call.objects.get(pk=call_id)
    except Call.DoesNotExist:
        CALL_TIMERS.pop(call_id, None)
        return

    if call.is_group:
        # Group calls: missed for everyone only if nobody joined; otherwise
        # just stop ringing for the members who never picked up.
        CALL_TIMERS.pop(call_id, None)
        from .group import group_ring_timeout

        try:
            group_ring_timeout(call)
        except Exception:
            pass
        return

    if call.status != CallStatus.RINGING:
        CALL_TIMERS.pop(call_id, None)
        return

    call.status = CallStatus.MISSED
    call.ended_at = timezone.now()
    call.save(update_fields=["status", "ended_at"])

    channel_layer = get_channel_layer()
    if channel_layer is not None:
        async_to_sync(channel_layer.group_send)(
            f"call_{call.room_id}",
            {
                "type": "call.event",
                "event": "missed_call",
                "payload": {"call_id": call.id, "status": call.status},
            },
        )
    CALL_TIMERS.pop(call_id, None)

    from .events import notify_calls_changed, publish_call_message

    try:
        publish_call_message(call)
        notify_calls_changed(call, "missed")
    except Exception:
        # A failed broadcast must never crash the timer thread.
        pass


def leave_call(call, user):
    """Mark the participant as left and end the call when at most one remains."""
    participant = call.participants.filter(user=user).first()
    if participant is None or participant.left_at:
        return

    participant.left_at = timezone.now()
    participant.save(update_fields=["left_at"])

    remaining = call.participants.filter(left_at__isnull=True).count()
    if remaining <= 1 and call.status in (CallStatus.RINGING, CallStatus.ONGOING):
        call.end()
        cancel_ring_timeout(call.id)
