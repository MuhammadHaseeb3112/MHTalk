from django.conf import settings
from django.db import models

from .message import Message


class MessageMention(models.Model):
    """A group member @mentioned in a message (drives the "@" chat-list badge)."""

    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="mention_rows")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mentioned_in")

    class Meta:
        db_table = "message_mentions"
        constraints = [
            models.UniqueConstraint(fields=("message", "user"), name="unique_message_mention"),
        ]
        indexes = [models.Index(fields=("user", "message"), name="mention_user_message_idx")]

    def __str__(self):
        return f"@{self.user_id} in {self.message_id}"
