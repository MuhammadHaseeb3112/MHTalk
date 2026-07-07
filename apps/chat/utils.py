from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .serializers import MessageSerializer
from .models import Message


def broadcast_message(
    message,
    request=None,
):
    """
    Broadcast a message to all websocket clients.
    """

    channel_layer = get_channel_layer()

    async_to_sync(
        channel_layer.group_send
    )(
        f"chat_{message.room_id}",
        {
            "type": "chat.message",
            "message": MessageSerializer(
                message,
                context={
                    "request": request,
                },
            ).data,
        },
    )


def get_message_with_relations(message_id):
    return (
        Message.objects
        .select_related(
            "sender",
            "sender__profile",

            "reply_to",
            "reply_to__sender",
            "reply_to__sender__profile",

            "forwarded_from",
            "forwarded_from__sender",
            "forwarded_from__sender__profile",
        )
        .prefetch_related(
            "attachments",
            "reactions",
            "voice_note",

        )
        .get(pk=message_id)
    )