import re
from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

from .health import health

urlpatterns = [
    path("api/health/", health, name="health"),

    path(
        "api/schema/",
        SpectacularAPIView.as_view(),
        name="schema",
    ),

    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(
            url_name="schema",
        ),
        name="swagger-ui",
    ),

    path(
        "api/redoc/",
        SpectacularRedocView.as_view(
            url_name="schema",
        ),
        name="redoc",
    ),
    
    path("admin/", admin.site.urls),

    path(
        "api/accounts/",
        include("apps.accounts.urls"),
    ),
    path(
        "api/chat/",
        include("apps.chat.urls"),
    ),

    path(
        "api/status/",
        include("apps.status.urls"),
    ),

    path(
        "api/calls/",
        include("apps.calls.urls"),
    ),

    path(
        "api/notifications/",
        include("apps.notifications.urls"),
    ),
]

if settings.DEBUG or getattr(settings, "MHTALK_SERVE_MEDIA", False):
    # Uploads are normally served by the reverse proxy (Caddy) or object
    # storage in production; MHTALK_SERVE_MEDIA=1 lets Django do it when
    # there is no proxy. Range-aware so videos and voice notes can play and seek in development.
    from django.urls import re_path

    from .media_views import serve_media

    urlpatterns += [
        re_path(
            r"^%s(?P<path>.*)$" % re.escape(settings.MEDIA_URL.lstrip("/")),
            serve_media,
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]

