from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    RegisterAPIView,
    LoginAPIView,
    LogoutAPIView,
    MeAPIView,
    UpdateProfileAPIView,
    ContactListCreateAPIView,
    ContactDetailAPIView,
    UserLookupAPIView,
    UserCommonGroupsAPIView,
    PrivacySettingsAPIView,
    DeleteAccountAPIView,
)

app_name = "accounts"


urlpatterns = [
    path("register/", RegisterAPIView.as_view(), name="register"),
    path("login/", LoginAPIView.as_view(), name="login"),
    path("logout/", LogoutAPIView.as_view(), name="logout"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("me/", MeAPIView.as_view(), name="me"),
    path("profile/update/", UpdateProfileAPIView.as_view(), name="update-profile"),
    path("contacts/", ContactListCreateAPIView.as_view(), name="contact-list-create"),
    path("contacts/<int:pk>/", ContactDetailAPIView.as_view(), name="contact-detail"),
    path("users/lookup/", UserLookupAPIView.as_view(), name="user-lookup"),
    path("privacy/", PrivacySettingsAPIView.as_view(), name="privacy-settings"),
    path("delete/", DeleteAccountAPIView.as_view(), name="delete-account"),
    path("users/<int:pk>/common-groups/", UserCommonGroupsAPIView.as_view(), name="user-common-groups"),
]
