"""Queue the duration probe again, by hand.

The probe tries three times on its own (``speakers.tasks.probe_asset_task``);
a failure that stood after that, or a video that landed while no media
worker ran, is measured by running this once the worker is back.
"""

from django.core.management.base import BaseCommand

from speakers.constants import VIDEO_KINDS, MediaStatus
from speakers.models import MediaAsset
from speakers.tasks import probe_asset_task


class Command(BaseCommand):
    help = (
        "Queue the duration probe for READY videos that have no duration yet; "
        "--all for every READY video, --asset for particular ones."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--all", action="store_true", help="Every READY video, measured or not."
        )
        parser.add_argument(
            "--asset",
            type=int,
            action="append",
            default=[],
            metavar="ID",
            help="Only this asset (repeatable).",
        )

    def handle(self, *args, **options):
        assets = MediaAsset.objects.filter(
            kind__in=VIDEO_KINDS, status=MediaStatus.READY
        )
        if options["asset"]:
            assets = assets.filter(pk__in=options["asset"])
        elif not options["all"]:
            assets = assets.filter(duration_seconds__isnull=True)
        count = 0
        for asset_id in assets.values_list("pk", flat=True):
            probe_asset_task.delay(asset_id)
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Queued {count} probe(s)"))
