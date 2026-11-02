from django.db import models


class CallType(models.TextChoices):
    AUDIO = "AUDIO", "Audio"
    VIDEO = "VIDEO", "Video"


class CallStatus(models.TextChoices):
    RINGING = "RINGING", "Ringing"
    ONGOING = "ONGOING", "Ongoing"
    ENDED = "ENDED", "Ended"
    REJECTED = "REJECTED", "Rejected"
    MISSED = "MISSED", "Missed"
    CANCELLED = "CANCELLED", "Cancelled"
    BUSY = "BUSY", "Busy"

class ParticipantState(models.TextChoices):
    """Where one person is in a call (mainly used by group calls)."""

    RINGING = "RINGING", "Ringing"
    JOINED = "JOINED", "Joined"
    DECLINED = "DECLINED", "Declined"
    MISSED = "MISSED", "Missed"
    LEFT = "LEFT", "Left"
