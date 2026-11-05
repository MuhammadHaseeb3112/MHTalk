import json
import uuid

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.chat.models import ChatRoom, Message, Participant
from apps.chat.choices import RoomType
from apps.chat.serializers import MessageSerializer
from apps.accounts.models import Contact, User
from apps.accounts.serializers import UserSerializer

from apps.status.choices import StatusVisibility
from drf_spectacular.utils import (
    extend_schema,
    OpenApiRequest,
    OpenApiResponse,
)


from .models import (
    Status,
    StatusView,
    StatusReaction,
)

from .utils import status_contact_ids, notify_status_feed_changed, notify_status_viewed
from .serializers import (
    StatusSerializer,
    UploadStatusSerializer,
    StatusViewSerializer,
    ContactStatusSerializer,
    StatusPrivacySerializer,
    ReactToStatusSerializer,
)


class StatusContactsAPIView(APIView):
    """List saved contacts and existing private-chat contacts for status privacy controls."""
    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(summary="Contacts for status privacy", tags=["Status"])
    def get(self, request):
        # The current MHTalk Contacts UI is populated from existing private
        # conversations as well as saved Contact records. Include both sources
        # so the privacy picker does not omit a contact visible in the app.
        saved_ids = set(Contact.objects.filter(owner=request.user).values_list("contact_user_id", flat=True))
        private_chat_ids = Participant.objects.filter(
            room__room_type=RoomType.PRIVATE,
            room__is_active=True,
            room__participants__user=request.user,
        ).exclude(user=request.user).values_list("user_id", flat=True)
        contact_ids = saved_ids | set(private_chat_ids)
        users = User.objects.filter(
            id__in=contact_ids, is_active=True, is_deleted=False
        ).exclude(pk=request.user.pk).select_related("profile").order_by("profile__display_name", "phone_number")
        data = []
        for user in users:
            data.append({"user": UserSerializer(user, context={"request": request}).data})
        return Response(data)


