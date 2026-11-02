import mimetypes
import os
import uuid

from django.db import models

from .message import Message

# View once media is stored here (relative to MEDIA_ROOT). Caddy and the
# development media server refuse /media/private/*; the file is only served
# by ViewOnceMediaAPIView after membership and "not opened yet" checks.
PRIVATE_MEDIA_DIR = "private"


def attachment_upload_to(instance, filename):
    """Public uploads keep the original layout; view once media is private
    and gets an unguessable name."""
    message = getattr(instance, "message", None)
    if message is not None and message.is_view_once:
        extension = os.path.splitext(filename)[1].lower()[:10]
        return f"{PRIVATE_MEDIA_DIR}/view_once/{uuid.uuid4().hex}{extension}"
    return f"chat/attachments/{filename}"


class Attachment(models.Model):
    """
    Represents a file attached to a message.

    A single message may have zero, one,
    or multiple attachments.
    """

    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="attachments",
    )

    file = models.FileField(
        upload_to=attachment_upload_to,
        help_text="Uploaded attachment file.",
    )

    file_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Original filename.",
    )

    file_size = models.PositiveBigIntegerField(
        default=0,
        help_text="File size in bytes.",
    )

    mime_type = models.CharField(
        max_length=100,
        blank=True,
        help_text="MIME type (e.g. image/jpeg).",
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        db_table = "attachments"

        verbose_name = "Attachment"
        verbose_name_plural = "Attachments"

        ordering = (
            "uploaded_at",
        )



    def save(self, *args, **kwargs):
        """
        Automatically populate metadata.
        """

        if self.file:

            self.file_name = self.file.name.split("/")[-1]

            try:
                self.file_size = self.file.size
            except Exception:
                pass

            mime, _ = mimetypes.guess_type(
                self.file.name,
            )

            self.mime_type = mime or ""

        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.file_name