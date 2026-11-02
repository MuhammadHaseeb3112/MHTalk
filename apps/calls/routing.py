from django.urls import re_path

from .consumers import CallConsumer, CallInboxConsumer

websocket_urlpatterns = [
    re_path(
        r"ws/calls/inbox/$",
        CallInboxConsumer.as_asgi(),
    ),
    re_path(
        r"ws/calls/(?P<room_id>\d+)/$",
        CallConsumer.as_asgi(),
    ),
]