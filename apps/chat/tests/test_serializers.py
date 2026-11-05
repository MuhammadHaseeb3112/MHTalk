from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from apps.accounts.models import User
from apps.chat.choices import (
    MessageType,
    RoomType,
)
from apps.chat.models import (
    Attachment,
    ChatRoom,
    Message,
    Participant,
)
from apps.chat.serializers import (
    AttachmentSerializer,
    ChatRoomDetailSerializer,
    ChatRoomSerializer,
    MessageSerializer,
    ParticipantSerializer,
    SendMessageSerializer,
)

class AttachmentSerializerTest(TestCase):
    """
    Tests for AttachmentSerializer.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+923130067082",
            password="StrongPass123!",
        )

        self.room = ChatRoom.objects.create(
            created_by=self.user,
        )

        self.message = Message.objects.create(
            room=self.room,
            sender=self.user,
            content="Hello",
        )

        self.attachment = Attachment.objects.create(
            message=self.message,
            file=SimpleUploadedFile(
                "photo.jpg",
                b"dummy image",
                content_type="image/jpeg",
            ),
        )

    def test_serializer_contains_expected_fields(self):
        serializer = AttachmentSerializer(self.attachment)

        self.assertEqual(
            set(serializer.data.keys()),
            {
                "id",
                "file",
                "file_name",
                "file_size",
                "mime_type",
                "uploaded_at",
            },
        )

    def test_file_name_serialized(self):
        serializer = AttachmentSerializer(self.attachment)

        self.assertEqual(
            serializer.data["file_name"],
            "photo.jpg",
        )

    def test_file_size_is_greater_than_zero(self):
        self.assertGreater(
            self.attachment.file_size,
            0,
        )


class ParticipantSerializerTest(TestCase):
    """
    Tests for ParticipantSerializer.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+923130067082",
            password="StrongPass123!",
        )

        self.room = ChatRoom.objects.create(
            created_by=self.user,
        )

        self.participant = Participant.objects.create(
            room=self.room,
            user=self.user,
            is_admin=True,
        )

    def test_serializer_contains_expected_fields(self):
        serializer = ParticipantSerializer(self.participant)

        self.assertEqual(
            set(serializer.data.keys()),
            {
                "id",
                "user",
                "is_admin",
                "is_muted",
                "is_archived",
                "joined_at",
                "muted_until",
            },
        )

    def test_admin_flag(self):
        serializer = ParticipantSerializer(self.participant)

        self.assertTrue(
            serializer.data["is_admin"],
        )

    def test_nested_user_exists(self):
        serializer = ParticipantSerializer(self.participant)

        self.assertIn(
            "user",
            serializer.data,
        )


