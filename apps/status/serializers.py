from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.serializers import UserSerializer

from .models import (
    Status,
    StatusView,
    StatusPrivacy,
    
)

from .choices import (
    StatusType,
    StatusVisibility,
)
from apps.accounts.models import Contact

# ==========================================================
# Status View
# ==========================================================

class StatusViewSerializer(serializers.ModelSerializer):
    """
    Serializer for users who viewed a status.
    """

    viewer = UserSerializer(
        read_only=True,
    )

    class Meta:

        model = StatusView

        fields = (
            "id",
            "viewer",
            "viewed_at",
        )

        read_only_fields = fields


# ==========================================================
# Status
# ==========================================================

class StatusSerializer(serializers.ModelSerializer):
    """
    Serializer for retrieving statuses.
    """

    user = UserSerializer(
        read_only=True,
    )

    views_count = serializers.SerializerMethodField()

    is_viewed = serializers.SerializerMethodField()

    audience_user_ids = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()

    class Meta:

        model = Status

        fields = (
            "id",
            "user",
            "status_type",
            "content",
            "media",
            "background_color",
            "text_color",
            "views_count",
            "visibility",
            "is_viewed",
            "is_expired",
            "created_at",
            "expires_at",
            "audience_user_ids",
        )

        read_only_fields = fields

    def get_views_count(self, obj):
        """Viewer counts are private to the status owner."""
        request = self.context.get("request")
        if not request or request.user.id != obj.user_id:
            return None
        return obj.views.count()

    def get_is_viewed(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return any(view.viewer_id == request.user.id for view in obj.views.all())

    def get_is_expired(
        self,
        obj,
    ):
        return obj.is_expired

    @extend_schema_field(serializers.ListField(child=serializers.IntegerField(), allow_null=True))
    def get_audience_user_ids(self, obj):
        """Custom audience (except / only share with) — owner only."""
        request = self.context.get("request")
        if not request or request.user.id != obj.user_id:
            return None
        return [rule.user_id for rule in obj.privacy_rules.all()]

class UploadStatusSerializer(serializers.ModelSerializer):
    """Upload a new text, image, or video status.

    For ``CONTACTS_EXCEPT`` / ``ONLY_SHARE_WITH`` send ``users`` (repeat the
    field or a comma-separated list) with the selected contact IDs. The
    audience is snapshotted on the status (``StatusPrivacy`` rows).
    """

    MAX_MEDIA_BYTES = 50 * 1024 * 1024

    media = serializers.FileField(
        required=False,
        allow_null=True,
    )
    users = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        write_only=True,
    )
    # Video status: keep only this part (seconds), cut on the server.
    trim_start = serializers.FloatField(required=False, min_value=0, write_only=True)
    trim_end = serializers.FloatField(required=False, min_value=0, write_only=True)

    class Meta:
        model = Status
        fields = (
            "status_type",
            "content",
            "media",
            "background_color",
            "text_color",
            "visibility",
            "users",
            "trim_start",
            "trim_end",
        )

    def to_internal_value(self, data):
        # Accept users=1&users=2, users="1,2" or users="[1,2]" from multipart forms.
        if hasattr(data, "getlist") and "users" in data:
            raw = data.getlist("users")
            mutable = data.copy()
            values = []
            for item in raw:
                text = str(item).strip().strip("[]")
                values.extend(part.strip() for part in text.split(",") if part.strip())
            mutable.setlist("users", values)
            data = mutable
        return super().to_internal_value(data)

    def validate(self, attrs):
        status_type = attrs.get("status_type")
        trim_start, trim_end = attrs.pop("trim_start", None), attrs.pop("trim_end", None)
        content = str(attrs.get("content") or "").strip()
        media = attrs.get("media")

        if status_type == StatusType.TEXT and not content:
            raise serializers.ValidationError({
                "content": "Text status cannot be empty."
            })
        if status_type == StatusType.TEXT and len(content) > 700:
            raise serializers.ValidationError({
                "content": "Text status must be 700 characters or fewer."
            })

        if status_type in (StatusType.IMAGE, StatusType.VIDEO):
            if not media:
                raise serializers.ValidationError({
                    "media": "Media file is required."
                })
            if getattr(media, "size", 0) > self.MAX_MEDIA_BYTES:
                raise serializers.ValidationError({
                    "media": "Status media must be 50 MB or smaller."
                })

            filename = media.name.lower()
            content_type = str(getattr(media, "content_type", "") or "").lower()

            if status_type == StatusType.IMAGE:
                if not filename.endswith(
                    (".jpg", ".jpeg", ".png", ".webp", ".gif")
                ) or (content_type and not content_type.startswith("image/")):
                    raise serializers.ValidationError({
                        "media": "Upload a valid image file."
                    })

            elif status_type == StatusType.VIDEO:
                if not filename.endswith(
                    (".mp4", ".mov", ".webm", ".m4v")
                ) or (content_type and not content_type.startswith("video/")):
                    raise serializers.ValidationError({
                        "media": "Upload a valid video file."
                    })
                if trim_end is not None:
                    from apps.chat.video_trim import trim_upload

                    attrs["media"] = trim_upload(media, trim_start or 0, trim_end)

        visibility = attrs.get("visibility", StatusVisibility.CONTACTS)
        user_ids = list(dict.fromkeys(attrs.get("users") or []))
        if visibility in (StatusVisibility.CONTACTS_EXCEPT, StatusVisibility.ONLY_SHARE_WITH):
            if visibility == StatusVisibility.ONLY_SHARE_WITH and not user_ids:
                raise serializers.ValidationError({
                    "users": "Select at least one contact to share with."
                })
            from .utils import status_contact_ids

            allowed = status_contact_ids(self.context["request"].user)
            invalid = set(user_ids) - allowed
            if invalid:
                raise serializers.ValidationError({
                    "users": "Status audiences can only include your contacts."
                })
        else:
            user_ids = []

        attrs["users"] = user_ids
        attrs["content"] = content
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        user_ids = validated_data.pop("users", [])
        status = Status.objects.create(
            user=request.user,
            **validated_data,
        )
        if user_ids:
            StatusPrivacy.objects.bulk_create(
                [StatusPrivacy(status=status, user_id=user_id) for user_id in user_ids],
                ignore_conflicts=True,
            )
        return status


