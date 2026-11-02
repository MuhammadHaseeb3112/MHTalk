import os
import uuid

from django.db import models

from .attachment import PRIVATE_MEDIA_DIR
from .message import Message


def voice_upload_to(instance, filename):
    """View once voice messages are private, like view once photos."""
    message = getattr(instance, "message", None)
    if message is not None and message.is_view_once:
        extension = os.path.splitext(filename)[1].lower()[:10]
        return f"{PRIVATE_MEDIA_DIR}/view_once/{uuid.uuid4().hex}{extension}"
    return f"chat/voice/{filename}"


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
        upload_to=voice_upload_to,
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