from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Now
from django.utils import timezone

from apps.chat.choices import SYSTEM_PREFIX, MessageType
from .chat_room import ChatRoom


def not_expired_q(prefix=""):
    """
    Q object matching messages that have not disappeared yet. ``Now()`` is
    evaluated by the database when the query runs, so querysets built at
    import time (e.g. serializer ``queryset=Message.objects.all()``) never
    carry a stale timestamp.
    """
    return Q(**{f"{prefix}expires_at__isnull": True}) | Q(**{f"{prefix}expires_at__gt": Now()})


class VisibleMessageManager(models.Manager):
    """
    Default manager: disappeared (expired) messages are invisible to every
    query the moment they expire, long before ``purge_expired_messages``
    physically deletes them. Use ``Message.all_objects`` to see them.
    """

    def get_queryset(self):
        return super().get_queryset().filter(not_expired_q())


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

    # Added in migration 0016 for safe client-side retry/idempotency. Keep a
    # non-null empty-string default so older clients can omit the value.
    client_message_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="Optional client idempotency key.",
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


    # Disappearing messages: set from the room timer when the message is
    # created. Expired messages are hidden by the default manager.
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
    )

    # View once photo/video: the file lives under MEDIA_ROOT/private/ and is
    # only served (once per recipient) by an authenticated endpoint.
    is_view_once = models.BooleanField(
        default=False,
    )

    # Link preview computed server-side once and shared by every recipient:
    # {"url", "title", "description", "site_name", "image"}.
    link_preview = models.JSONField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    objects = VisibleMessageManager()
    all_objects = models.Manager()


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

        constraints = [
            models.UniqueConstraint(
                fields=("room", "sender", "client_message_id"),
                condition=~models.Q(client_message_id=""),
                name="unique_room_sender_client_message",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.sender.phone_number}: {self.message_type}"

    @property
    def is_system(self) -> bool:
        """Chat notices (timer changes, group events) – never expire or forward."""
        return str(self.content or "").startswith((SYSTEM_PREFIX, "__WHATSUP_GROUP_EVENT__:"))

    def save(self, *args, **kwargs):
        # Every creation path (REST, WebSocket, forwards, call cards...) goes
        # through here, so the chat's disappearing timer is applied once.
        if self._state.adding and self.expires_at is None and self.room_id and not self.is_system:
            seconds = (
                ChatRoom.objects.filter(pk=self.room_id)
                .values_list("disappearing_seconds", flat=True)
                .first()
            )
            if seconds:
                self.expires_at = timezone.now() + timedelta(seconds=seconds)
        super().save(*args, **kwargs)