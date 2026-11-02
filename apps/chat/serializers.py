from django.conf import settings
from django.db import transaction
import json
from django.db.models import Exists, Max, OuterRef, Prefetch, Q, Subquery
from rest_framework import serializers
from django.utils import timezone
from apps.accounts.serializers import UserSerializer
from .choices import MessageType, SYSTEM_PREFIX
from apps.accounts.models import User
from .models import BlockedUser
from .models import ChatClear
from .models import (
    Attachment,
    ChatRoom,
    Message,
    Participant,
    Reaction,
    StarredMessage,
    DeletedMessage,
    VoiceNote,
    MessageReceipt,


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
                "created_at": timezone.now(),
            },
        )
        ChatRoom.objects.filter(pk=validated_data["message"].room_id).update(updated_at=timezone.now())

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

        if message.is_view_once:
            raise serializers.ValidationError(
                "View once media can't be starred."
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

        from .group_events import is_group_event

        if is_group_event(message):
            raise serializers.ValidationError("System messages cannot be pinned.")

        return message

    def save(self):
        message = self.validated_data["message"]

        if self.validated_data["is_pinned"] and not message.is_pinned:
            # WhatsApp keeps up to 3 pins per chat: pinning a 4th replaces the oldest.
            limit = getattr(settings, "MHTALK_MAX_PINNED_MESSAGES", 3)
            pinned = list(
                Message.objects.filter(room_id=message.room_id, is_pinned=True)
                .exclude(pk=message.pk)
                .order_by("-pinned_at", "-id")
                .values_list("pk", flat=True)
            )
            stale = pinned[limit - 1:]
            if stale:
                Message.objects.filter(pk__in=stale).update(is_pinned=False, pinned_at=None)
                self.unpinned_ids = stale

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

    room_id = serializers.IntegerField(read_only=True)
    reply_to = serializers.SerializerMethodField()
    poll = serializers.SerializerMethodField()
    mentions = serializers.SerializerMethodField()
    view_once_opened_by = serializers.SerializerMethodField()

    def get_poll(self, obj):
        if obj.message_type != MessageType.POLL or obj.is_deleted:
            return None
        from .features import poll_payload

        return poll_payload(getattr(obj, "poll", None))

    def get_mentions(self, obj):
        # Only messages that can contain "@" need the (prefetched) rows.
        if obj.is_deleted or "@" not in str(obj.content or ""):
            return []
        return [row.user_id for row in obj.mention_rows.all()]

    def get_view_once_opened_by(self, obj):
        if not obj.is_view_once:
            return []
        return [row.user_id for row in obj.view_once_opens.all()]

    def to_representation(self, obj):
        from apps.accounts.privacy import mask_read_state, viewer_from_context

        data = super().to_representation(obj)
        if obj.is_view_once:
            # Never expose a URL for view once media: it is fetched once
            # through /messages/<id>/view-once/ (see ViewOnceMediaAPIView).
            data["attachments"] = [
                {**attachment, "file": None} for attachment in data.get("attachments") or []
            ]
            if data.get("voice_note"):
                data["voice_note"] = {**data["voice_note"], "audio": None}
        return mask_read_state(data, obj.room_id, viewer_from_context(self.context))

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

        reply = obj.reply_to
        if reply.expires_at and reply.expires_at <= timezone.now():
            return None  # the quoted message has disappeared
        first_attachment = None
        if not reply.is_deleted:
            first_attachment = next(iter(reply.attachments.all()), None)

        return {
            "id": reply.id,
            "sender_id": reply.sender.id,
            "sender_phone": "" if reply.sender.is_deleted else reply.sender.phone_number,
            "sender_is_deleted": bool(reply.sender.is_deleted),
            "content": "" if reply.is_deleted else reply.content,
            "message_type": reply.message_type,
            "is_deleted": reply.is_deleted,
            "is_view_once": reply.is_view_once,
            "attachment": (
                {
                    "file": first_attachment.file.url if first_attachment.file and not reply.is_view_once else None,
                    "file_name": first_attachment.file_name,
                    "mime_type": first_attachment.mime_type,
                }
                if first_attachment
                else None
            ),
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

        starred_ids = self.context.get("starred_ids")
        if starred_ids is not None:
            return obj.id in starred_ids

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
            "sender_phone": "" if obj.forwarded_from.sender.is_deleted else obj.forwarded_from.sender.phone_number,
            "sender_is_deleted": bool(obj.forwarded_from.sender.is_deleted),
            "content": obj.forwarded_from.content,
            "message_type": obj.forwarded_from.message_type,
        }
    

    
    class Meta:
        model = Message

        fields = (
            "id",
            "room_id",
            "client_message_id",
            "sender",
            "message_type",
            "content",
            "reply_to",
            "attachments",
            "voice_note",
            "reactions",
            "is_edited",
            "is_deleted",
            "is_delivered",
            "delivered_at",
            "is_read",
            "read_at",
            "is_starred",
            "is_pinned",
            "pinned_at",
            "forwarded_from",
            "expires_at",
            "is_view_once",
            "view_once_opened_by",
            "link_preview",
            "mentions",
            "poll",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "sender",
            "attachments",
            "is_edited",
            "is_deleted",
            "is_delivered",
            "delivered_at",
            "is_read",
            "read_at",
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
            "client_message_id",

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
            from .features import validate_location_content

            attrs["content"] = json.dumps(validate_location_content(content))

        # -----------------------------
        # POLL
        # -----------------------------
        elif message_type == MessageType.POLL:
            from .features import validate_poll_content

            self._poll = validate_poll_content(content)
            attrs["content"] = self._poll["question"]

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

        if self.instance is None and attrs.get("room") is not None:
            from .features import validate_mentions

            self._mentions = validate_mentions(attrs["room"], self.initial_data.get("mentions"))

        return attrs

    def create(self, validated_data):
        from .features import create_poll, save_mentions

        request = self.context["request"]
        client_message_id = str(validated_data.pop("client_message_id", "") or "")[:64]
        if client_message_id:
            # Idempotent retry: the same client id in the same room returns the
            # message that was already stored instead of creating a duplicate.
            existing = Message.objects.filter(
                room=validated_data["room"],
                sender=request.user,
                client_message_id=client_message_id,
            ).first()
            if existing is not None:
                existing._was_duplicate = True
                return existing
        with transaction.atomic():
            message = Message.objects.create(
                sender=request.user,
                client_message_id=client_message_id,
                **validated_data,
            )
            if getattr(self, "_poll", None):
                create_poll(message, self._poll)
            save_mentions(message, getattr(self, "_mentions", []))
        return message

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

        from .group_events import is_group_event

        if is_group_event(original) or not original.room.participants.filter(
            user=request.user,
        ).exists():
            raise serializers.ValidationError(
                {
                    "message": (
                        "You cannot forward this message."
                    )
                }
            )

        if original.is_view_once or original.is_system:
            raise serializers.ValidationError(
                {"message": "View once media can't be forwarded."}
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
            link_preview=original.link_preview,
            reply_to=None,
        )

        from .features import copy_poll

        copy_poll(original, new_message)

        # Forwarded copies share the stored file; deletion only removes a file
        # once no other message references it (see soft_delete_messages_for_everyone).
        for attachment in original.attachments.all():
            Attachment.objects.create(
                message=new_message,
                file=attachment.file,
            )

        voice_note = getattr(original, "voice_note", None)
        if voice_note is not None:
            VoiceNote.objects.create(
                message=new_message,
                audio=voice_note.audio,
                duration=voice_note.duration,
                waveform=list(voice_note.waveform or []),
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

    client_message_id = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=64,
    )

    file = serializers.FileField()

    view_once = serializers.BooleanField(
        required=False,
        default=False,
    )

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
        Validate uploaded file: size, emptiness and allowed content types.
        """

        max_size = 25 * 1024 * 1024  # 25 MB

        if not getattr(file, "size", 0):
            raise serializers.ValidationError(
                "The selected file is empty."
            )

        if file.size > max_size:
            raise serializers.ValidationError(
                "Maximum file size is 25 MB."
            )

        content_type = str(getattr(file, "content_type", "") or "").lower()
        name = str(getattr(file, "name", "") or "").lower()
        blocked_extensions = (
            ".exe", ".bat", ".cmd", ".com", ".msi", ".scr", ".ps1", ".vbs", ".js", ".jar", ".sh",
        )
        if name.endswith(blocked_extensions) or content_type in (
            "application/x-msdownload",
            "application/x-msdos-program",
            "application/x-sh",
            "text/html",
            "application/javascript",
            "text/javascript",
        ):
            raise serializers.ValidationError(
                "This file type is not allowed."
            )

        return file

    def validate(
        self,
        attrs,
    ):
        """
        Validate the upload type and the reply message.
        """

        upload = attrs.get("file")
        message_type = attrs.get("message_type")
        content_type = str(getattr(upload, "content_type", "") or "").lower()
        if message_type == MessageType.IMAGE and content_type and not content_type.startswith("image/"):
            raise serializers.ValidationError({"file": "Photo messages require an image file."})
        if message_type == MessageType.VIDEO and content_type and not content_type.startswith("video/"):
            raise serializers.ValidationError({"file": "Video messages require a video file."})
        if message_type in (MessageType.TEXT, MessageType.LOCATION, MessageType.CONTACT, MessageType.POLL):
            raise serializers.ValidationError({"message_type": "Use IMAGE, VIDEO, DOCUMENT or STICKER for uploads."})
        if attrs.get("view_once") and message_type not in (MessageType.IMAGE, MessageType.VIDEO):
            raise serializers.ValidationError({"view_once": "Only photos and videos can be sent as view once."})

        from .features import validate_mentions

        attrs["mentions"] = validate_mentions(attrs["room"], self.initial_data.get("mentions"))

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

        client_message_id = str(validated_data.get("client_message_id") or "")[:64]
        if client_message_id:
            existing = Message.objects.filter(
                room=validated_data["room"],
                sender=request.user,
                client_message_id=client_message_id,
            ).first()
            if existing is not None:
                existing._was_duplicate = True
                return existing

        from .features import save_mentions

        with transaction.atomic():
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
                client_message_id=client_message_id,
                is_view_once=bool(validated_data.get("view_once")),
            )

            Attachment.objects.create(
                message=message,
                file=uploaded_file,
            )
            save_mentions(message, validated_data.get("mentions") or [])

        return message



# ==========================================================
# Chat Room
# ==========================================================

class ChatRoomSerializer(serializers.ModelSerializer):
    """
    Serializer for the chat list.

    Per-user state (pinned, favorite, archived, muted) comes from the
    requesting user's ``Participant`` row. ``ChatRoomListAPIView`` annotates
    ``_last_message_id`` and ``_unread_count`` and passes the latest messages in
    the serializer context so the list is built with a constant number of
    queries; other callers fall back to per-room queries.
    """

    participants = ParticipantSerializer(
        many=True,
        read_only=True,
    )

    participants_count = serializers.SerializerMethodField()
    created_by_id = serializers.IntegerField(read_only=True)
    last_message = serializers.SerializerMethodField()
    last_reaction = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    is_pinned = serializers.SerializerMethodField()
    pinned_at = serializers.SerializerMethodField()
    is_favorite = serializers.SerializerMethodField()
    is_archived = serializers.SerializerMethodField()
    is_muted = serializers.SerializerMethodField()
    muted_until = serializers.SerializerMethodField()
    unread_mention = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom
        fields = (
            "id",
            "name",
            "room_type",
            "description",
            "photo",
            "is_active",
            "edit_info_admins_only",
            "send_messages_admins_only",
            "add_members_admins_only",
            "created_by_id",
            "participants_count",
            "participants",
            "last_message",
            "last_reaction",
            "unread_count",
            "is_pinned",
            "pinned_at",
            "is_favorite",
            "is_archived",
            "is_muted",
            "muted_until",
            "disappearing_seconds",
            "unread_mention",
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

    # -- helpers ---------------------------------------------------------
    def _request_user(self):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        return request.user

    def _membership(self, obj):
        user = self._request_user()
        if user is None:
            return None
        cache = getattr(obj, "_membership_cache", None)
        if cache is None:
            cache = next(
                (p for p in obj.participants.all() if p.user_id == user.id),
                None,
            )
            obj._membership_cache = cache
        return cache

    def _blocked_ids(self):
        if "_blocked_ids" not in self.context:
            user = self._request_user()
            if user is None:
                ids = set()
            else:
                rows = BlockedUser.objects.filter(
                    Q(blocked_by=user) | Q(blocked_user=user)
                ).values_list("blocked_by_id", "blocked_user_id")
                rows = list(rows)
                ids = {blocked if blocker == user.id else blocker for blocker, blocked in rows}
                self.context["_blocked_me_ids"] = {blocker for blocker, blocked in rows if blocked == user.id}
            self.context["_blocked_ids"] = ids
        return self.context["_blocked_ids"]

    def to_representation(self, obj):
        data = super().to_representation(obj)
        blocked = self._blocked_ids()
        if blocked:
            # Like WhatsApp: no online / last seen across a block (either way).
            for participant in data.get("participants") or []:
                user = participant.get("user") or {}
                if user.get("id") in blocked and isinstance(user.get("profile"), dict):
                    user["profile"]["is_online"] = False
                    user["profile"]["last_seen"] = None
                    # Someone who blocked me also hides their photo from me.
                    if user.get("id") in self.context.get("_blocked_me_ids", ()):
                        user["profile"]["profile_picture"] = None
        return data

    # -- fields ----------------------------------------------------------
    def get_participants_count(self, obj):
        return len(obj.participants.all())

    def get_is_pinned(self, obj):
        membership = self._membership(obj)
        return bool(membership and membership.is_pinned)

    def get_pinned_at(self, obj):
        membership = self._membership(obj)
        return membership.pinned_at if membership and membership.pinned_at else None

    def get_is_favorite(self, obj):
        membership = self._membership(obj)
        return bool(membership and membership.is_favorite)

    def get_is_archived(self, obj):
        membership = self._membership(obj)
        return bool(membership and membership.is_archived)

    def get_is_muted(self, obj):
        membership = self._membership(obj)
        if not membership or not membership.is_muted:
            return False
        if membership.muted_until and membership.muted_until <= timezone.now():
            return False
        return True

    def get_muted_until(self, obj):
        membership = self._membership(obj)
        if not membership or not membership.is_muted:
            return None
        return membership.muted_until

    def get_last_message(self, obj):
        """
        Return the latest message this user can see in the room.
        """
        last_messages = self.context.get("last_messages")
        if last_messages is not None and hasattr(obj, "_last_message_id"):
            message = last_messages.get(obj._last_message_id)
        else:
            message = visible_messages_for_user(
                Message.objects.filter(room=obj),
                self._request_user(),
            ).order_by("-created_at", "-id").first()

        if not message:
            return None

        return MessageSerializer(
            message,
            context=self.context,
        ).data

    def get_last_reaction(self, obj):
        """
        The newest reaction in the chat when it is newer than the last message
        (the chat list then shows "Reacted 😂 to: …" like WhatsApp).
        """
        previews = self.context.get("last_reactions")
        if previews is None:
            previews = last_reaction_previews(self._request_user(), [obj], self.context)
        return previews.get(obj.pk)

    def get_unread_mention(self, obj):
        """True while an unread message in this chat @mentions the user."""
        if hasattr(obj, "_unread_mention"):
            return bool(obj._unread_mention)
        user = self._request_user()
        if user is None or obj.room_type != "GROUP":
            return False
        return unread_mentions_for_user(Message.objects.filter(room=obj), user).exists()

    def get_unread_count(self, obj):
        if hasattr(obj, "_unread_count"):
            return int(obj._unread_count or 0)
        user = self._request_user()
        if user is None:
            return 0
        return unread_messages_for_user(
            Message.objects.filter(room=obj),
            user,
        ).count()


def with_message_relations(queryset):
    """
    Load everything ``MessageSerializer`` touches in a fixed number of
    queries (no N+1): sender/profile, the replied and forwarded message with
    their senders, the voice note, attachments and reactions with their user.
    Every view that returns full messages goes through this one helper.
    """
    return queryset.select_related(
        "sender__profile",
        "reply_to__sender__profile",
        "forwarded_from__sender__profile",
        "voice_note",
        "poll",
    ).prefetch_related(
        "attachments",
        "reply_to__attachments",
        Prefetch("reactions", queryset=Reaction.objects.select_related("user")),
        "poll__options__votes",
        "mention_rows",
        "view_once_opens",
    )


def starred_ids_for(user, message_ids):
    """Ids among ``message_ids`` that ``user`` starred (one query)."""
    if not user or user.is_anonymous or not message_ids:
        return set()
    return set(
        StarredMessage.objects.filter(user=user, message_id__in=list(message_ids))
        .values_list("message_id", flat=True)
    )


def visible_messages_for_user(queryset, user):
    """
    Restrict a Message queryset to what ``user`` may see: excludes messages
    the user deleted for themselves and history hidden by Clear/Delete chat.
    """
    if user is None:
        return queryset
    cleared = ChatClear.objects.filter(
        room_id=OuterRef("room_id"),
        user=user,
        cleared_at__gte=OuterRef("created_at"),
    )
    hidden_for_me = DeletedMessage.objects.filter(
        message_id=OuterRef("pk"),
        user=user,
    )
    return queryset.filter(~Exists(cleared)).filter(~Exists(hidden_for_me))


def unread_messages_for_user(queryset, user):
    """Incoming, visible, not-yet-read messages for ``user``."""
    recipient_receipt = MessageReceipt.objects.filter(
        message_id=OuterRef("pk"), recipient_id=user.id,
    )
    recipient_read_receipt = MessageReceipt.objects.filter(
        message_id=OuterRef("pk"), recipient_id=user.id, read_at__isnull=False,
    )
    from .group_events import GROUP_EVENT_PREFIX

    return (
        visible_messages_for_user(queryset, user)
        .filter(is_deleted=False)
        .exclude(sender_id=user.id)
        # "X turned on disappearing messages" notices never count as unread.
        .exclude(content__startswith=SYSTEM_PREFIX)
        # group system messages ("X joined…") never count as unread
        .exclude(content__startswith=GROUP_EVENT_PREFIX)
        .annotate(
            _has_recipient_receipt=Exists(recipient_receipt),
            _recipient_has_read=Exists(recipient_read_receipt),
        )
        .filter(
            Q(_has_recipient_receipt=True, _recipient_has_read=False)
            | Q(_has_recipient_receipt=False, is_read=False)
        )
    )


def unread_mentions_for_user(queryset, user):
    """Unread messages that @mention ``user``."""
    return unread_messages_for_user(queryset.filter(mention_rows__user_id=user.id), user)


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

    def to_representation(self, obj):
        data = super().to_representation(obj)
        if obj.is_view_once:
            data["attachments"] = [{**item, "file": None} for item in data.get("attachments") or []]
        return data

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

def last_reaction_previews(user, rooms, context):
    """
    ``{room_id: {"emoji", "user_id", "created_at", "message"}}`` for rooms whose
    newest reaction is newer than their last visible message. A fixed number
    of queries whatever the number of rooms (used by the chat list).
    """
    if user is None or not rooms:
        return {}
    room_ids = [room.pk for room in rooms]
    latest_ids = {}
    for room in rooms:
        reaction_id = getattr(room, "_last_reaction_id", None)
        if reaction_id:
            latest_ids[room.pk] = reaction_id
    if not latest_ids and not any(hasattr(room, "_last_reaction_id") for room in rooms):
        latest = (
            Reaction.objects.filter(message__room_id=OuterRef("pk"), message__is_deleted=False)
            .order_by("-created_at", "-id")
            .values("id")[:1]
        )
        latest_ids = {
            row["pk"]: row["rid"]
            for row in ChatRoom.objects.filter(pk__in=room_ids).annotate(rid=Subquery(latest)).values("pk", "rid")
            if row["rid"]
        }
    if not latest_ids:
        return {}
    reactions = {
        reaction.id: reaction
        for reaction in Reaction.objects.filter(id__in=latest_ids.values()).select_related("message")
    }
    message_ids = [reaction.message_id for reaction in reactions.values()]
    hidden = set(DeletedMessage.objects.filter(user=user, message_id__in=message_ids).values_list("message_id", flat=True))
    cleared = dict(ChatClear.objects.filter(user=user, room_id__in=room_ids).values_list("room_id", "cleared_at"))
    last_times = dict(
        visible_messages_for_user(Message.objects.filter(room_id__in=room_ids), user)
        .values("room_id")
        .annotate(latest=Max("created_at"))
        .values_list("room_id", "latest")
    )
    messages = {message.id: message for message in with_message_relations(Message.objects.filter(id__in=message_ids))}
    previews = {}
    for room_id, reaction_id in latest_ids.items():
        reaction = reactions.get(reaction_id)
        if reaction is None or reaction.message_id in hidden:
            continue
        message = messages.get(reaction.message_id)
        if message is None:
            continue
        clear_time = cleared.get(room_id)
        if clear_time and message.created_at <= clear_time:
            continue
        last_time = last_times.get(room_id)
        if last_time and reaction.created_at <= last_time:
            continue
        previews[room_id] = {
            "emoji": reaction.emoji,
            "user_id": reaction.user_id,
            "created_at": reaction.created_at,
            "message": MessageSerializer(message, context=context).data,
        }
    return previews
