import json
from rest_framework import serializers
from django.utils import timezone
from apps.accounts.serializers import UserSerializer
from .choices import MessageType
from apps.accounts.models import User
from .models import BlockedUser
from .models import (
    Attachment,
    ChatRoom,
    Message,
    Participant,
    Reaction,
    StarredMessage,
    DeletedMessage,
    VoiceNote,


)


# ==========================================================
# Attachment
# ==========================================================

class AttachmentSerializer(serializers.ModelSerializer):
    """
    Serializer for message attachments.
    """

    class Meta:
        model = Attachment

        fields = (
            "id",
            "file",
            "file_name",
            "file_size",
            "mime_type",
            "uploaded_at",
        )

        read_only_fields = (
            "id",
            "file_name",
            "file_size",
            "mime_type",
            "uploaded_at",
        )



# ==========================================================
# Reaction
# ==========================================================

class ReactionSerializer(serializers.ModelSerializer):
    """
    Serializer for message reactions.
    """

    user_id = serializers.IntegerField(
        source="user.id",
        read_only=True,
    )

    sender_phone = serializers.CharField(
        source="user.phone_number",
        read_only=True,
    )

    class Meta:
        model = Reaction

        fields = (
            "id",
            "user_id",
            "sender_phone",
            "emoji",
            "created_at",
        )

        read_only_fields = (
            "id",
            "user_id",
            "sender_phone",
            "created_at",
        )


# ==========================================================
# Starred Message
# ==========================================================

class StarredMessageSerializer(serializers.ModelSerializer):
    """
    Serializer for starred messages.
    """

    user_id = serializers.IntegerField(
        source="user.id",
        read_only=True,
    )

    sender_phone = serializers.CharField(
        source="user.phone_number",
        read_only=True,
    )

    class Meta:
        model = StarredMessage

        fields = (
            "id",
            "user_id",
            "sender_phone",
            "created_at",
        )

        read_only_fields = (
            "id",
            "user_id",
            "sender_phone",
            "created_at",
        )
# ==========================================================
# React to Message
# ==========================================================

class ReactMessageSerializer(serializers.Serializer):
    """
    Serializer used to add or update
    a reaction on a message.
    """

    message = serializers.PrimaryKeyRelatedField(
        queryset=Message.objects.all(),
    )

    emoji = serializers.CharField(
        max_length=20,
    )

    def validate_message(
        self,
        message,
    ):
        request = self.context["request"]

        if not message.room.participants.filter(
            user=request.user,
        ).exists():
            raise serializers.ValidationError(
                "You are not a participant of this room."
            )

        if message.is_deleted:
            raise serializers.ValidationError(
                "Cannot react to a deleted message."
            )

        return message

    def create(
        self,
        validated_data,
    ):
        request = self.context["request"]

        reaction, _ = Reaction.objects.update_or_create(
            message=validated_data["message"],
            user=request.user,
            defaults={
                "emoji": validated_data["emoji"],
            },
        )

        return reaction
    

# ==========================================================
# Star Message
# ==========================================================

class StarMessageSerializer(serializers.Serializer):
    """
    Serializer for starring
    or unstarring a message.
    """

    message = serializers.PrimaryKeyRelatedField(
        queryset=Message.objects.all(),
    )

    is_starred = serializers.BooleanField()

    def validate_message(
        self,
        message,
    ):
        request = self.context["request"]

        if not message.room.participants.filter(
            user=request.user,
        ).exists():
            raise serializers.ValidationError(
                "You are not a participant of this room."
            )

        if message.is_deleted:
            raise serializers.ValidationError(
                "Cannot star a deleted message."
            )

        return message

    def save(self):
        request = self.context["request"]

        message = self.validated_data["message"]

        is_starred = self.validated_data["is_starred"]

        if is_starred:
            starred, _ = (
                StarredMessage.objects.get_or_create(
                    message=message,
                    user=request.user,
                )
            )
            return starred

        StarredMessage.objects.filter(
            message=message,
            user=request.user,
        ).delete()

        return None


