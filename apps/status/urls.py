from django.urls import path

from .views import (
    ContactsStatusAPIView,
    StatusContactsAPIView,
    DeleteStatusAPIView,
    MyStatusAPIView,
    UploadStatusAPIView,
    ViewStatusAPIView,
    StatusViewersAPIView,
    UpdateStatusPrivacyAPIView,
    StatusReactionAPIView,
)

app_name = "status"

urlpatterns = [
    path("contacts/", StatusContactsAPIView.as_view(), name="status-privacy-contacts"),

    path(
        "",
        ContactsStatusAPIView.as_view(),
        name="status-list",
    ),

    path(
        "upload/",
        UploadStatusAPIView.as_view(),
        name="status-upload",
    ),

    path(
        "me/",
        MyStatusAPIView.as_view(),
        name="my-status",
    ),

    path(
        "<int:pk>/view/",
        ViewStatusAPIView.as_view(),
        name="status-view",
    ),

    path(
        "<int:pk>/delete/",
        DeleteStatusAPIView.as_view(),
        name="status-delete",
    ),

    path(
        "<int:pk>/react/",
        StatusReactionAPIView.as_view(),
        name="status-react",
    ),

    path(
        "<int:pk>/viewers/",
        StatusViewersAPIView.as_view(),
        name="status-viewers",
    ),

    path(
        "<int:pk>/privacy/",
        UpdateStatusPrivacyAPIView.as_view(),
        name="status-privacy",
    ),
]