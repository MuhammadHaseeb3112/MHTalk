from django.utils import timezone
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
        )

        read_only_fields = fields

    def get_views_count(
        self,
        obj,
    ):
        return obj.views.count()

    def get_is_viewed(
        self,
        obj,
    ):
        request = self.context.get(
            "request",
        )

        if not request:
            return False

        return obj.views.filter(
            viewer=request.user,
        ).exists()

    def get_is_expired(
        self,
        obj,
    ):
        return obj.is_expired


# ==========================================================
# Upload Status
# ==========================================================

class UploadStatusSerializer(serializers.ModelSerializer):
    """
    Upload a new status.
    """

    class Meta:

        model = Status

        fields = (
            "status_type",
            "content",
            "media",
            "background_color",
            "text_color",
            "visibility",
        )

    def validate(
        self,
        attrs,
    ):
        status_type = attrs.get(
            "status_type",
        )

        content = attrs.get("content")

        if content is None:
            content = ""
        else:
            content = str(content).strip()

        media = attrs.get(
            "media",
        )

        if (
            status_type == StatusType.TEXT
            and not content
        ):
            raise serializers.ValidationError(
                {
                    "content":
                    "Text status cannot be empty."
                }
            )

        if (
            status_type in (
                StatusType.IMAGE,
                StatusType.VIDEO,
            )
            and not media
        ):
            raise serializers.ValidationError(
                {
                    "media":
                    "Media file is required."
                }
            )

        attrs["content"] = content

        return attrs

    def create(
        self,
        validated_data,
    ):
        request = self.context["request"]

        return Status.objects.create(
            user=request.user,
            **validated_data,
        )
    

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

        if status.user != request.user:
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
        return obj.views.count()

    def get_is_viewed(self, obj):
        request = self.context["request"]
        return obj.views.filter(
            viewer=request.user
        ).exists()

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
            if not status.views.filter(
                viewer=request.user,
            ).exists()
        )
    
