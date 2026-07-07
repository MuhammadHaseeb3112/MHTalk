from django.db import models


class StatusType(models.TextChoices):
    """
    Supported status types.
    """

    TEXT = "TEXT", "Text"
    IMAGE = "IMAGE", "Image"
    VIDEO = "VIDEO", "Video"


class StatusVisibility(models.TextChoices):

    CONTACTS = (
        "CONTACTS",
        "My Contacts",
    )

    EVERYONE = (
        "EVERYONE",
        "Everyone",
    )

    CONTACTS_EXCEPT = (
        "CONTACTS_EXCEPT",
        "My Contacts Except",
    )

    ONLY_SHARE_WITH = (
        "ONLY_SHARE_WITH",
        "Only Share With",
    )