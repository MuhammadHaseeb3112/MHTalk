from django.urls import path

from .views import (
    ContactsStatusAPIView,
    DeleteStatusAPIView,
    MyStatusAPIView,
    UploadStatusAPIView,
    ViewStatusAPIView,
    StatusViewersAPIView,
    UpdateStatusPrivacyAPIView,
)

app_name = "status"

urlpatterns = [

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