from django.test import TestCase

# Create your tests here.


# ---------------------------------------------------------------- signalling
import json as _json

from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.test import TransactionTestCase
from rest_framework_simplejwt.tokens import AccessToken


class CallSignallingSocketTests(TransactionTestCase):
    """Offer/answer reach the other person through the shared channel map."""

    def setUp(self):
        from apps.accounts.models import User
        from apps.calls.models import Call, CallParticipant
        from apps.chat.choices import RoomType
        from apps.chat.models import ChatRoom, Participant

        cache.clear()
        self.alice = User.objects.create_user(phone_number="+923050000001", password="StrongPass123!")
        self.bob = User.objects.create_user(phone_number="+923050000002", password="StrongPass123!")
        self.room = ChatRoom.objects.create(created_by=self.alice, room_type=RoomType.PRIVATE)
        Participant.objects.create(room=self.room, user=self.alice)
        Participant.objects.create(room=self.room, user=self.bob)
        self.call = Call.objects.create(room=self.room, caller=self.alice, call_type="AUDIO", status="RINGING")
        CallParticipant.objects.create(call=self.call, user=self.alice)
        CallParticipant.objects.create(call=self.call, user=self.bob)

    def socket(self, user):
        from config.asgi import application

        return WebsocketCommunicator(application, f"/ws/calls/{self.room.id}/?token={AccessToken.for_user(user)}")

    async def test_offer_is_delivered_to_target_and_mapping_is_shared(self):
        alice, bob = self.socket(self.alice), self.socket(self.bob)
        self.assertTrue((await alice.connect())[0])
        self.assertTrue((await bob.connect())[0])
        # the user -> socket map lives in the shared cache (Redis in production)
        self.assertTrue(await cache.aget(f"call_channel:{self.bob.id}"))
        await alice.send_json_to({"event": "offer", "call_id": self.call.id, "target": self.bob.id, "sdp": "v=0"})
        for _ in range(10):
            message = _json.loads(await bob.receive_from(timeout=3))
            if message.get("event") == "offer":
                break
        else:
            self.fail("offer never reached bob")
        self.assertEqual(message["payload"]["sdp"], "v=0")
        await bob.disconnect()
        self.assertIsNone(await cache.aget(f"call_channel:{self.bob.id}"))
        await alice.disconnect()


class CallReloadTests(CallSignallingSocketTests):
    """A reloaded page can get its call back (ringing or ongoing)."""

    def _ongoing(self):
        from django.utils import timezone

        self.call.status = "ONGOING"
        self.call.answered_at = timezone.now()
        self.call.save(update_fields=["status", "answered_at"])

    def test_current_lists_my_ringing_and_ongoing_calls(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(self.bob)
        data = client.get("/api/calls/current/").json()
        self.assertEqual([c["id"] for c in data], [self.call.id])
        self._ongoing()
        self.assertEqual(len(client.get("/api/calls/current/").json()), 1)
        self.call.end()
        self.assertEqual(client.get("/api/calls/current/").json(), [])

    async def test_reload_reconnect_within_grace_keeps_the_call(self):
        from asgiref.sync import sync_to_async
        from django.test import override_settings

        await sync_to_async(self._ongoing)()
        with override_settings(CALL_REJOIN_GRACE_SECONDS=0.5):
            alice, bob = self.socket(self.alice), self.socket(self.bob)
            await alice.connect()
            await bob.connect()
            await bob.disconnect()  # bob's page reloads...
            bob = self.socket(self.bob)
            await bob.connect()  # ...and comes back in time
            import asyncio

            await asyncio.sleep(0.9)
            await sync_to_async(self.call.refresh_from_db)()
            self.assertEqual(self.call.status, "ONGOING")
            await bob.disconnect()  # now he really leaves
            await asyncio.sleep(0.9)
            await sync_to_async(self.call.refresh_from_db)()
            self.assertEqual(self.call.status, "ENDED")
            ended = False
            for _ in range(10):
                try:
                    message = _json.loads(await alice.receive_from(timeout=1))
                except Exception:  # noqa: BLE001
                    break
                if message.get("event") == "call_ended":
                    ended = True
                    break
            self.assertTrue(ended, "alice was not told the call ended")
            await alice.disconnect()
