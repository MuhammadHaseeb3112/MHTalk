"""
WhatsApp-style blocking.

When Alice blocks Bob:
* Bob can still send, but Alice never receives it (Bob keeps one tick),
  not even after she unblocks; messages sent after unblocking arrive.
* Alice cannot message or call Bob until she unblocks.
* Bob's calls never ring for Alice and leave nothing in her call history.
* Neither sees the other's status or online / last seen.
"""

from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.calls.models import CallParticipant
from apps.chat.choices import RoomType
from apps.chat.models import ChatRoom, Message, MessageReceipt, Participant
from apps.chat.utils import persist_message_receipt


def make_user(phone):
    return User.objects.create_user(phone_number=phone, password="StrongPass123!")


class BlockingTests(TestCase):
    def setUp(self):
        self.alice = make_user("+923000000801")
        self.bob = make_user("+923000000802")
        self.room = ChatRoom.objects.create(created_by=self.alice, room_type=RoomType.PRIVATE)
        Participant.objects.create(room=self.room, user=self.alice)
        Participant.objects.create(room=self.room, user=self.bob)
        self.a = APIClient()
        self.a.force_authenticate(self.alice)
        self.b = APIClient()
        self.b.force_authenticate(self.bob)

    def block(self):
        response = self.a.post("/api/chat/users/block/", {"user": self.bob.id}, format="json")
        self.assertIn(response.status_code, (200, 201), response.content)

    def unblock(self):
        response = self.a.post("/api/chat/users/unblock/", {"user": self.bob.id}, format="json")
        self.assertIn(response.status_code, (200, 201, 204), response.content)

    def send(self, client, text):
        return client.post("/api/chat/messages/", {"room": self.room.id, "content": text}, format="json")

    def alice_messages(self):
        response = self.a.get(f"/api/chat/rooms/{self.room.id}/messages/")
        self.assertEqual(response.status_code, 200)
        data = response.data
        rows = data.get("results", data) if isinstance(data, dict) else data
        return [row["content"] for row in rows]

    def test_blocked_sender_is_accepted_but_hidden_and_never_delivered(self):
        self.block()
        response = self.send(self.b, "are you there?")
        self.assertEqual(response.status_code, 201, response.content)
        message = Message.objects.get(content="are you there?")

        self.assertNotIn("are you there?", self.alice_messages())
        # Alice coming online must not deliver it: Bob keeps a single tick.
        self.assertIsNone(persist_message_receipt(message.id, self.alice.id, "delivered"))
        self.assertFalse(
            MessageReceipt.objects.filter(message=message, delivered_at__isnull=False).exists()
        )
        rooms = self.a.get("/api/chat/rooms/").data
        rooms = rooms.get("results", rooms) if isinstance(rooms, dict) else rooms
        room = next(r for r in rooms if r["id"] == self.room.id)
        self.assertEqual(room["unread_count"], 0)

    def test_blocker_cannot_send(self):
        self.block()
        response = self.send(self.a, "hi")
        self.assertEqual(response.status_code, 403)

    def test_after_unblock_only_new_messages_arrive(self):
        self.block()
        self.send(self.b, "sent while blocked")
        self.unblock()
        self.send(self.b, "sent after unblock")
        messages = self.alice_messages()
        self.assertIn("sent after unblock", messages)
        self.assertNotIn("sent while blocked", messages)

    @mock.patch("apps.calls.views.schedule_ring_timeout")
    def test_blocked_callers_call_never_reaches_blocker(self, _timer):
        self.block()
        response = self.b.post("/api/calls/start/", {"room": self.room.id, "call_type": "AUDIO"}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        call_id = response.data["id"]
        self.assertFalse(CallParticipant.objects.filter(call_id=call_id, user=self.alice).exists())
        history = self.a.get("/api/calls/history/").data
        history = history.get("results", history) if isinstance(history, dict) else history
        self.assertEqual([row for row in history if row["id"] == call_id], [])

    @mock.patch("apps.calls.views.schedule_ring_timeout")
    def test_blocker_cannot_call(self, _timer):
        self.block()
        response = self.a.post("/api/calls/start/", {"room": self.room.id, "call_type": "AUDIO"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_presence_is_hidden_across_a_block(self):
        self.alice.profile.is_online = True
        self.alice.profile.save()
        self.block()
        rooms = self.b.get("/api/chat/rooms/").data
        rooms = rooms.get("results", rooms) if isinstance(rooms, dict) else rooms
        room = next(r for r in rooms if r["id"] == self.room.id)
        alice = next(p["user"] for p in room["participants"] if p["user"]["id"] == self.alice.id)
        self.assertFalse(alice["profile"]["is_online"])


class DeleteForMeTests(TestCase):
    """Regression: PostgreSQL rejects SELECT DISTINCT ... FOR UPDATE (was a 500)."""

    def test_delete_many_for_me_including_a_deleted_placeholder(self):
        alice = make_user("+923000000811")
        bob = make_user("+923000000812")
        room = ChatRoom.objects.create(created_by=alice, room_type=RoomType.PRIVATE)
        Participant.objects.create(room=room, user=alice)
        Participant.objects.create(room=room, user=bob)
        client = APIClient()
        client.force_authenticate(bob)
        first = Message.objects.create(room=room, sender=alice, content="one")
        second = Message.objects.create(room=room, sender=alice, content="two", is_deleted=True)
        response = client.post(
            "/api/chat/messages/delete-many-for-me/", {"messages": [first.id, second.id]}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        listed = client.get(f"/api/chat/rooms/{room.id}/messages/").data
        listed = listed.get("results", listed) if isinstance(listed, dict) else listed
        self.assertEqual([row["id"] for row in listed], [])
