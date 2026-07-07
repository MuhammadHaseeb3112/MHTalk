from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.status.choices import StatusType, StatusVisibility


class Status(models.Model):
    """
    WhatsApp-like status.

    Automatically expires after 24 hours.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="statuses",
    )

    status_type = models.CharField(
        max_length=20,
        choices=StatusType.choices,
        default=StatusType.TEXT,
        db_index=True,
    )

    content = models.TextField(
        blank=True,
        help_text="Text status.",
    )

    media = models.FileField(
        upload_to="status/",
        blank=True,
        null=True,
    )

    visibility = models.CharField(
        max_length=25,
        choices=StatusVisibility.choices,
        default=StatusVisibility.CONTACTS,
    )

    background_color = models.CharField(
        max_length=20,
        default="#075E54",
    )

    text_color = models.CharField(
        max_length=20,
        default="#FFFFFF",
    )

    is_deleted = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    expires_at = models.DateTimeField(
        editable=False,
        db_index=True,
    )

    class Meta:

        db_table = "statuses"

        ordering = (
            "-created_at",
        )

        verbose_name = "Status"

        verbose_name_plural = "Statuses"

        indexes = [
            models.Index(
                fields=[
                    "user",
                    "expires_at",
                ]
            ),
        ]

    def save(
        self,
        *args,
        **kwargs,
    ):
        if not self.expires_at:
            self.expires_at = (
                timezone.now()
                + timedelta(hours=24)
            )

        super().save(
            *args,
            **kwargs,
        )

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    def __str__(self):
        return (
            f"{self.user.phone_number}"
            f" ({self.status_type})"
        )