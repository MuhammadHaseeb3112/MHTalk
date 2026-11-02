"""Pinned messages (max 3), media from all chats and the MHTalk AI endpoint."""

from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.chat.choices import RoomType
from apps.chat.models import Attachment, ChatRoom, Message, Participant


def make_user(phone):
    return User.objects.create_user(phone_number=phone, password="StrongPass123!")


def make_room(*users):
    room = ChatRoom.objects.create(created_by=users[0], room_type=RoomType.PRIVATE)
    for user in users:
        Participant.objects.create(room=room, user=user)
    return room


class PinnedMessagesTests(TestCase):
    def setUp(self):
        self.alice = make_user("+923000000851")
        self.bob = make_user("+923000000852")
        self.room = make_room(self.alice, self.bob)
        self.client = APIClient()
        self.client.force_authenticate(self.alice)

    def pin(self, message):
        response = self.client.post("/api/chat/messages/pin/", {"message": message.id, "is_pinned": True}, format="json")
        self.assertEqual(response.status_code, 200, response.content)

    def test_fourth_pin_replaces_the_oldest(self):
        messages = [Message.objects.create(room=self.room, sender=self.bob, content=f"m{i}") for i in range(4)]
        for message in messages:
            self.pin(message)
        pinned = self.client.get(f"/api/chat/rooms/{self.room.id}/pinned/").data
        self.assertEqual([row["content"] for row in pinned], ["m3", "m2", "m1"])
        self.assertFalse(Message.objects.get(pk=messages[0].pk).is_pinned)

    def test_pinned_list_requires_membership(self):
        outsider = APIClient()
        outsider.force_authenticate(make_user("+923000000853"))
        response = outsider.get(f"/api/chat/rooms/{self.room.id}/pinned/")
        self.assertIn(response.status_code, (403, 404))


class AllMediaTests(TestCase):
    def test_media_from_all_my_chats_only(self):
        alice = make_user("+923000000861")
        bob = make_user("+923000000862")
        carol = make_user("+923000000863")
        mine = make_room(alice, bob)
        other = make_room(bob, carol)
        image = SimpleUploadedFile("a.png", b"\x89PNG\r\n\x1a\n" + b"0" * 20, content_type="image/png")
        message = Message.objects.create(room=mine, sender=bob, message_type="IMAGE", content="")
        Attachment.objects.create(message=message, file=image, file_name="a.png", file_size=28, mime_type="image/png")
        hidden = Message.objects.create(room=other, sender=bob, message_type="IMAGE", content="")
        Attachment.objects.create(
            message=hidden,
            file=SimpleUploadedFile("b.png", b"x" * 10, content_type="image/png"),
            file_name="b.png",
            file_size=10,
            mime_type="image/png",
        )
        Message.objects.create(room=mine, sender=bob, content="see https://example.com/page")

        client = APIClient()
        client.force_authenticate(alice)
        media = client.get("/api/chat/media/?kind=media").data["results"]
        self.assertEqual([row["file_name"] for row in media], ["a.png"])
        self.assertEqual(media[0]["room_id"], mine.id)
        links = client.get("/api/chat/media/?kind=links").data["results"]
        self.assertEqual(links[0]["url"], "https://example.com/page")


class AssistantTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(make_user("+923000000871"))

    @override_settings(WHATSUP_AI_API_KEY="")
    def test_disabled_without_a_key(self):
        self.assertFalse(self.client.get("/api/chat/ai/").data["enabled"])
        response = self.client.post("/api/chat/ai/", {"messages": [{"role": "user", "content": "hi"}]}, format="json")
        self.assertEqual(response.status_code, 503)

    @override_settings(WHATSUP_AI_API_KEY="test-key")
    def test_relays_the_conversation(self):
        with mock.patch("apps.chat.assistant.call_model", return_value="Hello!") as call:
            response = self.client.post(
                "/api/chat/ai/",
                {"messages": [{"role": "assistant", "content": "ignored lead"}, {"role": "user", "content": "hi"}]},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["reply"], "Hello!")
        sent = call.call_args[0][0]
        self.assertEqual(sent, [{"role": "user", "content": "hi"}])
        self.assertEqual(call.call_args[0][1]["key"], "test-key")
        self.assertEqual(call.call_args[0][1]["provider"], "gemini")

    @override_settings(WHATSUP_AI_API_KEY="free-key", WHATSUP_AI_PROVIDER="gemini", WHATSUP_AI_MODEL="")
    def test_gemini_uses_the_openai_compatible_endpoint(self):
        import io
        import json

        captured = {}

        class FakeResponse(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["auth"] = request.get_header("Authorization")
            captured["body"] = json.loads(request.data)
            return FakeResponse(json.dumps({"choices": [{"message": {"content": "Salam!"}}]}).encode())

        with mock.patch("apps.chat.assistant.urllib.request.urlopen", fake_urlopen):
            response = self.client.post("/api/chat/ai/", {"messages": [{"role": "user", "content": "hi"}]}, format="json")
        self.assertEqual(response.data["reply"], "Salam!")
        self.assertIn("generativelanguage.googleapis.com", captured["url"])
        self.assertEqual(captured["auth"], "Bearer free-key")
        self.assertEqual(captured["body"]["model"], "gemini-3.5-flash-lite")
        self.assertEqual(captured["body"]["messages"][0]["role"], "system")

    @override_settings(WHATSUP_AI_API_KEY="gsk_x", WHATSUP_AI_PROVIDER="groq")
    def test_status_reports_the_provider(self):
        data = self.client.get("/api/chat/ai/").data
        self.assertEqual((data["enabled"], data["provider"]), (True, "groq"))

    @override_settings(WHATSUP_AI_API_KEY="test-key")
    def test_rejects_bad_history(self):
        response = self.client.post("/api/chat/ai/", {"messages": [{"role": "system", "content": "x"}]}, format="json")
        self.assertEqual(response.status_code, 400)
