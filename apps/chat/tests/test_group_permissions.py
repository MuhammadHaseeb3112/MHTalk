"""Group permissions (edit info / send messages / add members) and invite links."""

import json

from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import User
from apps.chat.choices import RoomType
from apps.chat.group_events import GROUP_EVENT_PREFIX
from apps.chat.models import ChatRoom, Message, Participant
from apps.chat.permissions import can_add_members, can_edit_group_info, can_send_message
from config.asgi import application


def make_user(phone, name=""):
    user = User.objects.create_user(phone_number=phone, password="StrongPass123!")
    if name:
        user.profile.display_name = name
        user.profile.save()
    return user


def make_group(admin, members, **fields):
    room = ChatRoom.objects.create(created_by=admin, room_type=RoomType.GROUP, name="Team", **fields)
    Participant.objects.create(room=room, user=admin, is_admin=True)
    for member in members:
        Participant.objects.create(room=room, user=member)
    return room


def events(room):
    rows = Message.objects.filter(room=room, content__startswith=GROUP_EVENT_PREFIX).order_by("id")
    return [json.loads(row.content[len(GROUP_EVENT_PREFIX):]) for row in rows]


@override_settings(MEDIA_ROOT="/tmp/mhtalk-test-media")
class GroupPermissionTests(TestCase):
    def setUp(self):
        self.alice = make_user("+923000001001", "Alice")
        self.bob = make_user("+923000001002", "Bob")
        self.carol = make_user("+923000001003", "Carol")
        self.room = make_group(self.alice, [self.bob])
        self.client = APIClient()

    def as_user(self, user):
        self.client.force_authenticate(user)
        return self.client

    def test_helpers(self):
        self.assertTrue(can_send_message(self.bob, self.room))
        self.assertFalse(can_send_message(self.carol, self.room))
        self.assertFalse(can_edit_group_info(self.bob, self.room))
        self.assertTrue(can_edit_group_info(self.alice, self.room))
        self.assertFalse(can_add_members(self.bob, self.room))
        self.room.send_messages_admins_only = True
        self.room.edit_info_admins_only = False
        self.room.add_members_admins_only = False
        self.room.save()
        self.assertFalse(can_send_message(self.bob, self.room))
        self.assertTrue(can_send_message(self.alice, self.room))
        self.assertTrue(can_edit_group_info(self.bob, self.room))
        self.assertTrue(can_add_members(self.bob, self.room))
        self.assertFalse(can_add_members(self.carol, self.room))

    def test_only_admins_change_permissions_and_system_message_is_posted(self):
        url = f"/api/chat/rooms/{self.room.id}/permissions/"
        response = self.as_user(self.bob).patch(url, {"send_messages_admins_only": True}, format="json")
        self.assertEqual(response.status_code, 403)

        response = self.as_user(self.alice).patch(url, {"send_messages_admins_only": True}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["send_messages_admins_only"])
        self.room.refresh_from_db()
        self.assertTrue(self.room.send_messages_admins_only)
        [event] = events(self.room)
        self.assertEqual(event["event"], "permissions_changed")
        self.assertEqual(event["actor_id"], self.alice.id)
        self.assertEqual(
            event["text"].replace("{actor}", event["actor_name"]),
            "Alice changed this group's settings to allow only admins to send messages",
        )
        # Unchanged value: no extra message.
        self.as_user(self.alice).patch(url, {"send_messages_admins_only": True}, format="json")
        self.assertEqual(len(events(self.room)), 1)
        # Room payload exposes the settings for the UI.
        info = self.as_user(self.bob).get(f"/api/chat/rooms/{self.room.id}/info/").data
        self.assertTrue(info["send_messages_admins_only"])

    def test_system_messages_are_not_unread_and_not_editable(self):
        self.as_user(self.alice).patch(
            f"/api/chat/rooms/{self.room.id}/permissions/", {"edit_info_admins_only": False}, format="json"
        )
        rooms = self.as_user(self.bob).get("/api/chat/rooms/").data
        room = next(row for row in rooms if row["id"] == self.room.id)
        self.assertEqual(room["unread_count"], 0)
        self.assertTrue(room["last_message"]["content"].startswith(GROUP_EVENT_PREFIX))
        message = Message.objects.get(room=self.room)
        client = self.as_user(self.alice)
        self.assertNotEqual(client.patch(f"/api/chat/messages/{message.id}/", {"content": "x"}, format="json").status_code, 200)
        self.assertEqual(client.delete(f"/api/chat/messages/{message.id}/delete/").status_code, 404)
        self.assertEqual(client.post("/api/chat/messages/pin/", {"message": message.id, "is_pinned": True}, format="json").status_code, 400)
        self.assertEqual(client.post("/api/chat/messages/forward/", {"message": message.id, "room": self.room.id}, format="json").status_code, 400)

    def test_send_restricted_on_every_rest_path(self):
        self.room.send_messages_admins_only = True
        self.room.save()
        client = self.as_user(self.bob)
        source = Message.objects.create(room=self.room, sender=self.alice, content="hello")

        response = client.post("/api/chat/messages/", {"room": self.room.id, "content": "hi"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertIn("Only admins", response.data["detail"])

        upload = SimpleUploadedFile("a.png", b"\x89PNG\r\n\x1a\n", content_type="image/png")
        response = client.post("/api/chat/messages/upload/", {"room": self.room.id, "file": upload, "message_type": "IMAGE"})
        self.assertEqual(response.status_code, 403)

        audio = SimpleUploadedFile("v.webm", b"abc", content_type="audio/webm")
        response = client.post("/api/chat/messages/voice/", {"room": self.room.id, "audio": audio, "duration": 3})
        self.assertEqual(response.status_code, 403)

        response = client.post("/api/chat/messages/forward/", {"message": source.id, "room": self.room.id}, format="json")
        self.assertEqual(response.status_code, 403)

        self.assertEqual(Message.objects.filter(room=self.room, sender=self.bob).count(), 0)

        # Reactions are still allowed (WhatsApp).
        response = client.post("/api/chat/messages/react/", {"message": source.id, "emoji": "👍"}, format="json")
        self.assertIn(response.status_code, (200, 201))

        # Admins still send.
        response = self.as_user(self.alice).post("/api/chat/messages/", {"room": self.room.id, "content": "ok"}, format="json")
        self.assertEqual(response.status_code, 201)

    def test_edit_info_permission(self):
        url = f"/api/chat/rooms/{self.room.id}/info/"
        self.assertEqual(self.as_user(self.bob).patch(url, {"name": "Bob's"}).status_code, 403)
        self.room.edit_info_admins_only = False
        self.room.save()
        self.assertEqual(self.as_user(self.bob).patch(url, {"name": "Bob's"}).status_code, 200)
        self.room.refresh_from_db()
        self.assertEqual(self.room.name, "Bob's")

    def test_add_members_permission(self):
        url = f"/api/chat/rooms/{self.room.id}/participants/"
        self.assertEqual(self.as_user(self.bob).post(url, {"user_ids": [self.carol.id]}, format="json").status_code, 403)
        self.room.add_members_admins_only = False
        self.room.save()
        self.assertEqual(self.as_user(self.bob).post(url, {"user_ids": [self.carol.id]}, format="json").status_code, 201)
        self.assertTrue(Participant.objects.filter(room=self.room, user=self.carol).exists())


@override_settings(MEDIA_ROOT="/tmp/mhtalk-test-media")
class InviteLinkTests(TestCase):
    def setUp(self):
        cache.clear()
        self.alice = make_user("+923000002001", "Alice")
        self.bob = make_user("+923000002002", "Bob")
        self.dave = make_user("+923000002004", "Dave")
        self.room = make_group(self.alice, [self.bob])
        self.client = APIClient()

    def as_user(self, user):
        self.client.force_authenticate(user)
        return self.client

    def link(self, user):
        return self.as_user(user).get(f"/api/chat/rooms/{self.room.id}/invite-link/")

    def test_only_allowed_members_see_link(self):
        self.assertEqual(self.link(self.bob).status_code, 403)
        self.assertEqual(self.link(self.dave).status_code, 404)
        response = self.link(self.alice)
        self.assertEqual(response.status_code, 200)
        code = response.data["code"]
        self.assertGreaterEqual(len(code), 20)
        self.assertEqual(response.data["path"], f"/join/{code}")
        # Stable until reset.
        self.assertEqual(self.link(self.alice).data["code"], code)
        ChatRoom.objects.filter(pk=self.room.pk).update(add_members_admins_only=False)
        self.assertEqual(self.link(self.bob).data["code"], code)

    def test_preview_join_and_reset(self):
        code = self.link(self.alice).data["code"]
        preview = self.as_user(self.dave).get(f"/api/chat/invite/{code}/")
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data["name"], "Team")
        self.assertEqual(preview.data["participants_count"], 2)
        self.assertFalse(preview.data["is_member"])
        self.assertIn("Alice", preview.data["member_names"])

        joined = self.as_user(self.dave).post(f"/api/chat/invite/{code}/join/")
        self.assertEqual(joined.status_code, 201)
        self.assertEqual(joined.data["room_id"], self.room.id)
        self.assertTrue(Participant.objects.filter(room=self.room, user=self.dave, is_admin=False).exists())
        [event] = events(self.room)
        self.assertEqual(event["event"], "joined_via_link")
        self.assertEqual(event["actor_id"], self.dave.id)

        again = self.as_user(self.dave).post(f"/api/chat/invite/{code}/join/")
        self.assertEqual(again.status_code, 200)
        self.assertTrue(again.data["already_member"])
        self.assertTrue(self.as_user(self.dave).get(f"/api/chat/invite/{code}/").data["is_member"])

        new_code = self.as_user(self.alice).post(f"/api/chat/rooms/{self.room.id}/invite-link/reset/").data["code"]
        self.assertNotEqual(new_code, code)
        self.assertEqual(self.as_user(self.dave).get(f"/api/chat/invite/{code}/").status_code, 404)
        self.assertEqual(self.as_user(self.dave).post(f"/api/chat/invite/{code}/join/").status_code, 404)
        self.assertEqual(self.as_user(self.bob).post(f"/api/chat/rooms/{self.room.id}/invite-link/reset/").status_code, 403)

    def test_invalid_code_and_auth_required(self):
        self.assertEqual(self.as_user(self.dave).get("/api/chat/invite/nope/").status_code, 404)
        anonymous = APIClient()
        self.assertEqual(anonymous.get("/api/chat/invite/nope/").status_code, 401)

    def test_invite_endpoints_are_rate_limited(self):
        client = self.as_user(self.dave)
        statuses = [client.get("/api/chat/invite/guess/").status_code for _ in range(40)]
        self.assertIn(429, statuses)


class SendPermissionSocketTests(TransactionTestCase):
    def setUp(self):
        self.alice = make_user("+923000003001", "Alice")
        self.bob = make_user("+923000003002", "Bob")
        self.room = make_group(self.alice, [self.bob], send_messages_admins_only=True)
        self.source = Message.objects.create(room=self.room, sender=self.alice, content="hello")

    async def test_websocket_send_and_forward_rejected_for_non_admins(self):
        communicator = WebsocketCommunicator(
            application, f"/ws/chat/{self.room.id}/?token={AccessToken.for_user(self.bob)}"
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.send_to(text_data=json.dumps({"type": "message", "content": "hi"}))
        error = None
        for _ in range(5):
            event = json.loads(await communicator.receive_from(timeout=2))
            if event.get("type") == "error":
                error = event
                break
        self.assertIsNotNone(error)
        self.assertIn("Only admins", error["message"])
        await communicator.send_to(text_data=json.dumps({"type": "forward", "message_id": self.source.id}))
        event = json.loads(await communicator.receive_from(timeout=2))
        self.assertEqual(event["type"], "error")
        count = await sync_to_async(Message.objects.filter(room=self.room, sender=self.bob).count)()
        self.assertEqual(count, 0)
        await communicator.disconnect()