# ==========================================================
# Update Status Privacy
# ==========================================================

from django.contrib.auth import get_user_model

User = get_user_model()


class StatusPrivacySerializer(serializers.Serializer):
    """
    Update privacy rules for a status.
    """

    users = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        many=True,
    )

    def validate(self, attrs):
        status = self.context["status"]
        request = self.context["request"]

        if status.user_id != request.user.id:
            raise serializers.ValidationError(
                "You do not own this status."
            )

        if status.visibility not in (
            StatusVisibility.CONTACTS_EXCEPT,
            StatusVisibility.ONLY_SHARE_WITH,
        ):
            raise serializers.ValidationError(
                "Privacy rules can only be updated for "
                "CONTACTS_EXCEPT or ONLY_SHARE_WITH."
            )

        selected_user_ids = {
            user.id for user in attrs["users"]
        }

        # Users saved by the status owner.
        owner_saved_ids = set(
            Contact.objects.filter(
                owner_id=status.user_id,
            ).values_list(
                "contact_user_id",
                flat=True,
            )
        )

        # Users who have also saved the status owner.
        mutual_contact_ids = set(
            Contact.objects.filter(
                owner_id__in=owner_saved_ids,
                contact_user_id=status.user_id,
            ).values_list(
                "owner_id",
                flat=True,
            )
        )

        valid_selected_ids = (
            owner_saved_ids & mutual_contact_ids
        )

        invalid_ids = selected_user_ids - valid_selected_ids

        if invalid_ids:
            raise serializers.ValidationError({
                "users": (
                    "Selected users must be mutual contacts "
                    "of the status owner."
                )
            })

        return attrs


    def save(self):
        status = self.context["status"]
        users = self.validated_data["users"]

        status.privacy_rules.all().delete()

        StatusPrivacy.objects.bulk_create(
            [
                StatusPrivacy(
                    status=status,
                    user=user,
                )
                for user in users
            ]
        )

        return status
    


class StatusItemSerializer(serializers.ModelSerializer):

    views_count = serializers.SerializerMethodField()

    is_viewed = serializers.SerializerMethodField()

    is_expired = serializers.SerializerMethodField()

    class Meta:
        model = Status

        fields = (
            "id",
            "status_type",
            "content",
            "media",
            "background_color",
            "text_color",
            "views_count",
            "is_viewed",
            "is_expired",
            "created_at",
            "expires_at",
        )

    def get_views_count(self, obj):
        """Viewer counts are private to the status owner."""
        request = self.context.get("request")
        if not request or request.user.id != obj.user_id:
            return None
        return obj.views.count()

    def get_is_viewed(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return any(view.viewer_id == request.user.id for view in obj.views.all())

    def get_is_expired(self, obj):
        return obj.is_expired

# ==========================================================
# Contact Status Group
# ==========================================================

class ContactStatusSerializer(serializers.Serializer):
    """
    Group statuses by user.
    """

    user = UserSerializer(
        read_only=True,
    )

    statuses = StatusItemSerializer(
        many=True,
        read_only=True,
    )

    total_statuses = serializers.SerializerMethodField()

    unseen_count = serializers.SerializerMethodField()

    def get_total_statuses(
        self,
        obj,
    ):
        return len(obj["statuses"])

    def get_unseen_count(
        self,
        obj,
    ):
        request = self.context["request"]
        return sum(
            1
            for status in obj["statuses"]
            if not any(view.viewer_id == request.user.id for view in status.views.all())
        )

class ReactToStatusSerializer(serializers.Serializer):
    """
    A reaction or reply from the status viewer. ``emoji``: any emoji (shown
    big, "Reacted 😂"); ``text``: anything typed. Either way the chat shows
    the status preview card above it, like WhatsApp.
    """

    emoji = serializers.CharField(max_length=16, trim_whitespace=True, required=False, allow_blank=True)
    text = serializers.CharField(max_length=1000, trim_whitespace=True, required=False, allow_blank=True)

    def validate_emoji(self, value):
        import unicodedata

        value = "".join(value.split())
        if not value:
            return ""
        allowed_categories = {"So", "Sk", "Mn", "Me", "Cf"}
        has_symbol = False
        for char in value:
            category = unicodedata.category(char)
            if category == "So":
                has_symbol = True
            if category not in allowed_categories:
                raise serializers.ValidationError("Send an emoji.")
        if not has_symbol:
            raise serializers.ValidationError("Send an emoji.")
        return value

    def validate(self, attrs):
        if not attrs.get("emoji") and not attrs.get("text"):
            raise serializers.ValidationError({"emoji": "Send an emoji or a reply."})
        return attrs
