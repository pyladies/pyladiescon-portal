from django.core.management.base import BaseCommand
from django.db import transaction

from speakers.constants import ChecklistScope, ItemStatus
from speakers.models import ChecklistItem, ChecklistTemplate, ChecklistTemplateItem

from .seed_checklists import resolve_conference


class Command(BaseCommand):
    help = (
        "One-off after the general checklist arrived: move each presenter's "
        "copies of general lines (same title as a line of the every-presenter "
        "template) and once-per-presenter lines onto one session-less item, "
        "drop the other open copies, keep done ones, and delete the now "
        "redundant per-session template lines."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--conference", help="Year or slug; defaults to the active one."
        )

    @transaction.atomic
    def handle(self, *args, **options):
        conference = resolve_conference(options.get("conference"))
        general = ChecklistTemplate.for_general(conference)
        moved = dropped = lines = 0
        if general is not None:
            general_by_title = {line.title: line for line in general.items.all()}
            stale_lines = ChecklistTemplateItem.objects.filter(
                template__conference=conference,
                template__scope=ChecklistScope.PRESENTER,
                title__in=general_by_title,
            )
            for line in stale_lines:
                m, d = self._collapse(line, general_by_title[line.title])
                moved += m
                dropped += d
                line.delete()
                lines += 1
        once_lines = ChecklistTemplateItem.objects.filter(
            template__conference=conference, once_per_presenter=True
        )
        for line in once_lines:
            m, d = self._collapse(line, line)
            moved += m
            dropped += d
        self.stdout.write(
            f"{conference}: moved {moved} item(s) to the general list, dropped "
            f"{dropped} duplicate(s), deleted {lines} redundant template line(s)."
        )

    @staticmethod
    def _collapse(line, target_line):
        """Per presenter, keep one instance (a done one if any) as the
        session-less item of ``target_line``; drop other open copies."""
        moved = dropped = 0
        # A set, not .distinct(): the model's default ordering would make
        # DISTINCT include the order columns and repeat presenters.
        presenter_ids = set(
            ChecklistItem.objects.filter(template_item=line).values_list(
                "presenter_id", flat=True
            )
        )
        for presenter_id in presenter_ids:
            copies = list(
                ChecklistItem.objects.filter(
                    template_item=line, presenter_id=presenter_id
                )
            )
            # Keep a done copy if there is one, else the oldest.
            copies.sort(key=lambda i: (i.status != ItemStatus.DONE, i.pk))
            keep = copies[0]
            existing = (
                ChecklistItem.objects.filter(
                    template_item=target_line,
                    presenter_id=presenter_id,
                    session__isnull=True,
                )
                .exclude(pk=keep.pk)
                .first()
            )
            if existing is not None:
                keep = existing
            else:
                keep.template_item = target_line
                keep.session = None
                keep.save()
                moved += 1
            for extra in copies:
                if extra.pk == keep.pk:
                    continue
                if extra.status == ItemStatus.TODO:
                    extra.delete()
                    dropped += 1
        return moved, dropped
