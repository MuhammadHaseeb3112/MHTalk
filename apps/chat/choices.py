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