from django.core.management.base import BaseCommand, CommandError

from portal.models import Conference
from speakers.seeds import seed_checklists


class Command(BaseCommand):
    help = "Load the default checklist templates into an edition (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--conference",
            help="Year or slug of the edition; defaults to the active one.",
        )

    def handle(self, *args, **options):
        conference = resolve_conference(options.get("conference"))
        result = seed_checklists(conference)
        self.stdout.write(
            f"Seeded {result.templates} template(s) and {result.items} item(s) "
            f"into {conference}."
        )
        if result.described:
            self.stdout.write(f"Filled in {result.described} missing description(s).")
        for name, why in result.skipped:
            self.stdout.write(f"Skipped {name}: {why}.")


def resolve_conference(value):
    """Find an edition by year or slug, or the active one when ``value`` is empty."""
    if not value:
        conference = Conference.get_active()
        if conference is None:
            raise CommandError("No active conference; pass --conference.")
        return conference
    conference = Conference.objects.filter(slug=value).first()
    if conference is None and value.isdigit():
        conference = Conference.objects.filter(year=int(value)).first()
    if conference is None:
        raise CommandError(f"No conference matches {value!r}.")
    return conference
