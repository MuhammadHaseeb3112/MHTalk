from .choices import CallStatus
from .models import Call
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


ACTIVE_CALL_STATUSES = (
    CallStatus.RINGING,
    CallStatus.ONGOING,
)


def has_active_call(user):

    return Call.objects.filter(
        participants__user=user,
        status__in=ACTIVE_CALL_STATUSES,
    ).exists()


def room_has_active_call(room):

    return Call.objects.filter(
        room=room,
        status__in=ACTIVE_CALL_STATUSES,
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