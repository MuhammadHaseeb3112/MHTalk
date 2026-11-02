"""
Tests for the WhatsApp-Web parity features: chat preferences (pin,
favorite, archive), read sync, group admins, shared media, global search,
edit/delete windows, account lookup and missed-call acknowledgement.
"""

from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Contact, User
from apps.calls.choices import CallStatus
from apps.calls.models import Call, CallParticipant
from apps.chat.choices import MessageType, RoomType
from apps.chat.models import ChatRoom, Message, MessageReceipt, Participant


def make_user(phone, name=""):
    user = User.objects.create_user(phone_number=phone, password="StrongPass123!")
    if name:
        user.profile.display_name = name
        user.profile.save()
    return user


class ChatPreferenceTests(TestCase):
    def setUp(self):
        self.alice = make_user("+923000000301", "Alice")
        self.bob = make_user("+923000000302", "Bob")
        self.room = ChatRoom.objects.create(created_by=self.alice, room_type=RoomType.PRIVATE)
        Participant.objects.create(room=self.room, user=self.alice)
        Participant.objects.create(room=self.room, user=self.bob)
        self.client = APIClient()
        self.client.force_authenticate(self.alice)

    def test_room_list_exposes_per_user_state(self):
        Message.objects.create(room=self.room, sender=self.bob, content="hi")
        rooms = self.client.get("/api/chat/rooms/").data
        self.assertEqual(len(rooms), 1)
        row = rooms[0]
        self.assertEqual(row["unread_count"], 1)
        self.assertFalse(row["is_pinned"])
        self.assertFalse(row["is_favorite"])
        self.assertFalse(row["is_archived"])
        self.assertEqual(row["last_message"]["content"], "hi")

    def test_pin_and_favorite(self):
        self.assertEqual(self.client.post("/api/chat/rooms/pin/", {"room": self.room.id, "is_pinned": True}).status_code, 200)
        self.assertEqual(self.client.post("/api/chat/rooms/favorite/", {"room": self.room.id, "is_favorite": True}).status_code, 200)
        row = self.client.get("/api/chat/rooms/").data[0]
        self.assertTrue(row["is_pinned"])
        self.assertTrue(row["is_favorite"])

    def test_pin_limit(self):
        for index in range(3):
            other = make_user(f"+92300000040{index}")
            room = ChatRoom.objects.create(created_by=self.alice)
            Participant.objects.create(room=room, user=self.alice, is_pinned=True, pinned_at=timezone.now())
            Participant.objects.create(room=room, user=other)
        response = self.client.post("/api/chat/rooms/pin/", {"room": self.room.id, "is_pinned": True})
        self.assertEqual(response.status_code, 400)

    def test_archive_all_listing_and_bulk(self):
        response = self.client.post("/api/chat/rooms/archive/", {"rooms": [self.room.id], "is_archived": True}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/chat/rooms/").data, [])
        archived = self.client.get("/api/chat/rooms/?archived=true").data
        self.assertEqual([row["id"] for row in archived], [self.room.id])
        everything = self.client.get("/api/chat/rooms/?archived=all").data
        self.assertTrue(everything[0]["is_archived"])

    def test_archived_chat_stays_archived_on_new_message(self):
        self.client.post("/api/chat/rooms/archive/", {"room": self.room.id, "is_archived": True})
        bob_client = APIClient()
        bob_client.force_authenticate(self.bob)
        bob_client.post("/api/chat/messages/", {"room": self.room.id, "message_type": "TEXT", "content": "new"}, format="json")
        archived = self.client.get("/api/chat/rooms/?archived=true").data
        self.assertEqual(archived[0]["unread_count"], 1)
        self.assertEqual(self.client.get("/api/chat/rooms/").data, [])

    def test_mark_room_read_updates_receipts(self):
        bob_client = APIClient()
        bob_client.force_authenticate(self.bob)
        sent = bob_client.post("/api/chat/messages/", {"room": self.room.id, "message_type": "TEXT", "content": "read me"}, format="json")
        message_id = sent.data["data"]["id"]
        response = self.client.post(f"/api/chat/rooms/{self.room.id}/read/")
        self.assertEqual(response.data["marked_read"], 1)
        receipt = MessageReceipt.objects.get(message_id=message_id, recipient=self.alice)
        self.assertIsNotNone(receipt.read_at)
        self.assertTrue(Message.objects.get(pk=message_id).is_read)
        self.assertEqual(self.client.get("/api/chat/rooms/").data[0]["unread_count"], 0)

    def test_message_info_lists_reader(self):
        message = Message.objects.create(room=self.room, sender=self.alice, content="info")
        bob_client = APIClient()
        bob_client.force_authenticate(self.bob)
        bob_client.post(f"/api/chat/rooms/{self.room.id}/read/")
        info = self.client.get(f"/api/chat/messages/{message.id}/info/").data
        self.assertEqual(info["read_count"], 1)
        self.assertEqual(info["read_by"][0]["user_id"], self.bob.id)


class MessageRuleTests(TestCase):
    def setUp(self):
        self.alice = make_user("+923000000311")
        self.bob = make_user("+923000000312")
        self.room = ChatRoom.objects.create(created_by=self.alice)
        Participant.objects.create(room=self.room, user=self.alice)
        Participant.objects.create(room=self.room, user=self.bob)
        self.client = APIClient()
        self.client.force_authenticate(self.alice)

    def test_edit_window(self):
        message = Message.objects.create(room=self.room, sender=self.alice, content="typo")
        ok = self.client.patch(f"/api/chat/messages/{message.id}/", {"content": "fixed"}, format="json")
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.data["data"]["is_edited"])
        Message.objects.filter(pk=message.pk).update(created_at=timezone.now() - timedelta(hours=1))
        late = self.client.patch(f"/api/chat/messages/{message.id}/", {"content": "again"}, format="json")
        self.assertEqual(late.status_code, 403)

    def test_delete_for_everyone_window(self):
        message = Message.objects.create(room=self.room, sender=self.alice, content="old")
        Message.objects.filter(pk=message.pk).update(created_at=timezone.now() - timedelta(days=5))
        response = self.client.delete(f"/api/chat/messages/{message.id}/delete/")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Message.objects.get(pk=message.pk).is_deleted)

    def test_reaction_can_be_removed(self):
        message = Message.objects.create(room=self.room, sender=self.bob, content="nice")
        self.client.post("/api/chat/messages/react/", {"message": message.id, "emoji": "👍"}, format="json")
        self.assertEqual(message.reactions.count(), 1)
        self.client.post("/api/chat/messages/react/", {"message": message.id, "emoji": ""}, format="json")
        self.assertEqual(message.reactions.count(), 0)

    @override_settings(MEDIA_ROOT="/tmp/mhtalk_test_media")
    def test_upload_validation_and_shared_media(self):
        empty = SimpleUploadedFile("empty.png", b"", content_type="image/png")
        bad = self.client.post("/api/chat/messages/upload/", {"room": self.room.id, "message_type": "IMAGE", "file": empty}, format="multipart")
        self.assertEqual(bad.status_code, 400)

        script = SimpleUploadedFile("run.exe", b"MZ", content_type="application/x-msdownload")
        bad = self.client.post("/api/chat/messages/upload/", {"room": self.room.id, "message_type": "DOCUMENT", "file": script}, format="multipart")
        self.assertEqual(bad.status_code, 400)

        image = SimpleUploadedFile("photo.png", b"\x89PNG\r\n\x1a\nimage-bytes", content_type="image/png")
        ok = self.client.post("/api/chat/messages/upload/", {"room": self.room.id, "message_type": "IMAGE", "file": image, "content": "caption"}, format="multipart")
        self.assertEqual(ok.status_code, 201, ok.data)

        Message.objects.create(room=self.room, sender=self.bob, content="see https://example.com/page now")
        media = self.client.get(f"/api/chat/rooms/{self.room.id}/media/?kind=media").data
        self.assertEqual(media["count"], 1)
        links = self.client.get(f"/api/chat/rooms/{self.room.id}/media/?kind=links").data
        self.assertEqual(links["results"][0]["url"], "https://example.com/page")

    def test_global_search(self):
        Message.objects.create(room=self.room, sender=self.bob, content="Meeting at noon")
        results = self.client.get("/api/chat/messages/search/?q=meeting").data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["room_id"], self.room.id)


