from django.conf import settings
from django.db import models
from django.utils import timezone

from .chat_room import ChatRoom


class ChatClear(models.Model):
    """Per-user chat deletion/clear marker.

    Messages at or before ``cleared_at`` stay hidden from this user.
    ``hide_from_list`` distinguishes Clear chat (False) from Delete chat from
    list (True); a newer message restores a hidden conversation to the list.
    """

    room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name="clear_markers",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cleared_chats",
    )
    cleared_at = models.DateTimeField(default=timezone.now, db_index=True)
    hide_from_list = models.BooleanField(
        default=True,
        help_text="Hide the conversation from the chat list until a newer message arrives.",
        db_index=True,
    )

    class Meta:
        db_table = "chat_clears"
        constraints = [
            models.UniqueConstraint(fields=("room", "user"), name="unique_chat_clear_per_user"),
        ]
        indexes = [models.Index(fields=("user", "cleared_at"), name="chat_clears_user_cleared_idx")]

    def __str__(self):
        return f"User {self.user_id} cleared chat {self.room_id} at {self.cleared_at}"
