from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.chat.models import Participant
from apps.chat.choices import RoomType
from apps.status.choices import StatusVisibility
from drf_spectacular.utils import (
    extend_schema,
    OpenApiResponse,
)

from .models import (
    Status,
    StatusView,
)

from .serializers import (
    StatusSerializer,
    UploadStatusSerializer,
    StatusViewSerializer,
    ContactStatusSerializer,
    StatusPrivacySerializer,

)

class UploadStatusAPIView(APIView):
    """
    Upload a new status.
    """

    permission_classes = (
        permissions.IsAuthenticated,
    )

    parser_classes = (
        MultiPartParser,
        FormParser,
    )

    @extend_schema(
        summary="Upload Status",
        request=UploadStatusSerializer,
        description="""
        Upload a new image/video/text status.

        Status expires after 24 hours.
        """,
        responses={
            201: StatusSerializer,
        },
        tags=["Status"],
    )

    def post(
        self,
        request,
    ):   

        with transaction.atomic():


            serializer = UploadStatusSerializer(
                data=request.data,
                context={
                    "request": request,
                },
            )

            serializer.is_valid(
                raise_exception=True,
            )

            status_obj = serializer.save()

            return Response(
                {
                    "message":
                    "Status uploaded successfully.",
                    "data":
                    StatusSerializer(
                        status_obj,
                        context={
                            "request": request,
                        },
                    ).data,
                },
                status=status.HTTP_201_CREATED,
            )
    

class MyStatusAPIView(generics.ListAPIView):
    """
    Return my active statuses.
    """

    serializer_class = StatusSerializer

    permission_classes = (
        permissions.IsAuthenticated,
    )

    @extend_schema(
        summary="My Status",
        responses={
            200: StatusSerializer(many=True),
        },
        tags=["Status"],
    )

    def get_queryset(self):

        return (
            Status.objects.filter(
                user=self.request.user,
                is_deleted=False,
                expires_at__gt=timezone.now(),
            ).select_related(
                "user",
                "user__profile",
            ).prefetch_related(
                "views",
                "privacy_rules",
            )
            .order_by(
                "-created_at",
            )
        )
    
class ContactsStatusAPIView(APIView):
    """
    Return statuses grouped by contact.
    """

    permission_classes = (
        permissions.IsAuthenticated,
    )

    @extend_schema(
        summary="Contacts Status",
        responses={
            200: ContactStatusSerializer(many=True),
        },
        tags=["Status"],
    )


    def can_view_status(
        self,
        status,
        user,
    ):
        """
        Return True if the given user
        can view the status.
        """

        # Owner always sees their own status
        if status.user == user:
            return True

        visibility = status.visibility

        # Everyone
        if visibility == StatusVisibility.EVERYONE:
            return True

        # My Contacts
        if visibility == StatusVisibility.CONTACTS:
            return True

        # My Contacts Except
        if visibility == StatusVisibility.CONTACTS_EXCEPT:

            return not status.privacy_rules.filter(
                user=user,
            ).exists()

        # Only Share With
        if visibility == StatusVisibility.ONLY_SHARE_WITH:

            return status.privacy_rules.filter(
                user=user,
            ).exists()

        return False


    def get(
        self,
        request,
    ):

        room_ids = (
            Participant.objects.filter(
                user=request.user,
                room__room_type=RoomType.PRIVATE,
            )
            .values_list(
                "room_id",
                flat=True,
            )
        )

        contact_ids = (
            Participant.objects.filter(
                room_id__in=room_ids,
            )
            .exclude(
                user=request.user,
            )
            .values_list(
                "user_id",
                flat=True,
            )
            .distinct()
        )

        statuses = (
            Status.objects.filter(
                user_id__in=contact_ids,
                is_deleted=False,
                expires_at__gt=timezone.now(),
            )
            .select_related(
                "user",
                "user__profile",
            )
            .prefetch_related(
                "views",
                "privacy_rules",
            )
            .order_by(
                "user_id",
                "-created_at",
            )
        )

        grouped = {}

        for status in statuses:

            if not self.can_view_status(
                status,
                request.user,
            ):
                continue

            user_id = status.user_id

            if user_id not in grouped:

                grouped[user_id] = {
                    "user": status.user,
                    "statuses": [],
                }

            grouped[user_id]["statuses"].append(
                status,
            )

        # Remove empty groups
        grouped = {
            key: value
            for key, value in grouped.items()
            if value["statuses"]
        }

        serializer = ContactStatusSerializer(
            grouped.values(),
            many=True,
            context={
                "request": request,
            },
        )

        return Response(serializer.data)


        serializer = ContactStatusSerializer(
            grouped.values(),
            many=True,
            context={
                "request": request,
            },
        )

        return Response(serializer.data)
    

