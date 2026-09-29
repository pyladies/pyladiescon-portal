"""Abort multipart uploads nobody finished, by hand.

Thin wrapper over ``speakers.media.expire_abandoned_uploads`` so a manual run
behaves exactly like the scheduled task.
"""

from django.core.management.base import BaseCommand

from speakers.media import expire_abandoned_uploads


class Command(BaseCommand):
    help = "Abort multipart uploads past their expiry and mark them EXPIRED."

    def handle(self, *args, **options):
        count = expire_abandoned_uploads()
        self.stdout.write(self.style.SUCCESS(f"Expired {count} abandoned upload(s)"))
