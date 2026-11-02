from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated

from rest_framework.parsers import MultiPartParser, FormParser
from django.db.models import Q, Exists, OuterRef, Subquery, Count, F
from django.db.models.functions import Coalesce
from apps.accounts.models import User, Contact
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .utils import (
    broadcast_message,
    broadcast_room_changed,
    get_message_with_relations,
    broadcast_deleted_message,
    soft_delete_messages_for_everyone,
    mark_room_read,
    broadcast_receipts,
    persist_receipts_bulk,
    notify_user_rooms_changed,
)
from django.db.models import Prefetch
from apps.accounts.privacy import (
    DELETED_ACCOUNT_NAME,
    can_see_last_seen,
    can_see_online,
    can_see_photo,
    receipts_hidden_room_ids,
    viewer_from_context,
)
from .group_events import GROUP_EVENT_PREFIX
from .permissions import can_add_members, can_edit_group_info, send_message_error

from drf_spectacular.utils import (
    extend_schema,
    OpenApiResponse,
)


from .choices import RoomType, MessageType
from .models import (
    ChatRoom,
    Message,
    Participant,
    BlockedUser,
    VoiceNote,
    ChatClear,
    MessageReceipt,

)
from .models import StarredMessage, Attachment, Reaction
from .serializers import visible_messages_for_user, unread_messages_for_user, unread_mentions_for_user, with_message_relations, starred_ids_for
from .serializers import (
    ChatRoomDetailSerializer,
    ChatRoomSerializer,
    MessageSerializer,
    SendMessageSerializer,
    ParticipantSerializer,
    UploadMessageSerializer,
    ReactionSerializer,
    ReactMessageSerializer,
    PinMessageSerializer,
    MessageSearchSerializer,
    StarMessageSerializer,
    StarredMessageSerializer,
    ForwardMessageSerializer,

    BlockUserSerializer,
    UnblockUserSerializer,
    MuteChatSerializer,
    ArchiveChatSerializer,
    DeleteForMeSerializer,
    UserSerializer,
    UploadVoiceSerializer,
    CreatePrivateChatSerializer,
    CreateGroupSerializer,


)



def parse_id_list(value):
    """Accept [1, 2], ["1", "2"], "1,2" or '[1, 2]' and return unique positive ints."""
    import json as _json

    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            try:
                value = _json.loads(text)
            except ValueError:
                value = []
        else:
            value = [part for part in text.split(",") if part.strip()]
    if not isinstance(value, (list, tuple)):
        value = [value]
    flattened = []
    for item in value:
        if isinstance(item, str) and "," in item:
            flattened.extend(part for part in item.split(",") if part.strip())
        else:
            flattened.append(item)
    ids = []
    for item in flattened:
        if isinstance(item, bool):
            continue
        try:
            number = int(str(item).strip())
        except (TypeError, ValueError):
            continue
        if number > 0 and number not in ids:
            ids.append(number)
    return ids


def attach_link_preview(message, enabled=True):
    """
    Store the preview of the first link on a text message so recipients never
    fetch it themselves. ``enabled`` is false when the sender removed the
    preview in the composer. The composer already fetched it, so this is
    normally a cache hit.
    """
    from .link_preview import extract_first_url, get_link_preview

    if enabled is False or str(enabled).lower() in ("false", "0", "off"):
        return None
    if message.is_system or str(message.content or "").startswith("__WHATSUP_"):
        return None
    url = extract_first_url(message.content)
    if not url:
        return None
    preview = get_link_preview(url)
    if preview:
        message.link_preview = preview
        Message.all_objects.filter(pk=message.pk).update(link_preview=preview)
    return preview


def edit_window_open(message):
    """True while the sender may still edit ``message``."""
    limit = timedelta(minutes=settings.WHATSUP_EDIT_WINDOW_MINUTES)
    return timezone.now() - message.created_at <= limit


def delete_for_everyone_window_open(message):
    """True while the sender may still delete ``message`` for everyone."""
    limit = timedelta(hours=settings.WHATSUP_DELETE_FOR_EVERYONE_HOURS)
    return timezone.now() - message.created_at <= limit


def broadcast_reaction(message, user, emoji):
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(
        f"chat_{message.room_id}",
        {
            "type": "message.reaction",
            "message_id": message.id,
            "user_id": user.id,
            "sender_phone": user.phone_number,
            "emoji": emoji,
        },
    )


class MessageInfoAPIView(APIView):
    """Return real per-recipient delivery/read details for a message sent by the user."""
    permission_classes = [IsAuthenticated]

    def get(self, request, message_id):
        message = get_object_or_404(
            Message.objects.select_related("sender", "room"),
            pk=message_id,
            room__participants__user=request.user,
        )
        if message.sender_id != request.user.id:
            return Response({"detail": "Message info is available only for your own messages."}, status=status.HTTP_403_FORBIDDEN)

        # Backfill receipt rows for older messages only for people who belonged to
        # the room at send time. For historical private chats, preserve legacy
        # global receipt flags where they provide a reliable single-recipient state.
        participants_at_send = list(
            Participant.objects.filter(room_id=message.room_id, joined_at__lte=message.created_at)
            .exclude(user_id=message.sender_id)
            .select_related("user", "user__profile")
            .order_by("joined_at")
        )
        for participant in participants_at_send:
            defaults = {}
            if message.room.room_type == RoomType.PRIVATE:
                if message.is_delivered:
                    defaults["delivered_at"] = message.delivered_at or message.created_at
                if message.is_read:
                    defaults["read_at"] = message.read_at or message.updated_at
            MessageReceipt.objects.get_or_create(message=message, recipient=participant.user, defaults=defaults)

        # Use receipt rows as the source of truth. This also preserves the records
        # for people who were recipients when the message was sent but later left.
        receipt_rows = list(
            MessageReceipt.objects.filter(message=message)
            .exclude(recipient_id=message.sender_id)
            .select_related("recipient", "recipient__profile")
            .order_by("recipient__id")
        )
        participant_ids_at_send = {participant.user_id for participant in participants_at_send}
        # Older app versions may have created pending rows for members who joined
        # after a message. Hide those rows unless an actual delivery/read timestamp
        # proves that recipient received it.
        receipt_rows = [
            row for row in receipt_rows
            if row.recipient_id in participant_ids_at_send or row.delivered_at or row.read_at
        ]
        saved_names = dict(
            Contact.objects.filter(owner=request.user, contact_user_id__in=[row.recipient_id for row in receipt_rows])
            .values_list("contact_user_id", "name")
        )
        # Privacy: photo / presence per the recipient's settings; no "read"
        # in private chats where read receipts are off (groups always show).
        privacy = viewer_from_context({"request": request})
        hide_reads = message.room.room_type == RoomType.PRIVATE and bool(receipts_hidden_room_ids([message.room_id]))
        records = []
        for receipt in receipt_rows:
            user = receipt.recipient
            read_at = None if hide_reads else receipt.read_at
            delivered_at = receipt.delivered_at or (receipt.read_at if hide_reads else None)
            state = "read" if read_at else "delivered" if delivered_at else "pending"
            profile = getattr(user, "profile", None)
            if user.is_deleted:
                display_name = DELETED_ACCOUNT_NAME
            else:
                display_name = (saved_names.get(user.id) or "").strip() or (getattr(profile, "display_name", "") or "").strip() or user.phone_number
            show_photo = profile is not None and not user.is_deleted and can_see_photo(profile, user.id, privacy)
            show_online = profile is not None and not user.is_deleted and can_see_online(profile, user.id, privacy)
            show_last_seen = profile is not None and not user.is_deleted and can_see_last_seen(profile, user.id, privacy)
            records.append({
                "user_id": user.id,
                "name": display_name,
                "phone_number": "" if user.is_deleted else user.phone_number,
                "profile_picture": profile.profile_picture.url if show_photo and profile.profile_picture else None,
                "is_online": bool(profile.is_online) if show_online else False,
                "last_seen": profile.last_seen.isoformat() if show_last_seen and profile.last_seen else None,
                "state": state,
                "delivered_at": delivered_at.isoformat() if delivered_at else None,
                "read_at": read_at.isoformat() if read_at else None,
            })
        read_by = [row for row in records if row["state"] == "read"]
        delivered_to = [row for row in records if row["state"] in {"read", "delivered"}]
        pending = [row for row in records if row["state"] == "pending"]
        return Response({
            "message_id": message.id,
            "room_id": message.room_id,
            "room_type": message.room.room_type,
            "sent_at": message.created_at.isoformat(),
            "recipients": records,
            "read_by": read_by,
            "delivered_to": delivered_to,
            "pending": pending,
            "read_count": len(read_by),
            "delivered_count": len(delivered_to),
            "recipient_count": len(records),
        })


