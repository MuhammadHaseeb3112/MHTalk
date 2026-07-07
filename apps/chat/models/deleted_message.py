from django.conf import settings
from django.db import models

from .message import Message


class DeletedMessage(models.Model):
    """
    Stores messages deleted only
    for a specific user.
    """

    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="deleted_for_users",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="deleted_messages",
    )

    deleted_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        db_table = "deleted_messages"

        verbose_name = "Deleted Message"
        verbose_name_plural = "Deleted Messages"

        constraints = [
            models.UniqueConstraint(
                fields=(
                    "message",
                    "user",
                ),
                name="unique_deleted_message",
            )
        ]

    def __str__(self):
        return (
            f"{self.user.phone_number} "
            f"deleted message {self.message_id}"
        )