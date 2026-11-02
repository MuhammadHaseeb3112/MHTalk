"""
N+1 regression tests.

Every list endpoint must run the same number of SQL queries whether the user
has 2 chats or 6 chats (and 2 or 6 messages per chat, members, statuses...).
If a serializer starts touching an un-prefetched relation, the count grows
with the data and these tests fail.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.accounts.models import Contact, User
from apps.calls.models import Call, CallParticipant
from apps.chat.choices import RoomType
from apps.chat.models import (
    Attachment,
    ChatRoom,
    Message,
    MessageReceipt,
    Participant,
    Reaction,
    StarredMessage,
)
from apps.chat.utils import persist_receipts_bulk
from apps.status.models import Status


def make_user(phone, name):
    user = User.objects.create_user(phone_number=phone, password="StrongPass123!")
    user.profile.display_name = name
    user.profile.save()
    return user


def seed(size, prefix):
    me = make_user(f"+92{prefix}00000000", "Me")
    others = []
    private_room = None
    for index in range(size):
        other = make_user(f"+92{prefix}{index:07d}1", f"U{index}")
        others.append(other)
        Contact.objects.create(owner=me, contact_user=other, name=f"U{index}")
        Contact.objects.create(owner=other, contact_user=me, name="Me")
        room = ChatRoom.objects.create(created_by=me, room_type=RoomType.PRIVATE)
        Participant.objects.create(room=room, user=me)
        Participant.objects.create(room=room, user=other)
        private_room = private_room or room
        previous = None
        for number in range(size):
            message = Message.objects.create(
                room=room, sender=other if number % 2 else me, content=f"m{number}", reply_to=previous
            )
            Reaction.objects.create(message=message, user=other, emoji="👍")
            StarredMessage.objects.create(message=message, user=me)
            Attachment.objects.create(
                message=message,
                file=SimpleUploadedFile("a.png", b"x", content_type="image/png"),
                file_name="a.png",
                file_size=1,
                mime_type="image/png",
            )
            previous = message
        Status.objects.create(user=other, status_type="text", content="hi")
        call = Call.objects.create(room=room, caller=other, call_type="AUDIO", status="MISSED")
        CallParticipant.objects.create(call=call, user=me)
        CallParticipant.objects.create(call=call, user=other)
    group = ChatRoom.objects.create(created_by=me, room_type=RoomType.GROUP, name="G")
    Participant.objects.create(room=group, user=me)
    for other in others:
        Participant.objects.create(room=group, user=other)
        Message.objects.create(room=group, sender=other, content="g")
    return me, private_room, group


@override_settings(MEDIA_ROOT="/tmp/whatsup-test-media")
class QueryCountTests(TestCase):
    ENDPOINTS = (
        "/api/accounts/contacts/",
        "/api/chat/rooms/",
        "/api/chat/rooms/{private}/",
        "/api/chat/rooms/{group}/",
        "/api/chat/rooms/{group}/info/",
        "/api/chat/rooms/{private}/messages/",
        "/api/chat/rooms/{private}/messages/?limit=50",
        "/api/chat/rooms/{group}/messages/",
        "/api/chat/rooms/{private}/media/",
        "/api/chat/rooms/{private}/pinned/",
        "/api/chat/media/",
        "/api/chat/messages/starred/",
        "/api/chat/rooms/{private}/messages/search/?q=m",
        "/api/chat/messages/search/?q=m1",
        "/api/status/",
        "/api/status/me/",
        "/api/calls/history/",
        "/api/calls/missed/",
    )

    def measure(self, size, prefix):
        me, private_room, group = seed(size, prefix)
        client = APIClient()
        client.force_authenticate(me)
        counts = {}
        for template in self.ENDPOINTS:
            url = template.format(private=private_room.id, group=group.id)
            with CaptureQueriesContext(connection) as context:
                response = client.get(url)
            self.assertEqual(response.status_code, 200, url)
            counts[template] = len(context.captured_queries)
        return counts

    def test_list_endpoints_do_not_grow_with_data(self):
        small = self.measure(2, "301")
        large = self.measure(6, "302")
        grown = {url: (small[url], large[url]) for url in small if large[url] > small[url]}
        self.assertEqual(grown, {}, f"N+1 detected (queries at 2 vs 6 items): {grown}")


class BulkReceiptTests(TestCase):
    def setUp(self):
        self.sender = make_user("+923030000001", "S")
        self.members = [make_user(f"+92303000001{i}", f"M{i}") for i in range(5)]
        self.group = ChatRoom.objects.create(created_by=self.sender, room_type=RoomType.GROUP, name="G")
        Participant.objects.create(room=self.group, user=self.sender)
        for member in self.members:
            Participant.objects.create(room=self.group, user=member)
        self.messages = [Message.objects.create(room=self.group, sender=self.sender, content=str(i)) for i in range(20)]

    def test_constant_queries_and_group_ticks(self):
        reader = self.members[0]
        with CaptureQueriesContext(connection) as context:
            results = persist_receipts_bulk([m.id for m in self.messages], reader.id, "read")
        self.assertEqual(len(results), 20)
        self.assertLessEqual(len(context.captured_queries), 12)
        # One member read: group ticks must not turn blue yet.
        self.assertFalse(Message.objects.filter(pk=self.messages[0].pk, is_read=True).exists())
        self.assertEqual(MessageReceipt.objects.filter(recipient=reader, read_at__isnull=False).count(), 20)
        for member in self.members[1:]:
            persist_receipts_bulk([m.id for m in self.messages], member.id, "read")
        self.assertEqual(Message.objects.filter(room=self.group, is_read=True, is_delivered=True).count(), 20)

    def test_sender_and_outsiders_are_rejected(self):
        outsider = make_user("+923030000099", "O")
        self.assertEqual(persist_receipts_bulk([self.messages[0].id], self.sender.id, "read"), [])
        self.assertEqual(persist_receipts_bulk([self.messages[0].id], outsider.id, "read"), [])
