from django.db import models


class RoomType(models.TextChoices):
    """
    Available chat room types.
    """

    PRIVATE = "PRIVATE", "Private Chat"
    GROUP = "GROUP", "Group Chat"


class MessageType(models.TextChoices):
    """
    Available message types.
    """

    TEXT = "TEXT", "Text"
    IMAGE = "IMAGE", "Image"
    VIDEO = "VIDEO", "Video"
    VOICE = "VOICE", "Voice"
    DOCUMENT = "DOCUMENT", "Document"
    LOCATION = "LOCATION", "Location"
    CONTACT = "CONTACT", "Contact"
    STICKER = "STICKER", "Sticker"
    POLL = "POLL", "Poll"


# Disappearing-message timers offered by WhatsApp (seconds; 0 = off).
DISAPPEARING_CHOICES = (0, 24 * 60 * 60, 7 * 24 * 60 * 60, 90 * 24 * 60 * 60)

# Prefix of chat-level system notices (e.g. "turned on disappearing
# messages"). They are stored as TEXT messages like call cards, never expire
# and never count as unread.
SYSTEM_PREFIX = "__MHTALK_SYSTEM__:"
