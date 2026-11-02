"""
Web Push: subscription API, who gets pushed, payload privacy and cleanup of
expired subscriptions. ``pywebpush.webpush`` is mocked: no network.
"""

import json
from datetime import timedelta
from unittest import mock

import pywebpush
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Contact, Profile, User
from apps.calls.models import Call
from apps.chat.choices import RoomType
from apps.chat.models import ChatRoom, Participant
from apps.notifications.models import PushSubscription

# A real (test-only) key pair so py_vapid can sign the JWT.
VAPID = dict(
    VAPID_PUBLIC_KEY="BPPxw3uTGrzf0H2UMi30vRraon66qFpw0SM9iDVxgzZYCvA1XZ-TKGAOrDYtEUtZn5Qi1tVHPNVTAwqMAkH8l30",
    VAPID_PRIVATE_KEY="GLZweAPIBcAhoR4iggtlBNA85AV4nTzSWR5BsjUvETk",
    VAPID_SUBJECT="mailto:test@example.com",
    WHATSUP_PUSH_INLINE=True,
)
P256DH = "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM"
AUTH = "tBHItJI5svbpez7KI4CCXg"


def make_user(phone, name=""):
    user = User.objects.create_user(phone_number=phone, password="StrongPass123!")
    if name:
        user.profile.display_name = name
        user.profile.save()
    return user


def subscribe(user, endpoint, show_previews=True):
    return PushSubscription.objects.create(
        user=user, endpoint=endpoint, p256dh=P256DH, auth=AUTH, show_previews=show_previews
    )


def sent_payloads(mocked):
    """(endpoint, payload dict) for every webpush() call."""
    return [
        (call.kwargs["subscription_info"]["endpoint"], json.loads(call.kwargs["data"]))
        for call in mocked.call_args_list
    ]


