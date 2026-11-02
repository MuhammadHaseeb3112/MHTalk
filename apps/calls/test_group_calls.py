"""Group calls: ringing, join / decline / leave rules, the cap, signalling."""

import json
from unittest import mock

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import User
from apps.calls.choices import CallStatus, ParticipantState
from apps.calls.constants import MAX_GROUP_CALL_PARTICIPANTS
from apps.calls.events import CALL_EVENT_PREFIX, unseen_missed_count
from apps.calls.models import Call, CallParticipant
from apps.chat.choices import RoomType
from apps.chat.models import ChatRoom, Message, Participant


def make_group(owner, members, name="Team"):
    room = ChatRoom.objects.create(created_by=owner, room_type=RoomType.GROUP, name=name)
    for user in [owner, *members]:
        Participant.objects.create(room=room, user=user, is_admin=user == owner)
    return room


class GroupCallBase:
    def setUp(self):
        cache.clear()
        # Ring timeouts are threads in production; tests call the timeout directly.
        patcher = mock.patch("apps.calls.lifecycle.Timer")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.users = [
            User.objects.create_user(phone_number=f"+92305100{index:04d}", password="StrongPass123!")
            for index in range(4)
        ]
        self.alice, self.bob, self.carol, self.dave = self.users
        self.room = make_group(self.alice, [self.bob, self.carol, self.dave])

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def start(self, user=None, call_type="VIDEO", room=None):
        return self.client_for(user or self.alice).post(
            "/api/calls/start/", {"room": (room or self.room).id, "call_type": call_type}, format="json"
        )

    def join(self, user, call_id):
        return self.client_for(user).post(f"/api/calls/{call_id}/accept/")

    def leave(self, user, call_id):
        return self.client_for(user).post(f"/api/calls/{call_id}/end/")

    def decline(self, user, call_id):
        return self.client_for(user).post(f"/api/calls/{call_id}/reject/")


