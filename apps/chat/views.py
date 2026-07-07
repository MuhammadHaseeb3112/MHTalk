from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated

from rest_framework.parsers import MultiPartParser, FormParser
from django.db.models import Q
from apps.accounts.models import User
from datetime import timedelta
from django.utils import timezone
from .utils import broadcast_message,get_message_with_relations
from django.db.models import Prefetch

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

)
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

        ?archived=true
        ?archived=false
        """

        archived = (
            self.request.query_params
            .get(
                "archived",
                "false",
            )
            .lower()
        )

        is_archived = archived == "true"

        return (
            ChatRoom.objects
            .filter(
                participants__user=self.request.user,
                participants__is_archived=is_archived,
                is_active=True,
            )
            .select_related(
                "created_by",
            )
            .prefetch_related(
                "participants__user__profile",
                "messages",
            )
            .distinct()
            .order_by(
                "-updated_at",
            )
        )
    
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
                    queryset=(
                        Message.objects
                        .filter(
                            is_deleted=False,
                        )
                        .exclude(
                            deleted_for_users__user=self.request.user,
                        )
                        .select_related(
                            "sender",
                            "sender__profile",
                        )
                        .prefetch_related(
                            "attachments",
                            "reactions",
                            "voice_note",

                        )
                    ),
                ),
            )
            .distinct()
        )
    

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

        return (
            Message.objects
            .filter(
                room_id=room_id,
                room__participants__user=self.request.user,
                is_deleted=False,
            )
            .exclude(
                deleted_for_users__user=self.request.user,
            )
            .select_related(
                "sender",
                "sender__profile",

                "reply_to",
                "reply_to__sender",
                "reply_to__sender__profile",

                "forwarded_from",
                "forwarded_from__sender",
                "forwarded_from__sender__profile",
            )
            .prefetch_related(
                "attachments",
                "reactions",
                "voice_note",
            )
            .order_by(
                "created_at",
            )
        )
    

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
                "sender",
                "sender__profile",
            )
            .prefetch_related(
                "attachments",
                "reactions",
                "voice_note",
            )
            .exclude(
                deleted_for_users__user=request.user,
            )
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
    Return True if either participant
    has blocked the other.
    """

    if room.room_type != RoomType.PRIVATE:
        return False

    other = (
        room.participants
        .exclude(user=current_user)
        .select_related("user")
        .first()
    )

    if not other:
        return False

    return BlockedUser.objects.filter(
        Q(
            blocked_by=current_user,
            blocked_user=other.user,
        )
        |
        Q(
            blocked_by=other.user,
            blocked_user=current_user,
        )
    ).exists()
    

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

        if is_private_chat_blocked(
            room,
            request.user,
        ):
            return Response(
                {
                    "detail":
                    "You cannot send messages to this user.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        message = serializer.save()


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

        if is_private_chat_blocked(
            room,
            request.user,
        ):
            return Response(
                {
                    "detail":
                    "You cannot send messages to this user.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        message = serializer.save()

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

        if is_private_chat_blocked(
            room,
            request.user,
        ):
            return Response(
                {
                    "detail": "You cannot send messages to this user.",
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

        with transaction.atomic():

            message = Message.objects.create(
                room=room,
                sender=request.user,
                message_type=MessageType.VOICE,
                content="",
            )

            VoiceNote.objects.create(
                message=message,
                audio=audio,
                duration=duration,
                waveform=request.data.get(
                    "waveform",
                    [],
                ),
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

        if is_private_chat_blocked(
            room,
            request.user,
        ):
            return Response(
                {
                    "detail":
                    "You cannot send messages to this user.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        message = serializer.save()

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

        return Response(
            {
                "message": "Message updated successfully.",
                "data": MessageSerializer(
                    message,
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
            Message.objects.filter(
                starred_by__user=request.user,
                is_deleted=False,
            )
            .exclude(
                deleted_for_users__user=request.user,
            )
            .select_related(
                "sender",
                "sender__profile",

                "reply_to",
                "reply_to__sender",
                "reply_to__sender__profile",

                "forwarded_from",
                "forwarded_from__sender",
                "forwarded_from__sender__profile",
            )
            .prefetch_related(
                "attachments",
                "reactions",
                "voice_note",
            )
            .order_by(
                "-created_at",
            )
        )

        serializer = MessageSerializer(
            messages,
            many=True,
            context={
                "request": request,
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

        participant.save(
            update_fields=[
                "is_archived",
            ]
        )

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
        name = request.data.get("name")

        if not name:
            return Response(
                {
                    "error": "Group name is required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        

        with transaction.atomic():

            room = ChatRoom.objects.create(
                name=name,
                room_type=RoomType.GROUP,
                description=request.data.get(
                    "description",
                    "",
                ),
                photo=request.data.get(
                    "photo",
                ),
                created_by=request.user,
            )

            Participant.objects.create(
                room=room,
                user=request.user,
                is_admin=True,
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
        response = super().update(
            request,
            *args,
            **kwargs,
        )

        response.data = {
            "message": "Message updated successfully.",
            "data": response.data,
        }

        return response
    


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
        try:
            message = Message.objects.get(
                pk=pk,
                sender=request.user,
                is_deleted=False,
            )

        except Message.DoesNotExist:

            return Response(
                {
                    "error": "Message not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        message.content = ""

        message.is_deleted = True

        message.is_edited = False

        message.updated_at = timezone.now()

        message.save(
            update_fields=[
                "content",
                "is_deleted",
                "is_edited",
                "updated_at",

            ]
        )

        return Response(
            {
                "message": "Message deleted successfully.",
            },
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

        if not Participant.objects.filter(
            room=room,
            user=request.user,
            is_admin=True,
        ).exists():

            return Response(
                {
                    "error": "Only group admins can add participants.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        user_id = request.data.get(
            "user_id",
        )

        try:
            user = User.objects.get(
                pk=user_id,
                is_active=True,
            )

        except User.DoesNotExist:

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

        participant.delete()

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

        participant.delete()

        return Response(
            {
                "message": "You left the group successfully.",
            },
            status=status.HTTP_200_OK,
        )