"""
Physically delete disappeared messages and spent view once media.

Expired messages are already invisible to every query (``Message.objects``
filters them out); this command removes the rows and their stored files.
It also deletes the file of a view once photo/video/voice message once every recipient has
opened it. Production runs it every 5 minutes (``scheduler`` service in
docker-compose.prod.yml).
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, F, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.chat.models import Attachment, Message, Participant, ViewOnceOpen, VoiceNote
from apps.chat.utils import _delete_unreferenced_files

BATCH = 500


def purge_expired_messages(now=None, batch=BATCH):
    """Delete expired messages (and their files). Returns the number deleted."""
    now = now or timezone.now()
    total = 0
    while True:
        ids = list(
            Message.all_objects.filter(expires_at__isnull=False, expires_at__lte=now)
            .order_by("id")
            .values_list("id", flat=True)[:batch]
        )
        if not ids:
            break
        paths = list(Attachment.objects.filter(message_id__in=ids).values_list("file", flat=True)) + list(
            VoiceNote.objects.filter(message_id__in=ids).values_list("audio", flat=True)
        )
        with transaction.atomic():
            # Cascades to attachments, voice notes, receipts, reactions, stars,
            # polls, mentions...; replies/forwards keep a NULL reference.
            Message.all_objects.filter(pk__in=ids).delete()
        # A forwarded copy elsewhere may still use the same file.
        _delete_unreferenced_files(paths)
        total += len(ids)
        if len(ids) < batch:
            break
    return total


def purge_opened_view_once():
    """Delete view once files that every recipient (members at send time) has opened."""
    recipients = (
        Participant.objects.filter(room_id=OuterRef("room_id"), joined_at__lte=OuterRef("created_at"))
        .exclude(user_id=OuterRef("sender_id"))
        .order_by()
        .values("room_id")
        .annotate(total=Count("id"))
        .values("total")[:1]
    )
    opens = (
        ViewOnceOpen.objects.filter(message_id=OuterRef("pk"))
        .order_by()
        .values("message_id")
        .annotate(total=Count("id"))
        .values("total")[:1]
    )
    spent = (
        Message.all_objects.filter(is_view_once=True)
        .filter(
            (Q(attachments__isnull=False) & ~Q(attachments__file=""))
            | (Q(voice_note__isnull=False) & ~Q(voice_note__audio=""))
        )
        .annotate(_recipients=Coalesce(Subquery(recipients), 0), _opens=Coalesce(Subquery(opens), 0))
        .filter(Q(_opens__gte=F("_recipients")), _recipients__gt=0)
        .values_list("id", flat=True)
        .distinct()
    )
    ids = list(spent[:BATCH])
    if not ids:
        return 0
    paths = list(Attachment.objects.filter(message_id__in=ids).values_list("file", flat=True))
    Attachment.objects.filter(message_id__in=ids).update(file="")
    paths += list(VoiceNote.objects.filter(message_id__in=ids).values_list("audio", flat=True))
    VoiceNote.objects.filter(message_id__in=ids).update(audio="")
    _delete_unreferenced_files(paths)
    return len(ids)


class Command(BaseCommand):
    help = "Delete disappeared (expired) messages with their files, and fully opened view once media."

    def handle(self, *args, **options):
        deleted = purge_expired_messages()
        spent = purge_opened_view_once()
        self.stdout.write(f"Deleted {deleted} expired message(s); removed {spent} opened view once file(s).")
