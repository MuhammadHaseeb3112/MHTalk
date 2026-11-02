from django.conf import settings
from django.db import models


class PushSubscription(models.Model):
    """
    One browser / installed app that accepted Web Push for a user.

    ``endpoint`` is the push-service URL the browser handed out; it is unique
    per browser profile, so re-subscribing from the same device updates the
    row (and moves it to whoever is logged in now). ``show_previews`` mirrors
    the device's "Show previews" setting so the server never sends message
    text to a device that asked to hide it.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )
    endpoint = models.URLField(max_length=1000, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    user_agent = models.CharField(max_length=255, blank=True, default="")
    show_previews = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "push_subscriptions"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.user_id} • {self.endpoint[:60]}"

    def as_subscription_info(self):
        return {"endpoint": self.endpoint, "keys": {"p256dh": self.p256dh, "auth": self.auth}}
