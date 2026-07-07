from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.utils import timezone

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model for WhatsUp.

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
        default="Hey there! I'm using WhatsUp.",
        help_text="User status or bio.",
    )

    last_seen = models.DateTimeField(
        default=timezone.now,
    )

    is_online = models.BooleanField(default=False)

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