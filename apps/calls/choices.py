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