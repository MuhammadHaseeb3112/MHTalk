from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import User, Profile


class ProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for the Profile model.
    """

    MAX_PICTURE_BYTES = 5 * 1024 * 1024

    def validate_display_name(self, value):
        value = (value or "").strip()
        if len(value) > 100:
            raise serializers.ValidationError("Name must be 100 characters or fewer.")
        return value

    def validate_about(self, value):
        value = (value or "").strip()
        if len(value) > 139:
            raise serializers.ValidationError("About must be 139 characters or fewer.")
        return value

    def validate_profile_picture(self, value):
        if value is None:
            return value
        content_type = str(getattr(value, "content_type", "") or "").lower()
        if content_type and not content_type.startswith("image/"):
            raise serializers.ValidationError("Upload an image file.")
        if getattr(value, "size", 0) > self.MAX_PICTURE_BYTES:
            raise serializers.ValidationError("Profile photos must be 5 MB or smaller.")
        return value

    class Meta:
        model = Profile

        fields = (
            "display_name",
            "profile_picture",
            "about",
            "is_online",
            "last_seen",
        )

        read_only_fields = (
            "is_online",
            "last_seen",
        )


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for the User model.
    """

    profile = ProfileSerializer(read_only=True)

    def to_representation(self, instance):
        # Privacy settings (last seen, online, photo, about) are applied for
        # the viewer of this request; see apps/accounts/privacy.py.
        from .privacy import apply_user_privacy, viewer_from_context

        data = super().to_representation(instance)
        return apply_user_privacy(data, instance, viewer_from_context(self.context))

    class Meta:
        model = User

        fields = (
            "id",
            "phone_number",
            "email",
            "is_verified",
            "date_joined",
            "profile",
        )

        read_only_fields = (
            "id",
            "is_verified",
            "date_joined",
        )


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for user registration.
    """

    password = serializers.CharField(
        write_only=True,
        min_length=8,
        style={"input_type": "password"},
    )

    display_name = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        max_length=100,
    )

    class Meta:
        model = User

        fields = (
            "phone_number",
            "email",
            "password",
            "display_name",
        )


    def validate_phone_number(self, value):
        """  Validate phone number.  """

        value = (
            value.strip()
            .replace(" ", "")
            .replace("-", "")
            .replace("(", "")
            .replace(")", "")
        )

        if not value.startswith("+"):
            raise serializers.ValidationError(
                "Phone number must be in international format (e.g. +923130067082)."
            )

        if not value[1:].isdigit() or not 8 <= len(value) - 1 <= 15:
            raise serializers.ValidationError(
                "Enter a valid phone number with country code, using digits only (e.g. +923130067082)."
            )

        if User.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError(
                "A user with this phone number already exists."
            )

        return value
    
    def validate_password(self, value):
        """
        Validate password using Django's built-in validators.
        """

        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(e.messages)

        return value
    
    def create(self, validated_data):
        """
        Create and return a new user.
        """

        display_name = (validated_data.pop("display_name", "") or "").strip()
        user = User.objects.create_user(
            phone_number=validated_data["phone_number"],
            email=validated_data.get("email"),
            password=validated_data["password"],
        )
        if display_name:
            Profile.objects.filter(user=user).update(display_name=display_name)
            user.refresh_from_db()
        return user
    

class LoginSerializer(serializers.Serializer):
    """
    Serializer for user login.
    """

    phone_number = serializers.CharField()

    password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
    )

    def validate(self, attrs):
        """
        Validate user credentials.
        """

        password = attrs.get("password")

        phone_number = (
            attrs.get("phone_number", "")
            .strip()
            .replace(" ", "")
            .replace("-", "")
            .replace("(", "")
            .replace(")", "")
        )

        user = authenticate(
            phone_number=phone_number,
            password=password,
        )

        if not user:
            raise serializers.ValidationError(
                "Invalid credentials."
            )

        if not user.is_active:
            raise serializers.ValidationError(
                "This account is inactive."
            )

        attrs["user"] = user

        return attrs
    
class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class PrivacySettingsSerializer(serializers.Serializer):
    """Settings > Privacy (all fields optional on PATCH)."""

    last_seen = serializers.ChoiceField(choices=Profile.PRIVACY_CHOICES, source="last_seen_privacy", required=False)
    online = serializers.ChoiceField(choices=Profile.ONLINE_CHOICES, source="online_privacy", required=False)
    profile_photo = serializers.ChoiceField(choices=Profile.PRIVACY_CHOICES, source="photo_privacy", required=False)
    about = serializers.ChoiceField(choices=Profile.PRIVACY_CHOICES, source="about_privacy", required=False)
    read_receipts = serializers.BooleanField(required=False)

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if validated_data:
            instance.save(update_fields=[*validated_data.keys(), "updated_at"])
        return instance


class DeleteAccountSerializer(serializers.Serializer):
    """WhatsApp asks for the phone number; we also require the password."""

    phone_number = serializers.CharField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs):
        from .utils import normalize_phone_variants

        user = self.context["request"].user
        if user.phone_number not in normalize_phone_variants(attrs.get("phone_number")):
            raise serializers.ValidationError({"phone_number": "The phone number doesn't match your account."})
        if not user.check_password(attrs.get("password") or ""):
            raise serializers.ValidationError({"password": "Incorrect password."})
        return attrs
