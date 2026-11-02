from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.utils import timezone

from .managers import UserManager
from django.conf import settings
from django.db import models


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model for MHTalk.

    Authentication is performed using the user's phone number
    in E.164 format (e.g. +923130067082).
    """

    phone_number = models.CharField(
        max_length=20,
        unique=True,
        help_text="Phone number in E.164 format (e.g. +923130067082)",
    )

    email = models.EmailField(
        blank=True,
        null=True,
    )

    is_deleted = models.BooleanField(default=False)

    is_verified = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)

    is_staff = models.BooleanField(default=False)

    date_joined = models.DateTimeField(
        default=timezone.now,
    )

    objects = UserManager()

    USERNAME_FIELD = "phone_number"

    REQUIRED_FIELDS = []

    class Meta:
        db_table = "users"
        ordering = ["-date_joined"]

    def __str__(self):
        return self.phone_number
class Profile(models.Model):
    """
    Stores additional information about a user.

    Authentication-related fields remain in the User model.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
    )

    display_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="User's display name.",
    )

    profile_picture = models.ImageField(
        upload_to="profiles/",
        blank=True,
        null=True,
    )

    about = models.CharField(
        max_length=150,
        blank=True,
        default="Hey there! I'm using MHTalk.",
        help_text="User status or bio.",
    )

    last_seen = models.DateTimeField(
        default=timezone.now,
    )

    is_online = models.BooleanField(default=False)

    # Number of live WebSocket inbox connections (one per open tab/device).
    # ``is_online`` is derived from this counter so closing one of several
    # tabs no longer marks the user offline.
    active_connections = models.PositiveIntegerField(default=0)

    # -- Privacy (Settings > Privacy). Enforced server-side in
    # apps/accounts/privacy.py wherever profile data leaves the API.
    PRIVACY_EVERYONE = "everyone"
    PRIVACY_CONTACTS = "contacts"
    PRIVACY_NOBODY = "nobody"
    PRIVACY_CHOICES = (
        (PRIVACY_EVERYONE, "Everyone"),
        (PRIVACY_CONTACTS, "My contacts"),
        (PRIVACY_NOBODY, "Nobody"),
    )
    ONLINE_EVERYONE = "everyone"
    ONLINE_SAME_AS_LAST_SEEN = "same_as_last_seen"
    ONLINE_CHOICES = (
        (ONLINE_EVERYONE, "Everyone"),
        (ONLINE_SAME_AS_LAST_SEEN, "Same as last seen"),
    )

    last_seen_privacy = models.CharField(max_length=10, choices=PRIVACY_CHOICES, default=PRIVACY_EVERYONE)
    online_privacy = models.CharField(max_length=20, choices=ONLINE_CHOICES, default=ONLINE_EVERYONE)
    photo_privacy = models.CharField(max_length=10, choices=PRIVACY_CHOICES, default=PRIVACY_EVERYONE)
    about_privacy = models.CharField(max_length=10, choices=PRIVACY_CHOICES, default=PRIVACY_EVERYONE)
    read_receipts = models.BooleanField(
        default=True,
        help_text="Send/receive blue ticks in private chats (groups always send them).",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "profiles"
        verbose_name = "Profile"
        verbose_name_plural = "Profiles"

    def __str__(self):
        if self.display_name:
            return self.display_name
        return self.user.phone_number




class Contact(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_contacts",
    )

    contact_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_by_contacts",
    )

    name = models.CharField(
        max_length=100,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        db_table = "contacts"
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "contact_user"],
                name="unique_saved_contact",
            ),
            models.CheckConstraint(
                condition=~models.Q(
                    owner=models.F("contact_user")
                ),
                name="contact_cannot_save_self",
            ),
        ]

    def __str__(self):
        return (
            f"{self.owner.phone_number} saved "
            f"{self.contact_user.phone_number}"
        )

