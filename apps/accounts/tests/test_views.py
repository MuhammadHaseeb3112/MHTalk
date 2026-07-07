from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User


class AccountsAPIViewTestCase(APITestCase):
    """
    Test suite for Accounts API endpoints.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+923130067082",
            email="haseeb@example.com",
            password="StrongPassword123",
        )

        self.register_url = reverse("accounts:register")
        self.login_url = reverse("accounts:login")
        self.logout_url = reverse("accounts:logout")
        self.me_url = reverse("accounts:me")
        self.update_profile_url = reverse("accounts:update-profile")

    # ----------------------------------------------------
    # Registration
    # ----------------------------------------------------

    def test_register_user_successfully(self):
        """
        User should register successfully.
        """

        response = self.client.post(
            self.register_url,
            {
                "phone_number": "+923221112233",
                "email": "new@example.com",
                "password": "StrongPassword123",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            User.objects.count(),
            2,
        )

    def test_register_duplicate_phone(self):
        """
        Duplicate phone numbers should fail.
        """

        response = self.client.post(
            self.register_url,
            {
                "phone_number": "+923130067082",
                "password": "StrongPassword123",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    # ----------------------------------------------------
    # Login
    # ----------------------------------------------------

    def test_login_successfully(self):
        """
        Login should return JWT tokens.
        """

        response = self.client.post(
            self.login_url,
            {
                "phone_number": "+923130067082",
                "password": "StrongPassword123",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertIn(
            "access",
            response.data,
        )

        self.assertIn(
            "refresh",
            response.data,
        )

        self.assertIn(
            "user",
            response.data,
        )

    def test_login_wrong_password(self):
        """
        Login should fail with invalid password.
        """

        response = self.client.post(
            self.login_url,
            {
                "phone_number": "+923130067082",
                "password": "WrongPassword",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    # ----------------------------------------------------
    # Me API
    # ----------------------------------------------------

    def test_me_requires_authentication(self):
        """
        Unauthenticated users cannot access /me/.
        """

        response = self.client.get(self.me_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_get_current_user(self):
        """
        Authenticated user should receive their own profile.
        """

        refresh = RefreshToken.for_user(self.user)

        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}"
        )

        response = self.client.get(self.me_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["phone_number"],
            self.user.phone_number,
        )

    # ----------------------------------------------------
    # Update Profile
    # ----------------------------------------------------

    def test_update_profile(self):
        """
        User should update profile successfully.
        """

        refresh = RefreshToken.for_user(self.user)

        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}"
        )

        response = self.client.patch(
            self.update_profile_url,
            {
                "display_name": "Muhammad Haseeb",
                "about": "Senior Django Developer",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.user.refresh_from_db()

        self.assertEqual(
            self.user.profile.display_name,
            "Muhammad Haseeb",
        )

        self.assertEqual(
            self.user.profile.about,
            "Senior Django Developer",
        )

    # ----------------------------------------------------
    # Logout
    # ----------------------------------------------------

    def test_logout_successfully(self):
        """
        Logout should blacklist refresh token.
        """

        refresh = RefreshToken.for_user(self.user)

        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}"
        )

        response = self.client.post(
            self.logout_url,
            {
                "refresh": str(refresh),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

    def test_logout_requires_authentication(self):
        """
        Logout requires authentication.
        """

        refresh = RefreshToken.for_user(self.user)

        response = self.client.post(
            self.logout_url,
            {
                "refresh": str(refresh),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_logout_invalid_refresh_token(self):
        """
        Invalid refresh token should fail.
        """

        refresh = RefreshToken.for_user(self.user)

        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}"
        )

        response = self.client.post(
            self.logout_url,
            {
                "refresh": "invalid-token",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )