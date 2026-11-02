"""
WebSocket tests for the real-time layer.

They drive the real ASGI application (JWT middleware + URL router) with
Channels' WebsocketCommunicator and the in-memory channel layer configured
in ``config.settings.test``.
"""

import json

from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import User
from apps.chat.choices import RoomType
from apps.chat.models import ChatRoom, Participant
from config.asgi import application


def make_user(phone):
    return User.objects.create_user(phone_number=phone, password="StrongPass123!")


async def receive_until(communicator, wanted_type, attempts=10, timeout=2):
    """Read events until one of ``wanted_type`` arrives (skipping presence etc.)."""
    for _ in range(attempts):
        event = json.loads(await communicator.receive_from(timeout=timeout))
        if event.get("type") == wanted_type:
            return event
    raise AssertionError(f"No {wanted_type!r} event received")


class RealtimeSocketTests(TransactionTestCase):
    def setUp(self):
        self.alice = make_user("+923000000901")
        self.bob = make_user("+923000000902")
        self.carol = make_user("+923000000903")
        self.room = ChatRoom.objects.create(created_by=self.alice, room_type=RoomType.PRIVATE)
        Participant.objects.create(room=self.room, user=self.alice)
        Participant.objects.create(room=self.room, user=self.bob)

    def socket(self, path, user=None):
        query = f"?token={AccessToken.for_user(user)}" if user else ""
        return WebsocketCommunicator(application, f"{path}{query}")

    async def test_inbox_rejects_missing_token(self):
        communicator = self.socket("/ws/chat/inbox/")
        connected, _ = await communicator.connect()
        self.assertFalse(connected)
        await communicator.disconnect()

    async def test_inbox_answers_ping(self):
        communicator = self.socket("/ws/chat/inbox/", self.alice)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.send_to(text_data=json.dumps({"type": "ping"}))
        event = await receive_until(communicator, "pong")
        self.assertEqual(event["type"], "pong")
        await communicator.disconnect()

    async def test_room_socket_rejects_non_member(self):
        communicator = self.socket(f"/ws/chat/{self.room.id}/", self.carol)
        connected, _ = await communicator.connect()
        self.assertFalse(connected)
        await communicator.disconnect()

    async def test_rest_message_reaches_recipient_inbox(self):
        inbox = self.socket("/ws/chat/inbox/", self.bob)
        connected, _ = await inbox.connect()
        self.assertTrue(connected)

        def send():
            client = APIClient()
            client.force_authenticate(self.alice)
            return client.post(
                "/api/chat/messages/",
                {"room": self.room.id, "content": "Hello over the socket"},
                format="json",
            )

        response = await sync_to_async(send)()
        self.assertIn(response.status_code, (200, 201), response.content)

        event = await receive_until(inbox, "inbox.message")
        self.assertEqual(event["room_id"], self.room.id)
        self.assertEqual(event["message"]["content"], "Hello over the socket")
        await inbox.disconnect()

    async def test_typing_is_relayed_to_the_other_member(self):
        alice_room = self.socket(f"/ws/chat/{self.room.id}/", self.alice)
        bob_room = self.socket(f"/ws/chat/{self.room.id}/", self.bob)
        self.assertTrue((await alice_room.connect())[0])
        self.assertTrue((await bob_room.connect())[0])

        await alice_room.send_to(text_data=json.dumps({"type": "typing", "is_typing": True}))
        event = await receive_until(bob_room, "typing")
        self.assertTrue(event.get("is_typing"))

        await alice_room.disconnect()
        await bob_room.disconnect()
