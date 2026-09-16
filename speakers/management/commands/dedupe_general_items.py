from django.core.management.base import BaseCommand
from django.db import transaction

from speakers.checklists import collapse_general_duplicates

from .seed_checklists import resolve_conference


class Command(BaseCommand):
    help = (
        "One-off after lines moved to the every-presenter template: fold each "
        "presenter's per-session copies into one general item, drop the other "
        "open copies, keep done ones, and delete the redundant template lines. "
        "Loading the default checklists does the same."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--conference", help="Year or slug; defaults to the active one."
        )

    @transaction.atomic
    def handle(self, *args, **options):
        conference = resolve_conference(options.get("conference"))
        moved, dropped, lines = collapse_general_duplicates(conference)
        self.stdout.write(
            f"{conference}: moved {moved} item(s) to the general list, dropped "
            f"{dropped} duplicate(s), deleted {lines} redundant template line(s)."
        )
