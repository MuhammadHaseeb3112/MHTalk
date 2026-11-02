from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Contact, User
from apps.status.choices import StatusType, StatusVisibility
from apps.status.models import Status, StatusPrivacy, StatusView


class StatusFeatureAPITests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            phone_number="+923000000201", password="StrongPass123!"
        )
        self.viewer = User.objects.create_user(
            phone_number="+923000000202", password="StrongPass123!"
        )
        self.other = User.objects.create_user(
            phone_number="+923000000203", password="StrongPass123!"
        )
        self.owner_client = APIClient()
        self.owner_client.force_authenticate(self.owner)
        self.viewer_client = APIClient()
        self.viewer_client.force_authenticate(self.viewer)
        self.other_client = APIClient()
        self.other_client.force_authenticate(self.other)

    def add_mutual_contact(self, first, second):
        Contact.objects.get_or_create(owner=first, contact_user=second)
        Contact.objects.get_or_create(owner=second, contact_user=first)

    def test_everyone_status_can_be_viewed_and_count_comes_from_view_records(self):
        upload = self.owner_client.post(
            "/api/status/upload/",
            {"status_type": "TEXT", "content": "Hello MHTalk", "visibility": "EVERYONE"},
            format="multipart",
        )
        self.assertEqual(upload.status_code, 201)
        status_id = upload.data["data"]["id"]

        feed = self.viewer_client.get("/api/status/")
        self.assertEqual(feed.status_code, 200)
        self.assertTrue(any(
            int(group["user"]["id"]) == self.owner.id
            for group in feed.data
        ))
        feed_group = next(group for group in feed.data if int(group["user"]["id"]) == self.owner.id)
        self.assertIsNone(feed_group["statuses"][0]["views_count"])

        first_view = self.viewer_client.post(f"/api/status/{status_id}/view/")
        second_view = self.viewer_client.post(f"/api/status/{status_id}/view/")
        self.assertEqual(first_view.status_code, 200)
        self.assertEqual(second_view.status_code, 200)
        self.assertEqual(StatusView.objects.filter(status_id=status_id, viewer=self.viewer).count(), 1)

        mine = self.owner_client.get("/api/status/me/")
        self.assertEqual(mine.status_code, 200)
        self.assertEqual(mine.data[0]["views_count"], 1)

    def test_custom_audience_is_enforced_on_server(self):
        self.add_mutual_contact(self.owner, self.viewer)
        status_obj = Status.objects.create(
            user=self.owner,
            status_type=StatusType.TEXT,
            content="Selected audience only",
            visibility=StatusVisibility.ONLY_SHARE_WITH,
        )
        StatusPrivacy.objects.create(status=status_obj, user=self.viewer)

        viewer_feed = self.viewer_client.get("/api/status/")
        other_feed = self.other_client.get("/api/status/")
        self.assertTrue(any(
            int(group["user"]["id"]) == self.owner.id
            for group in viewer_feed.data
        ))
        self.assertFalse(any(
            int(group["user"]["id"]) == self.owner.id
            for group in other_feed.data
        ))
        denied_view = self.other_client.post(f"/api/status/{status_obj.id}/view/")
        self.assertEqual(denied_view.status_code, 403)

    def test_status_privacy_contacts_include_existing_private_chat_contacts(self):
        from apps.chat.choices import RoomType
        from apps.chat.models import ChatRoom, Participant

        room = ChatRoom.objects.create(created_by=self.owner, room_type=RoomType.PRIVATE)
        Participant.objects.create(room=room, user=self.owner)
        Participant.objects.create(room=room, user=self.viewer)

        contacts_response = self.owner_client.get("/api/status/contacts/")
        self.assertEqual(contacts_response.status_code, 200)
        contact_ids = {int(entry["user"]["id"]) for entry in contacts_response.data}
        self.assertIn(self.viewer.id, contact_ids)

        upload = self.owner_client.post(
            "/api/status/upload/",
            {
                "status_type": "TEXT",
                "content": "Private chat contact audience",
                "visibility": "ONLY_SHARE_WITH",
                "users": [str(self.viewer.id)],
            },
            format="multipart",
        )
        self.assertEqual(upload.status_code, 201, upload.data)
        status_id = upload.data["data"]["id"]
        viewer_feed = self.viewer_client.get("/api/status/")
        self.assertEqual(viewer_feed.status_code, 200)
        self.assertTrue(any(int(group["user"]["id"]) == self.owner.id for group in viewer_feed.data))
        self.assertEqual(self.other_client.post(f"/api/status/{status_id}/view/").status_code, 403)

    def test_expired_status_is_not_in_any_active_feed(self):
        expired = Status.objects.create(
            user=self.owner,
            status_type=StatusType.TEXT,
            content="This should expire",
            visibility=StatusVisibility.EVERYONE,
        )
        Status.objects.filter(pk=expired.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        owner_feed = self.owner_client.get("/api/status/me/")
        viewer_feed = self.viewer_client.get("/api/status/")
        self.assertEqual(owner_feed.status_code, 200)
        self.assertEqual(owner_feed.data, [])
        self.assertEqual(viewer_feed.status_code, 200)
        self.assertFalse(any(
            int(group["user"]["id"]) == self.owner.id
            for group in viewer_feed.data
        ))

