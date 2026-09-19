from django.core.management.base import BaseCommand

from speakers.seeds import clone_checklists

from .seed_checklists import resolve_conference


class Command(BaseCommand):
    help = "Copy checklist templates from one edition into another."

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="source", required=True, help="Year or slug")
        parser.add_argument("--to", dest="target", required=True, help="Year or slug")

    def handle(self, *args, **options):
        source = resolve_conference(options["source"])
        target = resolve_conference(options["target"])
        templates, items = clone_checklists(target, source)
        self.stdout.write(
            f"Cloned {templates} template(s) and {items} item(s) "
            f"from {source} into {target}."
        )
