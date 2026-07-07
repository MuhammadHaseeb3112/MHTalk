from django.conf import settings
from django.db import models

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

    is_on_hold = models.BooleanField(
        default=False,
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
    
    