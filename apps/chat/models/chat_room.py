from django.db import models

# Create your models here.
from django.conf import settings
from django.db import models


from apps.chat.choices import RoomType


class ChatRoom(models.Model):
    """
    Represents a conversation.

    A chat room can be either:

    - Private chat (2 participants)
    - Group chat (multiple participants)

    Messages are stored separately and linked to this room.
    """

    name = models.CharField(
        max_length=150,
        blank=True,
        help_text="Group name. Leave blank for private chats.",
    )

    room_type = models.CharField(
        max_length=10,
        choices=RoomType.choices,
        default=RoomType.PRIVATE,
        db_index=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_chat_rooms",
    )

    description = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional group description.",
    )

    photo = models.ImageField(
        upload_to="chat_rooms/",
        blank=True,
        null=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    disappearing_seconds = models.PositiveIntegerField(
        default=0,
        help_text="Disappearing messages timer for new messages (0 = off).",
    )

    # -- Group permissions (Group info > Group permissions). ``True`` means
    # only admins may do it. Checked by apps/chat/permissions.py.
    edit_info_admins_only = models.BooleanField(
        default=True,
        help_text="Only admins can edit the group name, icon, description and disappearing timer.",
    )

    send_messages_admins_only = models.BooleanField(
        default=False,
        help_text="Only admins can send messages.",
    )

    add_members_admins_only = models.BooleanField(
        default=True,
        help_text="Only admins can add members and share the invite link.",
    )

    # Group invite link code (https://<host>/join/<code>). Unguessable
    # (secrets.token_urlsafe); resetting it makes the old link stop working.
    invite_code = models.CharField(
        max_length=64,
        unique=True,
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
        db_table = "chat_rooms"

        ordering = (
            "-updated_at",
        )

        verbose_name = "Chat Room"

        verbose_name_plural = "Chat Rooms"

    def __str__(self) -> str:
        """
        Return a readable representation of the room.
        """

        if self.room_type == RoomType.GROUP:
            return self.name

        return f"Private Room #{self.pk}"