class PinMessageSerializer(serializers.Serializer):
    """
    Pin or unpin a message.
    """

    message = serializers.PrimaryKeyRelatedField(
        queryset=Message.objects.all(),
    )

    is_pinned = serializers.BooleanField()

    def validate_message(
        self,
        message,
    ):
        request = self.context["request"]

        if not message.room.participants.filter(
            user=request.user,
        ).exists():
            raise serializers.ValidationError(
                "You are not a participant of this room."
            )

        if message.is_deleted:
            raise serializers.ValidationError(
                "Cannot pin a deleted message."
            )

        return message

    def save(self):
        message = self.validated_data["message"]

        message.is_pinned = self.validated_data["is_pinned"]

        message.pinned_at = (
            timezone.now()
            if message.is_pinned
            else None
        )

        message.save(
            update_fields=[
                "is_pinned",
                "pinned_at",
            ]
        )

        return message



class VoiceNoteSerializer(serializers.ModelSerializer):
    """
    Serializer for voice notes.
    """

    class Meta:

        model = VoiceNote

        fields = (
            "id",
            "audio",
            "duration",
            "waveform",
            "created_at",
        )

        read_only_fields = (
            "id",
            "created_at",
        )



# ==========================================================
# Participant
# ==========================================================

class ParticipantSerializer(serializers.ModelSerializer):
    """
    Serializer for chat room participants.
    """

    user = UserSerializer(
        read_only=True,
    )

    class Meta:
        model = Participant

        fields = (
            "id",
            "user",
            "is_admin",
            "is_muted",
            "muted_until",
            "is_archived",
            "joined_at",
            "is_archived",
        )

        read_only_fields = (
            "id",
            "joined_at",
        )


# ==========================================================
# Message
# ==========================================================

class MessageSerializer(serializers.ModelSerializer):
    """
    Serializer used when retrieving chat messages.
    """

    sender = UserSerializer(
        read_only=True,
    )

    attachments = AttachmentSerializer(
        many=True,
        read_only=True,
    )

    voice_note = VoiceNoteSerializer(
        read_only=True,
    )

    is_starred = serializers.SerializerMethodField()

    forwarded_from = serializers.SerializerMethodField()

    reactions = ReactionSerializer(
        many=True,
        read_only=True,
    )

    content = serializers.SerializerMethodField()

    reply_to = serializers.SerializerMethodField()


    def get_content(self, obj):
        """
        Convert JSON strings back to Python objects.
        """

        if obj.message_type in (
            MessageType.CONTACT,
            MessageType.LOCATION,
        ):
            try:
                return json.loads(obj.content)
            except Exception:
                return obj.content

        return obj.content
    

    def get_reply_to(
        self,
        obj,
    ):
        """
        Return a preview of the replied message.
        """

        if not obj.reply_to:
            return None

        return {
            "id": obj.reply_to.id,
            "sender_id": obj.reply_to.sender.id,
            "sender_phone": obj.reply_to.sender.phone_number,
            "content": obj.reply_to.content,
            "message_type": obj.reply_to.message_type,
        }
    

    def get_is_starred(
        self,
        obj,
    ):
        request = self.context.get(
            "request",
        )

        if not request:
            return False

        if request.user.is_anonymous:
            return False

        return obj.starred_by.filter(
            user=request.user,
        ).exists()
    
    def get_forwarded_from(
        self,
        obj,
    ):
        if not obj.forwarded_from:
            return None

        return {
            "id": obj.forwarded_from.id,
            "sender_id": obj.forwarded_from.sender.id,
            "sender_phone": obj.forwarded_from.sender.phone_number,
            "content": obj.forwarded_from.content,
            "message_type": obj.forwarded_from.message_type,
        }
    

    class Meta:
        model = Message

        fields = (
            "id",
            "sender",
            "message_type",
            "content",
            "reply_to",
            "attachments",
            "voice_note",
            "reactions",
            "is_edited",
            "is_deleted",
            "is_starred",
            "is_pinned",
            "pinned_at",
            "forwarded_from",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "sender",
            "attachments",
            "is_edited",
            "is_deleted",
            "created_at",
            "updated_at",
        )


