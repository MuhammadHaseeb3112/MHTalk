from django.conf import settings
from django.db import models

from .message import Message


class ViewOnceOpen(models.Model):
    """A recipient opened a view once photo/video (it can never be shown again)."""

    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="view_once_opens")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="view_once_opens")
    opened_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "view_once_opens"
        constraints = [
            models.UniqueConstraint(fields=("message", "user"), name="unique_view_once_open"),
        ]

    def __str__(self):
        return f"{self.user_id} opened {self.message_id}"