class MessageSerializerTest(TestCase):
    """
    Tests for MessageSerializer.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+923130067082",
            password="StrongPass123!",
        )

        self.room = ChatRoom.objects.create(
            created_by=self.user,
        )

        Participant.objects.create(
            room=self.room,
            user=self.user,
        )

        self.message = Message.objects.create(
            room=self.room,
            sender=self.user,
            content="Hello World",
        )

        self.attachment = Attachment.objects.create(
            message=self.message,
            file=SimpleUploadedFile(
                "image.jpg",
                b"dummy image",
                content_type="image/jpeg",
            ),
        )

    def test_serializer_contains_expected_fields(self):
        serializer = MessageSerializer(self.message)

        self.assertEqual(
            set(serializer.data.keys()),
            {
                "id",
                "sender",
                "message_type",
                "content",
                "attachments",
                "is_edited",
                "is_deleted",
                "created_at",
                "updated_at",
                "reply_to",
                "voice_note",
                "reactions",
                "is_starred",
                "is_pinned",
                "pinned_at",
                "forwarded_from",
                "expires_at",
                "is_view_once",
                "view_once_opened_by",
                "link_preview",
                "status_ref",
                "mentions",
                "poll",
                "room_id",
                "client_message_id",
                "is_delivered",
                "delivered_at",
                "is_read",
                "read_at",
            },
        )

    def test_sender_serialized(self):
        serializer = MessageSerializer(self.message)

        self.assertEqual(
            serializer.data["sender"]["phone_number"],
            self.user.phone_number,
        )

    def test_attachment_serialized(self):
        serializer = MessageSerializer(self.message)

        self.assertEqual(
            len(serializer.data["attachments"]),
            1,
        )

    def test_content_serialized(self):
        serializer = MessageSerializer(self.message)

        self.assertEqual(
            serializer.data["content"],
            "Hello World",
        )

    def test_default_message_type(self):
        serializer = MessageSerializer(self.message)

        self.assertEqual(
            serializer.data["message_type"],
            MessageType.TEXT,
        )

    def test_is_not_deleted_by_default(self):
        serializer = MessageSerializer(self.message)

        self.assertFalse(
            serializer.data["is_deleted"],
        )

    def test_is_not_edited_by_default(self):
        serializer = MessageSerializer(self.message)

        self.assertFalse(
            serializer.data["is_edited"],
        )


class SendMessageSerializerTest(TestCase):
    """
    Tests for SendMessageSerializer.
    """

    def setUp(self):
        self.factory = APIRequestFactory()

        self.user = User.objects.create_user(
            phone_number="+923130067082",
            password="StrongPass123!",
        )

        self.other_user = User.objects.create_user(
            phone_number="+923001112233",
            password="StrongPass123!",
        )

        self.room = ChatRoom.objects.create(
            created_by=self.user,
        )

        Participant.objects.create(
            room=self.room,
            user=self.user,
        )

    def test_valid_serializer(self):
        request = self.factory.post("/")

        request.user = self.user

        serializer = SendMessageSerializer(
            data={
                "room": self.room.id,
                "content": "Hello",
            },
            context={"request": request},
        )

        self.assertTrue(serializer.is_valid())

    def test_empty_text_message_is_invalid(self):
        request = self.factory.post("/")

        request.user = self.user

        serializer = SendMessageSerializer(
            data={
                "room": self.room.id,
                "content": "     ",
            },
            context={"request": request},
        )

        self.assertFalse(serializer.is_valid())

        self.assertIn(
            "content",
            serializer.errors,
        )

    def test_user_not_participant(self):
        request = self.factory.post("/")

        request.user = self.other_user

        serializer = SendMessageSerializer(
            data={
                "room": self.room.id,
                "content": "Hello",
            },
            context={"request": request},
        )

        self.assertFalse(serializer.is_valid())

        self.assertIn(
            "room",
            serializer.errors,
        )

    def test_create_message(self):
        request = self.factory.post("/")

        request.user = self.user

        serializer = SendMessageSerializer(
            data={
                "room": self.room.id,
                "content": "New Message",
            },
            context={"request": request},
        )

        self.assertTrue(serializer.is_valid())

        message = serializer.save()

        self.assertEqual(
            message.sender,
            self.user,
        )

        self.assertEqual(
            message.room,
            self.room,
        )

        self.assertEqual(
            message.content,
            "New Message",
        )

    def test_default_message_type(self):
        request = self.factory.post("/")

        request.user = self.user

        serializer = SendMessageSerializer(
            data={
                "room": self.room.id,
                "content": "Hello",
            },
            context={"request": request},
        )

        self.assertTrue(serializer.is_valid())

        message = serializer.save()

        self.assertEqual(
            message.message_type,
            MessageType.TEXT,
        )

    def test_whitespace_trimmed(self):
        request = self.factory.post("/")

        request.user = self.user

        serializer = SendMessageSerializer(
            data={
                "room": self.room.id,
                "content": "   Hello Django   ",
            },
            context={"request": request},
        )

        self.assertTrue(serializer.is_valid())

        message = serializer.save()

        self.assertEqual(
            message.content,
            "Hello Django",
        )



class ChatRoomSerializerTest(TestCase):
    """
    Tests for ChatRoomSerializer.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+923130067082",
            password="StrongPass123!",
        )

        self.room = ChatRoom.objects.create(
            name="Family",
            room_type=RoomType.GROUP,
            created_by=self.user,
        )

        Participant.objects.create(
            room=self.room,
            user=self.user,
            is_admin=True,
        )

        self.message = Message.objects.create(
            room=self.room,
            sender=self.user,
            content="Latest Message",
        )

    def test_serializer_contains_expected_fields(self):
        serializer = ChatRoomSerializer(self.room)

        self.assertEqual(
            set(serializer.data.keys()),
            {
                "id",
                "name",
                "room_type",
                "description",
                "photo",
                "is_active",
                "edit_info_admins_only",
                "send_messages_admins_only",
                "add_members_admins_only",
                "participants_count",
                "participants",
                "last_message",
                "last_reaction",
                "created_at",
                "updated_at",
                "created_by_id",
                "unread_count",
                "is_pinned",
                "pinned_at",
                "is_favorite",
                "is_archived",
                "is_muted",
                "muted_until",
                "disappearing_seconds",
                "unread_mention",
            },
        )

    def test_room_name(self):
        serializer = ChatRoomSerializer(self.room)

        self.assertEqual(
            serializer.data["name"],
            "Family",
        )

    def test_participants_count(self):
        serializer = ChatRoomSerializer(self.room)

        self.assertEqual(
            serializer.data["participants_count"],
            1,
        )

    def test_last_message_exists(self):
        serializer = ChatRoomSerializer(self.room)

        self.assertIsNotNone(
            serializer.data["last_message"],
        )

    def test_last_message_content(self):
        serializer = ChatRoomSerializer(self.room)

        self.assertEqual(
            serializer.data["last_message"]["content"],
            "Latest Message",
        )

    def test_participants_serialized(self):
        serializer = ChatRoomSerializer(self.room)

        self.assertEqual(
            len(serializer.data["participants"]),
            1,
        )


class ChatRoomDetailSerializerTest(TestCase):
    """
    Tests for ChatRoomDetailSerializer.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+923130067082",
            password="StrongPass123!",
        )

        self.room = ChatRoom.objects.create(
            name="Office",
            room_type=RoomType.GROUP,
            created_by=self.user,
        )

        Participant.objects.create(
            room=self.room,
            user=self.user,
            is_admin=True,
        )

        self.message = Message.objects.create(
            room=self.room,
            sender=self.user,
            content="Hello Team",
        )

    def test_serializer_contains_expected_fields(self):
        serializer = ChatRoomDetailSerializer(self.room)

        self.assertEqual(
            set(serializer.data.keys()),
            {
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
            },
        )

    def test_participants_serialized(self):
        serializer = ChatRoomDetailSerializer(self.room)

        self.assertEqual(
            len(serializer.data["participants"]),
            1,
        )

    def test_messages_serialized(self):
        serializer = ChatRoomDetailSerializer(self.room)

        self.assertEqual(
            len(serializer.data["messages"]),
            1,
        )

    def test_message_content(self):
        serializer = ChatRoomDetailSerializer(self.room)

        self.assertEqual(
            serializer.data["messages"][0]["content"],
            "Hello Team",
        )

    def test_created_by(self):
        serializer = ChatRoomDetailSerializer(self.room)

        self.assertEqual(
            serializer.data["created_by"],
            self.user.id,
        )

    def test_room_name(self):
        serializer = ChatRoomDetailSerializer(self.room)

        self.assertEqual(
            serializer.data["name"],
            "Office",
        )