class UploadStatusAPIView(APIView):
    """
    Upload a new text, image, or video status.
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
        request=OpenApiRequest(
            request=UploadStatusSerializer,
            encoding={
                "media": {
                    "contentType": "application/octet-stream",
                },
            },
        ),
        description=(
            "Upload a new image, video, or text status. "
            "Status expires after 24 hours."
        ),
        responses={
            201: StatusSerializer,
        },
        tags=["Status"],
    )
    def post(self, request):
        with transaction.atomic():
            serializer = UploadStatusSerializer(
                data=request.data,
                context={"request": request},
            )
            serializer.is_valid(raise_exception=True)
            status_obj = serializer.save()
            transaction.on_commit(lambda: notify_status_feed_changed(request.user, "posted"))

            return Response(
                {
                    "message": "Status uploaded successfully.",
                    "data": StatusSerializer(
                        status_obj,
                        context={"request": request},
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
    Return statuses grouped by contact, plus EVERYONE statuses.
    """

    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(
        summary="Contacts Status",
        responses={200: ContactStatusSerializer(many=True)},
        tags=["Status"],
    )
    
    def can_view_status(self, status_obj, user, contact_ids, saved_me_ids=None, chat_partner_ids=None):
        # The owner's statuses are handled by MyStatusAPIView.
        if status_obj.user_id == user.id:
            return False

        # Never expose deleted or expired statuses.
        if (
            status_obj.is_deleted
            or status_obj.expires_at <= timezone.now()
        ):
            return False

        visibility = status_obj.visibility

        # EVERYONE does not require mutual contacts.
        if visibility == StatusVisibility.EVERYONE:
            return True

        # For all other privacy modes, the viewer must have
        # saved the status owner.
        if status_obj.user_id not in contact_ids:
            return False

        # Default Contacts visibility follows the mutual-contact rule.
        # Custom audiences are explicitly chosen by the publisher from their
        # saved contacts, so do not silently discard a selected contact merely
        # because the other person has not saved the publisher in return.
        if visibility == StatusVisibility.CONTACTS:
            # The feed passes both sets precomputed (one query each) so the
            # check costs no query per status.
            if saved_me_ids is not None:
                owner_has_saved_viewer = status_obj.user_id in saved_me_ids
            else:
                owner_has_saved_viewer = Contact.objects.filter(
                    owner_id=status_obj.user_id,
                    contact_user_id=user.id,
                ).exists()
            if chat_partner_ids is not None:
                shared_private_chat = status_obj.user_id in chat_partner_ids
            else:
                shared_private_chat = Participant.objects.filter(
                    room__room_type=RoomType.PRIVATE,
                    room__is_active=True,
                    room__participants__user_id=status_obj.user_id,
                    user_id=user.id,
                ).exists()
            return owner_has_saved_viewer or shared_private_chat

        # privacy_rules is prefetched by the feed query.
        listed = any(rule.user_id == user.id for rule in status_obj.privacy_rules.all())

        if visibility == StatusVisibility.CONTACTS_EXCEPT:
            return not listed

        # Only selected contacts.
        if visibility == StatusVisibility.ONLY_SHARE_WITH:
            return listed

        # Fail closed for unknown visibility values.
        return False


    def get(self, request):
        
        contact_ids = set(
            Contact.objects.filter(owner=request.user).values_list("contact_user_id", flat=True)
        )
        chat_partner_ids = set(Participant.objects.filter(
            room__room_type=RoomType.PRIVATE,
            room__is_active=True,
            room__participants__user=request.user,
        ).exclude(user=request.user).values_list("user_id", flat=True))
        contact_ids |= chat_partner_ids
        saved_me_ids = set(
            Contact.objects.filter(contact_user=request.user).values_list("owner_id", flat=True)
        )

        # Include contacts and all potential EVERYONE status owners.
        candidate_ids = contact_ids | set(
            Status.objects.filter(
                visibility=StatusVisibility.EVERYONE,
                is_deleted=False,
                user__is_active=True,
                user__is_deleted=False,
                expires_at__gt=timezone.now(),
            )
            .exclude(user=request.user)
            .values_list("user_id", flat=True)
            .distinct()
        )
        # Blocked either way: neither side sees the other's status.
        from apps.chat.utils import blocked_user_ids

        blocked = blocked_user_ids(request.user.id)
        candidate_ids -= blocked
        contact_ids -= blocked

        statuses = (
            Status.objects.filter(
                user_id__in=candidate_ids,
                user__is_active=True,
                user__is_deleted=False,
                is_deleted=False,
                expires_at__gt=timezone.now(),
            )
            .select_related("user", "user__profile")
            .prefetch_related("views", "privacy_rules")
            .order_by("user_id", "-created_at")
        )

        grouped = {}

        for status_obj in statuses:
            if not self.can_view_status(
                status_obj, request.user, contact_ids, saved_me_ids, chat_partner_ids
            ):
                continue

            user_id = status_obj.user_id

            if user_id not in grouped:
                grouped[user_id] = {
                    "user": status_obj.user,
                    "statuses": [],
                }

            grouped[user_id]["statuses"].append(status_obj)

        serializer = ContactStatusSerializer(
            grouped.values(),
            many=True,
            context={"request": request},
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

        
        if status_obj.user_id == request.user.id:
            return Response(
                {"detail": "You cannot view your own status."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        contact_ids = status_contact_ids(request.user)

        if not ContactsStatusAPIView().can_view_status(
            status_obj,
            request.user,
            contact_ids,
        ):
            return Response(
                {"detail": "You are not allowed to view this status."},
                status=status.HTTP_403_FORBIDDEN,
            )

        _view, created = StatusView.objects.get_or_create(
            status=status_obj,
            viewer=request.user,
        )
        if created:
            notify_status_viewed(status_obj, request.user)

        return Response(
            {"message": "Status viewed successfully."},
            status=status.HTTP_200_OK,
        )

    
class StatusReactionAPIView(APIView):
    """React to a visible status and post that reaction into the owner's DM."""
    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(
        summary="React to a status",
        request=ReactToStatusSerializer,
        responses={200: OpenApiResponse(description="Reaction sent to chat.")},
        tags=["Status"],
    )
    def post(self, request, pk):
        status_obj = get_object_or_404(
            Status.objects.select_related("user"),
            pk=pk,
            is_deleted=False,
            expires_at__gt=timezone.now(),
        )
        if status_obj.user_id == request.user.id:
            return Response({"detail": "You cannot react to your own status."}, status=status.HTTP_400_BAD_REQUEST)

        contact_ids = set(Contact.objects.filter(owner=request.user).values_list("contact_user_id", flat=True))
        contact_ids.update(
            Participant.objects.filter(
                room__room_type=RoomType.PRIVATE,
                room__is_active=True,
                room__participants__user=request.user,
            ).exclude(user=request.user).values_list("user_id", flat=True)
        )
        if not ContactsStatusAPIView().can_view_status(status_obj, request.user, contact_ids):
            return Response({"detail": "You cannot react to this status."}, status=status.HTTP_403_FORBIDDEN)

        serializer = ReactToStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        emoji = serializer.validated_data["emoji"]

        with transaction.atomic():
            room = (
                ChatRoom.objects.filter(
                    room_type=RoomType.PRIVATE,
                    is_active=True,
                    participants__user=request.user,
                )
                .filter(participants__user=status_obj.user)
                .distinct()
                .first()
            )
            if room is None:
                room = ChatRoom.objects.create(room_type=RoomType.PRIVATE, created_by=request.user)
                Participant.objects.get_or_create(room=room, user=request.user)
                Participant.objects.get_or_create(room=room, user=status_obj.user)

            media_url = ""
            if status_obj.media:
                try:
                    media_url = status_obj.media.url
                except (ValueError, AttributeError):
                    media_url = ""
            preview = {
                "kind": "status_reaction",
                "status_id": status_obj.id,
                "status_type": status_obj.status_type,
                "status_text": (status_obj.content or "").strip()[:180],
                "status_media": media_url,
                "emoji": emoji,
                "reactor_id": request.user.id,
                "owner_id": status_obj.user_id,
                "status_created_at": status_obj.created_at.isoformat(),
            }
            content = "__MHTALK_STATUS_REACTION__:" + json.dumps(preview, separators=(",", ":"))
            # Like WhatsApp, every reaction is its own chat message: reacting
            # three times to a status shows three "Reacted … to a status" cards.
            message = Message.objects.create(
                room=room,
                sender=request.user,
                client_message_id=f"status-reaction-{status_obj.id}-{request.user.id}-{uuid.uuid4().hex[:12]}",
                message_type="TEXT",
                content=content,
            )
            # The status keeps the viewer's latest reaction (shown on the status).
            reaction, _created_reaction = StatusReaction.objects.update_or_create(
                status=status_obj,
                reactor=request.user,
                defaults={"emoji": emoji, "chat_message": message},
            )
            room.updated_at = timezone.now()
            room.save(update_fields=["updated_at"])

        from apps.chat.utils import broadcast_message, get_message_with_relations

        message = get_message_with_relations(message.id)
        broadcast_message(message, request)
        message_data = MessageSerializer(message, context={"request": request}).data
        return Response(
            {
                "message": "Status reaction sent in chat.",
                "room_id": room.id,
                "status_reaction": {"id": reaction.id, "emoji": reaction.emoji, "status_id": status_obj.id},
                "chat_message": message_data,
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
        media = status_obj.media
        status_obj.save(update_fields=["is_deleted"])
        notify_status_feed_changed(request.user, "deleted")
        if media:
            transaction.on_commit(lambda: media.delete(save=False))

        return Response(
            {
                "message":
                "Status deleted successfully.",
            },
            status=status.HTTP_200_OK,
        )
    


class UpdateStatusPrivacyAPIView(APIView):
    """Status audiences are snapshotted at publication; old updates are immutable."""
    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(
        summary="Update status privacy (unsupported for published statuses)",
        request=StatusPrivacySerializer,
        responses={400: OpenApiResponse(description="Publish a new status to change its audience.")},
        tags=["Status"],
    )
    def post(self, request, pk):
        get_object_or_404(
            Status,
            pk=pk,
            user=request.user,
            is_deleted=False,
            expires_at__gt=timezone.now(),
        )
        return Response(
            {"detail": "Status privacy applies to new updates only. Publish a new status to use a different audience; existing updates are unchanged."},
            status=status.HTTP_400_BAD_REQUEST,
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