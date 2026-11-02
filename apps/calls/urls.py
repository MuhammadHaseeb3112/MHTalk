from django.urls import path

from .views import (
    AcceptCallAPIView,
    CallHistoryAPIView,
    EndCallAPIView,
    RejectCallAPIView,
    StartCallAPIView,
    HoldCallAPIView,
    ResumeCallAPIView,
    MissedCallsAPIView,
    IceServersAPIView,
    ActiveCallsAPIView,
)

app_name = "calls"

urlpatterns = [
    path("ice-servers/", IceServersAPIView.as_view(), name="ice-servers"),

    path(
        "start/",
        StartCallAPIView.as_view(),
        name="start-call",
    ),

    path(
        "<int:pk>/accept/",
        AcceptCallAPIView.as_view(),
        name="accept-call",
    ),

    path(
        "<int:pk>/reject/",
        RejectCallAPIView.as_view(),
        name="reject-call",
    ),

    path(
        "<int:pk>/end/",
        EndCallAPIView.as_view(),
        name="end-call",
    ),

    path(
        "missed/",
        MissedCallsAPIView.as_view(),
        name="missed-calls",
    ),

    path(
        "active/",
        ActiveCallsAPIView.as_view(),
        name="active-calls",
    ),

    path(
        "history/",
        CallHistoryAPIView.as_view(),
        name="call-history",
    ),

    path(
        "<int:pk>/hold/",
        HoldCallAPIView.as_view(),
        name="hold-call",
    ),

    path(
        "<int:pk>/resume/",
        ResumeCallAPIView.as_view(),
        name="resume-call",
    ),
]