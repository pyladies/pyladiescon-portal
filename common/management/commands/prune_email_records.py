"""Delete email records past retention.

Thin wrapper over ``common.models.prune_sent_emails`` so a manual run behaves
exactly like the scheduled task.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from common.models import prune_sent_emails


class Command(BaseCommand):
    help = (
        "Delete email records older than the edition plus "
        "EMAIL_RECORD_RETENTION_DAYS."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many records would be deleted without deleting them.",
        )

    def handle(self, *args, **options):
        days = settings.EMAIL_RECORD_RETENTION_DAYS
        count = prune_sent_emails(dry_run=options["dry_run"])
        if options["dry_run"]:
            self.stdout.write(
                f"Would delete {count} email record(s) past the edition plus {days} day(s)"
            )
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {count} email record(s) past the edition plus {days} day(s)"
            )
        )
