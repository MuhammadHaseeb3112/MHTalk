"""
Polls, @mentions, disappearing messages, view once media, link previews and
location messages.
"""

import json
import os
import shutil
import socket
import tempfile
import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from unittest import mock

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.chat import link_preview
from apps.chat.choices import SYSTEM_PREFIX, RoomType
from apps.chat.features import can_change_disappearing
from apps.chat.models import (
    Attachment,
    ChatRoom,
    Message,
    MessageMention,
    Participant,
    Poll,
    PollVote,
    StarredMessage,
    ViewOnceOpen,
    VoiceNote,
)
from config.media_views import is_private_media_path, serve_media

TEST_MEDIA = tempfile.mkdtemp(prefix="mhtalk-feature-media-")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def make_user(phone):
    return User.objects.create_user(phone_number=phone, password="StrongPass123!")


def make_room(*users, group=False):
    room = ChatRoom.objects.create(
        created_by=users[0],
        room_type=RoomType.GROUP if group else RoomType.PRIVATE,
        name="Team" if group else "",
    )
    for index, user in enumerate(users):
        Participant.objects.create(room=room, user=user, is_admin=group and index == 0)
    return room


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def send(client, room, **fields):
    payload = {"room": room.id, "message_type": "TEXT", **fields}
    return client.post("/api/chat/messages/", payload, format="json")


# ==========================================================================
# Polls
# ==========================================================================

