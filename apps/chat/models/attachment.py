from django.db import models
from .message import Message
import mimetypes


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
        upload_to="chat/attachments/",
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