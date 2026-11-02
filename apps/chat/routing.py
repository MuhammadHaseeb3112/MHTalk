from django.urls import path

from .consumers import ChatConsumer, ChatInboxConsumer

websocket_urlpatterns = [
    path("ws/chat/inbox/", ChatInboxConsumer.as_asgi(), name="chat-inbox"),
    path(
        "ws/chat/<int:room_id>/",
        ChatConsumer.as_asgi(),
        name="chat-room",
    ),
]