class GroupCallApiTests(GroupCallBase, TestCase):
    def test_start_rings_every_member(self):
        layer = get_channel_layer()
        inboxes = {}
        for user in (self.bob, self.carol, self.dave):
            channel = async_to_sync(layer.new_channel)()
            async_to_sync(layer.group_add)(f"user_call_{user.id}", channel)
            inboxes[user.id] = channel

        response = self.start()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["is_group"])
        call = Call.objects.get(pk=response.data["id"])
        states = dict(call.participants.values_list("user_id", "state"))
        self.assertEqual(states[self.alice.id], ParticipantState.JOINED)
        for user in (self.bob, self.carol, self.dave):
            self.assertEqual(states[user.id], ParticipantState.RINGING)
            message = async_to_sync(layer.receive)(inboxes[user.id])
            self.assertEqual(message["event"], "incoming_call")
            self.assertEqual(message["payload"]["call_id"], call.id)
            self.assertTrue(message["payload"]["is_group"])

    def test_second_start_offers_join_and_ringing_members_stay_free(self):
        call_id = self.start().data["id"]
        conflict = self.start(self.bob)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.data["call_id"], call_id)
        # Bob is only ringing: he can still place a private call.
        private = ChatRoom.objects.create(created_by=self.bob, room_type=RoomType.PRIVATE)
        Participant.objects.create(room=private, user=self.bob)
        Participant.objects.create(room=private, user=self.carol)
        self.assertEqual(self.start(self.bob, room=private).status_code, 201)
        # ... and Carol, now ringing in that private call, cannot join the group call.
        self.assertEqual(self.join(self.carol, call_id).status_code, 409)

    def test_join_decline_leave_rules(self):
        call_id = self.start().data["id"]

        joined = self.join(self.bob, call_id)
        self.assertEqual(joined.status_code, 200, joined.data)
        self.assertEqual(joined.data["present"], [self.alice.id])
        call = Call.objects.get(pk=call_id)
        self.assertEqual(call.status, CallStatus.ONGOING)

        # Declining only affects Dave.
        self.assertEqual(self.decline(self.dave, call_id).status_code, 200)
        call.refresh_from_db()
        self.assertEqual(call.status, CallStatus.ONGOING)

        joined = self.join(self.carol, call_id)
        self.assertEqual(sorted(joined.data["present"]), sorted([self.alice.id, self.bob.id]))

        # The caller leaves: 2 remain, the call goes on.
        self.leave(self.alice, call_id)
        call.refresh_from_db()
        self.assertEqual(call.status, CallStatus.ONGOING)

        # Alice rejoins (rejoin after leaving) and Dave joins late after declining.
        self.assertEqual(sorted(self.join(self.alice, call_id).data["present"]), sorted([self.bob.id, self.carol.id]))
        self.assertEqual(self.join(self.dave, call_id).status_code, 200)

        for user in (self.alice, self.bob, self.carol):
            self.leave(user, call_id)
        # Dave is alone: the call ended for everyone.
        call.refresh_from_db()
        self.assertEqual(call.status, CallStatus.ENDED)
        self.assertFalse(CallParticipant.objects.filter(call=call, state=ParticipantState.JOINED).exists())

        # One call card for the group, listing who joined.
        message = Message.objects.get(room=self.room, client_message_id=f"call-event-{call_id}")
        payload = json.loads(message.content[len(CALL_EVENT_PREFIX):])
        self.assertTrue(payload["is_group"])
        self.assertEqual(payload["joined_count"], 4)

        # Joining an ended call is refused.
        self.assertEqual(self.join(self.bob, call_id).status_code, 400)

    def test_cap_of_eight_participants(self):
        extra = [
            User.objects.create_user(phone_number=f"+92305200{index:04d}", password="StrongPass123!")
            for index in range(6)
        ]
        for user in extra:
            Participant.objects.create(room=self.room, user=user)
        call_id = self.start().data["id"]
        people = [self.bob, self.carol, self.dave, *extra]  # 9 besides Alice
        for user in people[: MAX_GROUP_CALL_PARTICIPANTS - 1]:
            self.assertEqual(self.join(user, call_id).status_code, 200)
        refused = self.join(people[MAX_GROUP_CALL_PARTICIPANTS - 1], call_id)
        self.assertEqual(refused.status_code, 409)
        self.assertIn("full", refused.data["detail"])
        # Someone leaves: there is room again.
        self.leave(self.bob, call_id)
        self.assertEqual(self.join(people[MAX_GROUP_CALL_PARTICIPANTS - 1], call_id).status_code, 200)

    def test_non_members_cannot_join_or_start(self):
        outsider = User.objects.create_user(phone_number="+923059999999", password="StrongPass123!")
        call_id = self.start().data["id"]
        self.assertEqual(self.join(outsider, call_id).status_code, 403)
        other_group = make_group(self.bob, [self.carol])
        self.assertEqual(self.start(outsider, room=other_group).status_code, 403)

    def test_everyone_declines_ends_call(self):
        call_id = self.start().data["id"]
        for user in (self.bob, self.carol, self.dave):
            self.decline(user, call_id)
        call = Call.objects.get(pk=call_id)
        self.assertEqual(call.status, CallStatus.REJECTED)
        for user in (self.bob, self.carol, self.dave):
            self.assertEqual(unseen_missed_count(user), 0)

    def test_ring_timeout_misses_only_people_who_never_joined(self):
        from apps.calls.lifecycle import timeout_call

        call_id = self.start().data["id"]
        self.join(self.bob, call_id)
        self.decline(self.dave, call_id)
        timeout_call(call_id)

        call = Call.objects.get(pk=call_id)
        self.assertEqual(call.status, CallStatus.ONGOING)  # Alice and Bob still talking
        self.assertEqual(call.participants.get(user=self.carol).state, ParticipantState.MISSED)
        # Carol can still join late.
        self.assertEqual(self.join(self.carol, call_id).status_code, 200)
        self.leave(self.carol, call_id)
        self.leave(self.bob, call_id)
        call.refresh_from_db()
        self.assertEqual(call.status, CallStatus.ENDED)

        self.assertEqual(unseen_missed_count(self.carol), 0)  # she joined
        self.assertEqual(unseen_missed_count(self.dave), 0)  # declined
        self.assertEqual(unseen_missed_count(self.bob), 0)

    def test_missed_badge_and_history_for_people_who_never_joined(self):
        from apps.calls.lifecycle import timeout_call

        call_id = self.start(call_type="AUDIO").data["id"]
        self.join(self.bob, call_id)
        timeout_call(call_id)
        self.leave(self.bob, call_id)

        self.assertEqual(unseen_missed_count(self.carol), 1)
        self.assertEqual(unseen_missed_count(self.bob), 0)
        history = self.client_for(self.carol).get("/api/calls/history/").data
        rows = history["results"] if isinstance(history, dict) else history
        self.assertTrue(rows[0]["is_missed"])
        missed = self.client_for(self.carol).get("/api/calls/history/?missed=1").data
        missed = missed["results"] if isinstance(missed, dict) else missed
        self.assertEqual([row["id"] for row in missed], [call_id])
        bob_missed = self.client_for(self.bob).get("/api/calls/history/?missed=1").data
        bob_missed = bob_missed["results"] if isinstance(bob_missed, dict) else bob_missed
        self.assertEqual(bob_missed, [])

    def test_timeout_with_nobody_joined_is_missed_for_all(self):
        from apps.calls.lifecycle import timeout_call

        call_id = self.start().data["id"]
        timeout_call(call_id)
        call = Call.objects.get(pk=call_id)
        self.assertEqual(call.status, CallStatus.MISSED)
        self.assertEqual(unseen_missed_count(self.bob), 1)
        self.assertEqual(unseen_missed_count(self.alice), 0)

    def test_active_calls_endpoint(self):
        call_id = self.start().data["id"]
        active = self.client_for(self.carol).get("/api/calls/active/")
        self.assertEqual(active.status_code, 200)
        self.assertEqual([row["id"] for row in active.data], [call_id])
        outsider = User.objects.create_user(phone_number="+923059999998", password="StrongPass123!")
        self.assertEqual(self.client_for(outsider).get("/api/calls/active/").data, [])
        self.leave(self.alice, call_id)  # caller alone hangs up -> ends
        self.assertEqual(self.client_for(self.carol).get("/api/calls/active/").data, [])

    def test_one_to_one_calls_unchanged(self):
        private = ChatRoom.objects.create(created_by=self.alice, room_type=RoomType.PRIVATE)
        Participant.objects.create(room=private, user=self.alice)
        Participant.objects.create(room=private, user=self.bob)
        call_id = self.start(room=private).data["id"]
        self.assertFalse(Call.objects.get(pk=call_id).is_group)
        self.assertEqual(self.join(self.bob, call_id).data, {"message": "Call accepted."})
        self.leave(self.bob, call_id)
        self.assertEqual(Call.objects.get(pk=call_id).status, CallStatus.ENDED)


