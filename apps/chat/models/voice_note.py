from django.db import models

from .message import Message


class VoiceNote(models.Model):
    """
    Metadata for a voice note.
    """

    message = models.OneToOneField(
        Message,
        on_delete=models.CASCADE,
        related_name="voice_note",
    )

    audio = models.FileField(
        upload_to="chat/voice/",
    )

    duration = models.PositiveIntegerField(
        help_text="Duration in seconds.",
    )

    waveform = models.JSONField(
        default=list,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:

        db_table = "voice_notes"

        ordering = (
            "-created_at",
        )

    def __str__(self):

        return f"Voice #{self.message_id}"