class ChatRoomInfoAPIView(APIView):
    """Lightweight, authenticated room metadata for contact/group info panels."""
    permission_classes = [IsAuthenticated]

    def get_room(self, request, pk):
        return get_object_or_404(
            ChatRoom.objects.select_related("created_by").prefetch_related("participants__user__profile"),
            pk=pk,
            participants__user=request.user,
            is_active=True,
        )

    def get(self, request, pk):
        room = self.get_room(request, pk)
        return Response(ChatRoomSerializer(room, context={"request": request}).data)

    def patch(self, request, pk):
        room = self.get_room(request, pk)
        if room.room_type != RoomType.GROUP:
            return Response({"detail": "Only group info can be edited here."}, status=status.HTTP_400_BAD_REQUEST)
        if not can_edit_group_info(request.user, room):
            return Response({"detail": "Only group admins can edit group info."}, status=status.HTTP_403_FORBIDDEN)

        changed_fields = []
        if "name" in request.data:
            name = str(request.data.get("name") or "").strip()
            if not name:
                return Response({"name": ["Group name is required."]}, status=status.HTTP_400_BAD_REQUEST)
            if len(name) > 150:
                return Response({"name": ["Group name must be 150 characters or fewer."]}, status=status.HTTP_400_BAD_REQUEST)
            room.name = name
            changed_fields.append("name")
        if "description" in request.data:
            description = str(request.data.get("description") or "").strip()
            if len(description) > 255:
                return Response({"description": ["Description must be 255 characters or fewer."]}, status=status.HTTP_400_BAD_REQUEST)
            room.description = description
            changed_fields.append("description")
        if request.data.get("remove_photo") in (True, "true", "1", "on") and room.photo:
            room.photo.delete(save=False)
            room.photo = None
            changed_fields.append("photo")
        elif request.FILES.get("photo"):
            photo = request.FILES["photo"]
            if not str(getattr(photo, "content_type", "")).lower().startswith("image/"):
                return Response({"photo": ["Upload an image file."]}, status=status.HTTP_400_BAD_REQUEST)
            if getattr(photo, "size", 0) > 5 * 1024 * 1024:
                return Response({"photo": ["Group photos must be 5 MB or smaller."]}, status=status.HTTP_400_BAD_REQUEST)
            room.photo = photo
            changed_fields.append("photo")
        if not changed_fields:
            return Response({"detail": "Provide a group name, description or photo to update."}, status=status.HTTP_400_BAD_REQUEST)
        changed_fields.append("updated_at")
        room.save(update_fields=list(dict.fromkeys(changed_fields)))
        broadcast_room_changed(room.id, "updated")
        return Response(ChatRoomSerializer(room, context={"request": request}).data)


class ChatRoomListAPIView(generics.ListAPIView):
    """
    Return all chat rooms of the authenticated user.
    """

    serializer_class = ChatRoomSerializer

    permission_classes = (
        permissions.IsAuthenticated,
    )

    @extend_schema(
        summary="List Chat Rooms",
        description="""
        Retrieve all chat rooms for the authenticated user.
        """,
        responses={
            200: ChatRoomSerializer(many=True),
        },
        tags=["Chat"],
    )

    def get_queryset(self):
        """
        Return chat rooms where the current user
        is a participant.

        Supports:
        ?archived=true   archived chats only
        ?archived=false  (default) non-archived chats only
        ?archived=all    every chat (each row carries ``is_archived``)

        The last visible message id and the unread count are annotated so the
        list is built without per-room queries.
        """

        archived = (
            self.request.query_params
            .get(
                "archived",
                "false",
            )
            .lower()
        )

        user = self.request.user

        hidden_from_list = ChatClear.objects.filter(
            room_id=OuterRef("pk"), user=user, hide_from_list=True
        )
        clear_time_for_message = Subquery(
            ChatClear.objects.filter(room_id=OuterRef("room_id"), user=user).values("cleared_at")[:1]
        )
        has_newer_message = Message.objects.filter(
            room_id=OuterRef("pk"),
            created_at__gt=clear_time_for_message,
            is_deleted=False,
        ).exclude(deleted_for_users__user=user)

        last_visible = (
            visible_messages_for_user(Message.objects.filter(room_id=OuterRef("pk")), user)
            .order_by("-created_at", "-id")
            .values("id")[:1]
        )
        unread_subquery = (
            unread_messages_for_user(Message.objects.filter(room_id=OuterRef("pk")), user)
            .order_by()
            .values("room_id")
            .annotate(total=Count("id"))
            .values("total")[:1]
        )

        membership = Participant.objects.filter(room_id=OuterRef("pk"), user=user)

        queryset = ChatRoom.objects.filter(
            participants__user=user,
            is_active=True,
        )
        if archived in ("true", "false"):
            queryset = queryset.filter(
                participants__user=user,
                participants__is_archived=(archived == "true"),
            )

        return (
            queryset
            .annotate(
                _hidden_from_list=Exists(hidden_from_list),
                _has_message_after_clear=Exists(has_newer_message),
                _last_message_id=Subquery(last_visible),
                _unread_count=Coalesce(Subquery(unread_subquery), 0),
                _unread_mention=Exists(
                    unread_mentions_for_user(Message.objects.filter(room_id=OuterRef("pk")), user)
                ),
                _is_pinned=Subquery(membership.values("is_pinned")[:1]),
                _pinned_at=Subquery(membership.values("pinned_at")[:1]),
            )
            .filter(Q(_hidden_from_list=False) | Q(_has_message_after_clear=True))
            .select_related("created_by")
            .prefetch_related("participants__user__profile")
            .distinct()
            .order_by(
                F("_is_pinned").desc(nulls_last=True),
                F("_pinned_at").desc(nulls_last=True),
                "-updated_at",
            )
        )

    def list(self, request, *args, **kwargs):
        rooms = list(self.get_queryset())
        message_ids = [room._last_message_id for room in rooms if room._last_message_id]
        last_messages = {
            message.id: message
            for message in with_message_relations(Message.objects.filter(id__in=message_ids))
        }
        starred_ids = starred_ids_for(request.user, message_ids)
        context = self.get_serializer_context()
        context["last_messages"] = last_messages
        context["starred_ids"] = starred_ids
        serializer = self.get_serializer_class()(rooms, many=True, context=context)
        return Response(serializer.data)