class GroupCallSignallingTests(GroupCallBase, TransactionTestCase):
    def socket(self, user):
        from config.asgi import application

        return WebsocketCommunicator(application, f"/ws/calls/{self.room.id}/?token={AccessToken.for_user(user)}")

    async def receive_event(self, communicator, name):
        for _ in range(20):
            message = json.loads(await communicator.receive_from(timeout=3))
            if message.get("event") == name:
                return message
        self.fail(f"{name} never arrived")

    async def test_signals_only_between_people_in_the_call(self):
        from asgiref.sync import sync_to_async

        call_id = (await sync_to_async(self.start)()).data["id"]
        await sync_to_async(self.join)(self.bob, call_id)

        alice, bob, carol = self.socket(self.alice), self.socket(self.bob), self.socket(self.carol)
        for communicator in (alice, bob, carol):
            self.assertTrue((await communicator.connect())[0])

        # Bob joined later: he offers to Alice. The server stamps the sender.
        await bob.send_json_to({"event": "offer", "call_id": call_id, "target": self.alice.id, "sdp": "v=0", "from": 999})
        offer = await self.receive_event(alice, "offer")
        self.assertEqual(offer["payload"]["from"], self.bob.id)

        # Carol is only ringing: she can't be offered to, nor send offers.
        await alice.send_json_to({"event": "offer", "call_id": call_id, "target": self.carol.id, "sdp": "v=0"})
        error = await self.receive_event(alice, "error")
        self.assertIn("not in this call", error["message"])
        await carol.send_json_to({"event": "offer", "call_id": call_id, "target": self.alice.id, "sdp": "v=0"})
        error = await self.receive_event(carol, "error")
        self.assertIn("not in this call", error["message"])

        # Closing the call screen leaves the call; with one person left it ends.
        await bob.disconnect()
        left = await self.receive_event(alice, "member_left")
        self.assertEqual(left["payload"]["user"], self.bob.id)
        ended = await self.receive_event(alice, "call_ended")
        self.assertEqual(ended["payload"]["call_id"], call_id)

        # Signals for a finished call are refused.
        await alice.send_json_to({"event": "ice_candidate", "call_id": call_id, "target": self.bob.id, "candidate": "c", "sdpMid": "0", "sdpMLineIndex": 0})
        error = await self.receive_event(alice, "error")
        self.assertIn("no longer active", error["message"])

        await alice.disconnect()
        await carol.disconnect()

    async def test_end_call_signal_only_leaves_a_group_call(self):
        from asgiref.sync import sync_to_async

        call_id = (await sync_to_async(self.start)()).data["id"]
        await sync_to_async(self.join)(self.bob, call_id)
        await sync_to_async(self.join)(self.carol, call_id)
        alice = self.socket(self.alice)
        self.assertTrue((await alice.connect())[0])
        await alice.send_json_to({"event": "end_call", "call_id": call_id})
        await self.receive_event(alice, "member_left")
        call = await Call.objects.aget(pk=call_id)
        self.assertEqual(call.status, CallStatus.ONGOING)
        await alice.disconnect()
