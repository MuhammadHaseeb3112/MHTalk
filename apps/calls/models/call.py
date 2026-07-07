from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.chat.models import ChatRoom

from ..choices import (
    CallStatus,
    CallType,
)


class Call(models.Model):
    """
    Represents a call session.
    """

    room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name="calls",
    )

    caller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="started_calls",
    )

    call_type = models.CharField(
        max_length=10,
        choices=CallType.choices,
        default=CallType.AUDIO,
    )

    status = models.CharField(
        max_length=20,
        choices=CallStatus.choices,
        default=CallStatus.RINGING,
    )

    started_at = models.DateTimeField(
        auto_now_add=True,
    )

    answered_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    ended_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    duration = models.PositiveIntegerField(
        default=0,
        help_text="Duration in seconds.",
    )

    class Meta:

        db_table = "calls"

        ordering = (
            "-started_at",
        )

    def end(self):

        self.ended_at = timezone.now()

        if self.answered_at:

            self.duration = int(
                (
                    self.ended_at -
                    self.answered_at
                ).total_seconds()
            )
        self.save(
            update_fields=[
                "status",
                "ended_at",
                "duration",
            ]
        )

    def __str__(self):

        return (
            f"{self.call_type} call "
            f"#{self.pk}"
        )