from django.conf import settings
from django.db import models

from .message import Message


class Reaction(models.Model):
    """
    Represents an emoji reaction to a message.
    """

    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="reactions",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="message_reactions",
    )

    emoji = models.CharField(
        max_length=20,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        db_table = "message_reactions"

        verbose_name = "Reaction"
        verbose_name_plural = "Reactions"

        ordering = (
            "created_at",
        )

        constraints = [
            models.UniqueConstraint(
                fields=(
                    "message",
                    "user",
                ),
                name="unique_user_reaction",
            )
        ]

    def __str__(
        self,
    ) -> str:
        return (
            f"{self.user.phone_number} "
            f"reacted {self.emoji}"
        )