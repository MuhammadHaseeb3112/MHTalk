from django.contrib import admin


from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .forms import (
    CustomUserCreationForm,
    CustomUserChangeForm,
)

from apps.status.models import Status

from .models import User, Profile, Contact


class ProfileInline(admin.StackedInline):
    model = Profile

    extra = 0

    can_delete = False

    fk_name = "user"

    verbose_name_plural = "Profile"

    readonly_fields = (
        "created_at",
        "updated_at",
        "last_seen",
        "is_online",
    )

    fieldsets = (
        (
            "Profile Information",
            {
                "fields": (
                    "display_name",
                    "profile_picture",
                    "about",
                    "is_online",
                ),
            },
        ),
        (
            "Activity",
            {
                "fields": (
                    "last_seen",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Custom admin for the User model.
    """

    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = User

    inlines = (ProfileInline,)

    list_per_page = 25

    """
    Custom admin for the User model.
    """

    list_display = (
        "id",
        "phone_number",
        "email",
        "is_verified",
        "is_staff",
        "is_active",
        "date_joined",
        "is_deleted",
    )

    list_display_links = (
        "phone_number",
    )

    list_filter = (
        "is_verified",
        "is_staff",
        "is_active",
        "is_superuser",
        "is_deleted",

    )

    search_fields = (
        "phone_number",
        "email",
    )

    ordering = (
        "-date_joined",
    )

    readonly_fields = (
        "date_joined",
        "last_login",
    )

    fieldsets = (
    (
        "Authentication",
        {
            "fields": (
                "phone_number",
                "password",
            ),
        },
    ),
    (
        "Personal Information",
        {
            "fields": (
                "email",
            ),
        },
    ),
    (
        "Permissions",
        {
            "fields": (
                "is_active",
                "is_verified",
                "is_staff",
                "is_superuser",
                "groups",
                "user_permissions",
            ),
        },
    ),
    (
        "Important Dates",
        {
            "fields": (
                "last_login",
                "date_joined",
            ),
        },
    ),
)

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "phone_number",
                    "email",
                    "password1",
                    "password2",
                    "is_verified",
                    "is_staff",
                    "is_superuser",
                    "is_active",
                ),
            },
        ),
    )



admin.site.register(Contact)
