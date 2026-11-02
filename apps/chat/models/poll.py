from django.conf import settings
from django.db import models

from .message import Message


class Poll(models.Model):
    """A WhatsApp poll attached to a POLL message (question + 2..12 options)."""

    message = models.OneToOneField(
        Message,
        on_delete=models.CASCADE,
        related_name="poll",
    )
    question = models.CharField(max_length=255)
    allow_multiple = models.BooleanField(
        default=False,
        help_text="Voters may pick more than one option.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "polls"

    def __str__(self):
        return self.question


class PollOption(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="options")
    text = models.CharField(max_length=100)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "poll_options"
        ordering = ("position", "id")

    def __str__(self):
        return self.text


class PollVote(models.Model):
    """One user's vote for one option (several rows for multiple answers)."""

    option = models.ForeignKey(PollOption, on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="poll_votes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "poll_votes"
        ordering = ("created_at", "id")
        constraints = [
            models.UniqueConstraint(fields=("option", "user"), name="unique_poll_vote_per_option"),
        ]

    def __str__(self):
        return f"{self.user_id} -> option {self.option_id}"
