"""Settings > Account > Delete my account."""

import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.accounts.models import Contact, User
from apps.chat.choices import RoomType
from apps.chat.group_events import GROUP_EVENT_PREFIX
from apps.chat.models import BlockedUser, ChatRoom, Message, Participant
from apps.status.models import Status

PASSWORD = "StrongPass123!"


def make_user(phone, name):
    user = User.objects.create_user(phone_number=phone, password=PASSWORD)
    user.profile.display_name = name
    user.profile.save()
    return user


@override_settings(MEDIA_ROOT="/tmp/whatsup-test-media")
class DeleteAccountTests(TestCase):
    def setUp(self):
        self.alice = make_user("+923000006001", "Alice")
        self.bob = make_user("+923000006002", "Bob")
        self.carol = make_user("+923000006003", "Carol")
        profile = self.alice.profile
        profile.about = "Busy"
        profile.profile_picture = SimpleUploadedFile("a.png", b"x", content_type="image/png")
        profile.save()

        self.private = ChatRoom.objects.create(created_by=self.alice, room_type=RoomType.PRIVATE)
        Participant.objects.create(room=self.private, user=self.alice)
        Participant.objects.create(room=self.private, user=self.bob)
        self.history = Message.objects.create(room=self.private, sender=self.alice, content="old message")

        self.group = ChatRoom.objects.create(created_by=self.alice, room_type=RoomType.GROUP, name="G")
        Participant.objects.create(room=self.group, user=self.alice, is_admin=True)
        Participant.objects.create(room=self.group, user=self.bob)
        Participant.objects.create(room=self.group, user=self.carol)

        Contact.objects.create(owner=self.alice, contact_user=self.bob, name="Bob")
        Contact.objects.create(owner=self.bob, contact_user=self.alice, name="Alice")
        BlockedUser.objects.create(blocked_by=self.alice, blocked_user=self.carol)
        Status.objects.create(user=self.alice, status_type="text", content="hi")

        self.client = APIClient()
        login = self.client.post(
            "/api/accounts/login/", {"phone_number": self.alice.phone_number, "password": PASSWORD}, format="json"
        )
        self.refresh = login.data["refresh"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    def delete(self, phone="+923000006001", password=PASSWORD):
        return self.client.post("/api/accounts/delete/", {"phone_number": phone, "password": password}, format="json")

    def test_requires_matching_phone_and_password(self):
        self.assertEqual(self.delete(phone="+923000006009").status_code, 400)
        self.assertEqual(self.delete(password="wrong-password").status_code, 400)
        self.alice.refresh_from_db()
        self.assertTrue(self.alice.is_active)
        # Local format of the same number is accepted.
        self.assertEqual(self.delete(phone="03000006001").status_code, 200)

    def test_delete_account_end_to_end(self):
        response = self.delete()
        self.assertEqual(response.status_code, 200)

        self.alice.refresh_from_db()
        self.assertFalse(self.alice.is_active)
        self.assertTrue(self.alice.is_deleted)
        self.assertNotEqual(self.alice.phone_number, "+923000006001")
        self.assertEqual(self.alice.profile.display_name, "Deleted account")
        self.assertEqual(self.alice.profile.about, "")
        self.assertFalse(self.alice.profile.profile_picture)

        # Statuses, contacts (both directions) and blocks are gone.
        self.assertFalse(Status.objects.filter(user=self.alice).exists())
        self.assertFalse(Contact.objects.filter(owner=self.alice).exists())
        self.assertFalse(Contact.objects.filter(contact_user=self.alice).exists())
        self.assertFalse(BlockedUser.objects.filter(blocked_by=self.alice).exists())

        # Left the group; Bob took over as admin; "Alice left" was posted.
        self.assertFalse(Participant.objects.filter(room=self.group, user=self.alice).exists())
        self.assertEqual(Participant.objects.filter(room=self.group, is_admin=True).count(), 1)
        event = Message.objects.filter(room=self.group, content__startswith=GROUP_EVENT_PREFIX).get()
        payload = json.loads(event.content[len(GROUP_EVENT_PREFIX):])
        self.assertEqual(payload["event"], "left")
        self.assertEqual(payload["actor_name"], "Alice")

        # Every refresh token is blacklisted and the access token stops working.
        outstanding = OutstandingToken.objects.filter(user=self.alice)
        self.assertTrue(outstanding.exists())
        self.assertEqual(BlacklistedToken.objects.filter(token__in=outstanding).count(), outstanding.count())
        self.assertEqual(self.client.get("/api/accounts/me/").status_code, 401)
        refresh = APIClient().post("/api/accounts/token/refresh/", {"refresh": self.refresh}, format="json")
        self.assertEqual(refresh.status_code, 401)

        # Bob still reads the history, sent by "Deleted account".
        bob = APIClient()
        bob.force_authenticate(self.bob)
        messages = bob.get(f"/api/chat/rooms/{self.private.id}/messages/").data
        sender = next(m for m in messages if m["id"] == self.history.id)["sender"]
        self.assertEqual(sender["profile"]["display_name"], "Deleted account")
        self.assertTrue(sender["is_deleted"])
        self.assertEqual(sender["phone_number"], "")
        self.assertIsNone(sender["profile"]["profile_picture"])
        # ...but can't send to a deleted account.
        response = bob.post("/api/chat/messages/", {"room": self.private.id, "content": "hello?"}, format="json")
        self.assertEqual(response.status_code, 403)

        # The old credentials no longer log in, and the number can be registered again.
        login = APIClient().post(
            "/api/accounts/login/", {"phone_number": "+923000006001", "password": PASSWORD}, format="json"
        )
        self.assertEqual(login.status_code, 400)
        register = APIClient().post(
            "/api/accounts/register/",
            {"phone_number": "+923000006001", "password": "AnotherPass123!", "display_name": "New Alice"},
            format="json",
        )
        self.assertEqual(register.status_code, 201)
        self.assertNotEqual(register.data["user"]["id"], self.alice.id)

    def test_last_member_group_is_left_quietly(self):
        solo = ChatRoom.objects.create(created_by=self.alice, room_type=RoomType.GROUP, name="Solo")
        Participant.objects.create(room=solo, user=self.alice, is_admin=True)
        self.assertEqual(self.delete().status_code, 200)
        self.assertFalse(Participant.objects.filter(room=solo).exists())
        self.assertFalse(Message.objects.filter(room=solo).exists())

    def test_requires_authentication(self):
        self.assertEqual(APIClient().post("/api/accounts/delete/", {}, format="json").status_code, 401)
