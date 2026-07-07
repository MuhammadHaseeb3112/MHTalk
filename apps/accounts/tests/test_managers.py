from django.test import TestCase

from apps.accounts.models import User


class UserManagerTestCase(TestCase):
    """
    Test suite for the custom UserManager.
    """

    def test_create_user_successfully(self):
        """
        Should create a normal user successfully.
        """

        user = User.objects.create_user(
            phone_number="+923130067082",
            email="haseeb@example.com",
            password="StrongPassword123",
        )

        self.assertEqual(user.phone_number, "+923130067082")
        self.assertEqual(user.email, "haseeb@example.com")
        self.assertTrue(user.check_password("StrongPassword123"))

        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_verified)

    def test_create_superuser_successfully(self):
        """
        Should create a superuser successfully.
        """

        admin = User.objects.create_superuser(
            phone_number="+923001112233",
            password="AdminPassword123",
        )

        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_active)
        self.assertTrue(admin.is_verified)

    def test_phone_number_is_required(self):
        """
        User creation should fail if phone number is missing.
        """

        with self.assertRaises(ValueError):
            User.objects.create_user(
                phone_number="",
                password="password123",
            )

    def test_password_is_hashed(self):
        """
        Password should never be stored as plain text.
        """

        user = User.objects.create_user(
            phone_number="+923111111111",
            password="MyPassword123",
        )

        self.assertNotEqual(user.password, "MyPassword123")

        self.assertTrue(
            user.check_password("MyPassword123")
        )

    def test_email_is_normalized(self):
        """
        Email should be normalized automatically.
        """

        user = User.objects.create_user(
            phone_number="+923222222222",
            email="HaSeEb@Example.COM",
            password="password123",
        )

        self.assertEqual(
            user.email,
            "HaSeEb@example.com",
        )

    def test_phone_number_is_normalized(self):
        """
        Spaces and dashes should be removed.
        """

        user = User.objects.create_user(
            phone_number="+92 313-0067082",
            password="password123",
        )

        self.assertEqual(
            user.phone_number,
            "+923130067082",
        )

    def test_superuser_must_have_is_staff_true(self):
        """
        Superuser must always have is_staff=True.
        """

        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                phone_number="+923334445555",
                password="password123",
                is_staff=False,
            )

    def test_superuser_must_have_is_superuser_true(self):
        """
        Superuser must always have is_superuser=True.
        """

        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                phone_number="+923334445556",
                password="password123",
                is_superuser=False,
            )

    def test_superuser_must_have_is_active_true(self):
        """
        Superuser must always be active.
        """

        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                phone_number="+923334445557",
                password="password123",
                is_active=False,
            )