@override_settings(MEDIA_ROOT=TEST_MEDIA)
class PollTests(TestCase):
    def setUp(self):
        self.alice = make_user("+923100000001")
        self.bob = make_user("+923100000002")
        self.carol = make_user("+923100000003")
        self.group = make_room(self.alice, self.bob, self.carol, group=True)
        self.alice_client = client_for(self.alice)
        self.bob_client = client_for(self.bob)

    def create_poll(self, options=("Pizza", "Burger", "Salad"), allow_multiple=False, room=None):
        response = send(
            self.alice_client,
            room or self.group,
            message_type="POLL",
            content={"question": "Lunch?", "options": list(options), "allow_multiple": allow_multiple},
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.data["data"]

    def vote(self, client, message_id, option_ids):
        return client.post(f"/api/chat/messages/{message_id}/poll/vote/", {"option_ids": option_ids}, format="json")

    def test_create_poll_returns_options(self):
        data = self.create_poll()
        self.assertEqual(data["message_type"], "POLL")
        self.assertEqual(data["content"], "Lunch?")
        self.assertEqual([o["text"] for o in data["poll"]["options"]], ["Pizza", "Burger", "Salad"])
        self.assertFalse(data["poll"]["allow_multiple"])
        self.assertEqual(data["poll"]["total_voters"], 0)

    def test_poll_works_in_private_chats(self):
        private = make_room(self.alice, self.bob)
        data = self.create_poll(room=private)
        self.assertEqual(len(data["poll"]["options"]), 3)

    def test_poll_validation(self):
        cases = [
            {"question": "", "options": ["a", "b"]},
            {"question": "Q", "options": ["only one"]},
            {"question": "Q", "options": [str(i) for i in range(13)]},
            {"question": "Q", "options": ["same", "Same"]},
            {"question": "Q", "options": "a,b"},
            {"question": "Q" * 256, "options": ["a", "b"]},
            {"question": "Q", "options": ["a", "b" * 101]},
        ]
        for content in cases:
            response = send(self.alice_client, self.group, message_type="POLL", content=content)
            self.assertEqual(response.status_code, 400, content)
        self.assertFalse(Poll.objects.exists())
        # Blank options are ignored; 12 is the maximum.
        data = self.create_poll(options=[str(i) for i in range(12)] + ["", "  "])
        self.assertEqual(len(data["poll"]["options"]), 12)

    def test_single_answer_vote_change_and_unvote(self):
        data = self.create_poll()
        pizza, burger = data["poll"]["options"][0]["id"], data["poll"]["options"][1]["id"]
        response = self.vote(self.bob_client, data["id"], [pizza])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["poll"]["options"][0]["voters"], [self.bob.id])
        # Two answers in a single-answer poll are refused.
        self.assertEqual(self.vote(self.bob_client, data["id"], [pizza, burger]).status_code, 400)
        # Changing the answer moves the vote.
        poll = self.vote(self.bob_client, data["id"], [burger]).data["poll"]
        self.assertEqual(poll["options"][0]["count"], 0)
        self.assertEqual(poll["options"][1]["voters"], [self.bob.id])
        # Empty list removes the vote.
        poll = self.vote(self.bob_client, data["id"], []).data["poll"]
        self.assertEqual(poll["total_voters"], 0)
        self.assertFalse(PollVote.objects.exists())

    def test_multiple_answers(self):
        data = self.create_poll(allow_multiple=True)
        ids = [option["id"] for option in data["poll"]["options"]]
        poll = self.vote(self.bob_client, data["id"], ids[:2]).data["poll"]
        self.assertEqual([o["count"] for o in poll["options"]], [1, 1, 0])
        poll = self.vote(client_for(self.carol), data["id"], [ids[1]]).data["poll"]
        self.assertEqual([o["count"] for o in poll["options"]], [1, 2, 0])
        self.assertEqual(poll["total_voters"], 2)

    def test_vote_validation_and_membership(self):
        data = self.create_poll()
        other = self.create_poll(options=("x", "y"))
        foreign_option = other["poll"]["options"][0]["id"]
        self.assertEqual(self.vote(self.bob_client, data["id"], [foreign_option]).status_code, 400)
        self.assertEqual(self.vote(self.bob_client, data["id"], ["abc"]).status_code, 400)
        self.assertEqual(self.bob_client.post(f"/api/chat/messages/{data['id']}/poll/vote/", {"option_ids": 5}, format="json").status_code, 400)
        outsider = client_for(make_user("+923100000009"))
        option = data["poll"]["options"][0]["id"]
        self.assertEqual(self.vote(outsider, data["id"], [option]).status_code, 404)
        text = Message.objects.create(room=self.group, sender=self.alice, content="hi")
        self.assertEqual(self.vote(self.bob_client, text.id, [option]).status_code, 400)

    def test_vote_is_broadcast_as_patch(self):
        data = self.create_poll()
        option = data["poll"]["options"][2]["id"]
        with mock.patch("apps.chat.feature_views.broadcast_message_patch") as patch:
            self.vote(self.bob_client, data["id"], [option])
        room_id, message_id, payload = patch.call_args.args
        self.assertEqual((room_id, message_id), (self.group.id, data["id"]))
        self.assertEqual(payload["poll"]["options"][2]["voters"], [self.bob.id])

    def test_room_socket_receives_patch(self):
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        channel = async_to_sync(layer.new_channel)()
        async_to_sync(layer.group_add)(f"chat_{self.group.id}", channel)
        data = self.create_poll()
        # drain the chat.message event of the poll itself
        async_to_sync(layer.receive)(channel)
        self.vote(self.bob_client, data["id"], [data["poll"]["options"][0]["id"]])
        event = async_to_sync(layer.receive)(channel)
        self.assertEqual(event["type"], "message.patch")
        self.assertEqual(event["patch"]["poll"]["options"][0]["voters"], [self.bob.id])

    def test_forwarding_a_poll_copies_options_without_votes(self):
        data = self.create_poll()
        self.vote(self.bob_client, data["id"], [data["poll"]["options"][0]["id"]])
        target = make_room(self.alice, self.carol)
        response = self.alice_client.post("/api/chat/messages/forward/", {"message": data["id"], "room": target.id}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        copy = response.data["data"]["poll"]
        self.assertEqual([o["text"] for o in copy["options"]], ["Pizza", "Burger", "Salad"])
        self.assertEqual(copy["total_voters"], 0)

    def test_polls_cannot_be_edited(self):
        data = self.create_poll()
        response = self.alice_client.patch(f"/api/chat/messages/{data['id']}/", {"content": "x"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_message_list_with_polls_has_no_n_plus_one(self):
        def count(polls):
            room = make_room(self.alice, self.bob, self.carol, group=True)
            for _ in range(polls):
                data = self.create_poll(room=room)
                self.vote(self.bob_client, data["id"], [data["poll"]["options"][0]["id"]])
                Message.objects.create(room=room, sender=self.bob, content=f"hey @{self.alice.phone_number}")
            with CaptureQueriesContext(connection) as context:
                response = self.alice_client.get(f"/api/chat/rooms/{room.id}/messages/?limit=50")
            self.assertEqual(response.status_code, 200)
            return len(context.captured_queries)

        self.assertEqual(count(2), count(6))


# ==========================================================================
# Mentions
# ==========================================================================

class MentionTests(TestCase):
    def setUp(self):
        self.alice = make_user("+923200000001")
        self.bob = make_user("+923200000002")
        self.carol = make_user("+923200000003")
        self.group = make_room(self.alice, self.bob, self.carol, group=True)
        self.alice_client = client_for(self.alice)
        self.bob_client = client_for(self.bob)

    def room_row(self, client, room):
        rows = client.get("/api/chat/rooms/?archived=all").data
        return next(row for row in rows if row["id"] == room.id)

    def test_mentions_are_stored_and_serialized(self):
        response = send(self.alice_client, self.group, content=f"hi @{self.bob.phone_number}", mentions=[self.bob.id])
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["data"]["mentions"], [self.bob.id])
        listed = self.bob_client.get(f"/api/chat/rooms/{self.group.id}/messages/").data
        self.assertEqual(listed[-1]["mentions"], [self.bob.id])

    def test_non_members_and_private_chats_are_rejected(self):
        outsider = make_user("+923200000009")
        response = send(self.alice_client, self.group, content="@x", mentions=[outsider.id])
        self.assertEqual(response.status_code, 400)
        private = make_room(self.alice, self.bob)
        response = send(self.alice_client, private, content="@x", mentions=[self.bob.id])
        self.assertEqual(response.status_code, 400)
        self.assertFalse(MessageMention.objects.exists())

    def test_unread_mention_badge_until_read(self):
        send(self.alice_client, self.group, content=f"@{self.bob.phone_number} look", mentions=[self.bob.id])
        self.assertTrue(self.room_row(self.bob_client, self.group)["unread_mention"])
        self.assertFalse(self.room_row(client_for(self.carol), self.group)["unread_mention"])
        self.assertFalse(self.room_row(self.alice_client, self.group)["unread_mention"])
        info = self.bob_client.get(f"/api/chat/rooms/{self.group.id}/info/").data
        self.assertTrue(info["unread_mention"])
        self.bob_client.post(f"/api/chat/rooms/{self.group.id}/read/")
        self.assertFalse(self.room_row(self.bob_client, self.group)["unread_mention"])

    def test_upload_caption_mentions(self):
        response = self.alice_client.post(
            "/api/chat/messages/upload/",
            {
                "room": self.group.id,
                "message_type": "IMAGE",
                "content": f"@{self.carol.phone_number}",
                "mentions": f"{self.carol.id}",
                "file": SimpleUploadedFile("a.png", PNG, content_type="image/png"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["data"]["mentions"], [self.carol.id])


# ==========================================================================
# Disappearing messages
# ==========================================================================

@override_settings(MEDIA_ROOT=TEST_MEDIA)
class DisappearingMessagesTests(TestCase):
    def setUp(self):
        self.alice = make_user("+923300000001")
        self.bob = make_user("+923300000002")
        self.room = make_room(self.alice, self.bob)
        self.alice_client = client_for(self.alice)
        self.bob_client = client_for(self.bob)

    def set_timer(self, client, seconds, room=None):
        return client.post(f"/api/chat/rooms/{(room or self.room).id}/disappearing/", {"seconds": seconds}, format="json")

    def expire(self, *messages):
        Message.all_objects.filter(pk__in=[m.pk for m in messages]).update(expires_at=timezone.now() - timedelta(seconds=1))

    def test_turning_on_posts_system_message_and_sets_expiry(self):
        response = self.set_timer(self.alice_client, 604800)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["disappearing_seconds"], 604800)
        notice = response.data["message"]
        self.assertTrue(notice["content"].startswith(SYSTEM_PREFIX))
        payload = json.loads(notice["content"][len(SYSTEM_PREFIX):])
        self.assertEqual(payload, {"kind": "disappearing", "seconds": 604800, "actor_id": self.alice.id})
        self.assertIsNone(notice["expires_at"])  # the notice itself stays
        sent = send(self.bob_client, self.room, content="secret").data["data"]
        self.assertIsNotNone(sent["expires_at"])
        message = Message.objects.get(pk=sent["id"])
        self.assertAlmostEqual((message.expires_at - message.created_at).total_seconds(), 604800, delta=5)
        info = self.bob_client.get(f"/api/chat/rooms/{self.room.id}/info/").data
        self.assertEqual(info["disappearing_seconds"], 604800)
        # Same value again: no duplicate notice.
        self.assertIsNone(self.set_timer(self.alice_client, 604800).data["message"])
        # Off
        self.assertEqual(self.set_timer(self.bob_client, 0).data["disappearing_seconds"], 0)
        self.assertIsNone(send(self.bob_client, self.room, content="kept").data["data"]["expires_at"])

    def test_system_notice_is_not_unread(self):
        self.set_timer(self.alice_client, 86400)
        row = next(r for r in self.bob_client.get("/api/chat/rooms/").data if r["id"] == self.room.id)
        self.assertEqual(row["unread_count"], 0)
        self.assertTrue(row["last_message"]["content"].startswith(SYSTEM_PREFIX))

    def test_validation_and_membership(self):
        self.assertEqual(self.set_timer(self.alice_client, 3600).status_code, 400)
        self.assertEqual(self.set_timer(self.alice_client, "abc").status_code, 400)
        self.assertEqual(self.set_timer(self.alice_client, True).status_code, 400)
        outsider = client_for(make_user("+923300000009"))
        self.assertEqual(self.set_timer(outsider, 86400).status_code, 404)

    def test_group_timer_follows_edit_group_info_permission(self):
        carol = make_user("+923300000003")
        group = make_room(self.alice, self.bob, carol, group=True)
        # Default: only admins can edit group info (and the timer).
        self.assertEqual(self.set_timer(client_for(carol), 86400, room=group).status_code, 403)
        self.assertFalse(can_change_disappearing(group, carol))
        self.assertEqual(self.set_timer(self.alice_client, 86400, room=group).status_code, 200)
        group.edit_info_admins_only = False
        group.save()
        self.assertTrue(can_change_disappearing(group, carol))
        self.assertEqual(self.set_timer(client_for(carol), 0, room=group).status_code, 200)

    def test_expired_messages_disappear_from_every_query(self):
        keep = Message.objects.create(room=self.room, sender=self.bob, content="keep findme")
        gone = Message.objects.create(room=self.room, sender=self.bob, content="gone findme", is_pinned=True, pinned_at=timezone.now())
        image = Message.objects.create(room=self.room, sender=self.bob, message_type="IMAGE", content="")
        Attachment.objects.create(message=image, file=SimpleUploadedFile("p.png", PNG, content_type="image/png"))
        StarredMessage.objects.create(message=gone, user=self.alice)
        self.expire(gone, image)
        c = self.alice_client
        ids = [m["id"] for m in c.get(f"/api/chat/rooms/{self.room.id}/messages/").data]
        self.assertEqual(ids, [keep.id])
        self.assertEqual([m["id"] for m in c.get(f"/api/chat/rooms/{self.room.id}/messages/?limit=10").data], [keep.id])
        self.assertEqual([m["id"] for m in c.get(f"/api/chat/rooms/{self.room.id}/messages/search/?q=findme").data], [keep.id])
        self.assertEqual([m["id"] for m in c.get("/api/chat/messages/search/?q=findme").data], [keep.id])
        self.assertEqual(c.get(f"/api/chat/rooms/{self.room.id}/pinned/").data, [])
        self.assertEqual(c.get("/api/chat/messages/starred/").data, [])
        self.assertEqual(c.get(f"/api/chat/rooms/{self.room.id}/media/?kind=media").data["count"], 0)
        self.assertEqual(c.get("/api/chat/media/?kind=media").data["count"], 0)
        row = next(r for r in c.get("/api/chat/rooms/").data if r["id"] == self.room.id)
        self.assertEqual(row["unread_count"], 1)
        self.assertEqual(row["last_message"]["id"], keep.id)
        detail = c.get(f"/api/chat/rooms/{self.room.id}/").data
        self.assertEqual([m["id"] for m in detail["messages"]], [keep.id])
        self.assertEqual(c.post("/api/chat/messages/react/", {"message": gone.id, "emoji": "👍"}, format="json").status_code, 400)
        self.assertEqual(c.get(f"/api/chat/messages/{gone.id}/info/").status_code, 404)

    def test_reply_to_disappeared_message_has_no_quote(self):
        original = Message.objects.create(room=self.room, sender=self.bob, content="soon gone")
        reply = Message.objects.create(room=self.room, sender=self.alice, content="re", reply_to=original)
        self.expire(original)
        listed = self.alice_client.get(f"/api/chat/rooms/{self.room.id}/messages/").data
        self.assertEqual([(m["id"], m["reply_to"]) for m in listed], [(reply.id, None)])

    def test_purge_command_deletes_rows_and_files(self):
        self.room.disappearing_seconds = 86400
        self.room.save()
        message = Message.objects.create(room=self.room, sender=self.bob, message_type="IMAGE", content="")
        attachment = Attachment.objects.create(message=message, file=SimpleUploadedFile("x.png", PNG, content_type="image/png"))
        path = attachment.file.path
        alive = Message.objects.create(room=self.room, sender=self.bob, content="alive")
        self.assertTrue(os.path.exists(path))
        out = StringIO()
        call_command("purge_expired_messages", stdout=out)
        self.assertTrue(Message.all_objects.filter(pk=message.pk).exists())  # not expired yet
        self.expire(message)
        call_command("purge_expired_messages", stdout=out)
        self.assertFalse(Message.all_objects.filter(pk=message.pk).exists())
        self.assertFalse(Attachment.objects.filter(pk=attachment.pk).exists())
        self.assertFalse(os.path.exists(path))
        self.assertTrue(Message.objects.filter(pk=alive.pk).exists())
        self.assertIn("Deleted 1 expired message", out.getvalue())

    def test_purge_keeps_files_still_used_by_a_forwarded_copy(self):
        message = Message.objects.create(room=self.room, sender=self.bob, message_type="IMAGE", content="")
        attachment = Attachment.objects.create(message=message, file=SimpleUploadedFile("y.png", PNG, content_type="image/png"))
        other = make_room(self.alice, make_user("+923300000005"))
        copy = Message.objects.create(room=other, sender=self.alice, message_type="IMAGE", forwarded_from=message)
        Attachment.objects.create(message=copy, file=attachment.file.name)
        self.expire(message)
        call_command("purge_expired_messages", stdout=StringIO())
        self.assertTrue(os.path.exists(attachment.file.path))
        self.assertIsNone(Message.objects.get(pk=copy.pk).forwarded_from)


# ==========================================================================
# View once
# ==========================================================================

@override_settings(MEDIA_ROOT=TEST_MEDIA)
class ViewOnceTests(TestCase):
    def setUp(self):
        self.alice = make_user("+923400000001")
        self.bob = make_user("+923400000002")
        self.room = make_room(self.alice, self.bob)
        self.alice_client = client_for(self.alice)
        self.bob_client = client_for(self.bob)

    def upload(self, view_once=True, message_type="IMAGE", name="secret.png", content_type="image/png"):
        return self.alice_client.post(
            "/api/chat/messages/upload/",
            {
                "room": self.room.id,
                "message_type": message_type,
                "view_once": "true" if view_once else "false",
                "file": SimpleUploadedFile(name, PNG, content_type=content_type),
            },
            format="multipart",
        )

    def test_view_once_is_stored_privately_without_url(self):
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.content)
        data = response.data["data"]
        self.assertTrue(data["is_view_once"])
        self.assertIsNone(data["attachments"][0]["file"])
        self.assertEqual(data["attachments"][0]["mime_type"], "image/png")
        attachment = Attachment.objects.get(message_id=data["id"])
        self.assertTrue(attachment.file.name.startswith("private/view_once/"))
        self.assertNotIn("secret", attachment.file.name)
        self.assertTrue(os.path.exists(attachment.file.path))
        listed = self.bob_client.get(f"/api/chat/rooms/{self.room.id}/messages/").data
        self.assertIsNone(listed[-1]["attachments"][0]["file"])
        rooms = self.bob_client.get("/api/chat/rooms/").data
        self.assertIsNone(rooms[0]["last_message"]["attachments"][0]["file"])

    def test_recipient_opens_exactly_once(self):
        message_id = self.upload().data["data"]["id"]
        url = f"/api/chat/messages/{message_id}/view-once/"
        with mock.patch("apps.chat.feature_views.broadcast_message_patch") as patch:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.bob_client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), PNG)
        self.assertEqual(response["Cache-Control"], "no-store, private")
        self.assertEqual(patch.call_args.args[2], {"view_once_opened_by": [self.bob.id]})
        self.assertIn(self.alice.id, patch.call_args.kwargs["inbox_user_ids"])
        second = self.bob_client.get(url)
        self.assertEqual(second.status_code, 410)
        sender_view = self.alice_client.get(f"/api/chat/rooms/{self.room.id}/messages/").data[-1]
        self.assertEqual(sender_view["view_once_opened_by"], [self.bob.id])
        self.assertTrue(sender_view["is_read"])  # opening reads it

    def test_sender_and_outsiders_cannot_open(self):
        message_id = self.upload().data["data"]["id"]
        url = f"/api/chat/messages/{message_id}/view-once/"
        self.assertEqual(self.alice_client.get(url).status_code, 403)
        self.assertEqual(client_for(make_user("+923400000009")).get(url).status_code, 404)
        self.assertEqual(APIClient().get(url).status_code, 401)
        self.assertFalse(ViewOnceOpen.objects.exists())
        normal = self.upload(view_once=False).data["data"]["id"]
        self.assertEqual(self.bob_client.get(f"/api/chat/messages/{normal}/view-once/").status_code, 404)

    def test_member_who_joined_later_cannot_open(self):
        carol = make_user("+923400000003")
        group = make_room(self.alice, self.bob, group=True)
        message = Message.objects.create(room=group, sender=self.alice, message_type="IMAGE", is_view_once=True)
        Attachment.objects.create(message=message, file=SimpleUploadedFile("a.png", PNG, content_type="image/png"))
        Participant.objects.create(room=group, user=carol)
        Participant.objects.filter(room=group, user=carol).update(joined_at=timezone.now() + timedelta(seconds=5))
        self.assertEqual(client_for(carol).get(f"/api/chat/messages/{message.id}/view-once/").status_code, 404)

    def test_only_photos_and_videos(self):
        response = self.upload(message_type="DOCUMENT", name="a.pdf", content_type="application/pdf")
        self.assertEqual(response.status_code, 400)

    def test_no_forward_star_or_media_listing(self):
        message_id = self.upload().data["data"]["id"]
        other = make_room(self.alice, make_user("+923400000004"))
        response = self.alice_client.post("/api/chat/messages/forward/", {"message": message_id, "room": other.id}, format="json")
        self.assertEqual(response.status_code, 400)
        response = self.bob_client.post("/api/chat/messages/star/", {"message": message_id, "is_starred": True}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.bob_client.get(f"/api/chat/rooms/{self.room.id}/media/?kind=media").data["count"], 0)
        reply = send(self.bob_client, self.room, content="wow", reply_to=message_id).data["data"]
        self.assertTrue(reply["reply_to"]["is_view_once"])
        self.assertIsNone(reply["reply_to"]["attachment"]["file"])

    def test_private_media_is_never_served_by_url(self):
        message_id = self.upload().data["data"]["id"]
        name = Attachment.objects.get(message_id=message_id).file.name
        request = RequestFactory().get("/media/" + name)
        for path in (name, "/" + name, "./" + name, "PRIVATE/" + name.split("/", 1)[1], name.replace("/", "%2F", 1), "private\\" + name.split("/", 1)[1]):
            self.assertTrue(is_private_media_path(path), path)
            with self.assertRaises(Exception):
                serve_media(request, path, document_root=TEST_MEDIA)
        self.assertFalse(is_private_media_path("chat/attachments/a.png"))

    def test_purge_removes_file_once_everyone_opened(self):
        message_id = self.upload().data["data"]["id"]
        attachment = Attachment.objects.get(message_id=message_id)
        path = attachment.file.path
        call_command("purge_expired_messages", stdout=StringIO())
        self.assertTrue(os.path.exists(path))
        self.bob_client.get(f"/api/chat/messages/{message_id}/view-once/")
        call_command("purge_expired_messages", stdout=StringIO())
        self.assertFalse(os.path.exists(path))
        self.assertEqual(self.bob_client.get(f"/api/chat/messages/{message_id}/view-once/").status_code, 410)


    def test_view_once_voice_message(self):
        response = self.alice_client.post(
            "/api/chat/messages/voice/",
            {
                "room": self.room.id,
                "duration": 3,
                "waveform": "[10, 40, 80]",
                "view_once": "true",
                "audio": SimpleUploadedFile("voice.webm", b"\x1aE\xdf\xa3voice-bytes", content_type="audio/webm"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.data["data"] if "data" in response.data else response.data
        self.assertTrue(data["is_view_once"])
        self.assertIsNone(data["voice_note"]["audio"])
        self.assertEqual(data["voice_note"]["duration"], 3)
        note = VoiceNote.objects.get(message_id=data["id"])
        self.assertTrue(note.audio.name.startswith("private/view_once/"))
        url = f"/api/chat/messages/{data['id']}/view-once/"
        self.assertEqual(self.alice_client.get(url).status_code, 403)
        with self.captureOnCommitCallbacks(execute=True):
            opened = self.bob_client.get(url)
        self.assertEqual(opened.status_code, 200)
        self.assertEqual(b"".join(opened.streaming_content), b"\x1aE\xdf\xa3voice-bytes")
        self.assertTrue(opened["Content-Type"].startswith("audio/"))
        self.assertEqual(self.bob_client.get(url).status_code, 410)
        path = note.audio.path
        call_command("purge_expired_messages", stdout=StringIO())
        self.assertFalse(os.path.exists(path))

    def test_normal_voice_message_keeps_public_url(self):
        response = self.alice_client.post(
            "/api/chat/messages/voice/",
            {"room": self.room.id, "duration": 2, "audio": SimpleUploadedFile("v.webm", b"abc", content_type="audio/webm")},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.data["data"] if "data" in response.data else response.data
        self.assertFalse(data["is_view_once"])
        self.assertTrue(data["voice_note"]["audio"])
        self.assertTrue(VoiceNote.objects.get(message_id=data["id"]).audio.name.startswith("chat/voice/"))

# ==========================================================================
# Link previews
# ==========================================================================

PAGE = b"""<!doctype html><html><head>
<meta charset="utf-8"><title>Fallback title</title>
<meta property="og:title" content="Example &amp; Co">
<meta property="og:description" content="  A   page about things. ">
<meta property="og:site_name" content="Example">
<meta property="og:image" content="/img/cover.png">
</head><body><meta property="og:title" content="ignored"></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    routes = {}

    def do_GET(self):  # noqa: N802
        status, headers, body = self.routes.get(self.path, (404, {}, b"nope"))
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class LinkPreviewGuardTests(TestCase):
    def test_public_ip_check(self):
        blocked = [
            "127.0.0.1", "10.1.2.3", "172.16.0.1", "192.168.1.1", "169.254.169.254", "0.0.0.0",
            "100.64.0.1", "224.0.0.1", "255.255.255.255", "240.0.0.1", "192.0.2.1", "198.18.0.1",
            "::1", "::", "fe80::1", "fc00::1", "ff02::1", "::ffff:127.0.0.1", "::ffff:10.0.0.1",
            "64:ff9b::7f00:1", "2002:7f00:1::", "not-an-ip",
        ]
        for address in blocked:
            self.assertFalse(link_preview.is_public_ip(address), address)
        for address in ("93.184.216.34", "8.8.8.8", "2606:4700:4700::1111", "::ffff:8.8.8.8"):
            self.assertTrue(link_preview.is_public_ip(address), address)
        self.assertTrue(link_preview.is_public_ip("127.0.0.1", allow_loopback=True))
        self.assertFalse(link_preview.is_public_ip("10.0.0.1", allow_loopback=True))

    def test_scheme_and_credentials_are_refused(self):
        for url in ("ftp://example.com/", "file:///etc/passwd", "gopher://x/", "http://user:pw@example.com/", "http:///nohost"):
            with self.assertRaises(link_preview.PreviewError, msg=url):
                link_preview.fetch_html(url)

    def fake_dns(self, *addresses):
        return mock.patch(
            "apps.chat.link_preview.socket.getaddrinfo",
            return_value=[(socket.AF_INET6 if ":" in a else socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, 80)) for a in addresses],
        )

    def test_hosts_resolving_to_private_addresses_are_refused(self):
        for addresses in (("127.0.0.1",), ("10.0.0.5",), ("169.254.169.254",), ("93.184.216.34", "192.168.0.10"), ("::1",)):
            with self.fake_dns(*addresses), mock.patch("apps.chat.link_preview.socket.create_connection") as connect:
                with self.assertRaises(link_preview.PreviewError):
                    link_preview.fetch_html("http://evil.example/")
                connect.assert_not_called()

    def test_connection_goes_to_the_vetted_ip(self):
        with self.fake_dns("93.184.216.34"), mock.patch(
            "apps.chat.link_preview.socket.create_connection", side_effect=OSError("offline")
        ) as connect:
            with self.assertRaises(link_preview.PreviewError):
                link_preview.fetch_html("http://example.com:8080/a?b=1")
        self.assertEqual(connect.call_args.args[0], ("93.184.216.34", 8080))

    def test_extract_and_parse(self):
        self.assertEqual(link_preview.extract_first_url("see https://ex.com/a?b=1). ok"), "https://ex.com/a?b=1")
        self.assertIsNone(link_preview.extract_first_url("no link here"))
        preview = link_preview.parse_preview(PAGE.decode(), "https://ex.com/post/1")
        self.assertEqual(preview["title"], "Example & Co")
        self.assertEqual(preview["description"], "A page about things.")
        self.assertEqual(preview["site_name"], "Example")
        self.assertEqual(preview["image"], "https://ex.com/img/cover.png")
        twitter = link_preview.parse_preview(
            '<head><meta name="twitter:title" content="T"><meta name="twitter:image" content="javascript:alert(1)"></head>',
            "https://ex.com/",
        )
        self.assertEqual((twitter["title"], twitter["image"], twitter["site_name"]), ("T", "", "ex.com"))
        self.assertEqual(link_preview.parse_preview("<title> Only title </title>", "http://x.io/")["title"], "Only title")
        self.assertIsNone(link_preview.parse_preview("<p>nothing</p>", "http://x.io/"))


@override_settings(MHTALK_LINK_PREVIEW_ALLOW_LOOPBACK=True)
class LinkPreviewFetchTests(TestCase):
    """Fetches from a local http.server (loopback is allowed only here)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        _Handler.routes = {
            "/page": (200, {"Content-Type": "text/html; charset=utf-8"}, PAGE),
            "/hop1": (302, {"Location": "/hop2"}, b""),
            "/hop2": (301, {"Location": "/page"}, b""),
            "/loop": (302, {"Location": "/loop"}, b""),
            "/to-metadata": (302, {"Location": "http://169.254.169.254/latest/meta-data/"}, b""),
            "/to-ftp": (302, {"Location": "ftp://127.0.0.1/"}, b""),
            "/json": (200, {"Content-Type": "application/json"}, b'{"title": "x"}'),
            "/huge": (200, {"Content-Type": "text/html"}, b"<html><head>" + b" " * (900 * 1024) + b'<meta property="og:title" content="late"></head>'),
            "/latin1": (200, {"Content-Type": "text/html; charset=iso-8859-1"}, "<title>Caf\xe9</title>".encode("latin-1")),
        }
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        super().tearDownClass()

    def setUp(self):
        cache.clear()

    def test_fetch_and_parse(self):
        preview = link_preview.get_link_preview(self.base + "/page")
        self.assertEqual(preview["title"], "Example & Co")
        self.assertEqual(preview["image"], self.base + "/img/cover.png")
        self.assertEqual(preview["url"], self.base + "/page")

    def test_redirects_are_followed_up_to_three(self):
        self.assertEqual(link_preview.get_link_preview(self.base + "/hop1")["title"], "Example & Co")
        self.assertIsNone(link_preview.get_link_preview(self.base + "/loop"))

    def test_redirect_to_private_address_or_other_scheme_is_refused(self):
        with self.assertRaises(link_preview.PreviewError):
            link_preview.fetch_html(self.base + "/to-metadata")
        with self.assertRaises(link_preview.PreviewError):
            link_preview.fetch_html(self.base + "/to-ftp")

    def test_only_html_and_size_cap(self):
        self.assertIsNone(link_preview.get_link_preview(self.base + "/json"))
        _url, html = link_preview.fetch_html(self.base + "/huge")
        self.assertLessEqual(len(html.encode()), link_preview.MAX_BYTES)
        self.assertIsNone(link_preview.parse_preview(html, self.base))
        self.assertEqual(link_preview.get_link_preview(self.base + "/latin1")["title"], "Café")

    def test_timeout(self):
        with mock.patch.object(link_preview, "TIMEOUT_SECONDS", 0.0):
            with self.assertRaises(link_preview.PreviewError):
                link_preview.fetch_html(self.base + "/page")

    def test_loopback_is_refused_without_the_test_setting(self):
        with override_settings(MHTALK_LINK_PREVIEW_ALLOW_LOOPBACK=False):
            self.assertIsNone(link_preview.get_link_preview(self.base + "/page"))

    def test_results_are_cached(self):
        url = self.base + "/page"
        self.assertIsNotNone(link_preview.get_link_preview(url))
        with mock.patch("apps.chat.link_preview.fetch_html") as fetch:
            self.assertEqual(link_preview.get_link_preview(url)["title"], "Example & Co")
            fetch.assert_not_called()

    def test_endpoint_and_message_storage(self):
        alice = make_user("+923500000001")
        bob = make_user("+923500000002")
        room = make_room(alice, bob)
        client = client_for(alice)
        response = client.get("/api/chat/link-preview/", {"url": self.base + "/page"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["preview"]["site_name"], "Example")
        self.assertEqual(client.get("/api/chat/link-preview/", {"url": "javascript:alert(1)"}).status_code, 400)
        self.assertEqual(APIClient().get("/api/chat/link-preview/", {"url": self.base + "/page"}).status_code, 401)

        sent = send(client, room, content=f"look {self.base}/page").data["data"]
        self.assertEqual(sent["link_preview"]["title"], "Example & Co")
        listed = client_for(bob).get(f"/api/chat/rooms/{room.id}/messages/").data
        self.assertEqual(listed[-1]["link_preview"]["title"], "Example & Co")
        removed = send(client, room, content=f"again {self.base}/page", link_preview=False).data["data"]
        self.assertIsNone(removed["link_preview"])


# ==========================================================================
# Location
# ==========================================================================

class LocationTests(TestCase):
    def setUp(self):
        self.alice = make_user("+923600000001")
        self.bob = make_user("+923600000002")
        self.room = make_room(self.alice, self.bob)
        self.client_a = client_for(self.alice)

    def test_current_location_without_address(self):
        response = send(self.client_a, self.room, message_type="LOCATION", content={"latitude": 24.8607, "longitude": 67.0011, "accuracy": 12.4})
        self.assertEqual(response.status_code, 201, response.content)
        content = response.data["data"]["content"]
        self.assertEqual((content["latitude"], content["longitude"], content["address"]), (24.8607, 67.0011, ""))

    def test_legacy_format_with_address_and_name(self):
        response = send(
            self.client_a, self.room, message_type="LOCATION",
            content={"latitude": "51.5", "longitude": "-0.12", "address": "London", "name": "Office"},
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["data"]["content"]["name"], "Office")

    def test_invalid_coordinates(self):
        for content in ({"latitude": 91, "longitude": 0}, {"latitude": 0}, {"latitude": "x", "longitude": 1}, "here", {"latitude": "nan", "longitude": 1}):
            response = send(self.client_a, self.room, message_type="LOCATION", content=content)
            self.assertEqual(response.status_code, 400, content)

    def test_live_location_update_and_stop(self):
        response = send(self.client_a, self.room, message_type="LOCATION", content={"latitude": 24.86, "longitude": 67.0, "live_seconds": 900})
        self.assertEqual(response.status_code, 201, response.content)
        data = response.data["data"]
        self.assertTrue(data["content"]["live"])
        url = f"/api/chat/messages/{data['id']}/live-location/"
        moved = self.client_a.post(url, {"latitude": 24.87, "longitude": 67.01, "accuracy": 5}, format="json")
        self.assertEqual(moved.status_code, 200, moved.content)
        self.assertEqual(moved.data["content"]["latitude"], 24.87)
        other = client_for(self.bob).post(url, {"latitude": 1, "longitude": 1}, format="json")
        self.assertEqual(other.status_code, 403)
        stopped = self.client_a.post(url, {"stop": True}, format="json")
        self.assertTrue(stopped.data["content"]["stopped"])
        after = self.client_a.post(url, {"latitude": 24.9, "longitude": 67.0}, format="json")
        self.assertEqual(after.status_code, 400)

    def test_live_location_bad_duration(self):
        response = send(self.client_a, self.room, message_type="LOCATION", content={"latitude": 1, "longitude": 1, "live_seconds": 5})
        self.assertEqual(response.status_code, 400)


def tearDownModule():
    shutil.rmtree(TEST_MEDIA, ignore_errors=True)
