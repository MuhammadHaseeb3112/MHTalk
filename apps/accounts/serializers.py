from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import User, Profile


class ProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for the Profile model.
    """

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

    class Meta:
        model = User

        fields = (
            "phone_number",
            "email",
            "password",
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

        return User.objects.create_user(
            phone_number=validated_data["phone_number"],
            email=validated_data.get("email"),
            password=validated_data["password"],
        )
    

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