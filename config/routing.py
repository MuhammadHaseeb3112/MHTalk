from apps.chat.routing import (
    websocket_urlpatterns as chat_patterns,
)

from apps.calls.routing import (
    websocket_urlpatterns as call_patterns,
)

websocket_urlpatterns = [
    *chat_patterns,
    *call_patterns,
]