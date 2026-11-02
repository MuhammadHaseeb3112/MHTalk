from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.chat.choices import (
    MessageType,
    RoomType,
)
from apps.chat.models import (
    ChatRoom,
    Message,
    Participant,
)


class ChatRoomListAPIViewTest(APITestCase):
    """
    Tests for ChatRoomListAPIView.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+923130067082",
            password="StrongPass123!",
        )

        self.other_user = User.objects.create_user(
            phone_number="+923001112233",
            password="StrongPass123!",
        )

        self.room = ChatRoom.objects.create(
            room_type=RoomType.PRIVATE,
            created_by=self.user,
        )

        Participant.objects.create(
            room=self.room,
            user=self.user,
        )

        Participant.objects.create(
            room=self.room,
            user=self.other_user,
        )

        self.url = reverse("chat:room-list")

    def test_authenticated_user_can_list_rooms(self):
        """
        Authenticated users should receive
        their chat rooms.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            len(response.data),
            1,
        )

    def test_unauthenticated_user_cannot_list_rooms(self):
        """
        Anonymous users should not access
        the endpoint.
        """

        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_only_user_rooms_are_returned(self):
        """
        A user should only receive rooms
        they belong to.
        """

        third_user = User.objects.create_user(
            phone_number="+923451234567",
            password="StrongPass123!",
        )

        another_room = ChatRoom.objects.create(
            room_type=RoomType.PRIVATE,
            created_by=third_user,
        )

        Participant.objects.create(
            room=another_room,
            user=third_user,
        )

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.get(self.url)

        self.assertEqual(
            len(response.data),
            1,
        )

    def test_inactive_rooms_not_returned(self):
        """
        Inactive rooms should not appear.
        """

        self.room.is_active = False
        self.room.save()

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.get(self.url)

        self.assertEqual(
            len(response.data),
            0,
        )


