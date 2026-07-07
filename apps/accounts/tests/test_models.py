from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User, Profile


class UserModelTestCase(TestCase):
    """
    Test suite for the User model.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+923130067082",
            email="haseeb@example.com",
            password="StrongPassword123",
        )

    def test_user_is_created(self):
        """
        User should be created successfully.
        """
        self.assertIsInstance(self.user, User)

    def test_user_phone_number(self):
        """
        User phone number should be stored correctly.
        """
        self.assertEqual(
            self.user.phone_number,
            "+923130067082",
        )

    def test_user_email(self):
        """
        User email should be stored correctly.
        """
        self.assertEqual(
            self.user.email,
            "haseeb@example.com",
        )

    def test_user_string_representation(self):
        """
        __str__ should return the phone number.
        """
        self.assertEqual(
            str(self.user),
            "+923130067082",
        )

    def test_default_flags(self):
        """
        Verify default boolean values.
        """
        self.assertTrue(self.user.is_active)
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)
        self.assertFalse(self.user.is_deleted)
        self.assertFalse(self.user.is_verified)

    def test_date_joined_is_set(self):
        """
        date_joined should be populated automatically.
        """
        self.assertIsNotNone(self.user.date_joined)
        self.assertLessEqual(
            self.user.date_joined,
            timezone.now(),
        )


class ProfileModelTestCase(TestCase):
    """
    Test suite for the Profile model.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+923001112233",
            password="StrongPassword123",
        )

        self.profile = self.user.profile

    def test_profile_created_by_signal(self):
        """
        Profile should be automatically created.
        """
        self.assertTrue(
            Profile.objects.filter(user=self.user).exists()
        )

    def test_profile_relationship(self):
        """
        Every user should have exactly one profile.
        """
        self.assertEqual(
            self.profile.user,
            self.user,
        )

    def test_default_display_name(self):
        """
        Display name should default to the phone number.
        """
        self.assertEqual(
            self.profile.display_name,
            self.user.phone_number,
        )

    def test_default_about(self):
        """
        Default about text should be correct.
        """
        self.assertEqual(
            self.profile.about,
            "Hey there! I'm using WhatsUp.",
        )

    def test_default_online_status(self):
        """
        User should be offline by default.
        """
        self.assertFalse(
            self.profile.is_online
        )

    def test_last_seen_is_created(self):
        """
        last_seen should be populated automatically.
        """
        self.assertIsNotNone(
            self.profile.last_seen
        )

    def test_created_at_exists(self):
        """
        created_at should be generated automatically.
        """
        self.assertIsNotNone(
            self.profile.created_at
        )

    def test_updated_at_exists(self):
        """
        updated_at should be generated automatically.
        """
        self.assertIsNotNone(
            self.profile.updated_at
        )

    def test_profile_string_representation_display_name(self):
        """
        __str__ should return display_name if available.
        """
        self.profile.display_name = "Muhammad Haseeb"
        self.profile.save()

        self.assertEqual(
            str(self.profile),
            "Muhammad Haseeb",
        )

    def test_profile_string_representation_phone_number(self):
        """
        __str__ should return phone number if display_name is empty.
        """
        self.profile.display_name = ""
        self.profile.save()

        self.assertEqual(
            str(self.profile),
            self.user.phone_number,
        )

    def test_one_profile_per_user(self):
        """
        A user should have only one profile.
        """
        self.assertEqual(
            Profile.objects.filter(user=self.user).count(),
            1,
        )