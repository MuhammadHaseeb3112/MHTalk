from django.contrib import admin

from .models import (
    Attachment,
    ChatRoom,
    Message,
    Participant,
)


# =============================================================================
# Inlines
# =============================================================================

class ParticipantInline(admin.TabularInline):
    """
    Inline admin for chat participants.
    """

    model = Participant
    extra = 0

    autocomplete_fields = (
        "user",
    )

    readonly_fields = (
        "joined_at",
    )

    show_change_link = True


class AttachmentInline(admin.TabularInline):
    """
    Inline admin for message attachments.
    """

    model = Attachment
    extra = 0

    readonly_fields = (
        "file_name",
        "file_size",
        "mime_type",
        "uploaded_at",
    )

    show_change_link = True


# =============================================================================
# Chat Room
# =============================================================================

@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    """
    Admin configuration for ChatRoom.
    """

    inlines = (
        ParticipantInline,
    )

    list_display = (
        "id",
        "name",
        "room_type",
        "created_by",
        "is_active",
        "created_at",
    )

    list_display_links = (
        "id",
        "name",
    )

    list_editable = (
        "is_active",
    )

    list_filter = (
        "room_type",
        "is_active",
        "created_at",
    )

    search_fields = (
        "name",
        "description",
        "created_by__phone_number",
    )

    autocomplete_fields = (
        "created_by",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    list_select_related = (
        "created_by",
    )

    ordering = (
        "-updated_at",
    )

    list_per_page = 25

    date_hierarchy = "created_at"

    show_full_result_count = True

    empty_value_display = "-"

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "name",
                    "room_type",
                    "created_by",
                ),
            },
        ),
        (
            "Group Information",
            {
                "classes": ("collapse",),
                "fields": (
                    "description",
                    "photo",
                ),
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "is_active",
                ),
            },
        ),
        (
            "Important Dates",
            {
                "classes": ("collapse",),
                "fields": (
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )


# =============================================================================
# Participant
# =============================================================================

@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    """
    Admin configuration for Participant.
    """

    list_display = (
        "id",
        "room",
        "user",
        "is_admin",
        "is_muted",
        "is_archived",
        "joined_at",
    )

    list_display_links = (
        "id",
        "user",
    )

    list_editable = (
        "is_admin",
        "is_muted",
        "is_archived",
    )

    list_filter = (
        "is_admin",
        "is_muted",
        "is_archived",
        "joined_at",
    )

    search_fields = (
        "user__phone_number",
        "room__name",
    )

    autocomplete_fields = (
        "room",
        "user",
    )

    readonly_fields = (
        "joined_at",
    )

    list_select_related = (
        "room",
        "user",
    )

    ordering = (
        "-joined_at",
    )

    list_per_page = 25

    date_hierarchy = "joined_at"

    empty_value_display = "-"

    fieldsets = (
        (
            "Participant",
            {
                "fields": (
                    "room",
                    "user",
                ),
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_admin",
                    "is_muted",
                    "is_archived",
                ),
            },
        ),
        (
            "Important Dates",
            {
                "fields": (
                    "joined_at",
                ),
            },
        ),
    )


# =============================================================================
# Message
# =============================================================================

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    """
    Admin configuration for Message.
    """

    inlines = (
        AttachmentInline,
    )

    list_display = (
        "id",
        "sender",
        "room",
        "message_type",
        "is_edited",
        "is_deleted",
        "created_at",
    )

    list_display_links = (
        "id",
        "sender",
    )

    list_editable = (
        "is_deleted",
    )

    list_filter = (
        "message_type",
        "is_deleted",
        "is_edited",
        "created_at",
    )

    search_fields = (
        "content",
        "sender__phone_number",
        "room__name",
    )

    autocomplete_fields = (
        "room",
        "sender",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    list_select_related = (
        "room",
        "sender",
    )

    ordering = (
        "-created_at",
    )

    list_per_page = 50

    date_hierarchy = "created_at"

    empty_value_display = "-"

    fieldsets = (
        (
            "Message",
            {
                "fields": (
                    "room",
                    "sender",
                    "message_type",
                    "content",
                ),
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "is_edited",
                    "is_deleted",
                ),
            },
        ),
        (
            "Important Dates",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )


# =============================================================================
# Attachment
# =============================================================================

@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    """
    Admin configuration for Attachment.
    """

    list_display = (
        "id",
        "message",
        "file_name",
        "file_size",
        "mime_type",
        "uploaded_at",
    )

    list_display_links = (
        "id",
        "file_name",
    )

    list_filter = (
        "mime_type",
        "uploaded_at",
    )

    search_fields = (
        "file_name",
        "message__content",
    )

    autocomplete_fields = (
        "message",
    )

    readonly_fields = (
        "file_name",
        "file_size",
        "mime_type",
        "uploaded_at",
    )

    list_select_related = (
        "message",
    )

    ordering = (
        "-uploaded_at",
    )

    list_per_page = 25

    date_hierarchy = "uploaded_at"

    empty_value_display = "-"