class ChatRoomDetailAPIViewTest(APITestCase):
    """
    Tests for ChatRoomDetailAPIView.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+923130067082",
            password="StrongPass123!",
        )

        self.other_user = User.objects.create_user(
            phone_number="+923001112233",
            password="StrongPass123!",
        )

        self.third_user = User.objects.create_user(
            phone_number="+923451234567",
            password="StrongPass123!",
        )

        self.room = ChatRoom.objects.create(
            room_type=RoomType.PRIVATE,
            created_by=self.user,
        )

        Participant.objects.create(
            room=self.room,
            user=self.user,
        )

        Participant.objects.create(
            room=self.room,
            user=self.other_user,
        )

        Message.objects.create(
            room=self.room,
            sender=self.user,
            content="Hello",
        )

        self.url = reverse(
            "chat:room-detail",
            kwargs={
                "pk": self.room.pk,
            },
        )

    def test_authenticated_user_can_view_room(self):
        """
        A participant should be able to
        retrieve the room details.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

    def test_non_participant_cannot_view_room(self):
        """
        Users outside the room should not
        access the room details.
        """

        self.client.force_authenticate(
            user=self.third_user,
        )

        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_unauthenticated_user_cannot_view_room(self):
        """
        Anonymous users should receive 401.
        """

        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_inactive_room_not_found(self):
        """
        Inactive rooms should not be returned.
        """

        self.room.is_active = False
        self.room.save()

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_invalid_room_returns_404(self):
        """
        Invalid room id should return 404.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.get(
            reverse(
                "chat:room-detail",
                kwargs={
                    "pk": 9999,
                },
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_room_contains_participants(self):
        """
        Participants should be included
        in the response.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.get(self.url)

        self.assertIn(
            "participants",
            response.data,
        )

    def test_room_contains_messages(self):
        """
        Messages should be included
        in the response.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.get(self.url)

        self.assertIn(
            "messages",
            response.data,
        )


class MessageListAPIViewTest(APITestCase):
    """
    Tests for MessageListAPIView.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+923130067082",
            password="StrongPass123!",
        )

        self.other_user = User.objects.create_user(
            phone_number="+923001112233",
            password="StrongPass123!",
        )

        self.third_user = User.objects.create_user(
            phone_number="+923451234567",
            password="StrongPass123!",
        )

        self.room = ChatRoom.objects.create(
            room_type=RoomType.PRIVATE,
            created_by=self.user,
        )

        Participant.objects.create(
            room=self.room,
            user=self.user,
        )

        Participant.objects.create(
            room=self.room,
            user=self.other_user,
        )

        self.message1 = Message.objects.create(
            room=self.room,
            sender=self.user,
            content="Hello",
        )

        self.message2 = Message.objects.create(
            room=self.room,
            sender=self.other_user,
            content="Hi",
        )

        self.url = reverse(
            "chat:message-list",
            kwargs={
                "room_id": self.room.pk,
            },
        )

    def test_authenticated_user_can_list_messages(self):
        """
        Room participants should receive messages.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            len(response.data),
            2,
        )

    def test_unauthenticated_user_cannot_list_messages(self):
        """
        Anonymous users should receive 401.
        """

        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_non_participant_cannot_view_messages(self):
        """
        Users outside the room should not
        receive any messages.
        """

        self.client.force_authenticate(
            user=self.third_user,
        )

        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            len(response.data),
            0,
        )

    def test_deleted_messages_are_returned_as_tombstones(self):
        """
        Messages deleted for everyone stay in the history as a
        tombstone ("This message was deleted") with no content.
        """

        self.message2.is_deleted = True
        self.message2.content = ""
        self.message2.save()

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.get(self.url)

        self.assertEqual(
            len(response.data),
            2,
        )
        tombstone = next(item for item in response.data if item["id"] == self.message2.id)
        self.assertTrue(tombstone["is_deleted"])
        self.assertEqual(tombstone["content"], "")

    def test_message_history_supports_limit_and_before(self):
        self.client.force_authenticate(user=self.user)

        newest = self.client.get(self.url, {"limit": 1})
        self.assertEqual(len(newest.data), 1)
        self.assertEqual(newest.data[0]["id"], self.message2.id)

        older = self.client.get(self.url, {"limit": 1, "before": self.message2.id})
        self.assertEqual(len(older.data), 1)
        self.assertEqual(older.data[0]["id"], self.message1.id)

    def test_messages_are_ordered_by_created_at(self):
        """
        Messages should be returned in
        chronological order.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.get(self.url)

        self.assertEqual(
            response.data[0]["content"],
            "Hello",
        )

        self.assertEqual(
            response.data[1]["content"],
            "Hi",
        )

    def test_invalid_room_returns_empty_queryset(self):
        """
        Invalid room id should return
        an empty list.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.get(
            reverse(
                "chat:message-list",
                kwargs={
                    "room_id": 9999,
                },
            ),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            len(response.data),
            0,
        )

    def test_response_contains_expected_fields(self):
        """
        Serialized messages should contain
        the expected fields.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.get(self.url)

        self.assertIn(
            "id",
            response.data[0],
        )

        self.assertIn(
            "sender",
            response.data[0],
        )

        self.assertIn(
            "content",
            response.data[0],
        )

        self.assertIn(
            "message_type",
            response.data[0],
        )


