from django.core.management.base import BaseCommand, CommandError

from portal.models import Conference
from speakers.program_types import seed_program_types


class Command(BaseCommand):
    help = "Seed the default session types and presenter roles for an edition."

    def add_arguments(self, parser):
        parser.add_argument(
            "--conference", help="Year or slug; defaults to the active one."
        )

    def handle(self, *args, **options):
        value = options.get("conference")
        if value:
            conference = Conference.objects.filter(slug=value).first()
            if conference is None and value.isdigit():
                conference = Conference.objects.filter(year=int(value)).first()
        else:
            conference = Conference.get_active()
        if conference is None:
            raise CommandError("No conference found; pass --conference.")
        types, roles = seed_program_types(conference)
        self.stdout.write(
            self.style.SUCCESS(
                f"{conference}: {types} session types and {roles} roles created."
            )
        )
