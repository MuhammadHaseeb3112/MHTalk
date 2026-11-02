from django.conf import settings
from django.db import models

from .status import Status


class StatusReaction(models.Model):
    """A viewer's latest reaction to a status, mirrored into the private chat."""

    status = models.ForeignKey(Status, on_delete=models.CASCADE, related_name="reactions")
    reactor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="status_reactions",
    )
    emoji = models.CharField(max_length=16)
    chat_message = models.ForeignKey(
        "chat.Message",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="status_reactions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "status_reactions"
        constraints = [
            models.UniqueConstraint(
                fields=("status", "reactor"),
                name="unique_status_reaction_per_user",
            )
        ]
        ordering = ("-updated_at",)

    def __str__(self):
        return f"{self.reactor_id} reacted {self.emoji} to status {self.status_id}"