class GroupTests(TestCase):
    def setUp(self):
        self.alice = make_user("+923000000321")
        self.bob = make_user("+923000000322")
        self.carol = make_user("+923000000323")
        self.client = APIClient()
        self.client.force_authenticate(self.alice)

    def test_create_group_with_members_and_promote(self):
        response = self.client.post(
            "/api/chat/rooms/group/",
            {"name": "Team", "participants": [self.bob.id, self.carol.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        room_id = response.data["id"]
        self.assertEqual(Participant.objects.filter(room_id=room_id).count(), 3)

        promote = self.client.patch(f"/api/chat/rooms/{room_id}/participants/{self.bob.id}/admin/", {"is_admin": True}, format="json")
        self.assertEqual(promote.status_code, 200)
        self.assertTrue(Participant.objects.get(room_id=room_id, user=self.bob).is_admin)

        dismiss_creator = self.client.patch(f"/api/chat/rooms/{room_id}/participants/{self.alice.id}/admin/", {"is_admin": False}, format="json")
        self.assertEqual(dismiss_creator.status_code, 400)

        bob_client = APIClient()
        bob_client.force_authenticate(self.carol)
        forbidden = bob_client.patch(f"/api/chat/rooms/{room_id}/participants/{self.bob.id}/admin/", {"is_admin": False}, format="json")
        self.assertEqual(forbidden.status_code, 403)

    def test_common_groups(self):
        self.client.post("/api/chat/rooms/group/", {"name": "Shared", "participants": [self.bob.id]}, format="json")
        groups = self.client.get(f"/api/accounts/users/{self.bob.id}/common-groups/").data
        self.assertEqual([group["name"] for group in groups], ["Shared"])


class AccountTests(TestCase):
    def test_register_returns_tokens_and_name(self):
        client = APIClient()
        response = client.post(
            "/api/accounts/register/",
            {"phone_number": "+923000000331", "password": "StrongPass123!", "display_name": "Sara"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("access", response.data)
        self.assertEqual(response.data["user"]["profile"]["display_name"], "Sara")

        refreshed = client.post("/api/accounts/token/refresh/", {"refresh": response.data["refresh"]}, format="json")
        self.assertEqual(refreshed.status_code, 200)
        self.assertIn("access", refreshed.data)

    def test_lookup_by_local_number(self):
        target = make_user("+923001234567")
        me = make_user("+923000000332")
        client = APIClient()
        client.force_authenticate(me)
        found = client.get("/api/accounts/users/lookup/", {"phone": "0300 1234567"})
        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.data["user"]["id"], target.id)
        missing = client.get("/api/accounts/users/lookup/", {"phone": "+15550000000"})
        self.assertEqual(missing.status_code, 404)

    def test_editing_contact_number_does_not_change_account(self):
        first = make_user("+923000000341")
        second = make_user("+923000000342")
        me = make_user("+923000000343")
        contact = Contact.objects.create(owner=me, contact_user=first, name="Friend")
        client = APIClient()
        client.force_authenticate(me)
        response = client.patch(f"/api/accounts/contacts/{contact.id}/", {"name": "Friend", "phone_number": second.phone_number}, format="json")
        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        self.assertEqual(first.phone_number, "+923000000341")
        self.assertEqual(response.data["contact_user"]["id"], second.id)


class MissedCallTests(TestCase):
    def test_missed_badge_and_acknowledge(self):
        caller = make_user("+923000000351")
        callee = make_user("+923000000352")
        room = ChatRoom.objects.create(created_by=caller)
        Participant.objects.create(room=room, user=caller)
        Participant.objects.create(room=room, user=callee)
        call = Call.objects.create(room=room, caller=caller, status=CallStatus.MISSED, ended_at=timezone.now())
        CallParticipant.objects.create(call=call, user=caller)
        CallParticipant.objects.create(call=call, user=callee)

        client = APIClient()
        client.force_authenticate(callee)
        self.assertEqual(client.get("/api/calls/missed/").data["unseen_count"], 1)
        history = client.get("/api/calls/history/").data
        self.assertTrue(history[0]["is_missed"])
        self.assertFalse(history[0]["is_missed_seen"])
        client.post("/api/calls/missed/")
        self.assertEqual(client.get("/api/calls/missed/").data["unseen_count"], 0)

        caller_client = APIClient()
        caller_client.force_authenticate(caller)
        self.assertEqual(caller_client.get("/api/calls/missed/").data["unseen_count"], 0)

    def test_rejected_call_creates_call_card(self):
        caller = make_user("+923000000361")
        callee = make_user("+923000000362")
        room = ChatRoom.objects.create(created_by=caller)
        Participant.objects.create(room=room, user=caller)
        Participant.objects.create(room=room, user=callee)
        call = Call.objects.create(room=room, caller=caller)
        CallParticipant.objects.create(call=call, user=caller)
        CallParticipant.objects.create(call=call, user=callee)
        client = APIClient()
        client.force_authenticate(callee)
        self.assertEqual(client.post(f"/api/calls/{call.id}/reject/").status_code, 200)
        card = Message.objects.get(client_message_id=f"call-event-{call.id}")
        self.assertTrue(card.content.startswith("__MHTALK_CALL_EVENT__:"))
        self.assertIn('"status":"REJECTED"', card.content)
