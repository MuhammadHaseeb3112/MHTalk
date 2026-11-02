from django.conf import settings
from django.db import models

from ..choices import ParticipantState
from .call import Call


class CallParticipant(models.Model):
    """
    Participant in a call.
    """

    call = models.ForeignKey(
        Call,
        on_delete=models.CASCADE,
        related_name="participants",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )

    joined_at = models.DateTimeField(
        auto_now_add=True,
    )

    left_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    is_muted = models.BooleanField(
        default=False,
    )

    missed_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this participant acknowledged the call as a missed call (clears the Calls badge).",
    )

    is_on_hold = models.BooleanField(
        default=False,
    )

    state = models.CharField(
        max_length=10,
        choices=ParticipantState.choices,
        default=ParticipantState.RINGING,
        help_text="Ringing / joined / declined / missed / left (group calls).",
    )

    answered_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="First time this person joined the call (null: never joined).",
    )

    class Meta:

        db_table = "call_participants"

        unique_together = (
            "call",
            "user",
        )

    def __str__(self):

        return (
            f"{self.user.phone_number}"
            f" ({self.call_id})"
        )
