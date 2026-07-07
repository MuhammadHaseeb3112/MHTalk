from django.test import TestCase

from apps.accounts.models import User
from apps.accounts.serializers import (
    LoginSerializer,
    ProfileSerializer,
    UserRegistrationSerializer,
    UserSerializer,
)


class UserRegistrationSerializerTestCase(TestCase):
    """
    Test suite for UserRegistrationSerializer.
    """

    def test_register_user_successfully(self):
        """
        Serializer should create a new user.
        """

        serializer = UserRegistrationSerializer(
            data={
                "phone_number": "+923130067082",
                "email": "haseeb@example.com",
                "password": "StrongPassword123",
            }
        )

        self.assertTrue(serializer.is_valid())

        user = serializer.save()

        self.assertEqual(
            user.phone_number,
            "+923130067082",
        )

        self.assertEqual(
            user.email,
            "haseeb@example.com",
        )

        self.assertTrue(
            user.check_password("StrongPassword123")
        )

    def test_duplicate_phone_number(self):
        """
        Duplicate phone numbers should not be allowed.
        """

        User.objects.create_user(
            phone_number="+923130067082",
            password="StrongPassword123",
        )

        serializer = UserRegistrationSerializer(
            data={
                "phone_number": "+923130067082",
                "password": "StrongPassword123",
            }
        )

        self.assertFalse(serializer.is_valid())

        self.assertIn(
            "phone_number",
            serializer.errors,
        )

    def test_invalid_phone_number(self):
        """
        Phone number must be in E.164 format.
        """

        serializer = UserRegistrationSerializer(
            data={
                "phone_number": "03130067082",
                "password": "StrongPassword123",
            }
        )

        self.assertFalse(serializer.is_valid())

        self.assertIn(
            "phone_number",
            serializer.errors,
        )

    def test_password_is_hashed(self):
        """
        Password should never be stored in plain text.
        """

        serializer = UserRegistrationSerializer(
            data={
                "phone_number": "+923221112233",
                "password": "StrongPassword123",
            }
        )

        self.assertTrue(serializer.is_valid())

        user = serializer.save()

        self.assertNotEqual(
            user.password,
            "StrongPassword123",
        )

        self.assertTrue(
            user.check_password("StrongPassword123")
        )

    def test_email_is_optional(self):
        """
        Registration should work without email.
        """

        serializer = UserRegistrationSerializer(
            data={
                "phone_number": "+923441112233",
                "password": "StrongPassword123",
            }
        )

        self.assertTrue(serializer.is_valid())

    def test_missing_phone_number(self):
        """
        Phone number is required.
        """

        serializer = UserRegistrationSerializer(
            data={
                "password": "StrongPassword123",
            }
        )

        self.assertFalse(serializer.is_valid())

        self.assertIn(
            "phone_number",
            serializer.errors,
        )

    def test_missing_password(self):
        """
        Password is required.
        """

        serializer = UserRegistrationSerializer(
            data={
                "phone_number": "+923441112233",
            }
        )

        self.assertFalse(serializer.is_valid())

        self.assertIn(
            "password",
            serializer.errors,
        )


class LoginSerializerTestCase(TestCase):
    """
    Test suite for LoginSerializer.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+923130067082",
            password="StrongPassword123",
        )

    def test_login_successfully(self):
        """
        Login should succeed with valid credentials.
        """

        serializer = LoginSerializer(
            data={
                "phone_number": "+923130067082",
                "password": "StrongPassword123",
            }
        )

        self.assertTrue(serializer.is_valid())

        self.assertEqual(
            serializer.validated_data["user"],
            self.user,
        )

    def test_login_wrong_password(self):
        """
        Login should fail with wrong password.
        """

        serializer = LoginSerializer(
            data={
                "phone_number": "+923130067082",
                "password": "WrongPassword",
            }
        )

        self.assertFalse(serializer.is_valid())

    def test_login_unknown_phone(self):
        """
        Login should fail for unknown phone.
        """

        serializer = LoginSerializer(
            data={
                "phone_number": "+923999999999",
                "password": "StrongPassword123",
            }
        )

        self.assertFalse(serializer.is_valid())

    def test_login_inactive_user(self):
        """
        Inactive users should not be able to login.
        """

        self.user.is_active = False
        self.user.save()

        serializer = LoginSerializer(
            data={
                "phone_number": "+923130067082",
                "password": "StrongPassword123",
            }
        )

        self.assertFalse(serializer.is_valid())


class UserSerializerTestCase(TestCase):
    """
    Test suite for UserSerializer.
    """

    def test_user_serializer_fields(self):
        """
        Serializer should return expected fields.
        """

        user = User.objects.create_user(
            phone_number="+923001112233",
            email="user@example.com",
            password="StrongPassword123",
        )

        serializer = UserSerializer(user)

        self.assertEqual(
            serializer.data["phone_number"],
            "+923001112233",
        )

        self.assertEqual(
            serializer.data["email"],
            "user@example.com",
        )

        self.assertIn(
            "profile",
            serializer.data,
        )


class ProfileSerializerTestCase(TestCase):
    """
    Test suite for ProfileSerializer.
    """

    def test_profile_serializer_fields(self):
        """
        Serializer should expose profile fields.
        """

        user = User.objects.create_user(
            phone_number="+923555667788",
            password="StrongPassword123",
        )

        serializer = ProfileSerializer(user.profile)

        self.assertIn(
            "display_name",
            serializer.data,
        )

        self.assertIn(
            "about",
            serializer.data,
        )

        self.assertIn(
            "is_online",
            serializer.data,
        )

        self.assertIn(
            "last_seen",
            serializer.data,
        )