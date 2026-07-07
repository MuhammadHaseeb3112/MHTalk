from django.conf import settings
from django.db import models

from .status import Status


class StatusPrivacy(models.Model):
    """
    Stores custom visibility rules
    for a status.
    """

    status = models.ForeignKey(
        Status,
        on_delete=models.CASCADE,
        related_name="privacy_rules",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )

    class Meta:

        db_table = "status_privacy"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "status",
                    "user",
                ],
                name="unique_status_privacy",
            )
        ]

    def __str__(self):
        return f"{self.status_id} -> {self.user.phone_number}"