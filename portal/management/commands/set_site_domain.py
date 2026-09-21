from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Set the domain (and optionally the name) of the current Site. Emailed "
        "links are built from it; a fresh database has the placeholder example.com."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "domain", help="Host, with port if needed, e.g. localhost:8000"
        )
        parser.add_argument("--name", help="Display name; defaults to the domain")

    def handle(self, *args, **options):
        site = Site.objects.get_current()
        site.domain = options["domain"]
        site.name = options["name"] or options["domain"]
        site.save()
        self.stdout.write(f"Site {site.pk} is now {site.domain} ({site.name}).")
