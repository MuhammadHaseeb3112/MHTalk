from django.contrib import admin

from .models import (
    Status,
    StatusView,
)


@admin.register(Status)
class StatusAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "user",
        "status_type",
        "created_at",
        "expires_at",
        "is_deleted",
    )

    list_filter = (
        "status_type",
        "is_deleted",
    )

    search_fields = (
        "user__phone_number",
        "content",
    )


@admin.register(StatusView)
class StatusViewAdmin(admin.ModelAdmin):

    list_display = (
        "status",
        "viewer",
        "viewed_at",
    )

    search_fields = (
        "viewer__phone_number",
    )