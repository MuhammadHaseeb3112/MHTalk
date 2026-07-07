import asyncio

from channels.layers import get_channel_layer

from asgiref.sync import async_to_sync

from .models import Call

from .choices import CallStatus


async def ringing_timeout(call):

    await asyncio.sleep(30)

    call.refresh_from_db()

    if call.status != CallStatus.RINGING:
        return

    call.status = CallStatus.MISSED
    call.save()

    layer = get_channel_layer()

    async_to_sync(
        layer.group_send
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