from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.chat.choices import MessageType
from apps.chat.models import Attachment, ChatClear, ChatRoom, Message, Participant


class ChatDeletionAPITests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            phone_number="+923000000101", password="StrongPass123!"
        )
        self.bob = User.objects.create_user(
            phone_number="+923000000102", password="StrongPass123!"
        )
        self.room = ChatRoom.objects.create(created_by=self.alice)
        Participant.objects.create(room=self.room, user=self.alice)
        Participant.objects.create(room=self.room, user=self.bob)
        self.old_message = Message.objects.create(
            room=self.room, sender=self.alice, message_type=MessageType.TEXT,
            content="old history", client_message_id="",
        )
        self.alice_client = APIClient()
        self.alice_client.force_authenticate(self.alice)
        self.bob_client = APIClient()
        self.bob_client.force_authenticate(self.bob)

    def test_delete_chat_hides_history_only_for_requesting_user(self):
        response = self.alice_client.delete(f"/api/chat/rooms/{self.room.id}/delete/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ChatClear.objects.filter(room=self.room, user=self.alice).exists())

        alice_messages = self.alice_client.get(
            f"/api/chat/rooms/{self.room.id}/messages/"
        )
        bob_messages = self.bob_client.get(
            f"/api/chat/rooms/{self.room.id}/messages/"
        )
        self.assertEqual(alice_messages.status_code, 200)
        self.assertEqual(alice_messages.data, [])
        self.assertEqual(bob_messages.status_code, 200)
        self.assertEqual(len(bob_messages.data), 1)


    def test_clear_chat_hides_history_but_keeps_room_in_list(self):
        response = self.alice_client.post(f"/api/chat/rooms/{self.room.id}/clear/")
        self.assertEqual(response.status_code, 200)
        marker = ChatClear.objects.get(room=self.room, user=self.alice)
        self.assertFalse(marker.hide_from_list)

        rooms = self.alice_client.get("/api/chat/rooms/")
        self.assertEqual(rooms.status_code, 200)
        self.assertIn(self.room.id, [int(room["id"]) for room in rooms.data])
        history = self.alice_client.get(f"/api/chat/rooms/{self.room.id}/messages/")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.data, [])

    def test_delete_from_list_hides_until_new_message(self):
        response = self.alice_client.delete(f"/api/chat/rooms/{self.room.id}/delete/")
        self.assertEqual(response.status_code, 200)
        rooms = self.alice_client.get("/api/chat/rooms/")
        self.assertNotIn(self.room.id, [int(room["id"]) for room in rooms.data])

        Message.objects.create(
            room=self.room, sender=self.bob, message_type=MessageType.TEXT,
            content="fresh message",
        )
        rooms = self.alice_client.get("/api/chat/rooms/")
        self.assertIn(self.room.id, [int(room["id"]) for room in rooms.data])
        history = self.alice_client.get(f"/api/chat/rooms/{self.room.id}/messages/")
        self.assertEqual([message["content"] for message in history.data], ["fresh message"])

    def test_new_message_makes_cleared_chat_visible_without_old_history(self):
        self.alice_client.delete(f"/api/chat/rooms/{self.room.id}/delete/")
        new_message = Message.objects.create(
            room=self.room, sender=self.bob, message_type=MessageType.TEXT,
            content="new message",
        )
        Message.objects.filter(pk=new_message.pk).update(
            created_at=timezone.now() + timedelta(seconds=2)
        )
        rooms = self.alice_client.get("/api/chat/rooms/")
        self.assertEqual(rooms.status_code, 200)
        room_ids = [int(room["id"]) for room in rooms.data]
        self.assertIn(self.room.id, room_ids)
        visible = self.alice_client.get(f"/api/chat/rooms/{self.room.id}/messages/")
        self.assertEqual([message["content"] for message in visible.data], ["new message"])

    def test_bulk_delete_for_everyone_validates_all_ids_before_changing_any(self):
        other_message = Message.objects.create(
            room=self.room, sender=self.bob, message_type=MessageType.TEXT,
            content="not authored by Alice",
        )
        response = self.alice_client.post(
            "/api/chat/messages/delete-for-everyone/",
            {"room": self.room.id, "messages": [self.old_message.id, other_message.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.old_message.refresh_from_db()
        other_message.refresh_from_db()
        self.assertFalse(self.old_message.is_deleted)
        self.assertFalse(other_message.is_deleted)

    def test_bulk_delete_for_everyone_soft_deletes_authored_messages_and_removes_media(self):
        attachment = Attachment.objects.create(
            message=self.old_message,
            file="chat/attachments/removed-after-delete.png",
            mime_type="image/png",
        )
        response = self.alice_client.post(
            "/api/chat/messages/delete-for-everyone/",
            {"room": self.room.id, "messages": [self.old_message.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.old_message.refresh_from_db()
        self.assertTrue(self.old_message.is_deleted)
        self.assertEqual(self.old_message.content, "")
        self.assertFalse(Attachment.objects.filter(pk=attachment.pk).exists())

        history = self.alice_client.get(
            f"/api/chat/rooms/{self.room.id}/messages/"
        )
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.data), 1)
        self.assertTrue(history.data[0]["is_deleted"])
        self.assertEqual(history.data[0]["content"], "")
        self.assertEqual(history.data[0]["attachments"], [])
        rooms = self.alice_client.get("/api/chat/rooms/")
        self.assertEqual(rooms.status_code, 200)
        self.assertTrue(rooms.data[0]["last_message"]["is_deleted"])
        self.assertEqual(rooms.data[0]["last_message"]["content"], "")