# ==========================================================
# Send Message
# ==========================================================

class SendMessageSerializer(serializers.ModelSerializer):
    """
    Serializer used to send a new message.
    """


    content = serializers.JSONField(
        required=False,
    )

    class Meta:
        model = Message

        fields = (
            "room",
            "message_type",
            "content",
            "reply_to",

        )

    def validate_room(self, room):
        """
        Ensure the authenticated user belongs
        to the selected room.
        """

        request = self.context["request"]

        if not room.participants.filter(
            user=request.user,
        ).exists():
            raise serializers.ValidationError(
                "You are not a participant of this room."
            )

        return room

    def validate(self, attrs):
        """
        Validate message content.
        """

        message_type = attrs.get(
            "message_type",
            MessageType.TEXT,
        )

        content = attrs.get(
            "content",
            "",
        )

        # -----------------------------
        # TEXT
        # -----------------------------
        if message_type == MessageType.TEXT:

            content = str(content).strip()

            if not content:
                raise serializers.ValidationError(
                    {
                        "content": "Text messages cannot be empty."
                    }
                )

            attrs["content"] = content

        # -----------------------------
        # CONTACT
        # -----------------------------
        elif message_type == MessageType.CONTACT:

            if not isinstance(content, dict):
                raise serializers.ValidationError(
                    {
                        "content": "Contact must be a JSON object."
                    }
                )

            if "name" not in content or "phone" not in content:
                raise serializers.ValidationError(
                    {
                        "content": "Contact requires name and phone."
                    }
                )

            attrs["content"] = json.dumps(content)

        # -----------------------------
        # LOCATION
        # -----------------------------
        elif message_type == MessageType.LOCATION:

            if not isinstance(content, dict):
                raise serializers.ValidationError(
                    {
                        "content": "Location must be a JSON object."
                    }
                )

            required = [
                "latitude",
                "longitude",
                "address",
            ]

            for field in required:
                if field not in content:
                    raise serializers.ValidationError(
                        {
                            "content": f"{field} is required."
                        }
                    )

            attrs["content"] = json.dumps(content)

        else:

            attrs["content"] = str(content)


        reply_to = attrs.get(
            "reply_to",
        )

        if reply_to:

            room = attrs.get("room")

            if reply_to.room != room:
                raise serializers.ValidationError(
                    {
                        "reply_to": (
                            "Reply message must belong "
                            "to the same room."
                        )
                    }
                )

            if reply_to.is_deleted:
                raise serializers.ValidationError(
                    {
                        "reply_to": (
                            "Cannot reply to a deleted message."
                        )
                    }
                )

        return attrs

    def create(self, validated_data):

        request = self.context["request"]

        return Message.objects.create(
            sender=request.user,
            **validated_data,
        )


# ==========================================================
# Block User
# ==========================================================

class BlockUserSerializer(serializers.Serializer):
    """
    Block or unblock a user.
    """

    user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
    )

    def validate_user(
        self,
        user,
    ):
        request = self.context["request"]

        if user == request.user:
            raise serializers.ValidationError(
                "You cannot block yourself."
            )

        return user

    def save(self):
        request = self.context["request"]

        blocked_user = self.validated_data["user"]

        blocked, _ = BlockedUser.objects.get_or_create(
            blocked_by=request.user,
            blocked_user=blocked_user,
        )

        return blocked
    


class UnblockUserSerializer(serializers.Serializer):

    user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
    )

    def save(self):

        request = self.context["request"]

        BlockedUser.objects.filter(
            blocked_by=request.user,
            blocked_user=self.validated_data["user"],
        ).delete()

        return self.validated_data["user"]
    
# ==========================================================
# Mute Chat
# ==========================================================