@override_settings(**VAPID)
class SubscriptionAPITests(TestCase):
    def setUp(self):
        self.alice = make_user("+923070000001", "Alice")
        self.bob = make_user("+923070000002", "Bob")
        self.client = APIClient()
        self.client.force_authenticate(self.alice)

    def body(self, endpoint="https://fcm.googleapis.com/fcm/send/abc", **extra):
        return {"endpoint": endpoint, "keys": {"p256dh": P256DH, "auth": AUTH}, **extra}

    def test_public_key_requires_auth(self):
        self.assertEqual(APIClient().get("/api/notifications/push/public-key/").status_code, 401)
        response = self.client.get("/api/notifications/push/public-key/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"enabled": True, "public_key": VAPID["VAPID_PUBLIC_KEY"]})

    @override_settings(VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="")
    def test_disabled_without_keys(self):
        self.assertFalse(self.client.get("/api/notifications/push/public-key/").data["enabled"])
        with self.assertLogs("django.request", "ERROR"):
            response = self.client.post("/api/notifications/push/subscribe/", self.body(), format="json")
        self.assertEqual(response.status_code, 503)

    def test_subscribe_update_and_unsubscribe(self):
        response = self.client.post(
            "/api/notifications/push/subscribe/", self.body(show_previews=False), format="json", HTTP_USER_AGENT="UA"
        )
        self.assertEqual(response.status_code, 201, response.content)
        sub = PushSubscription.objects.get()
        self.assertEqual((sub.user, sub.show_previews, sub.user_agent), (self.alice, False, "UA"))

        # Same endpoint again updates the row (e.g. "Show previews" toggled).
        response = self.client.post("/api/notifications/push/subscribe/", self.body(show_previews=True), format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PushSubscription.objects.count(), 1)
        self.assertTrue(PushSubscription.objects.get().show_previews)

        # Another user cannot remove it.
        other = APIClient()
        other.force_authenticate(self.bob)
        other.post("/api/notifications/push/unsubscribe/", {"endpoint": sub.endpoint}, format="json")
        self.assertEqual(PushSubscription.objects.count(), 1)

        response = self.client.post("/api/notifications/push/unsubscribe/", {"endpoint": sub.endpoint}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PushSubscription.objects.exists())

    def test_same_browser_moves_to_new_account(self):
        self.client.post("/api/notifications/push/subscribe/", self.body(), format="json")
        other = APIClient()
        other.force_authenticate(self.bob)
        other.post("/api/notifications/push/subscribe/", self.body(), format="json")
        self.assertEqual(list(PushSubscription.objects.values_list("user_id", flat=True)), [self.bob.id])

    def test_rejects_non_public_endpoints(self):
        for endpoint in (
            "http://fcm.googleapis.com/x",
            "https://localhost/x",
            "https://127.0.0.1/x",
            "https://10.0.0.5/x",
            "https://[::1]/x",
        ):
            response = self.client.post("/api/notifications/push/subscribe/", self.body(endpoint), format="json")
            self.assertEqual(response.status_code, 400, endpoint)
        response = self.client.post("/api/notifications/push/subscribe/", {"endpoint": "https://push.example.com/1"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(PushSubscription.objects.exists())

    def test_generate_vapid_keys_command(self):
        from io import StringIO

        out = StringIO()
        call_command("generate_vapid_keys", "--subject", "mailto:a@b.c", stdout=out)
        lines = dict(line.split("=", 1) for line in out.getvalue().strip().splitlines())
        self.assertEqual(lines["VAPID_SUBJECT"], "mailto:a@b.c")
        self.assertEqual(len(lines["VAPID_PUBLIC_KEY"]), 87)  # 65 bytes, base64url
        self.assertEqual(len(lines["VAPID_PRIVATE_KEY"]), 43)  # 32 bytes, base64url
        from py_vapid import Vapid

        Vapid.from_string(lines["VAPID_PRIVATE_KEY"])  # loadable by pywebpush


@override_settings(**VAPID)
@mock.patch("pywebpush.webpush")
class MessagePushTests(TestCase):
    def setUp(self):
        self.alice = make_user("+923070000011", "Alice")
        self.bob = make_user("+923070000012", "Bob")
        self.carol = make_user("+923070000013", "Carol")
        self.room = ChatRoom.objects.create(created_by=self.alice, room_type=RoomType.PRIVATE)
        Participant.objects.create(room=self.room, user=self.alice)
        Participant.objects.create(room=self.room, user=self.bob)
        self.group = ChatRoom.objects.create(created_by=self.alice, room_type=RoomType.GROUP, name="Weekend")
        for user in (self.alice, self.bob, self.carol):
            Participant.objects.create(room=self.group, user=user)
        self.a = APIClient()
        self.a.force_authenticate(self.alice)
        self.bob_sub = subscribe(self.bob, "https://fcm.googleapis.com/fcm/send/bob")
        self.alice_sub = subscribe(self.alice, "https://fcm.googleapis.com/fcm/send/alice")
        self.carol_sub = subscribe(self.carol, "https://updates.push.services.mozilla.com/carol", show_previews=False)

    def send(self, room, text, client=None):
        with self.captureOnCommitCallbacks(execute=True):
            response = (client or self.a).post("/api/chat/messages/", {"room": room.id, "content": text}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response

    def test_private_message_pushes_offline_recipient_only(self, webpush):
        self.send(self.room, "hello bob")
        payloads = sent_payloads(webpush)
        self.assertEqual(len(payloads), 1)  # never to the sender
        endpoint, payload = payloads[0]
        self.assertEqual(endpoint, self.bob_sub.endpoint)
        self.assertEqual(payload["title"], "Alice")
        self.assertEqual(payload["body"], "hello bob")
        self.assertEqual(payload["room_id"], self.room.id)
        self.assertEqual(payload["tag"], f"room-{self.room.id}")
        self.assertEqual(payload["url"], f"/?room={self.room.id}")
        kwargs = webpush.call_args.kwargs
        self.assertEqual(kwargs["timeout"], 5)
        self.assertEqual(kwargs["vapid_claims"]["sub"], "mailto:test@example.com")

    def test_saved_contact_name_is_used(self, webpush):
        Contact.objects.create(owner=self.bob, contact_user=self.alice, name="Ally")
        self.send(self.room, "hi")
        self.assertEqual(sent_payloads(webpush)[0][1]["title"], "Ally")

    def test_users_with_an_open_socket_are_not_pushed(self, webpush):
        Profile.objects.filter(user=self.bob).update(active_connections=1, is_online=True)
        self.send(self.room, "you are online")
        webpush.assert_not_called()

    def test_muted_chat_is_not_pushed_until_mute_expires(self, webpush):
        Participant.objects.filter(room=self.room, user=self.bob).update(is_muted=True, muted_until=None)
        self.send(self.room, "muted forever")
        webpush.assert_not_called()
        Participant.objects.filter(room=self.room, user=self.bob).update(
            is_muted=True, muted_until=timezone.now() - timedelta(minutes=1)
        )
        self.send(self.room, "mute expired")
        self.assertEqual(len(webpush.call_args_list), 1)

    def test_message_hidden_for_blocker_is_not_pushed(self, webpush):
        b = APIClient()
        b.force_authenticate(self.bob)
        b.post("/api/chat/users/block/", {"user": self.alice.id}, format="json")
        self.send(self.room, "are you there?")
        webpush.assert_not_called()

    def test_group_message_and_preview_privacy(self, webpush):
        self.send(self.group, "secret plans")
        by_endpoint = dict(sent_payloads(webpush))
        self.assertEqual(set(by_endpoint), {self.bob_sub.endpoint, self.carol_sub.endpoint})
        self.assertEqual(by_endpoint[self.bob_sub.endpoint]["title"], "Weekend")
        self.assertEqual(by_endpoint[self.bob_sub.endpoint]["body"], "Alice: secret plans")
        # Carol turned "Show previews" off on that device: nothing revealing.
        carol = by_endpoint[self.carol_sub.endpoint]
        self.assertEqual((carol["title"], carol["body"]), ("MHTalk", "New message"))
        self.assertNotIn("secret", json.dumps(carol))
        self.assertNotIn("Alice", json.dumps(carol))
        self.assertNotIn("Weekend", json.dumps(carol))

    def test_gone_subscriptions_are_deleted(self, webpush):
        gone = mock.Mock(status_code=410)
        webpush.side_effect = pywebpush.WebPushException("Push failed: 410 Gone", response=gone)
        self.send(self.room, "anyone?")
        self.assertFalse(PushSubscription.objects.filter(pk=self.bob_sub.pk).exists())
        self.assertTrue(PushSubscription.objects.filter(pk=self.alice_sub.pk).exists())

    def test_other_failures_keep_the_subscription_and_never_break_sending(self, webpush):
        with self.assertLogs("apps.notifications.push", "WARNING"):
            webpush.side_effect = pywebpush.WebPushException("Push failed: 500", response=mock.Mock(status_code=500))
            self.send(self.room, "still sent")
            webpush.side_effect = TimeoutError("slow push service")
            self.send(self.room, "still sent 2")
        self.assertTrue(PushSubscription.objects.filter(pk=self.bob_sub.pk).exists())

    @override_settings(VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="")
    def test_nothing_happens_without_keys(self, webpush):
        self.send(self.room, "hi")
        webpush.assert_not_called()

    def test_runs_only_after_commit(self, webpush):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.a.post("/api/chat/messages/", {"room": self.room.id, "content": "x"}, format="json")
        webpush.assert_not_called()
        self.assertTrue(callbacks)

    def test_missed_call_card_pushes_but_answered_call_does_not(self, webpush):
        from apps.calls.events import publish_call_message

        missed = Call.objects.create(room=self.room, caller=self.alice, call_type="VIDEO", status="MISSED")
        with self.captureOnCommitCallbacks(execute=True):
            publish_call_message(missed)
        (endpoint, payload), = sent_payloads(webpush)
        self.assertEqual(endpoint, self.bob_sub.endpoint)
        self.assertEqual(payload["body"], "📞 Missed video call")
        self.assertEqual(payload["call_id"], missed.id)
        self.assertNotIn("__WHATSUP_", json.dumps(payload))

        webpush.reset_mock()
        answered = Call.objects.create(
            room=self.room, caller=self.alice, call_type="AUDIO", status="ENDED", answered_at=timezone.now()
        )
        with self.captureOnCommitCallbacks(execute=True):
            publish_call_message(answered)
        webpush.assert_not_called()


@override_settings(**VAPID)
@mock.patch("pywebpush.webpush")
class CallPushTests(TestCase):
    def setUp(self):
        self.alice = make_user("+923070000021", "Alice")
        self.bob = make_user("+923070000022", "Bob")
        self.room = ChatRoom.objects.create(created_by=self.alice, room_type=RoomType.PRIVATE)
        Participant.objects.create(room=self.room, user=self.alice)
        Participant.objects.create(room=self.room, user=self.bob)
        self.a = APIClient()
        self.a.force_authenticate(self.alice)
        self.bob_sub = subscribe(self.bob, "https://fcm.googleapis.com/fcm/send/bob")
        subscribe(self.alice, "https://fcm.googleapis.com/fcm/send/alice")

    def start(self, call_type="AUDIO"):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.a.post("/api/calls/start/", {"room": self.room.id, "call_type": call_type}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response

    def test_incoming_call_is_pushed_to_callee(self, webpush):
        response = self.start()
        (endpoint, payload), = sent_payloads(webpush)
        self.assertEqual(endpoint, self.bob_sub.endpoint)
        self.assertEqual(payload["type"], "call")
        self.assertEqual(payload["title"], "Alice")
        self.assertEqual(payload["body"], "Incoming voice call from Alice")
        self.assertEqual(payload["call_id"], response.data["id"])
        self.assertEqual(webpush.call_args.kwargs["ttl"], 60)

    def test_online_callee_and_blocker_are_not_pushed(self, webpush):
        Profile.objects.filter(user=self.bob).update(active_connections=2)
        self.start()
        webpush.assert_not_called()

    def test_blocked_caller_never_pushes(self, webpush):
        b = APIClient()
        b.force_authenticate(self.bob)
        b.post("/api/chat/users/block/", {"user": self.alice.id}, format="json")
        self.start("VIDEO")
        webpush.assert_not_called()


@override_settings(**VAPID)
@mock.patch("pywebpush.webpush")
class FeatureMessagePushTests(TestCase):
    """Polls, view once, system notices / group events and group calls."""

    def setUp(self):
        self.alice = make_user("+923070000031", "Alice")
        self.bob = make_user("+923070000032", "Bob")
        self.group = ChatRoom.objects.create(created_by=self.alice, room_type=RoomType.GROUP, name="Lunch club")
        Participant.objects.create(room=self.group, user=self.alice, is_admin=True)
        Participant.objects.create(room=self.group, user=self.bob)
        self.a = APIClient()
        self.a.force_authenticate(self.alice)
        self.bob_sub = subscribe(self.bob, "https://fcm.googleapis.com/fcm/send/bob3")

    def test_poll_shows_question(self, webpush):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.a.post(
                "/api/chat/messages/",
                {"room": self.group.id, "message_type": "POLL", "content": {"question": "Lunch?", "options": ["Pizza", "Salad"]}},
                format="json",
            )
        self.assertEqual(response.status_code, 201, response.content)
        (_, payload), = sent_payloads(webpush)
        self.assertEqual(payload["body"], "Alice: 📊 Poll: Lunch?")

    def test_view_once_never_reveals_caption(self, webpush):
        from apps.chat.utils import broadcast_message, get_message_with_relations
        from apps.chat.models import Message

        message = Message.objects.create(
            room=self.group, sender=self.alice, message_type="IMAGE", is_view_once=True, content="secret caption"
        )
        with self.captureOnCommitCallbacks(execute=True):
            broadcast_message(get_message_with_relations(message.pk))
        (_, payload), = sent_payloads(webpush)
        self.assertEqual(payload["body"], "Alice: 📷 View once photo")
        self.assertNotIn("secret", json.dumps(payload))

    def test_system_notices_and_group_events_do_not_push(self, webpush):
        from apps.chat.group_events import post_group_event
        from apps.chat.models import Message
        from apps.chat.utils import broadcast_message, get_message_with_relations

        with self.captureOnCommitCallbacks(execute=True):
            post_group_event(self.group, self.alice, "renamed", "Alice changed the group name")
            notice = Message.objects.create(
                room=self.group, sender=self.alice, content='__WHATSUP_SYSTEM__:{"kind":"disappearing","seconds":86400}'
            )
            broadcast_message(get_message_with_relations(notice.pk))
        webpush.assert_not_called()

    def test_incoming_group_call_is_pushed(self, webpush):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.a.post("/api/calls/start/", {"room": self.group.id, "call_type": "VIDEO"}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        (endpoint, payload), = sent_payloads(webpush)
        self.assertEqual(endpoint, self.bob_sub.endpoint)
        self.assertEqual(payload["type"], "call")
        self.assertEqual(payload["title"], "Lunch club")
        self.assertEqual(payload["body"], "Incoming group video call from Alice")
