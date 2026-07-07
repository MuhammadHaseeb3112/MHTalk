from django.conf import settings
from django.db import models

from apps.chat.choices import MessageType
from .chat_room import ChatRoom


class Message(models.Model):
    """
    Represents a single message sent inside a chat room.

    A message may be text, image, video, document,
    voice note, location, contact, or sticker.
    """

    room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name="messages",
    )

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_messages",
    )

    reply_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replies",
    )

    forwarded_from = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="forwarded_messages",
    )

    message_type = models.CharField(
        max_length=20,
        choices=MessageType.choices,
        default=MessageType.TEXT,
        db_index=True,
    )

    content = models.TextField(
        blank=True,
        help_text="Text message content.",
    )

    is_delivered = models.BooleanField(
    default=False,
    )

    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    is_read = models.BooleanField(
    default=False,
    )

    read_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    is_edited = models.BooleanField(
        default=False,
    )

    is_deleted = models.BooleanField(
        default=False,
        help_text="Soft delete.",
    )

    is_pinned = models.BooleanField(
        default=False,
    )

    pinned_at = models.DateTimeField(
        null=True,
        blank=True,
    )


    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )


    class Meta:
        db_table = "messages"

        ordering = (
            "created_at",
        )

        verbose_name = "Message"

        verbose_name_plural = "Messages"

        indexes = [
            models.Index(
                fields=[
                    "room",
                    "created_at",
                ]
            ),
        ]

    def __str__(self) -> str:
        return f"{self.sender.phone_number}: {self.message_type}"