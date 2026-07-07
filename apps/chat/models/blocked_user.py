from django.conf import settings
from django.db import models


class BlockedUser(models.Model):
    """
    Represents a blocked user.
    """

    blocked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocked_users",
    )

    blocked_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocked_by_users",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        db_table = "blocked_users"

        verbose_name = "Blocked User"
        verbose_name_plural = "Blocked Users"

        constraints = [
            models.UniqueConstraint(
                fields=(
                    "blocked_by",
                    "blocked_user",
                ),
                name="unique_blocked_user",
            )
        ]

    def __str__(self):
        return (
            f"{self.blocked_by.phone_number} "
            f"blocked "
            f"{self.blocked_user.phone_number}"
        )