class SendMessageAPIViewTest(APITestCase):
    """
    Tests for SendMessageAPIView.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+923130067082",
            password="StrongPass123!",
        )

        self.other_user = User.objects.create_user(
            phone_number="+923001112233",
            password="StrongPass123!",
        )

        self.third_user = User.objects.create_user(
            phone_number="+923451234567",
            password="StrongPass123!",
        )

        self.room = ChatRoom.objects.create(
            room_type=RoomType.PRIVATE,
            created_by=self.user,
        )

        Participant.objects.create(
            room=self.room,
            user=self.user,
        )

        Participant.objects.create(
            room=self.room,
            user=self.other_user,
        )

        self.url = reverse(
            "chat:message-create",
        )

    def test_authenticated_user_can_send_message(self):
        """
        A room participant can send a message.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        payload = {
            "room": self.room.pk,
            "content": "Hello Django!",
        }

        response = self.client.post(
            self.url,
            payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            Message.objects.count(),
            1,
        )

        message = Message.objects.get(
            sender=self.user,
        )

        self.assertEqual(
            message.content,
            "Hello Django!",
        )

    def test_unauthenticated_user_cannot_send_message(self):
        """
        Anonymous users should receive 401.
        """

        payload = {
            "room": self.room.pk,
            "content": "Hello",
        }

        response = self.client.post(
            self.url,
            payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_sender_is_authenticated_user(self):
        """
        The sender should automatically be
        the authenticated user.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.post(
            self.url,
            {
                "room": self.room.pk,
                "content": "Automatic Sender",
            },
            format="json",
        )

        message = Message.objects.get()

        self.assertEqual(
            message.sender,
            self.user,
        )

    def test_message_belongs_to_correct_room(self):
        """
        The created message should belong
        to the specified room.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        self.client.post(
            self.url,
            {
                "room": self.room.pk,
                "content": "Room Test",
            },
            format="json",
        )

        message = Message.objects.get()

        self.assertEqual(
            message.room,
            self.room,
        )

    def test_empty_message_is_invalid(self):
        """
        Empty text messages should be rejected.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.post(
            self.url,
            {
                "room": self.room.pk,
                "content": "",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_whitespace_message_is_invalid(self):
        """
        Whitespace-only messages should be rejected.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.post(
            self.url,
            {
                "room": self.room.pk,
                "content": "      ",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_non_participant_cannot_send_message(self):
        """
        Users outside the room should not
        be allowed to send messages.
        """

        self.client.force_authenticate(
            user=self.third_user,
        )

        response = self.client.post(
            self.url,
            {
                "room": self.room.pk,
                "content": "Unauthorized",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_response_contains_message_data(self):
        """
        Successful responses should contain
        the serialized message.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.post(
            self.url,
            {
                "room": self.room.pk,
                "content": "Testing Response",
            },
            format="json",
        )

        self.assertIn(
            "message",
            response.data,
        )

        self.assertIn(
            "data",
            response.data,
        )

        self.assertEqual(
    response.data["message"],
    "Message sent successfully.",
)
        
        self.assertEqual(
    response.data["data"]["content"],
    "Testing Response",
)
        
    def test_message_content_is_trimmed(self):
        self.client.force_authenticate(
            user=self.user,
        )

        self.client.post(
            self.url,
            {
                "room": self.room.pk,
                "content": "   Hello Django   ",
            },
            format="json",
        )

        message = Message.objects.get(
            sender=self.user,
        )

        self.assertEqual(
            message.content,
            "Hello Django",
        )

    def test_default_message_type_is_text(self):
        """
        Messages should default to TEXT.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        self.client.post(
            self.url,
            {
                "room": self.room.pk,
                "content": "Hello",
            },
            format="json",
        )

        message = Message.objects.get(
            sender=self.user,
        )

        self.assertEqual(
            message.message_type,
            MessageType.TEXT,
        )


class UpdateMessageAPIViewTest(APITestCase):
    """
    Tests for UpdateMessageAPIView.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+923130067082",
            password="StrongPass123!",
        )

        self.other_user = User.objects.create_user(
            phone_number="+923001112233",
            password="StrongPass123!",
        )

        self.room = ChatRoom.objects.create(
            room_type=RoomType.PRIVATE,
            created_by=self.user,
        )

        Participant.objects.create(
            room=self.room,
            user=self.user,
        )

        Participant.objects.create(
            room=self.room,
            user=self.other_user,
        )

        self.message = Message.objects.create(
            room=self.room,
            sender=self.user,
            content="Old Message",
        )

        self.url = reverse(
            "chat:message-update",
            kwargs={
                "pk": self.message.pk,
            },
        )

    def test_owner_can_update_message(self):
        """
        Message owner should be able
        to update the message.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.patch(
            self.url,
            {
                "content": "Updated Message",
            },
            format="json",
        )

        self.message.refresh_from_db()

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            self.message.content,
            "Updated Message",
        )

    def test_message_marked_as_edited(self):
        """
        Updated messages should be
        marked as edited.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        self.client.patch(
            self.url,
            {
                "content": "Edited",
            },
            format="json",
        )

        self.message.refresh_from_db()

        self.assertTrue(
            self.message.is_edited,
        )

    def test_other_user_cannot_update_message(self):
        """
        Other users cannot update
        someone else's message.
        """

        self.client.force_authenticate(
            user=self.other_user,
        )

        response = self.client.patch(
            self.url,
            {
                "content": "Hack",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_guest_cannot_update_message(self):
        """
        Anonymous users cannot
        update messages.
        """

        response = self.client.patch(
            self.url,
            {
                "content": "Hack",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_empty_message_is_invalid(self):
        """
        Empty messages should not
        be accepted.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.patch(
            self.url,
            {
                "content": "",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )


class DeleteMessageAPIViewTest(APITestCase):
    """
    Tests for DeleteMessageAPIView.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+923130067082",
            password="StrongPass123!",
        )

        self.other_user = User.objects.create_user(
            phone_number="+923001112233",
            password="StrongPass123!",
        )

        self.room = ChatRoom.objects.create(
            room_type=RoomType.PRIVATE,
            created_by=self.user,
        )

        Participant.objects.create(
            room=self.room,
            user=self.user,
        )

        Participant.objects.create(
            room=self.room,
            user=self.other_user,
        )

        self.message = Message.objects.create(
            room=self.room,
            sender=self.user,
            content="Delete Me",
        )

        self.url = reverse(
            "chat:message-delete",
            kwargs={
                "pk": self.message.pk,
            },
        )

    def test_owner_can_delete_message(self):
        """
        Message owner should be able
        to soft delete a message.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.delete(
            self.url,
        )

        self.message.refresh_from_db()

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertTrue(
            self.message.is_deleted,
        )

    def test_message_not_removed_from_database(self):
        """
        Soft delete should not remove
        the database record.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        self.client.delete(
            self.url,
        )

        self.assertEqual(
            Message.objects.count(),
            1,
        )

    def test_other_user_cannot_delete_message(self):
        """
        Other users cannot delete
        someone else's message.
        """

        self.client.force_authenticate(
            user=self.other_user,
        )

        response = self.client.delete(
            self.url,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_guest_cannot_delete_message(self):
        """
        Anonymous users cannot
        delete messages.
        """

        response = self.client.delete(
            self.url,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_deleting_already_deleted_message_returns_404(self):
        """
        Deleted messages should not
        be deleted twice.
        """

        self.message.is_deleted = True
        self.message.save()

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.delete(
            self.url,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

class CreatePrivateChatAPIViewTest(APITestCase):
    """
    Tests for CreatePrivateChatAPIView.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+923130067082",
            password="StrongPass123!",
        )

        self.other_user = User.objects.create_user(
            phone_number="+923001112233",
            password="StrongPass123!",
        )

        self.third_user = User.objects.create_user(
            phone_number="+923451234567",
            password="StrongPass123!",
        )

        self.url = reverse(
            "chat:private-room-create",
        )

    def test_create_private_chat(self):
        """
        Authenticated users should be able
        to create a private chat.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.post(
            self.url,
            {
                "user_id": self.other_user.id,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            ChatRoom.objects.count(),
            1,
        )

        self.assertEqual(
            Participant.objects.count(),
            2,
        )

    def test_existing_private_chat_is_returned(self):
        """
        Creating the same private chat twice
        should return the existing room.
        """

        room = ChatRoom.objects.create(
            room_type=RoomType.PRIVATE,
            created_by=self.user,
        )

        Participant.objects.create(
            room=room,
            user=self.user,
        )

        Participant.objects.create(
            room=room,
            user=self.other_user,
        )

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.post(
            self.url,
            {
                "user_id": self.other_user.id,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            ChatRoom.objects.count(),
            1,
        )

    def test_user_cannot_chat_with_self(self):
        """
        Users should not be able to create
        a private chat with themselves.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.post(
            self.url,
            {
                "user_id": self.user.id,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_invalid_user_returns_404(self):
        """
        Invalid users should return 404.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.post(
            self.url,
            {
                "user_id": 9999,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_missing_user_id(self):
        """
        user_id is required.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.post(
            self.url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_unauthenticated_user(self):
        """
        Anonymous users cannot create chats.
        """

        response = self.client.post(
            self.url,
            {
                "user_id": self.other_user.id,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_private_room_type(self):
        """
        Newly created rooms should be PRIVATE.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        self.client.post(
            self.url,
            {
                "user_id": self.other_user.id,
            },
            format="json",
        )

        room = ChatRoom.objects.first()

        self.assertEqual(
            room.room_type,
            RoomType.PRIVATE,
        )

    def test_creator_is_request_user(self):
        """
        The authenticated user should become
        the room creator.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        self.client.post(
            self.url,
            {
                "user_id": self.other_user.id,
            },
            format="json",
        )

        room = ChatRoom.objects.first()

        self.assertEqual(
            room.created_by,
            self.user,
        )

    def test_two_participants_created(self):
        """
        Exactly two participants should be
        added to the private room.
        """

        self.client.force_authenticate(
            user=self.user,
        )

        self.client.post(
            self.url,
            {
                "user_id": self.other_user.id,
            },
            format="json",
        )

        room = ChatRoom.objects.first()

        self.assertEqual(
            room.participants.count(),
            2,
        )


class CreateGroupChatAPIViewTest(APITestCase):
    """
    Tests for CreateGroupChatAPIView.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+923130067082",
            password="StrongPass123!",
        )

        self.url = reverse(
            "chat:group-room-create",
        )

    def test_create_group_successfully(self):
        self.client.force_authenticate(
            user=self.user,
        )

        response = self.client.post(
            self.url,
            {
                "name": "Family",
                "description": "Family Group",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        participant = Participant.objects.get()

        self.assertEqual(
            participant.user,
            self.user,
        )

        self.assertTrue(
            participant.is_admin,
        )

    def test_group_creator_becomes_admin(self):
        self.client.force_authenticate(user=self.user)

        self.client.post(
            self.url,
            {
                "name": "Office",
            },
            format="json",
        )

        participant = Participant.objects.get(
            user=self.user,
        )

        self.assertTrue(
            participant.is_admin,
        )

    def test_group_room_type(self):
        self.client.force_authenticate(user=self.user)

        self.client.post(
            self.url,
            {
                "name": "Office",
            },
            format="json",
        )

        room = ChatRoom.objects.first()

        self.assertEqual(
            room.room_type,
            RoomType.GROUP,
        )

    def test_group_name_required(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_guest_cannot_create_group(self):
        response = self.client.post(
            self.url,
            {
                "name": "Family",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_creator_added_as_participant(self):
        self.client.force_authenticate(user=self.user)

        self.client.post(
            self.url,
            {
                "name": "Friends",
            },
            format="json",
        )

        self.assertEqual(
            Participant.objects.count(),
            1,
        )


class AddParticipantAPIViewTest(APITestCase):
    """
    Tests for AddParticipantAPIView.
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            phone_number="+923130067082",
            password="StrongPass123!",
        )

        self.member = User.objects.create_user(
            phone_number="+923001112233",
            password="StrongPass123!",
        )

        self.new_user = User.objects.create_user(
            phone_number="+923451234567",
            password="StrongPass123!",
        )

        self.room = ChatRoom.objects.create(
            name="Family",
            room_type=RoomType.GROUP,
            created_by=self.admin,
        )

        Participant.objects.create(
            room=self.room,
            user=self.admin,
            is_admin=True,
        )

        Participant.objects.create(
            room=self.room,
            user=self.member,
        )

        self.url = reverse(
            "chat:participant-add",
            kwargs={
                "room_id": self.room.pk,
            },
        )

    def test_admin_can_add_participant(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.url,
            {
                "user_id": self.new_user.id,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertTrue(
            Participant.objects.filter(
                room=self.room,
                user=self.new_user,
            ).exists()
        )

    def test_non_admin_cannot_add_participant(self):
        self.client.force_authenticate(user=self.member)

        response = self.client.post(
            self.url,
            {
                "user_id": self.new_user.id,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_duplicate_participant(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.url,
            {
                "user_id": self.member.id,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_invalid_user(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.url,
            {
                "user_id": 9999,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_guest_cannot_add_participant(self):
        response = self.client.post(
            self.url,
            {
                "user_id": self.new_user.id,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

class RemoveParticipantAPIViewTest(APITestCase):
    """
    Tests for RemoveParticipantAPIView.
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            phone_number="+923130067082",
            password="StrongPass123!",
        )

        self.member = User.objects.create_user(
            phone_number="+923001112233",
            password="StrongPass123!",
        )

        self.other_admin = User.objects.create_user(
            phone_number="+923451234567",
            password="StrongPass123!",
        )

        self.room = ChatRoom.objects.create(
            name="Office",
            room_type=RoomType.GROUP,
            created_by=self.admin,
        )

        Participant.objects.create(
            room=self.room,
            user=self.admin,
            is_admin=True,
        )

        Participant.objects.create(
            room=self.room,
            user=self.other_admin,
            is_admin=True,
        )

        Participant.objects.create(
            room=self.room,
            user=self.member,
        )

    def test_admin_can_remove_participant(self):
        self.client.force_authenticate(user=self.admin)

        url = reverse(
            "chat:participant-remove",
            kwargs={
                "room_id": self.room.pk,
                "user_id": self.member.pk,
            },
        )

        response = self.client.delete(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertFalse(
            Participant.objects.filter(
                room=self.room,
                user=self.member,
            ).exists()
        )

    def test_non_admin_cannot_remove(self):
        self.client.force_authenticate(user=self.member)

        url = reverse(
            "chat:participant-remove",
            kwargs={
                "room_id": self.room.pk,
                "user_id": self.other_admin.pk,
            },
        )

        response = self.client.delete(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_creator_cannot_be_removed(self):
        self.client.force_authenticate(user=self.other_admin)

        url = reverse(
            "chat:participant-remove",
            kwargs={
                "room_id": self.room.pk,
                "user_id": self.admin.pk,
            },
        )

        response = self.client.delete(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_invalid_participant(self):
        self.client.force_authenticate(user=self.admin)

        url = reverse(
            "chat:participant-remove",
            kwargs={
                "room_id": self.room.pk,
                "user_id": 9999,
            },
        )

        response = self.client.delete(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_guest_cannot_remove(self):
        url = reverse(
            "chat:participant-remove",
            kwargs={
                "room_id": self.room.pk,
                "user_id": self.member.pk,
            },
        )

        response = self.client.delete(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

class LeaveGroupAPIViewTest(APITestCase):
    """
    Tests for LeaveGroupAPIView.
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            phone_number="+923130067082",
            password="StrongPass123!",
        )

        self.member = User.objects.create_user(
            phone_number="+923001112233",
            password="StrongPass123!",
        )

        self.room = ChatRoom.objects.create(
            name="Friends",
            room_type=RoomType.GROUP,
            created_by=self.admin,
        )

        Participant.objects.create(
            room=self.room,
            user=self.admin,
            is_admin=True,
        )

        Participant.objects.create(
            room=self.room,
            user=self.member,
        )

        self.url = reverse(
            "chat:leave-group",
            kwargs={
                "room_id": self.room.pk,
            },
        )

    def test_member_can_leave_group(self):
        self.client.force_authenticate(
            user=self.member,
        )

        response = self.client.post(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertFalse(
            Participant.objects.filter(
                room=self.room,
                user=self.member,
            ).exists()
        )

    def test_admin_can_leave_group(self):
        self.client.force_authenticate(
            user=self.admin,
        )

        response = self.client.post(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

    def test_non_participant_cannot_leave(self):
        outsider = User.objects.create_user(
            phone_number="+923111111111",
            password="StrongPass123!",
        )

        self.client.force_authenticate(
            user=outsider,
        )

        response = self.client.post(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_guest_cannot_leave(self):
        response = self.client.post(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_last_admin_promotes_new_admin(self):
        self.client.force_authenticate(
            user=self.admin,
        )

        self.client.post(self.url)

        participant = Participant.objects.get(
            room=self.room,
            user=self.member,
        )

        self.assertTrue(
            participant.is_admin,
        )