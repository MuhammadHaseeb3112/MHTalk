from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import Profile


class Command(BaseCommand):
    help = (
        "Mark every user offline and reset WebSocket connection counters. "
        "Run after an unclean server shutdown so nobody appears online forever."
    )

    def handle(self, *args, **options):
        updated = Profile.objects.filter(is_online=True).update(
            is_online=False,
            last_seen=timezone.now(),
        )
        Profile.objects.exclude(active_connections=0).update(active_connections=0)
        self.stdout.write(self.style.SUCCESS(f"Reset presence for {updated} online profile(s)."))
