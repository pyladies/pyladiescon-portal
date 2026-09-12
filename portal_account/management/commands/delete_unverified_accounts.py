"""Delete accounts that never verified their email address.

Thin wrapper over ``portal_account.cleanup`` so a manual run behaves exactly
like the scheduled task.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from portal_account.cleanup import delete_unverified_accounts


class Command(BaseCommand):
    help = (
        "Delete accounts that never verified their email address within "
        "UNVERIFIED_ACCOUNT_RETENTION_DAYS."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many accounts would be deleted without deleting them.",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Override UNVERIFIED_ACCOUNT_RETENTION_DAYS for this run.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        if days is None:
            days = settings.UNVERIFIED_ACCOUNT_RETENTION_DAYS
        count = delete_unverified_accounts(days, dry_run=options["dry_run"])
        if options["dry_run"]:
            self.stdout.write(
                f"Would delete {count} unverified account(s) older than {days} day(s)"
            )
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {count} unverified account(s) older than {days} day(s)"
            )
        )
