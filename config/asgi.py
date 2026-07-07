import os

from channels.routing import (
    ProtocolTypeRouter,
    URLRouter,
)
from django.core.asgi import get_asgi_application

from apps.chat.middleware import JWTAuthMiddlewareStack

from apps.chat.routing import (
    websocket_urlpatterns as chat_websocket_urlpatterns,
)

from apps.calls.routing import (
    websocket_urlpatterns as call_websocket_urlpatterns,
)

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings.development",
)

django_asgi_app = get_asgi_application()

websocket_urlpatterns = [
    *chat_websocket_urlpatterns,
    *call_websocket_urlpatterns,
]

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,

        "websocket": JWTAuthMiddlewareStack(
            URLRouter(
                websocket_urlpatterns,
            )
        ),
    }
)