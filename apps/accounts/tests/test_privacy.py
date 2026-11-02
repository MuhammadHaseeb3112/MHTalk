"""Privacy settings: last seen & online, profile photo, about, read receipts."""

import json

from channels.testing import WebsocketCommunicator
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import Contact, Profile, User
from apps.chat.choices import RoomType
from apps.chat.models import ChatRoom, Message, Participant
from apps.chat.utils import persist_receipts_bulk
from config.asgi import application


def make_user(phone, name):
    user = User.objects.create_user(phone_number=phone, password="StrongPass123!")
    user.profile.display_name = name
    user.profile.about = f"About {name}"
    user.profile.profile_picture = SimpleUploadedFile(f"{name}.png", b"x", content_type="image/png")
    user.profile.save()
    return user


def private_room(a, b):
    room = ChatRoom.objects.create(created_by=a, room_type=RoomType.PRIVATE)
    Participant.objects.create(room=room, user=a)
    Participant.objects.create(room=room, user=b)
    return room


def set_privacy(user, **fields):
    Profile.objects.filter(user=user).update(**fields)


@override_settings(MEDIA_ROOT="/tmp/mhtalk-test-media")
class PrivacySettingsTests(TestCase):
    def setUp(self):
        self.alice = make_user("+923000004001", "Alice")
        self.bob = make_user("+923000004002", "Bob")
        self.carol = make_user("+923000004003", "Carol")
        self.room_ab = private_room(self.alice, self.bob)
        self.room_ac = private_room(self.alice, self.carol)
        # Alice saved Bob (so Bob is one of "Alice's contacts"), not Carol.
        Contact.objects.create(owner=self.alice, contact_user=self.bob, name="Bobby")
        self.client = APIClient()

    def as_user(self, user):
        # A fresh instance, like a real request (no stale cached profile).
        self.client.force_authenticate(User.objects.get(pk=user.pk))
        return self.client

    def alice_as_seen_by(self, viewer):
        rooms = self.as_user(viewer).get("/api/chat/rooms/").data
        for room in rooms:
            for participant in room["participants"]:
                if participant["user"]["id"] == self.alice.id:
                    return participant["user"]["profile"]
        raise AssertionError("Alice not found")

    def test_defaults_and_update_endpoint(self):
        response = self.as_user(self.alice).get("/api/accounts/privacy/")
        self.assertEqual(response.data, {
            "last_seen": "everyone", "online": "everyone", "profile_photo": "everyone",
            "about": "everyone", "read_receipts": True,
        })
        response = self.as_user(self.alice).patch(
            "/api/accounts/privacy/", {"last_seen": "contacts", "read_receipts": False}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["last_seen"], "contacts")
        self.assertFalse(response.data["read_receipts"])
        self.assertEqual(
            self.as_user(self.alice).patch("/api/accounts/privacy/", {"about": "friends"}, format="json").status_code, 400
        )
        me = self.as_user(self.alice).get("/api/accounts/me/").data
        self.assertEqual(me["privacy"]["last_seen"], "contacts")

    def test_everyone_shows_everything(self):
        profile = self.alice_as_seen_by(self.carol)
        self.assertTrue(profile["profile_picture"])
        self.assertEqual(profile["about"], "About Alice")
        self.assertIsNotNone(profile["last_seen"])
        # Other people never see someone else's privacy block.
        rooms = self.as_user(self.carol).get("/api/chat/rooms/").data
        for room in rooms:
            for participant in room["participants"]:
                if participant["user"]["id"] == self.alice.id:
                    self.assertNotIn("privacy", participant["user"])

    def test_my_contacts_and_nobody(self):
        set_privacy(self.alice, photo_privacy="contacts", about_privacy="contacts", last_seen_privacy="contacts")
        bob_view = self.alice_as_seen_by(self.bob)
        carol_view = self.alice_as_seen_by(self.carol)
        self.assertTrue(bob_view["profile_picture"])
        self.assertEqual(bob_view["about"], "About Alice")
        self.assertIsNotNone(bob_view["last_seen"])
        self.assertIsNone(carol_view["profile_picture"])
        self.assertEqual(carol_view["about"], "")
        self.assertIsNone(carol_view["last_seen"])

        set_privacy(self.alice, photo_privacy="nobody", about_privacy="nobody", last_seen_privacy="nobody")
        bob_view = self.alice_as_seen_by(self.bob)
        self.assertIsNone(bob_view["profile_picture"])
        self.assertEqual(bob_view["about"], "")
        self.assertIsNone(bob_view["last_seen"])
        # The owner still sees everything.
        me = self.as_user(self.alice).get("/api/accounts/me/").data
        self.assertTrue(me["profile"]["profile_picture"])

    def test_privacy_applies_to_contacts_lookup_and_status(self):
        set_privacy(self.alice, photo_privacy="nobody", about_privacy="nobody")
        Contact.objects.create(owner=self.carol, contact_user=self.alice, name="Al")
        contacts = self.as_user(self.carol).get("/api/accounts/contacts/").data
        rows = contacts["results"] if isinstance(contacts, dict) else contacts
        self.assertIsNone(rows[0]["contact_user"]["profile"]["profile_picture"])
        lookup = self.as_user(self.carol).get("/api/accounts/users/lookup/", {"phone": self.alice.phone_number}).data
        self.assertIsNone(lookup["user"]["profile"]["profile_picture"])
        self.assertEqual(lookup["user"]["profile"]["about"], "")

    def test_last_seen_reciprocity(self):
        set_privacy(self.carol, last_seen_privacy="nobody")
        # Alice shares with everyone, but Carol hides hers, so Carol can't see Alice's.
        self.assertIsNone(self.alice_as_seen_by(self.carol)["last_seen"])
        self.assertIsNotNone(self.alice_as_seen_by(self.bob)["last_seen"])

    def test_online_visibility(self):
        set_privacy(self.alice, last_seen_privacy="nobody", online_privacy="same_as_last_seen")
        Profile.objects.filter(user=self.alice).update(is_online=True)
        self.assertFalse(self.alice_as_seen_by(self.bob)["is_online"])
        set_privacy(self.alice, online_privacy="everyone")
        # Alice hides last seen -> Bob still sees "online" (Everyone), but
        # Alice's own reciprocity only affects what *she* sees.
        self.assertTrue(self.alice_as_seen_by(self.bob)["is_online"])

    def test_read_receipts_off_hides_blue_ticks_in_private_chats_both_ways(self):
        to_bob = Message.objects.create(room=self.room_ab, sender=self.alice, content="hi")
        to_alice = Message.objects.create(room=self.room_ab, sender=self.bob, content="yo")
        set_privacy(self.bob, read_receipts=False)
        persist_receipts_bulk([to_bob.id], self.bob.id, "read")
        persist_receipts_bulk([to_alice.id], self.alice.id, "read")
        # Bob read it, but he turned receipts off: Alice sees no blue tick.
        alice_msgs = self.as_user(self.alice).get(f"/api/chat/rooms/{self.room_ab.id}/messages/").data
        row = next(m for m in alice_msgs if m["id"] == to_bob.id)
        self.assertFalse(row["is_read"])
        self.assertTrue(row["is_delivered"])
        # ...and Bob doesn't see Alice's read receipts either.
        bob_msgs = self.as_user(self.bob).get(f"/api/chat/rooms/{self.room_ab.id}/messages/").data
        row = next(m for m in bob_msgs if m["id"] == to_alice.id)
        self.assertFalse(row["is_read"])
        # Bob's unread counter still clears.
        rooms = self.as_user(self.bob).get("/api/chat/rooms/").data
        self.assertEqual(next(r for r in rooms if r["id"] == self.room_ab.id)["unread_count"], 0)
        # Message info shows "delivered", never "read".
        info = self.as_user(self.alice).get(f"/api/chat/messages/{to_bob.id}/info/").data
        self.assertEqual(info["read_count"], 0)
        self.assertEqual(info["delivered_count"], 1)

    def test_groups_always_send_read_receipts(self):
        set_privacy(self.bob, read_receipts=False)
        group = ChatRoom.objects.create(created_by=self.alice, room_type=RoomType.GROUP, name="G")
        Participant.objects.create(room=group, user=self.alice, is_admin=True)
        Participant.objects.create(room=group, user=self.bob)
        message = Message.objects.create(room=group, sender=self.alice, content="hi")
        persist_receipts_bulk([message.id], self.bob.id, "read")
        rows = self.as_user(self.alice).get(f"/api/chat/rooms/{group.id}/messages/").data
        self.assertTrue(rows[0]["is_read"])

    def test_message_info_respects_photo_privacy(self):
        set_privacy(self.bob, photo_privacy="nobody")
        message = Message.objects.create(room=self.room_ab, sender=self.alice, content="hi")
        info = self.as_user(self.alice).get(f"/api/chat/messages/{message.id}/info/").data
        self.assertIsNone(info["recipients"][0]["profile_picture"])

    def test_broadcast_payload_uses_public_view(self):
        """A message pushed to every socket never carries the sender's private data."""
        from apps.chat.serializers import MessageSerializer
        from rest_framework.test import APIRequestFactory

        set_privacy(self.alice, photo_privacy="contacts")
        from apps.chat.utils import get_message_with_relations

        message = Message.objects.create(room=self.room_ab, sender=self.alice, content="hi")
        message = get_message_with_relations(message.id)
        request = APIRequestFactory().get("/")
        request.user = self.alice
        data = MessageSerializer(message, context={"request": request, "public_view": True}).data
        self.assertIsNone(data["sender"]["profile"]["profile_picture"])
        self.assertIsNone(data["sender"]["profile"]["last_seen"])
        self.assertNotIn("privacy", data["sender"])