class MuteChatSerializer(serializers.Serializer):
    """
    Mute or unmute a chat.
    """

    room = serializers.PrimaryKeyRelatedField(
        queryset=ChatRoom.objects.all(),
    )

    duration = serializers.ChoiceField(
        choices=(
            ("8h", "8 Hours"),
            ("1w", "1 Week"),
            ("always", "Always"),
            ("off", "Unmute"),
        )
    )

    def validate_room(self, room):
        request = self.context["request"]

        if not room.participants.filter(
            user=request.user,
        ).exists():
            raise serializers.ValidationError(
                "You are not a participant of this room."
            )

        return room
    

# ==========================================================
# Archive Chat
# ==========================================================

class ArchiveChatSerializer(serializers.Serializer):
    """
    Archive or unarchive a chat.
    """

    room = serializers.PrimaryKeyRelatedField(
        queryset=ChatRoom.objects.all(),
    )

    is_archived = serializers.BooleanField()

    def validate_room(
        self,
        room,
    ):
        request = self.context["request"]

        if not room.participants.filter(
            user=request.user,
        ).exists():
            raise serializers.ValidationError(
                "You are not a participant of this room."
            )

        return room


class ForwardMessageSerializer(serializers.Serializer):
    """
    Forward an existing message to another room.
    """

    room = serializers.PrimaryKeyRelatedField(
        queryset=ChatRoom.objects.all(),
    )

    message = serializers.PrimaryKeyRelatedField(
        queryset=Message.objects.filter(
            is_deleted=False,
        ),
    )

    def validate(
        self,
        attrs,
    ):
        request = self.context["request"]

        room = attrs["room"]
        original = attrs["message"]

        if not room.participants.filter(
            user=request.user,
        ).exists():
            raise serializers.ValidationError(
                {
                    "room": (
                        "You are not a participant "
                        "of this room."
                    )
                }
            )

        if not original.room.participants.filter(
            user=request.user,
        ).exists():
            raise serializers.ValidationError(
                {
                    "message": (
                        "You cannot forward this message."
                    )
                }
            )

        return attrs

    def create(
        self,
        validated_data,
    ):
        request = self.context["request"]

        original = validated_data["message"]

        new_message = Message.objects.create(
            room=validated_data["room"],
            sender=request.user,

            forwarded_from=original,

            message_type=original.message_type,
            content=original.content,

            reply_to=None,
        )

        # Copy attachments
        for attachment in original.attachments.all():

            Attachment.objects.create(
                message=new_message,
                file=attachment.file,
            )

        return new_message
    


# ==========================================================
# Delete For Me
# ==========================================================

class DeleteForMeSerializer(serializers.Serializer):
    """
    Delete a message only for
    the authenticated user.
    """

    message = serializers.PrimaryKeyRelatedField(
        queryset=Message.objects.filter(
            is_deleted=False,
        ),
    )

    def validate_message(
        self,
        message,
    ):
        request = self.context["request"]

        if not message.room.participants.filter(
            user=request.user,
        ).exists():
            raise serializers.ValidationError(
                "You are not a participant of this chat."
            )

        return message

    def save(self):
        request = self.context["request"]

        message = self.validated_data["message"]

        DeletedMessage.objects.get_or_create(
            message=message,
            user=request.user,
        )

        return message

# ==========================================================
# Upload Message
# ==========================================================

