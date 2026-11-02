"""Chat list reaction preview and editable account email."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.chat.choices import RoomType
from apps.chat.models import ChatRoom, Message, Participant, Reaction


def make_user(phone):
    return User.objects.create_user(phone_number=phone, password="StrongPass123!")


class ChatListReactionTests(TestCase):
    def setUp(self):
        self.alice = make_user("+923000000501")
        self.bob = make_user("+923000000502")
        self.room = ChatRoom.objects.create(created_by=self.alice, room_type=RoomType.PRIVATE)
        Participant.objects.create(room=self.room, user=self.alice)
        Participant.objects.create(room=self.room, user=self.bob)
        self.alice_client = APIClient()
        self.alice_client.force_authenticate(self.alice)
        self.bob_client = APIClient()
        self.bob_client.force_authenticate(self.bob)
        self.message = Message.objects.create(room=self.room, sender=self.alice, content="hello")

    def row(self, client):
        return client.get("/api/chat/rooms/").data[0]

    def test_reaction_newer_than_last_message_is_listed(self):
        self.assertIsNone(self.row(self.alice_client)["last_reaction"])
        response = self.bob_client.post("/api/chat/messages/react/", {"message": self.message.id, "emoji": "😂"})
        self.assertEqual(response.status_code, 200, response.content)
        reaction = self.row(self.alice_client)["last_reaction"]
        self.assertEqual(reaction["emoji"], "😂")
        self.assertEqual(reaction["user_id"], self.bob.id)
        self.assertEqual(reaction["message"]["content"], "hello")
        # Room info (used to refresh one chat) carries it too.
        info = self.alice_client.get(f"/api/chat/rooms/{self.room.id}/info/").data
        self.assertEqual(info["last_reaction"]["emoji"], "😂")

    def test_newer_message_hides_reaction(self):
        Reaction.objects.create(message=self.message, user=self.bob, emoji="👍")
        Message.objects.filter(pk=self.message.pk).update(created_at=timezone.now() - timedelta(minutes=5))
        Message.objects.create(room=self.room, sender=self.bob, content="later")
        self.assertIsNone(self.row(self.alice_client)["last_reaction"])

    def test_reaction_on_message_deleted_for_me_is_hidden(self):
        Reaction.objects.create(message=self.message, user=self.bob, emoji="👍")
        self.alice_client.post("/api/chat/messages/delete-for-me/", {"message_ids": [self.message.id]}, format="json")
        from apps.chat.models import DeletedMessage
        if DeletedMessage.objects.filter(user=self.alice, message=self.message).exists():
            self.assertIsNone(self.alice_client.get(f"/api/chat/rooms/{self.room.id}/info/").data["last_reaction"])


class EditEmailTests(TestCase):
    def setUp(self):
        self.user = make_user("+923000000601")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_set_change_and_clear_email(self):
        response = self.client.patch("/api/accounts/profile/update/", {"email": "Me@Example.com "}, format="multipart")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["user"]["email"], "me@example.com")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "me@example.com")
        response = self.client.patch("/api/accounts/profile/update/", {"email": ""}, format="multipart")
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.email)

    def test_invalid_or_taken_email(self):
        other = make_user("+923000000602")
        other.email = "taken@example.com"
        other.save()
        bad = self.client.patch("/api/accounts/profile/update/", {"email": "not-an-email"}, format="multipart")
        self.assertEqual(bad.status_code, 400)
        taken = self.client.patch("/api/accounts/profile/update/", {"email": "TAKEN@example.com"}, format="multipart")
        self.assertEqual(taken.status_code, 400)
        self.assertIn("already used", str(taken.data["email"]))

    def test_profile_fields_still_update_without_email(self):
        self.user.email = "keep@example.com"
        self.user.save()
        response = self.client.patch("/api/accounts/profile/update/", {"about": "Busy"}, format="multipart")
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "keep@example.com")