class ChatRoomDetailAPIView(generics.RetrieveAPIView):
    """
    Return details of a single chat room.
    """

    serializer_class = ChatRoomDetailSerializer

    permission_classes = (
        permissions.IsAuthenticated,
    )

    lookup_field = "pk"

    @extend_schema(
        summary="Chat Room Details",
        description="""
        Retrieve complete information about a chat room,
        including participants and metadata.
        """,
        responses={
        200: ChatRoomDetailSerializer,
        404: OpenApiResponse(description="Room not found."),
        },
        tags=["Chat"],

    )


    def get_queryset(self):
        """
        Users may only retrieve rooms
        they belong to.
        """

        return (
            ChatRoom.objects
            .filter(
                participants__user=self.request.user,
                is_active=True,
            )
            .select_related(
                "created_by",
            )
            .prefetch_related(
                "participants__user__profile",
                Prefetch(
                    "messages",
                    queryset=with_message_relations(
                        Message.objects
                        .filter(~Exists(ChatClear.objects.filter(
                            room_id=OuterRef("room_id"),
                            user=self.request.user,
                            cleared_at__gte=OuterRef("created_at"),
                        )))
                        .exclude(
                            deleted_for_users__user=self.request.user,
                        )
                    ),
                ),
            )
            .distinct()
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        pk = self.kwargs.get("pk")
        if pk is not None and self.request.user.is_authenticated:
            context["starred_ids"] = set(
                StarredMessage.objects.filter(user=self.request.user, message__room_id=pk)
                .values_list("message_id", flat=True)
            )
        return context
    

class MessageListAPIView(generics.ListAPIView):
    """
    Return messages for a chat room.
    """

    serializer_class = MessageSerializer

    permission_classes = (
        permissions.IsAuthenticated,
    )

    @extend_schema(
        summary="List Room Messages",
        description="""
        Retrieve all visible messages from a chat room.

        Deleted messages for the authenticated user
        are excluded.
        """,
        responses={
            200: MessageSerializer(many=True),
            403: OpenApiResponse(description="Not a participant."),
        },
        tags=["Chat"],
    )

    def get_queryset(self):
        room_id = self.kwargs["room_id"]

        clear_before_message = ChatClear.objects.filter(
            room_id=room_id,
            user=self.request.user,
            cleared_at__gte=OuterRef("created_at"),
        )

        return (
            Message.objects
            .filter(
                room_id=room_id,
                room__participants__user=self.request.user,
            )
            .filter(~Exists(clear_before_message))
            .exclude(
                deleted_for_users__user=self.request.user,
            )
            .order_by(
                "created_at",
                "id",
            )
        )

    def list(self, request, *args, **kwargs):
        """
        Without parameters the full history is returned (original contract).

        Optional windowing for long conversations:
        ``?limit=50`` returns the newest 50 messages,
        ``?before=<message_id>&limit=50`` returns the 50 messages older than
        that message. Results are always ordered oldest -> newest.
        """
        queryset = self.get_queryset()
        limit = request.query_params.get("limit")
        before = request.query_params.get("before")
        if before and str(before).isdigit():
            anchor = queryset.filter(pk=int(before)).values("created_at", "id").first()
            if anchor:
                queryset = queryset.filter(
                    Q(created_at__lt=anchor["created_at"])
                    | Q(created_at=anchor["created_at"], id__lt=anchor["id"])
                )
        if limit and str(limit).isdigit():
            size = max(1, min(200, int(limit)))
            newest = list(with_message_relations(queryset.order_by("-created_at", "-id")[:size]))
            messages = list(reversed(newest))
        else:
            messages = list(with_message_relations(queryset))
        ids = [message.id for message in messages]
        context = self.get_serializer_context()
        context["starred_ids"] = starred_ids_for(request.user, ids)
        serializer = self.get_serializer_class()(messages, many=True, context=context)
        return Response(serializer.data)

class SearchMessagesAPIView(APIView):
    """
    Search messages inside a room.
    """

    permission_classes = [
        IsAuthenticated,
    ]

    @extend_schema(
        summary="Search Messages",
        description="""
        Search messages within a chat room using a keyword.
        """,
        responses={
            200: MessageSearchSerializer(many=True),
        },
        tags=["Chat"],
    )


    def get(
        self,
        request,
        room_id,
    ):
        query = request.GET.get(
            "q",
            "",
        ).strip()

        if not query:
            return Response(
                {
                    "detail": "Search query is required."
                },
                status=400,
            )

        room = get_object_or_404(
            ChatRoom,
            pk=room_id,
        )

        if not room.participants.filter(
            user=request.user,
        ).exists():
            return Response(
                {
                    "detail": "You are not a participant."
                },
                status=403,
            )


        messages = (
            Message.objects.filter(
                room=room,
                is_deleted=False,
            )
            .select_related(
                "sender__profile",
                "reply_to__sender",
            )
            .prefetch_related(
                "attachments",
                "reply_to__attachments",
            )
            .exclude(
                deleted_for_users__user=request.user,
            )
            .filter(~Exists(ChatClear.objects.filter(
                room_id=OuterRef("room_id"),
                user=request.user,
                cleared_at__gte=OuterRef("created_at"),
            )))
            .filter(
                Q(content__icontains=query)
                |
                Q(attachments__file_name__icontains=query)
                |
                Q(voice_note__audio__icontains=query)
            )
            .distinct()
            .order_by("-created_at")
        )

        serializer = MessageSearchSerializer(
            messages,
            many=True,
        )

        return Response(serializer.data)
    

def is_private_chat_blocked(
    room,
    current_user,
):
    """
    Return True when the *sender* has blocked the other member of a private
    chat (they must unblock first). When the other person blocked the sender
    the message is accepted but hidden from them (see
    ``apps.chat.utils.hide_from_blockers``), exactly like WhatsApp.
    """
    from .utils import sender_has_blocked_peer

    return sender_has_blocked_peer(room, current_user)


class SendMessageAPIView(generics.CreateAPIView):
    """
    Send a new message to a chat room.
    """

    serializer_class = SendMessageSerializer

    permission_classes = (
        permissions.IsAuthenticated,
    )

    @extend_schema(
        summary="Send Message",
        request=SendMessageSerializer,
        description="""
        Send a new message to a chat room.

        Supports:
        • Text
        • Reply
        • Forward
        • Attachments
        • Voice Notes
        """,
        responses={
            201: MessageSerializer,
            400: OpenApiResponse(description="Validation error."),
            403: OpenApiResponse(description="Not a participant."),
        },
        tags=["Chat"],
    )


    def perform_create(self, serializer):
        """
        Save the message with the authenticated user
        as the sender.
        """

        serializer.save()

    def create(self, request, *args, **kwargs):
        """
        Return the newly created message.
        """

        serializer = self.get_serializer(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        room = serializer.validated_data["room"]

        denied = send_message_error(request.user, room)
        if denied:
            return Response({"detail": denied}, status=status.HTTP_403_FORBIDDEN)

        if is_private_chat_blocked(
            room,
            request.user,
        ):
            return Response(
                {
                    "detail":
                    "Unblock this contact to send a message.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        message = serializer.save()

        if not getattr(message, "_was_duplicate", False):
            if message.message_type == MessageType.TEXT:
                attach_link_preview(message, request.data.get("link_preview", True))
            message = get_message_with_relations(message.id)
            broadcast_message(
                message,
                request,
            )

        return Response(
            {
                "message": "Message sent successfully.",
                "data": MessageSerializer(
                    message,
                    context=self.get_serializer_context(),
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )
    


class UploadMessageAPIView(APIView):
    """
    Upload a file and create a chat message.
    """

    permission_classes = [IsAuthenticated]

    parser_classes = (
        MultiPartParser,
        FormParser,
    )

    @extend_schema(
        summary="Upload Attachment",
        request = UploadMessageSerializer,
        description="""
        Upload one or more files and send them as a chat message.

        Supported:
        • Images
        • Videos
        • Documents
        • Audio
        """,
        responses={
            201: MessageSerializer,
            400: OpenApiResponse(description="Invalid upload."),
        },
        tags=["Chat"],
    )


    def post(
        self,
        request,
    ):
        serializer = UploadMessageSerializer(
            data=request.data,
            context={
                "request": request,
            },
        )

        serializer.is_valid(
            raise_exception=True,
        )

        room = serializer.validated_data["room"]

        denied = send_message_error(request.user, room)
        if denied:
            return Response({"detail": denied}, status=status.HTTP_403_FORBIDDEN)

        if is_private_chat_blocked(
            room,
            request.user,
        ):
            return Response(
                {
                    "detail":
                    "Unblock this contact to send a message.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        message = serializer.save()

        if not getattr(message, "_was_duplicate", False):
            message = get_message_with_relations(message.id)
            broadcast_message(
                message,
                request,
            )

        return Response(
            {
                "message": (
                    "File uploaded successfully."
                ),
                "data": MessageSerializer(
                    message,
                    context={
                        "request": request,
                    },
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )
    

class UploadVoiceAPIView(APIView):
    """
    Upload a voice message.
    """

    permission_classes = (
        permissions.IsAuthenticated,
    )

    parser_classes = (
        MultiPartParser,
        FormParser,
    )

    @extend_schema(
        summary="Send Voice Note",
        request=UploadVoiceSerializer,
        description="""
        Upload and send a voice note.

        Accepts an audio file, duration and optional waveform.
        """,
        responses={
            201: MessageSerializer,
        },
        tags=["Chat"],
    )


    def post(
        self,
        request,
    ):

        room = get_object_or_404(
            ChatRoom,
            pk=request.data.get("room"),
        )

        denied = send_message_error(request.user, room)
        if denied:
            return Response({"detail": denied}, status=status.HTTP_403_FORBIDDEN)

        if is_private_chat_blocked(
            room,
            request.user,
        ):
            return Response(
                {
                    "detail": "Unblock this contact to send a message.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        
        if not room.participants.filter(
            user=request.user,
        ).exists():
            return Response(
                {
                    "detail": "You are not a participant of this room.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        
        audio = request.FILES.get("audio")

        if not audio:
            return Response(
                {
                    "detail": "Audio file is required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if getattr(audio, "size", 0) > 25 * 1024 * 1024:
            return Response(
                {"detail": "Voice messages must be 25 MB or smaller."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        content_type = str(getattr(audio, "content_type", "") or "").lower()
        if content_type and not content_type.startswith("audio/"):
            return Response(
                {"detail": "Upload an audio file for a voice message."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        try:
            duration = int(
                request.data.get(
                    "duration",
                    0,
                )
            )
        except (TypeError, ValueError):

            return Response(
                {
                    "detail":
                    "Invalid duration.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if duration <= 0:

            return Response(
                {
                    "detail":
                    "Duration must be greater than zero.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if duration > 600:
            return Response(
                {"detail": "Voice messages cannot exceed 10 minutes."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        waveform = request.data.get("waveform", [])
        if isinstance(waveform, str):
            import json
            try:
                waveform = json.loads(waveform) if waveform.strip() else []
            except (TypeError, ValueError):
                waveform = []
        if not isinstance(waveform, list):
            waveform = []
        waveform = [max(1, min(100, int(value))) for value in waveform[:96] if str(value).lstrip("-").isdigit()]
        view_once = str(request.data.get("view_once", "")).lower() in ("1", "true", "yes", "on")

        with transaction.atomic():

            message = Message.objects.create(
                room=room,
                sender=request.user,
                message_type=MessageType.VOICE,
                content="",
                is_view_once=view_once,
            )

            VoiceNote.objects.create(
                message=message,
                audio=audio,
                duration=duration,
                waveform=waveform,
            )

            message = get_message_with_relations(
                message.id,
            )

            broadcast_message(
                message,
                request,
            )

        serializer = MessageSerializer(
            message,
            context={
                "request": request,
            },
        )

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
        )


class ForwardMessageAPIView(APIView):
    """
    Forward a message to another room.
    """

    permission_classes = [
        IsAuthenticated,
    ]

    @extend_schema(
        summary="Forward Message",
        request = ForwardMessageSerializer,
        description="""
        Forward one or multiple messages to another chat room.

        Supports:
        • Text
        • Attachments
        • Voice Notes
        """,
        responses={
            201: MessageSerializer,
            404: OpenApiResponse(description="Message not found."),
        },
        tags=["Chat"],
    )


    def post(
        self,
        request,
    ):
        serializer = ForwardMessageSerializer(
            data=request.data,
            context={
                "request": request,
            },
        )

        serializer.is_valid(
            raise_exception=True,
        )

        room = serializer.validated_data["room"]

        denied = send_message_error(request.user, room)
        if denied:
            return Response({"detail": denied}, status=status.HTTP_403_FORBIDDEN)

        if is_private_chat_blocked(
            room,
            request.user,
        ):
            return Response(
                {
                    "detail":
                    "Unblock this contact to send a message.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        message = get_message_with_relations(serializer.save().id)

        broadcast_message(
            message,
            request,
        )

        return Response(
            {
                "message": (
                    "Message forwarded successfully."
                ),
                "data": MessageSerializer(
                    message,
                    context={
                        "request": request,
                    },
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )
    

class ReactMessageAPIView(APIView):
    """
    Add or update a reaction
    to a message.
    """


    @extend_schema(
        summary="React to Message",
        request = ReactMessageSerializer,
        description="""
        Add, update or remove a reaction on a message.
        """,
        responses={
            200: OpenApiResponse(description="Reaction updated."),
        },
        tags=["Chat"],
    )

    def post(
        self,
        request,
    ):
        # An empty emoji removes the user's reaction (WhatsApp "tap again to remove").
        if str(request.data.get("emoji", "")).strip() == "" and request.data.get("message"):
            message = get_object_or_404(
                Message.objects.filter(room__participants__user=request.user, is_deleted=False).distinct(),
                pk=request.data.get("message"),
            )
            Reaction.objects.filter(message=message, user=request.user).delete()
            broadcast_reaction(message, request.user, "")
            return Response({"message": "Reaction removed."}, status=status.HTTP_200_OK)

        serializer = ReactMessageSerializer(
            data=request.data,
            context={
                "request": request,
            },
        )

        serializer.is_valid(
            raise_exception=True,
        )

        reaction = serializer.save()
        broadcast_reaction(reaction.message, request.user, reaction.emoji)

        return Response(
            {
                "message": (
                    "Reaction updated successfully."
                ),
                "data": ReactionSerializer(
                    reaction,
                ).data,
            },
            status=status.HTTP_200_OK,
        )

class PinMessageAPIView(APIView):
    """
    Pin or unpin a message.
    """

    @extend_schema(
        summary="Pin Message",
        request = PinMessageSerializer,
        description="""
        Pin or unpin a message inside the chat room.
        """,
        responses={
            200: OpenApiResponse(description="Pin updated."),
        },
        tags=["Chat"],
    )

    def post(
        self,
        request,
    ):
        serializer = PinMessageSerializer(
            data=request.data,
            context={
                "request": request,
            },
        )

        serializer.is_valid(
            raise_exception=True,
        )

        message = serializer.save()

        channel_layer = get_channel_layer()
        if channel_layer is not None:
            async_to_sync(channel_layer.group_send)(
                f"chat_{message.room_id}",
                {"type": "message.pinned", "message_id": message.id, "is_pinned": message.is_pinned},
            )
            for unpinned_id in getattr(serializer, "unpinned_ids", ()):
                async_to_sync(channel_layer.group_send)(
                    f"chat_{message.room_id}",
                    {"type": "message.pinned", "message_id": unpinned_id, "is_pinned": False},
                )

        return Response(
            {
                "message": "Message updated successfully.",
                "data": MessageSerializer(
                    message,
                    context={"request": request},
                ).data,
            },
            status=status.HTTP_200_OK,
        )

class StarMessageAPIView(APIView):
    """
    Star or unstar a message.
    """

    permission_classes = [
        IsAuthenticated,
    ]

    
    @extend_schema(
        summary="Star Message",
        request = StarMessageSerializer,
        description="""
        Add or remove a message from the authenticated user's starred messages.
        """,
        responses={
            200: OpenApiResponse(description="Star status updated."),
        },
        tags=["Chat"],
    )

    def post(
        self,
        request,
    ):
        serializer = StarMessageSerializer(
            data=request.data,
            context={
                "request": request,
            },
        )

        serializer.is_valid(
            raise_exception=True,
        )

        starred = serializer.save()

        if starred:
            return Response(
                {
                    "message": (
                        "Message starred successfully."
                    ),
                    "data": StarredMessageSerializer(
                        starred,
                    ).data,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "message": (
                    "Message unstarred successfully."
                ),
            },
            status=status.HTTP_200_OK,
        )
    
class StarredMessagesAPIView(APIView):
    """
    Return all starred messages
    of the authenticated user.
    """

    permission_classes = [
        IsAuthenticated,
    ]


    @extend_schema(
        summary="List Starred Messages",
        description="""
        Retrieve all messages starred by the authenticated user.
        """,
        responses={
            200: MessageSerializer(many=True),
        },
        tags=["Chat"],
    )


    def get(
        self,
        request,
    ):
        messages = (
            # Only messages still visible to me (not deleted, not hidden by
            # "delete for me" or a cleared chat) so tapping one can open it.
            visible_messages_for_user(
                Message.objects.filter(
                    starred_by__user=request.user,
                    is_deleted=False,
                ),
                request.user,
            )
            .order_by(
                "-created_at",
            )
        )
        messages = list(with_message_relations(messages))

        serializer = MessageSerializer(
            messages,
            many=True,
            context={
                "request": request,
                # every message here is starred by definition
                "starred_ids": {message.id for message in messages},
            },
        )

        return Response(
            serializer.data,
        )
    

class MuteChatAPIView(APIView):
    """
    Mute or unmute a chat.
    """

    permission_classes = [
        IsAuthenticated,
    ]


    @extend_schema(
        summary="Mute Chat",
        request = MuteChatSerializer,
        description="""
        Mute or unmute notifications for a chat.

        Supported durations:

        • 8 hours

        • 1 week

        • Always

        • Off
        """,
        responses={
            200: OpenApiResponse(description="Mute status updated."),
        },
        tags=["Chat"],
    )

    def post(
        self,
        request,
    ):
        serializer = MuteChatSerializer(
            data=request.data,
            context={
                "request": request,
            },
        )

        serializer.is_valid(
            raise_exception=True,
        )

        room = serializer.validated_data["room"]
        duration = serializer.validated_data["duration"]

        participant = Participant.objects.get(
            room=room,
            user=request.user,
        )

        if duration == "off":

            participant.is_muted = False
            participant.muted_until = None

        else:

            participant.is_muted = True

            if duration == "8h":
                participant.muted_until = (
                    timezone.now()
                    + timedelta(hours=8)
                )

            elif duration == "1w":
                participant.muted_until = (
                    timezone.now()
                    + timedelta(days=7)
                )

            elif duration == "always":
                participant.muted_until = None

        participant.save(
            update_fields=[
                "is_muted",
                "muted_until",
            ]
        )
        notify_user_rooms_changed(request.user.id, "muted", participant.room_id)

        return Response(
            {
                "message": "Chat updated successfully.",
                "is_muted": participant.is_muted,
                "muted_until": participant.muted_until,
            }
        )
    

class ArchiveChatAPIView(APIView):
    """
    Archive or unarchive a chat.
    """

    permission_classes = [
        IsAuthenticated,
    ]


    @extend_schema(
        summary="Archive Chat",
        request = ArchiveChatSerializer,
        description="""
        Archive or unarchive a chat for the authenticated user.
        """,
        responses={
            200: OpenApiResponse(description="Archive updated."),
        },
        tags=["Chat"],
    )

    def post(
        self,
        request,
    ):
        # Bulk form: {"rooms": [1, 2, 3], "is_archived": true}
        if request.data.get("rooms") is not None:
            room_ids = parse_id_list(request.data.get("rooms"))
            is_archived = str(request.data.get("is_archived", "true")).lower() in ("true", "1", "on")
            if not room_ids:
                return Response({"rooms": ["Select at least one chat."]}, status=status.HTTP_400_BAD_REQUEST)
            updated = Participant.objects.filter(
                user=request.user,
                room_id__in=room_ids,
            ).update(
                is_archived=is_archived,
                # Archived chats are never pinned (WhatsApp behaviour).
                **({"is_pinned": False, "pinned_at": None} if is_archived else {}),
            )
            notify_user_rooms_changed(request.user.id, "archived")
            return Response({"message": "Chats updated successfully.", "updated": updated, "is_archived": is_archived})

        serializer = ArchiveChatSerializer(
            data=request.data,
            context={
                "request": request,
            },
        )

        serializer.is_valid(
            raise_exception=True,
        )

        participant = Participant.objects.get(
            room=serializer.validated_data["room"],
            user=request.user,
        )

        participant.is_archived = serializer.validated_data[
            "is_archived"
        ]
        update_fields = ["is_archived"]
        if participant.is_archived and participant.is_pinned:
            participant.is_pinned = False
            participant.pinned_at = None
            update_fields += ["is_pinned", "pinned_at"]

        participant.save(
            update_fields=update_fields
        )
        notify_user_rooms_changed(request.user.id, "archived", participant.room_id)

        return Response(
            {
                "message": "Chat updated successfully.",
                "is_archived": participant.is_archived,
            }
        )

class CreatePrivateChatAPIView(APIView):
    """
    Create or return an existing private chat.
    """

    permission_classes = (
        permissions.IsAuthenticated,
    )

    @extend_schema(
        summary="Create Private Chat",
        request=CreatePrivateChatSerializer,
        description="""
        Create or retrieve a private chat room between two users.

        If a private room already exists, the existing room is returned.
        """,
        responses={
            201: ChatRoomSerializer,
            400: OpenApiResponse(description="Invalid request."),
            403: OpenApiResponse(description="Permission denied."),
        },
        tags=["Chat"],
    )

    def post(self, request):
        other_user_id = request.data.get(
            "user_id",
        )

        if not other_user_id:
            return Response(
                {
                    "error": "user_id is required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            other_user = User.objects.get(
                pk=other_user_id,
                is_active=True,
            )
        except User.DoesNotExist:
            return Response(
                {
                    "error": "User not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if other_user == request.user:
            return Response(
                {
                    "error": "You cannot create a chat with yourself.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        room = (
            ChatRoom.objects.filter(
                room_type=RoomType.PRIVATE,
                participants__user=request.user,
            )
            .filter(
                participants__user=other_user,
            )
            .distinct()
            .first()
        )

        if room:
            return Response(
                ChatRoomSerializer(
                    room,
                    context={
                        "request": request,
                    },
                ).data,
                status=status.HTTP_200_OK,
            )

        with transaction.atomic():

            room = ChatRoom.objects.create(
                room_type=RoomType.PRIVATE,
                created_by=request.user,
            )

            Participant.objects.create(
                room=room,
                user=request.user,
            )

            Participant.objects.create(
                room=room,
                user=other_user,
            )

        return Response(
            ChatRoomSerializer(
                room,
                context={
                    "request": request,
                },
            ).data,
            status=status.HTTP_201_CREATED,
        )
    

class CreateGroupChatAPIView(APIView,):
    """
    Create a new group chat.
    """

    permission_classes = (
        permissions.IsAuthenticated,
    )

    @extend_schema(
        summary="Create Group Chat",
        request=CreateGroupSerializer,
        description="""
        Create a new group chat with multiple participants.

        The authenticated user becomes the group creator.
        """,
        responses={
            201: ChatRoomSerializer,
            400: OpenApiResponse(description="Validation error."),
        },
        tags=["Chat"],
    )

    def post(self, request):
        name = str(request.data.get("name") or "").strip()

        if not name:
            return Response(
                {
                    "error": "Group name is required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(name) > 150:
            return Response({"name": ["Group name must be 150 characters or fewer."]}, status=status.HTTP_400_BAD_REQUEST)

        photo = request.FILES.get("photo")
        if photo is not None:
            if not str(getattr(photo, "content_type", "")).lower().startswith("image/"):
                return Response({"photo": ["Upload an image file."]}, status=status.HTTP_400_BAD_REQUEST)
            if getattr(photo, "size", 0) > 5 * 1024 * 1024:
                return Response({"photo": ["Group photos must be 5 MB or smaller."]}, status=status.HTTP_400_BAD_REQUEST)

        member_ids = parse_id_list(
            request.data.getlist("participants") if hasattr(request.data, "getlist") else request.data.get("participants")
        )
        members = list(
            User.objects.filter(pk__in=member_ids, is_active=True).exclude(pk=request.user.pk)
        )

        with transaction.atomic():
            room = ChatRoom.objects.create(
                name=name,
                room_type=RoomType.GROUP,
                description=str(request.data.get("description") or "")[:255],
                photo=photo,
                created_by=request.user,
            )

            Participant.objects.create(
                room=room,
                user=request.user,
                is_admin=True,
            )
            for member in members:
                Participant.objects.get_or_create(room=room, user=member)

        broadcast_room_changed(room.id, "created")

        room = ChatRoom.objects.prefetch_related("participants__user__profile").get(pk=room.pk)
        return Response(
            ChatRoomSerializer(
                room,
                context={
                    "request": request,
                },
            ).data,
            status=status.HTTP_201_CREATED,
        )

class UpdateMessageAPIView(generics.UpdateAPIView):
    """
    Update a message sent by the authenticated user.
    """

    serializer_class = SendMessageSerializer

    permission_classes = (
        permissions.IsAuthenticated,
    )

    http_method_names = [
        "patch",
    ]

    @extend_schema(
        summary="Edit Message",
        request=SendMessageSerializer,
        description="""
        Update the content of a previously sent message.

        Only the sender can edit their own message.
        """,
        responses={
            200: MessageSerializer,
            403: OpenApiResponse(description="Permission denied."),
            404: OpenApiResponse(description="Message not found."),
        },
        tags=["Chat"],
    )

    def get_queryset(self):
        """
        Return editable messages belonging to
        the authenticated user.
        """

        return Message.objects.filter(
            sender=self.request.user,
            is_deleted=False,
        )

    def perform_update(self, serializer):
        """
        Mark the message as edited.
        """

        serializer.save(
            is_edited=True,
        )

    def update(self, request, *args, **kwargs):
        message = self.get_object()

        if message.message_type != MessageType.TEXT or str(message.content or "").startswith("__WHATSUP_"):
            return Response(
                {"detail": "Only text messages can be edited."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not edit_window_open(message):
            return Response(
                {"detail": f"Messages can only be edited within {settings.WHATSUP_EDIT_WINDOW_MINUTES} minutes of sending."},
                status=status.HTTP_403_FORBIDDEN,
            )

        content = request.data.get("content")
        if not isinstance(content, str) or not content.strip():
            return Response(
                {"content": ["Message cannot be empty."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        message.content = content.strip()
        message.is_edited = True
        message.save(update_fields=["content", "is_edited", "updated_at"])

        channel_layer = get_channel_layer()
        if channel_layer is not None:
            async_to_sync(channel_layer.group_send)(
                f"chat_{message.room_id}",
                {
                    "type": "message.edited",
                    "message_id": message.id,
                    "content": message.content,
                    "is_edited": True,
                },
            )
        broadcast_room_changed(message.room_id, "message_edited")

        message = get_message_with_relations(message.id)
        return Response(
            {
                "message": "Message updated successfully.",
                "data": MessageSerializer(message, context={"request": request}).data,
            },
            status=status.HTTP_200_OK,
        )

class DeleteMessageAPIView(APIView):
    """
    Soft delete a message.
    """

    permission_classes = (
        permissions.IsAuthenticated,
    )


    @extend_schema(
        summary="Delete Message",
        request=None,
        description="""
        Delete a message for everyone in the chat.

        Only the sender can perform this action.
        """,
        responses={
            200: OpenApiResponse(description="Message deleted."),
            403: OpenApiResponse(description="Permission denied."),
        },
        tags=["Chat"],
    )


    def delete(self, request, pk):
        with transaction.atomic():
            try:
                message = Message.objects.select_for_update().exclude(
                    content__startswith=GROUP_EVENT_PREFIX,
                ).get(
                    pk=pk,
                    sender=request.user,
                    room__participants__user=request.user,
                    is_deleted=False,
                )
            except Message.DoesNotExist:
                return Response(
                    {"detail": "Message not found or you do not have permission to delete it."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if not delete_for_everyone_window_open(message):
                return Response(
                    {"detail": f"Messages can only be deleted for everyone within {settings.WHATSUP_DELETE_FOR_EVERYONE_HOURS} hours of sending."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            soft_delete_messages_for_everyone([message])

        return Response(
            {"message": "Message deleted for everyone successfully.", "message_id": message.id},
            status=status.HTTP_200_OK,
        )
    

class DeleteForMeAPIView(APIView):
    """
    Delete a message only for
    the authenticated user.
    """

    permission_classes = [
        IsAuthenticated,
    ]


    @extend_schema(
        summary="Delete Message For Me",
        request = DeleteForMeSerializer,
        description="""
        Hide a message only for the authenticated user.

        Other participants continue to see it.
        """,
        responses={
            200: OpenApiResponse(description="Message hidden."),
        },
        tags=["Chat"],
    )

    def post(
        self,
        request,
    ):
        serializer = DeleteForMeSerializer(
            data=request.data,
            context={
                "request": request,
            },
        )

        serializer.is_valid(
            raise_exception=True,
        )

        message = serializer.save()

        return Response(
            {
                "message": (
                    "Message deleted for you successfully."
                ),
                "message_id": message.id,
            },
            status=status.HTTP_200_OK,
        )
    

class DeleteChatAPIView(APIView):
    """Clear a conversation for the authenticated participant only."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Delete chat for current user",
        description="Hides the room from the current user's list and hides messages sent before deletion. New messages make the room reappear.",
        request=None,
        responses={200: OpenApiResponse(description="Chat cleared for this user.")},
        tags=["Chat"],
    )
    def delete(self, request, pk):
        room = get_object_or_404(
            ChatRoom.objects.filter(participants__user=request.user, is_active=True), pk=pk
        )
        ChatClear.objects.update_or_create(
            room=room, user=request.user,
            defaults={"cleared_at": timezone.now(), "hide_from_list": True},
        )
        return Response({"message": "Chat removed from your list until a new message arrives.", "room_id": room.id}, status=200)


class ClearChatAPIView(APIView):
    """Hide existing messages but keep the conversation in the user's list."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Clear chat history for current user",
        description="Hides messages sent before the clear timestamp from this user while keeping the room visible in the chat list.",
        request=None,
        responses={200: OpenApiResponse(description="Chat history cleared for this user.")},
        tags=["Chat"],
    )
    def post(self, request, pk):
        room = get_object_or_404(
            ChatRoom.objects.filter(participants__user=request.user, is_active=True), pk=pk
        )
        ChatClear.objects.update_or_create(
            room=room,
            user=request.user,
            defaults={"cleared_at": timezone.now(), "hide_from_list": False},
        )
        return Response({"message": "Chat history cleared. The conversation remains in your list.", "room_id": room.id}, status=200)


class DeleteMessagesForEveryoneAPIView(APIView):
    """Atomically soft-delete multiple messages authored by the caller."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Bulk delete messages for everyone",
        description="All IDs must belong to the supplied room and be authored by the authenticated user. All messages are validated before any update is committed.",
        request={"type": "object", "properties": {
            "room": {"type": "integer"},
            "messages": {"type": "array", "items": {"type": "integer"}, "minItems": 1, "maxItems": 100},
        }, "required": ["room", "messages"]},
        responses={200: OpenApiResponse(description="Messages deleted and broadcast to connected participants.")},
        tags=["Chat"],
    )
    def post(self, request):
        raw_room_id = request.data.get("room")
        raw_ids = request.data.get("messages")
        if isinstance(raw_ids, str):
            try:
                import json
                raw_ids = json.loads(raw_ids)
            except (ValueError, TypeError):
                raw_ids = None
        if isinstance(raw_room_id, bool) or not str(raw_room_id or "").isdigit():
            return Response({"room": "A valid room ID is required."}, status=400)
        if not isinstance(raw_ids, list) or not raw_ids or len(raw_ids) > 100:
            return Response({"messages": "Provide between 1 and 100 message IDs."}, status=400)
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, str))
            or (isinstance(value, str) and not value.isdigit())
            for value in raw_ids
        ):
            return Response({"messages": "Every message ID must be a positive integer."}, status=400)
        ids = [int(value) for value in raw_ids]
        if any(value <= 0 for value in ids) or len(set(ids)) != len(ids):
            return Response({"messages": "IDs must be unique positive integers."}, status=400)

        room = get_object_or_404(
            ChatRoom.objects.filter(participants__user=request.user, is_active=True),
            pk=int(raw_room_id),
        )
        with transaction.atomic():
            messages = list(
                Message.objects.select_for_update().filter(
                    id__in=ids, room=room, sender=request.user, is_deleted=False,
                ).exclude(content__startswith=GROUP_EVENT_PREFIX).order_by("id")
            )
            if len(messages) != len(ids):
                return Response({
                    "detail": "Every selected message must exist in this chat, belong to you, and not already be deleted. No messages were changed."
                }, status=403)
            if any(not delete_for_everyone_window_open(message) for message in messages):
                return Response({
                    "detail": f"Some selected messages are older than {settings.WHATSUP_DELETE_FOR_EVERYONE_HOURS} hours and can only be deleted for you. No messages were changed."
                }, status=403)
            soft_delete_messages_for_everyone(messages)
        return Response({"message": "Messages deleted for everyone.", "room_id": room.id, "message_ids": ids}, status=200)


class DeleteMessagesForMeAPIView(APIView):
    """Atomically hide multiple room messages from the current user only."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        raw_ids = request.data.get("messages")
        if isinstance(raw_ids, str):
            try:
                import json
                raw_ids = json.loads(raw_ids)
            except (ValueError, TypeError):
                raw_ids = None
        if not isinstance(raw_ids, list) or not raw_ids or len(raw_ids) > 100:
            return Response({"messages": "Provide between 1 and 100 message IDs."}, status=400)
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, str))
            or (isinstance(value, str) and not value.isdigit())
            for value in raw_ids
        ):
            return Response({"messages": "Every message ID must be a positive integer."}, status=400)
        ids = [int(value) for value in raw_ids]
        if any(value <= 0 for value in ids) or len(set(ids)) != len(ids):
            return Response({"messages": "IDs must be unique positive integers."}, status=400)
        from .models import DeletedMessage
        with transaction.atomic():
            # No DISTINCT here: PostgreSQL rejects "SELECT DISTINCT ... FOR
            # UPDATE". Filtering rooms through a subquery avoids duplicate rows.
            # Deleted-for-everyone placeholders can also be removed for me.
            my_rooms = Participant.objects.filter(user=request.user).values("room_id")
            messages = list(Message.objects.select_for_update().filter(
                id__in=ids,
                room_id__in=my_rooms,
            ))
            if len(messages) != len(ids):
                return Response({"detail": "A selected message was not found or is not in one of your chats. No messages were changed."}, status=404)
            DeletedMessage.objects.bulk_create(
                [DeletedMessage(message=message, user=request.user) for message in messages],
                ignore_conflicts=True,
            )
        return Response({"message": "Messages deleted for you.", "message_ids": ids}, status=200)


class BlockUserAPIView(APIView):

    permission_classes = [
        IsAuthenticated,
    ]


    @extend_schema(
        summary="Block User",
        request = BlockUserSerializer,
        description="""
        Block another user.

        Blocked users cannot send messages
        in private chats.
        """,
        responses={
            200: OpenApiResponse(description="User blocked."),
        },
        tags=["Chat"],
    )


    def post(
        self,
        request,
    ):
        serializer = BlockUserSerializer(
            data=request.data,
            context={
                "request": request,
            },
        )

        serializer.is_valid(
            raise_exception=True,
        )

        blocked = serializer.save()

        return Response(
            {
                "message":
                "User blocked successfully.",
                "blocked_user":
                blocked.blocked_user.id,
            }
        )
    

class UnblockUserAPIView(APIView):

    permission_classes = [
        IsAuthenticated,
    ]


    @extend_schema(
        summary="Unblock User",
        request=UnblockUserSerializer,
        description="""
        Remove a previously blocked user.
        """,
        responses={
            200: UserSerializer(many=True),
        },
        tags=["Chat"],
    )

    def post(
        self,
        request,
    ):
        serializer = UnblockUserSerializer(
            data=request.data,
            context={
                "request": request,
            },
        )

        serializer.is_valid(
            raise_exception=True,
        )

        serializer.save()

        return Response(
            {
                "message":
                "User unblocked successfully.",
            }
        )
    

class BlockedUsersAPIView(APIView):

    permission_classes = [
        IsAuthenticated,
    ]


    @extend_schema(
        summary="Blocked Users",
        description="""
        Retrieve all users blocked by the authenticated user.
        """,
        responses={
            200: UserSerializer(many=True),
        },
        tags=["Chat"],
    )

    def get(
        self,
        request,
    ):
    

        blocked = BlockedUser.objects.filter(
            blocked_by=request.user,
        ).select_related(
            "blocked_user",
        )

        data = [
            {
                "id": item.blocked_user.id,
                "phone_number":
                item.blocked_user.phone_number,
            }
            for item in blocked
        ]

        return Response(data)
    


class AddParticipantAPIView(APIView):
    """
    Add a participant to a group.
    """

    permission_classes = (
        permissions.IsAuthenticated,
    )


    @extend_schema(
        summary="Add Group Participant",
        request=ParticipantSerializer,
        description="""
        Add a new participant to a group chat.

        Only group administrators can perform this action.
        """,
        responses={
            201: ParticipantSerializer,
            403: OpenApiResponse(description="Not a group admin."),
        },
        tags=["Chat"],
    )



    def post(self, request, room_id):
        try:
            room = ChatRoom.objects.get(
                pk=room_id,
                room_type=RoomType.GROUP,
            )
        except ChatRoom.DoesNotExist:
            return Response(
                {
                    "error": "Group not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if not can_add_members(request.user, room):
            return Response(
                {
                    "error": "Only group admins can add participants.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Accept a single ``user_id`` (original contract) or a ``user_ids`` list.
        raw_many = request.data.get("user_ids")
        if raw_many is not None:
            user_ids = parse_id_list(raw_many)
            if not user_ids:
                return Response({"error": "Select at least one contact."}, status=status.HTTP_400_BAD_REQUEST)
            users = list(User.objects.filter(pk__in=user_ids, is_active=True))
            added = []
            for user in users:
                participant, created = Participant.objects.get_or_create(room=room, user=user)
                if created:
                    added.append(participant)
            if added:
                broadcast_room_changed(room.id, "participant_added")
            return Response(
                ParticipantSerializer(added, many=True).data,
                status=status.HTTP_201_CREATED,
            )

        user_id = request.data.get(
            "user_id",
        )

        try:
            user = User.objects.get(
                pk=user_id,
                is_active=True,
            )
        except (User.DoesNotExist, ValueError, TypeError):
            return Response(
                {
                    "error": "User not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        participant, created = Participant.objects.get_or_create(
            room=room,
            user=user,
        )

        if not created:
            return Response(
                {
                    "error": "User is already a participant.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        broadcast_room_changed(room.id, "participant_added")

        return Response(
            ParticipantSerializer(
                participant,
            ).data,
            status=status.HTTP_201_CREATED,
        )

class RemoveParticipantAPIView(APIView):
    """
    Remove a participant from a group.
    """

    permission_classes = (
        permissions.IsAuthenticated,
    )


    @extend_schema(
        summary="Remove Group Participant",
        request=None,
        description="""
        Remove a participant from a group.

        Only group administrators can perform this action.
        """,
        responses={
            200: OpenApiResponse(description="Participant removed."),
        },
        tags=["Chat"],
    )

    def delete(self, request, room_id, user_id):
        if not Participant.objects.filter(
            room_id=room_id,
            user=request.user,
            is_admin=True,
        ).exists():

            return Response(
                {
                    "error": "Only group admins can remove participants.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            participant = Participant.objects.get(
                room_id=room_id,
                user_id=user_id,
            )

            if participant.user == participant.room.created_by:

                 return Response(
                        {
                            "error": "The group creator cannot be removed.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        except Participant.DoesNotExist:

            return Response(
                {
                    "error": "Participant not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        
        if participant.is_admin:

            remaining_admins = (
                Participant.objects.filter(
                    room=participant.room,
                    is_admin=True,
                ).exclude(
                    pk=participant.pk,
                )
            )

            if not remaining_admins.exists():

                new_admin = (
                    Participant.objects.filter(
                        room=participant.room,
                    )
                    .exclude(
                        pk=participant.pk,
                    )
                    .first()
                )

                if new_admin:
                    new_admin.is_admin = True
                    new_admin.save(
                        update_fields=["is_admin"],
                    )

        room_id = participant.room_id
        removed_user_id = participant.user_id
        participant.delete()
        broadcast_room_changed(room_id, "participant_removed", extra_user_ids=[removed_user_id])

        return Response(
            {
                "message": "Participant removed successfully.",
            },
            status=status.HTTP_200_OK,
        )
    

class LeaveGroupAPIView(APIView):
    """
    Leave a group chat.
    """

    permission_classes = (
        permissions.IsAuthenticated,
    )


    @extend_schema(
        summary="Leave Group",
        request=None,
        description="""
        Leave a group conversation.

        If the last administrator leaves,
        another participant becomes admin automatically.
        """,
        responses={
            200: OpenApiResponse(description="Left successfully."),
        },
        tags=["Chat"],
    )



    def post(self, request, room_id):
        try:
            participant = Participant.objects.get(
                room_id=room_id,
                user=request.user,
            )

        except Participant.DoesNotExist:

            return Response(
                {
                    "error": "You are not a participant of this group.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        
        if participant.is_admin:

            remaining_admins = (
                Participant.objects.filter(
                    room=participant.room,
                    is_admin=True,
                ).exclude(
                    pk=participant.pk,
                )
            )

            if not remaining_admins.exists():

                new_admin = (
                    Participant.objects.filter(
                        room=participant.room,
                    )
                    .exclude(
                        pk=participant.pk,
                    )
                    .first()
                )

                if new_admin:
                    new_admin.is_admin = True
                    new_admin.save(
                        update_fields=["is_admin"],
                    )

        group_id = participant.room_id
        leaving_user_id = participant.user_id
        participant.delete()
        broadcast_room_changed(group_id, "participant_left", extra_user_ids=[leaving_user_id])

        return Response(
            {
                "message": "You left the group successfully.",
            },
            status=status.HTTP_200_OK,
        )


# ==========================================================
# Per-user chat preferences
# ==========================================================

def _get_membership(request, room_id):
    return get_object_or_404(
        Participant.objects.select_related("room"),
        room_id=room_id,
        user=request.user,
        room__is_active=True,
    )


class PinChatAPIView(APIView):
    """Pin or unpin a chat at the top of the user's list (max 3, like WhatsApp)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Pin chat",
        request={"type": "object", "properties": {"room": {"type": "integer"}, "is_pinned": {"type": "boolean"}}},
        tags=["Chat"],
    )
    def post(self, request):
        participant = _get_membership(request, request.data.get("room"))
        is_pinned = str(request.data.get("is_pinned", "true")).lower() in ("true", "1", "on")
        if is_pinned and not participant.is_pinned:
            pinned_count = Participant.objects.filter(
                user=request.user, is_pinned=True, room__is_active=True,
            ).count()
            if pinned_count >= settings.WHATSUP_MAX_PINNED_CHATS:
                return Response(
                    {"detail": f"You can only pin up to {settings.WHATSUP_MAX_PINNED_CHATS} chats."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        participant.is_pinned = is_pinned
        participant.pinned_at = timezone.now() if is_pinned else None
        participant.save(update_fields=["is_pinned", "pinned_at"])
        notify_user_rooms_changed(request.user.id, "pinned", participant.room_id)
        return Response({"room": participant.room_id, "is_pinned": participant.is_pinned})


class FavoriteChatAPIView(APIView):
    """Add or remove a chat from the user's Favorites filter."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Favorite chat",
        request={"type": "object", "properties": {"room": {"type": "integer"}, "is_favorite": {"type": "boolean"}}},
        tags=["Chat"],
    )
    def post(self, request):
        participant = _get_membership(request, request.data.get("room"))
        participant.is_favorite = str(request.data.get("is_favorite", "true")).lower() in ("true", "1", "on")
        participant.save(update_fields=["is_favorite"])
        notify_user_rooms_changed(request.user.id, "favorite", participant.room_id)
        return Response({"room": participant.room_id, "is_favorite": participant.is_favorite})


class MarkRoomReadAPIView(APIView):
    """
    Mark every incoming message in a chat as read for the current user.

    Persists per-recipient receipts and notifies the senders (blue ticks).
    Clients call this when a conversation is opened and visible.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Mark chat as read", request=None, tags=["Chat"])
    def post(self, request, pk):
        _get_membership(request, pk)
        results = mark_room_read(pk, request.user)
        broadcast_receipts(results)
        notify_user_rooms_changed(request.user.id, "read", int(pk))
        return Response({"room_id": int(pk), "marked_read": len(results)})


class MarkAllReadAPIView(APIView):
    """Mark every chat (optionally only archived ones) as read."""

    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Mark all chats as read", request=None, tags=["Chat"])
    def post(self, request):
        memberships = Participant.objects.filter(user=request.user, room__is_active=True)
        if "archived" in request.data:
            memberships = memberships.filter(
                is_archived=str(request.data.get("archived")).lower() in ("true", "1", "on")
            )
        # One batched pass over every chat instead of one pass per chat.
        unread_ids = list(
            unread_messages_for_user(
                Message.objects.filter(room_id__in=memberships.values("room_id")), request.user
            )
            .order_by("created_at")
            .values_list("id", flat=True)[:5000]
        )
        results = persist_receipts_bulk(unread_ids, request.user.id, "read")
        broadcast_receipts(results)
        total = len(results)
        notify_user_rooms_changed(request.user.id, "read")
        return Response({"marked_read": total})


class ParticipantAdminAPIView(APIView):
    """Promote a member to group admin or dismiss an admin."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Change group admin",
        request={"type": "object", "properties": {"is_admin": {"type": "boolean"}}},
        tags=["Chat"],
    )
    def patch(self, request, room_id, user_id):
        room = get_object_or_404(ChatRoom, pk=room_id, room_type=RoomType.GROUP, is_active=True)
        if not Participant.objects.filter(room=room, user=request.user, is_admin=True).exists():
            return Response({"detail": "Only group admins can change admins."}, status=status.HTTP_403_FORBIDDEN)
        participant = get_object_or_404(Participant, room=room, user_id=user_id)
        make_admin = str(request.data.get("is_admin", "true")).lower() in ("true", "1", "on")
        if not make_admin:
            if participant.user_id == room.created_by_id:
                return Response({"detail": "The group creator is always an admin."}, status=status.HTTP_400_BAD_REQUEST)
            other_admins = Participant.objects.filter(room=room, is_admin=True).exclude(pk=participant.pk)
            if not other_admins.exists():
                return Response({"detail": "A group must have at least one admin."}, status=status.HTTP_400_BAD_REQUEST)
        participant.is_admin = make_admin
        participant.save(update_fields=["is_admin"])
        broadcast_room_changed(room.id, "admin_changed")
        return Response(ParticipantSerializer(participant).data)


LINK_PATTERN = r"https?://[^\s]+"


def shared_media_payload(base, kind):
    """Media / docs / audio / links found in a queryset of visible messages."""
    import re

    if kind == "links":
        messages = (
            base.filter(message_type=MessageType.TEXT, content__iregex=LINK_PATTERN)
            .exclude(content__startswith="__WHATSUP_")
            .select_related("sender", "sender__profile")
            .order_by("-created_at")[:200]
        )
        data = []
        for message in messages:
            for url in re.findall(LINK_PATTERN, message.content or ""):
                data.append({
                    "message_id": message.id,
                    "room_id": message.room_id,
                    "url": url.rstrip(").,"),
                    "text": message.content,
                    "sender_id": message.sender_id,
                    "created_at": message.created_at,
                })
        return data

    # View once media is never listed (it can only be opened once from the chat).
    attachments = Attachment.objects.filter(message__in=base.filter(is_view_once=False)).select_related("message")
    if kind == "media":
        attachments = attachments.filter(
            Q(mime_type__startswith="image/") | Q(mime_type__startswith="video/")
        )
    elif kind == "audio":
        attachments = attachments.filter(mime_type__startswith="audio/")
    else:
        attachments = attachments.exclude(
            Q(mime_type__startswith="image/")
            | Q(mime_type__startswith="video/")
            | Q(mime_type__startswith="audio/")
        )
    attachments = attachments.order_by("-message__created_at", "-id")[:300]
    return [
        {
            "id": attachment.id,
            "message_id": attachment.message_id,
            "room_id": attachment.message.room_id,
            "file": attachment.file.url if attachment.file else None,
            "file_name": attachment.file_name,
            "file_size": attachment.file_size,
            "mime_type": attachment.mime_type,
            "caption": attachment.message.content,
            "sender_id": attachment.message.sender_id,
            "created_at": attachment.message.created_at,
        }
        for attachment in attachments
    ]


class RoomSharedMediaAPIView(APIView):
    """
    Shared media, documents, audio and links of one conversation.

    ``?kind=media`` (images & videos), ``docs``, ``audio`` or ``links``.
    Only messages visible to the requesting user are returned.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Shared media, links and docs", tags=["Chat"])
    def get(self, request, pk):
        _get_membership(request, pk)
        kind = request.query_params.get("kind", "media")
        base = visible_messages_for_user(
            Message.objects.filter(room_id=pk, is_deleted=False), request.user
        )
        data = shared_media_payload(base, kind)
        return Response({"kind": kind, "results": data, "count": len(data)})


class AllSharedMediaAPIView(APIView):
    """WhatsApp Web's "Media from all chats": the same tabs across every chat."""

    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Media, docs and links from all chats", tags=["Chat"])
    def get(self, request):
        kind = request.query_params.get("kind", "media")
        my_rooms = Participant.objects.filter(user=request.user).values("room_id")
        base = visible_messages_for_user(
            Message.objects.filter(room_id__in=my_rooms, is_deleted=False), request.user
        )
        data = shared_media_payload(base, kind)
        return Response({"kind": kind, "results": data, "count": len(data)})


class RoomPinnedMessagesAPIView(APIView):
    """Pinned messages of a chat, newest pin first (shown in the pin bar)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Pinned messages in a chat", tags=["Chat"])
    def get(self, request, pk):
        _get_membership(request, pk)
        messages = (
            with_message_relations(visible_messages_for_user(
                Message.objects.filter(room_id=pk, is_pinned=True, is_deleted=False), request.user
            ))
            .order_by("-pinned_at", "-id")[: settings.WHATSUP_MAX_PINNED_MESSAGES]
        )
        return Response(MessageSerializer(messages, many=True, context={"request": request}).data)


class GlobalMessageSearchAPIView(APIView):
    """Search the user's visible messages across all of their chats."""

    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Search messages in all chats", tags=["Chat"])
    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if len(query) < 2:
            return Response([])
        messages = (
            visible_messages_for_user(
                Message.objects.filter(
                    room__participants__user=request.user,
                    room__is_active=True,
                    is_deleted=False,
                    message_type=MessageType.TEXT,
                    content__icontains=query,
                ).exclude(content__startswith="__WHATSUP_"),
                request.user,
            )
            .select_related("sender", "sender__profile")
            .distinct()
            .order_by("-created_at")[:50]
        )
        return Response([
            {
                "id": message.id,
                "room_id": message.room_id,
                "sender_id": message.sender_id,
                "sender_phone": message.sender.phone_number,
                "content": message.content,
                "created_at": message.created_at,
            }
            for message in messages
        ])