class UploadMessageSerializer(serializers.Serializer):
    """
    Serializer for uploading message attachments.
    """

    room = serializers.PrimaryKeyRelatedField(
        queryset=ChatRoom.objects.all(),
    )

    message_type = serializers.ChoiceField(
        choices=MessageType.choices,
    )

    reply_to = serializers.PrimaryKeyRelatedField(
        queryset=Message.objects.all(),
        required=False,
        allow_null=True,
    )

    content = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    file = serializers.FileField()

    def validate_room(
        self,
        room,
    ):
        """
        Ensure the authenticated user belongs
        to the selected room.
        """

        request = self.context["request"]

        if not room.participants.filter(
            user=request.user,
        ).exists():
            raise serializers.ValidationError(
                "You are not a participant of this room."
            )

        return room

    def validate_file(
        self,
        file,
    ):
        """
        Validate uploaded file.
        """

        max_size = 25 * 1024 * 1024  # 25 MB

        if file.size > max_size:
            raise serializers.ValidationError(
                "Maximum file size is 25 MB."
            )

        return file
    

    def validate(
        self,
        attrs,
    ):
        """
        Validate reply message.
        """

        reply_to = attrs.get(
            "reply_to",
        )

        if reply_to:

            room = attrs["room"]

            if reply_to.room != room:
                raise serializers.ValidationError(
                    {
                        "reply_to":
                        "Reply must belong to the same room."
                    }
                )

            if reply_to.is_deleted:
                raise serializers.ValidationError(
                    {
                        "reply_to":
                        "Cannot reply to a deleted message."
                    }
                )

        return attrs

    def create(
        self,
        validated_data,
    ):
        """
        Create message and attachment.
        """

        request = self.context["request"]

        uploaded_file = validated_data.pop(
            "file",
        )

        message = Message.objects.create(
            sender=request.user,
            room=validated_data["room"],
            message_type=validated_data["message_type"],
            content=validated_data.get(
                "content",
                "",
            ),
            reply_to=validated_data.get(
                "reply_to",
            ),
        )

        Attachment.objects.create(
            message=message,
            file=uploaded_file,
        )

        return message



# ==========================================================
# Chat Room
# ==========================================================

class ChatRoomSerializer(serializers.ModelSerializer):
    """
    Serializer for chat room list.
    """

    participants = ParticipantSerializer(
        many=True,
        read_only=True,
    )

    participants_count = serializers.IntegerField(
        source="participants.count",
        read_only=True,
    )

    last_message = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom

        fields = (
            "id",
            "name",
            "room_type",
            "description",
            "photo",
            "is_active",
            "participants_count",
            "participants",
            "last_message",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "participants_count",
            "last_message",
            "created_at",
            "updated_at",
        )

    def get_last_message(self, obj):
        """
        Return the latest message in the room.
        """

        message = (
            obj.messages
            .order_by("-created_at")
            .first()
        )

        if not message:
            return None

        return MessageSerializer(
            message,
            context=self.context,
        ).data


# ==========================================================
# Chat Room Detail
# ==========================================================

class ChatRoomDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for chat room details.
    """

    participants = ParticipantSerializer(
        many=True,
        read_only=True,
    )

    messages = MessageSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = ChatRoom

        fields = (
            "id",
            "name",
            "room_type",
            "description",
            "photo",
            "created_by",
            "is_active",
            "participants",
            "messages",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "created_by",
            "participants",
            "messages",
            "created_at",
            "updated_at",
        )



class MessageSearchSerializer(serializers.ModelSerializer):
    """
    Serializer for searched messages.
    """

    sender = UserSerializer(
        read_only=True,
    )

    attachments = AttachmentSerializer(
        many=True,
        read_only=True,
    )

    reply_to = serializers.SerializerMethodField()

    class Meta:
        model = Message

        fields = (
            "id",
            "sender",
            "message_type",
            "content",
            "reply_to",
            "attachments",
            "is_edited",
            "is_deleted",
            "created_at",
        )

    def get_reply_to(self, obj):
        if not obj.reply_to:
            return None

        return {
            "id": obj.reply_to.id,
            "content": obj.reply_to.content,
            "sender_id": obj.reply_to.sender.id,
            "sender_phone": obj.reply_to.sender.phone_number,
        }


class UploadVoiceSerializer(serializers.Serializer):

    room = serializers.IntegerField()

    audio = serializers.FileField()

    duration = serializers.IntegerField()

    waveform = serializers.JSONField(
        required=False,
    )

class CreateGroupSerializer(serializers.Serializer):

    name = serializers.CharField()

    description = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    photo = serializers.ImageField(
        required=False,
    )


class CreatePrivateChatSerializer(serializers.Serializer):

    user_id = serializers.IntegerField()