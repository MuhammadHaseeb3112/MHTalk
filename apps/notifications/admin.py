from django.contrib import admin

from .models import PushSubscription


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "user_agent", "show_previews", "created_at")
    search_fields = ("user__phone_number", "endpoint", "user_agent")
    raw_id_fields = ("user",)
