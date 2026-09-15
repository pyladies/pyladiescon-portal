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
        templates, items = seed_checklists(conference)
        self.stdout.write(
            f"Seeded {templates} template(s) and {items} item(s) into {conference}."
        )


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