class PresencePrivacySocketTests(TransactionTestCase):
    def setUp(self):
        self.alice = User.objects.create_user(phone_number="+923000005001", password="StrongPass123!")
        self.bob = User.objects.create_user(phone_number="+923000005002", password="StrongPass123!")
        self.room = private_room(self.alice, self.bob)

    async def _presence_seen_by_bob(self):
        bob_inbox = WebsocketCommunicator(application, f"/ws/chat/inbox/?token={AccessToken.for_user(self.bob)}")
        self.assertTrue((await bob_inbox.connect())[0])
        alice_inbox = WebsocketCommunicator(application, f"/ws/chat/inbox/?token={AccessToken.for_user(self.alice)}")
        self.assertTrue((await alice_inbox.connect())[0])
        event = None
        for _ in range(10):
            candidate = json.loads(await bob_inbox.receive_from(timeout=2))
            if candidate.get("type") == "presence" and candidate.get("user_id") == self.alice.id:
                event = candidate
                break
        await alice_inbox.disconnect()
        await bob_inbox.disconnect()
        return event

    async def test_online_shown_by_default(self):
        event = await self._presence_seen_by_bob()
        self.assertTrue(event["is_online"])

    async def test_online_hidden_when_same_as_last_seen_nobody(self):
        from asgiref.sync import sync_to_async

        await sync_to_async(set_privacy)(self.alice, last_seen_privacy="nobody", online_privacy="same_as_last_seen")
        event = await self._presence_seen_by_bob()
        self.assertFalse(event["is_online"])
        self.assertIsNone(event["last_seen"])

    async def test_room_snapshot_respects_privacy(self):
        from asgiref.sync import sync_to_async

        await sync_to_async(Profile.objects.filter(user=self.alice).update)(
            is_online=True, last_seen_privacy="nobody", online_privacy="same_as_last_seen"
        )
        room_socket = WebsocketCommunicator(
            application, f"/ws/chat/{self.room.id}/?token={AccessToken.for_user(self.bob)}"
        )
        self.assertTrue((await room_socket.connect())[0])
        event = json.loads(await room_socket.receive_from(timeout=2))
        self.assertEqual(event["type"], "presence")
        self.assertFalse(event["is_online"])
        self.assertIsNone(event["last_seen"])
        await room_socket.disconnect()
