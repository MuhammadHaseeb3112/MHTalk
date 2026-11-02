from django.conf import settings
from django.db import models

from .chat_room import ChatRoom


class Participant(models.Model):
    """
    Represents a user's membership in a chat room.

    A participant belongs to exactly one chat room and one user.

    This model stores chat-specific information about that user,
    such as whether they are an admin, muted, archived, etc.
    """

    room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name="participants",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_participations",
    )

    is_admin = models.BooleanField(
        default=False,
        help_text="Whether this participant is a group administrator.",
    )

    is_muted = models.BooleanField(
        default=False,
        help_text="Whether notifications are muted.",
    )

    muted_until = models.DateTimeField(
        null=True,
        blank=True,
    )

    is_archived = models.BooleanField(
        default=False,
        help_text="Whether the chat is archived for this user.",
    )

    is_pinned = models.BooleanField(
        default=False,
        help_text="Whether the chat is pinned to the top of this user's list.",
    )

    pinned_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    is_favorite = models.BooleanField(
        default=False,
        help_text="Whether the chat appears under this user's Favorites filter.",
    )

    joined_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        db_table = "participants"

        verbose_name = "Participant"

        verbose_name_plural = "Participants"

        ordering = (
            "-joined_at",
        )

        constraints = [
            models.UniqueConstraint(
                fields=("room", "user"),
                name="unique_room_participant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user.phone_number} • {self.room}"