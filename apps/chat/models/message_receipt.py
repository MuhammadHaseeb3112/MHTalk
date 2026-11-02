from django.conf import settings
from django.db import models

from .message import Message


class MessageReceipt(models.Model):
    """Delivery and read state for one recipient of one message.

    Receipt state is deliberately per-recipient; a message-level boolean cannot
    represent a group conversation correctly.
    """

    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="receipts")
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="message_receipts",
    )
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "message_receipts"
        constraints = [
            models.UniqueConstraint(fields=("message", "recipient"), name="unique_message_recipient_receipt"),
        ]
        indexes = [
            models.Index(fields=("recipient", "read_at"), name="receipt_recipient_read_idx"),
        ]

    def __str__(self):
        return f"Receipt for message {self.message_id} / user {self.recipient_id}"
