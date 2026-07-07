from django.conf import settings
from django.db import models

from .status import Status


class StatusView(models.Model):
    """
    Stores who viewed a status.
    """

    status = models.ForeignKey(
        Status,
        on_delete=models.CASCADE,
        related_name="views",
    )

    viewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="viewed_statuses",
    )

    viewed_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:

        db_table = "status_views"

        ordering = (
            "-viewed_at",
        )

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "status",
                    "viewer",
                ],
                name="unique_status_view",
            )
        ]

    def __str__(self):
        return (
            f"{self.viewer.phone_number}"
            f" viewed {self.status_id}"
        )