class ViewStatusAPIView(APIView):
    """
    Mark a status as viewed.
    """

    permission_classes = (
        permissions.IsAuthenticated,
    )

    @extend_schema(
        summary="View Status",
        request=None,
        responses={
            200: OpenApiResponse(description="Viewed."),
        },
        tags=["Status"],
    )

    def post(
        self,
        request,
        pk,
    ):

        status_obj = get_object_or_404(
            Status,
            pk=pk,
            is_deleted=False,
            expires_at__gt=timezone.now(),
        )

        if status_obj.user == request.user:
            return Response(
                {
                    "detail": "You cannot view your own status."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        StatusView.objects.get_or_create(
            status=status_obj,
            viewer=request.user,
        )

        return Response(
            {
                "message":
                "Status viewed successfully.",
            },
            status=status.HTTP_200_OK,
        )
    
class DeleteStatusAPIView(APIView):
    """
    Soft delete a status.
    """

    permission_classes = (
        permissions.IsAuthenticated,
    )

    @extend_schema(
        summary="Delete Status",
        request=None,
        responses={
            200: OpenApiResponse(description="Deleted."),
        },
        tags=["Status"],
    )

    def delete(
        self,
        request,
        pk,
    ):

        status_obj = get_object_or_404(
            Status,
            pk=pk,
            user=request.user,
            is_deleted=False,
            expires_at__gt=timezone.now(),
        )

        status_obj.is_deleted = True

        status_obj.save(
            update_fields=[
                "is_deleted",
            ]
        )

        return Response(
            {
                "message":
                "Status deleted successfully.",
            },
            status=status.HTTP_200_OK,
        )
    


class UpdateStatusPrivacyAPIView(APIView):
    """
    Update status privacy rules.
    """

    permission_classes = (
        permissions.IsAuthenticated,
    )

    @extend_schema(
        summary="Update Status Privacy",
        request=StatusPrivacySerializer,
        responses={
            200: OpenApiResponse(description="Updated."),
        },
        tags=["Status"],
    )

    def post(
        self,
        request,
        pk,
    ):

        status_obj = get_object_or_404(
            Status,
            pk=pk,
            user=request.user,
            is_deleted=False,
            expires_at__gt=timezone.now(),
        )

        serializer = StatusPrivacySerializer(
            data=request.data,
            context={
                "request": request,
                "status": status_obj,
            },
        )

        serializer.is_valid(
            raise_exception=True,
        )

        serializer.save()

        return Response(
            {
                "message":
                "Status privacy updated successfully.",
            },
            status=status.HTTP_200_OK,
        )
    

class StatusViewersAPIView(generics.ListAPIView):
    """
    Return viewers of my status.
    """

    serializer_class = StatusViewSerializer

    permission_classes = (
        permissions.IsAuthenticated,
    )

    @extend_schema(
        summary="Status Viewers",
        responses={
            200: StatusViewSerializer(many=True),
        },
        tags=["Status"],
    )

    def get_queryset(self):

        status_obj = get_object_or_404(
            Status,
            pk=self.kwargs["pk"],
            user=self.request.user,
            is_deleted=False,
            expires_at__gt=timezone.now(),
        )

        return (
            StatusView.objects.filter(
                status=status_obj,
            )
            .select_related(
                "viewer",
                "viewer__profile",
            )
            .order_by(
                "-viewed_at",
            )
        )