from django.conf import settings
from django.db import models

from .message import Message


class StarredMessage(models.Model):
    """
    Represents a message starred by a user.
    """

    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="starred_by",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="starred_messages",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        db_table = "starred_messages"

        verbose_name = "Starred Message"
        verbose_name_plural = "Starred Messages"

        ordering = (
            "-created_at",
        )

        constraints = [
            models.UniqueConstraint(
                fields=(
                    "message",
                    "user",
                ),
                name="unique_starred_message",
            )
        ]

    def __str__(self):
        return (
            f"{self.user.phone_number} "
            f"starred message {self.message_id}"
        )