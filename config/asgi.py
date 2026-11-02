import os

from django.core.asgi import get_asgi_application

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings.development",
)

# Django must be set up before anything imports models (middleware, routing).
django_asgi_app = get_asgi_application()

from channels.routing import (  # noqa: E402
    ProtocolTypeRouter,
    URLRouter,
)

from apps.chat.middleware import JWTAuthMiddlewareStack  # noqa: E402

from apps.chat.routing import (  # noqa: E402
    websocket_urlpatterns as chat_websocket_urlpatterns,
)

from apps.calls.routing import (  # noqa: E402
    websocket_urlpatterns as call_websocket_urlpatterns,
)


def _reset_stale_presence():
    """
    Connection counters live in the database. After a restart no socket is
    connected yet, so clear them; otherwise users who were online when the
    server stopped would appear online forever. Disable with
    MHTALK_RESET_PRESENCE_ON_STARTUP=0 when running several ASGI workers
    (then run ``manage.py reset_presence`` once per deploy instead).
    """
    if os.environ.get("MHTALK_RESET_PRESENCE_ON_STARTUP", "1") != "1":
        return
    try:
        from django.core.management import call_command

        call_command("reset_presence", verbosity=0)
    except Exception:
        # The database may not be migrated yet; presence is non-critical.
        pass


_reset_stale_presence()

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