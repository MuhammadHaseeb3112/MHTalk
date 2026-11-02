from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase

from apps.accounts.models import User
from apps.chat.choices import MessageType, RoomType
from apps.chat.models import (
    Attachment,
    ChatRoom,
    Message,
    Participant,
)


class ChatRoomModelTest(TestCase):
    """
    Tests for the ChatRoom model.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+923130067082",
            password="StrongPass123!",
        )

    def test_create_private_room(self):
        room = ChatRoom.objects.create(
            created_by=self.user,
        )

        self.assertEqual(room.room_type, RoomType.PRIVATE)
        self.assertTrue(room.is_active)

    def test_create_group_room(self):
        room = ChatRoom.objects.create(
            name="Family",
            room_type=RoomType.GROUP,
            created_by=self.user,
        )

        self.assertEqual(room.name, "Family")
        self.assertEqual(room.room_type, RoomType.GROUP)

    def test_private_room_string_representation(self):
        room = ChatRoom.objects.create(
            created_by=self.user,
        )

        self.assertIn("Private Room", str(room))

    def test_group_room_string_representation(self):
        room = ChatRoom.objects.create(
            name="Office",
            room_type=RoomType.GROUP,
            created_by=self.user,
        )

        self.assertEqual(str(room), "Office")


class ParticipantModelTest(TestCase):
    """
    Tests for the Participant model.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+923130067082",
            password="StrongPass123!",
        )

        self.room = ChatRoom.objects.create(
            created_by=self.user,
        )

    def test_create_participant(self):
        participant = Participant.objects.create(
            room=self.room,
            user=self.user,
        )

        self.assertFalse(participant.is_admin)
        self.assertFalse(participant.is_muted)
        self.assertFalse(participant.is_archived)

    def test_participant_string_representation(self):
        participant = Participant.objects.create(
            room=self.room,
            user=self.user,
        )

        self.assertEqual(
            str(participant),
            f"{self.user.phone_number} • {self.room}",
        )

    def test_unique_room_participant_constraint(self):
        Participant.objects.create(
            room=self.room,
            user=self.user,
        )

        with self.assertRaises(IntegrityError):
            Participant.objects.create(
                room=self.room,
                user=self.user,
            )


class MessageModelTest(TestCase):
    """
    Tests for the Message model.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+923130067082",
            password="StrongPass123!",
        )

        self.room = ChatRoom.objects.create(
            created_by=self.user,
        )

    def test_create_text_message(self):
        message = Message.objects.create(
            room=self.room,
            sender=self.user,
            content="Hello World",
        )

        self.assertEqual(
            message.message_type,
            MessageType.TEXT,
        )

        self.assertEqual(
            message.content,
            "Hello World",
        )

        self.assertFalse(message.is_deleted)
        self.assertFalse(message.is_edited)

    def test_create_image_message(self):
        message = Message.objects.create(
            room=self.room,
            sender=self.user,
            message_type=MessageType.IMAGE,
        )

        self.assertEqual(
            message.message_type,
            MessageType.IMAGE,
        )

    def test_message_string_representation(self):
        message = Message.objects.create(
            room=self.room,
            sender=self.user,
            content="Hello",
        )

        self.assertEqual(
            str(message),
            f"{self.user.phone_number}: {MessageType.TEXT}",
        )


class AttachmentModelTest(TestCase):
    """
    Tests for the Attachment model.
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
            content="Image",
        )

    def test_create_attachment(self):
        uploaded_file = SimpleUploadedFile(
            "photo.jpg",
            b"dummy image content",
            content_type="image/jpeg",
        )

        attachment = Attachment.objects.create(
            message=self.message,
            file=uploaded_file,
        )

        self.assertEqual(
            attachment.file_name,
            "photo.jpg",
        )

        self.assertEqual(
            attachment.mime_type,
            "image/jpeg",
        )

        self.assertGreater(
            attachment.file_size,
            0,
        )

    def test_attachment_string_representation(self):
        uploaded_file = SimpleUploadedFile(
            "resume.pdf",
            b"dummy pdf",
            content_type="application/pdf",
        )

        attachment = Attachment.objects.create(
            message=self.message,
            file=uploaded_file,
        )

        self.assertEqual(
            str(attachment),
            "resume.pdf",
        )