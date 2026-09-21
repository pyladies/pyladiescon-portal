"""Daily checklist digests (design §9.4).

One email per presenter with their open items due within 7, 3 or 1 days,
computed against today in the presenter's own timezone; one email per
assignee (or the organizers list) with open organizer items. Every
(item, threshold) pair is logged so the same reminder never goes out
twice, however often the job runs.
"""

import logging
from collections import defaultdict

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from common.send_emails import send_email

from .constants import OPEN_ITEM_STATUSES, ItemOwner
from .emails import absolute_url, organizer_recipients
from .models import ChecklistItem, ReminderLog, SpeakerSettings

THRESHOLDS = (7, 3, 1)

logger = logging.getLogger(__name__)


def _pending_thresholds(item, today, sent):
    """Thresholds this item has crossed that have not been sent yet.

    Items without a due date never reach here (the job filters them out).
    ``days_left`` below zero (overdue) crosses every threshold, so an
    overdue item is reminded once and then left to the board.
    """
    days_left = (item.due_date - today).days
    return [
        threshold
        for threshold in THRESHOLDS
        if days_left <= threshold and threshold not in sent.get(item.pk, set())
    ]


def _sent_map(conference):
    sent = defaultdict(set)
    for item_id, threshold in ReminderLog.objects.filter(
        conference=conference
    ).values_list("item_id", "threshold_days"):
        sent[item_id].add(threshold)
    return sent


def _dashboard_url():
    return absolute_url(reverse("speakers:my_dashboard"))


def _queue_url():
    return absolute_url(reverse("speakers:checklist_queue"))


def send_checklist_digests(conference, now=None):
    """Send today's digests for one edition. Returns the number of emails."""
    now = now or timezone.now()
    settings_row = SpeakerSettings.objects.filter(conference=conference).first()
    sent = _sent_map(conference)
    items = list(
        ChecklistItem.objects.filter(
            conference=conference,
            status__in=list(OPEN_ITEM_STATUSES),
            due_date__isnull=False,
        ).select_related("presenter", "session", "assignee")
    )
    emails = DigestCount(0)
    emails += _speaker_digests(conference, items, now, sent)
    emails += _organizer_digests(conference, items, now, sent, settings_row)
    return emails


def _speaker_digests(conference, items, now, sent):
    by_presenter = defaultdict(list)
    for item in items:
        if item.owner == ItemOwner.SPEAKER and item.presenter_id is not None:
            by_presenter[item.presenter].append(item)
    emails = DigestCount(0)
    for presenter, presenter_items in by_presenter.items():
        today = now.astimezone(presenter.tzinfo).date()
        due = [
            (item, _pending_thresholds(item, today, sent)) for item in presenter_items
        ]
        due = [(item, thresholds) for item, thresholds in due if thresholds]
        if not due:
            continue
        if not _try_deliver(
            conference,
            [presenter.email],
            "emails/speakers/checklist_digest.md",
            {
                "name": presenter.display_name,
                "items": [item for item, _ in due],
                "today": today,
                "timezone": presenter.timezone,
                "link": _dashboard_url(),
                "for_organizer": False,
            },
            due,
            subject=f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} {conference.name}: "
            f"{len(due)} thing(s) coming up",
        ):
            emails.failed += 1
            continue
        emails = emails + 1
    return emails


def _organizer_digests(conference, items, now, sent, settings_row):
    tzinfo = settings_row.tzinfo if settings_row else timezone.get_default_timezone()
    today = now.astimezone(tzinfo).date()
    by_recipient = defaultdict(list)
    fallback = None
    for item in items:
        if item.owner != ItemOwner.ORGANIZER:
            continue
        thresholds = _pending_thresholds(item, today, sent)
        if not thresholds:
            continue
        if item.assignee is not None and item.assignee.email:
            by_recipient[(item.assignee.email,)].append((item, thresholds))
        else:
            if fallback is None:
                fallback = (
                    [settings_row.organizers_email]
                    if settings_row and settings_row.organizers_email
                    else organizer_recipients()
                )
            if fallback:
                by_recipient[tuple(fallback)].append((item, thresholds))
    emails = DigestCount(0)
    for recipients, due in by_recipient.items():
        if not _try_deliver(
            conference,
            list(recipients),
            "emails/speakers/checklist_digest.md",
            {
                "name": "team",
                "items": [item for item, _ in due],
                "today": today,
                "timezone": str(tzinfo),
                "link": _queue_url(),
                "for_organizer": True,
            },
            due,
            subject=f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} {conference.name}: "
            f"{len(due)} organizer item(s) coming up",
        ):
            emails.failed += 1
            continue
        emails = emails + 1
    return emails


class DigestCount(int):
    """How many digests went out; ``failed`` counts the ones that did not.
    An int, so callers comparing against a number keep working."""

    failed = 0

    def __add__(self, other):
        result = DigestCount(int(self) + int(other))
        result.failed = self.failed + getattr(other, "failed", 0)
        return result


def _try_deliver(conference, recipients, template, context, due, subject):
    """Deliver one digest; a failure is logged and reported, never raised,
    so one bad mailbox does not stop everyone after it in the loop."""
    try:
        _deliver(conference, recipients, template, context, due, subject)
    except Exception:  # noqa: BLE001 - anything the mail backend raises
        logger.exception("Digest to %s failed", recipients)
        return False
    return True


def _deliver(conference, recipients, template, context, due, subject):
    """Send one digest and log every (item, threshold) it covered, atomically
    so a crash mid-way never leaves a reminder half-recorded."""
    with transaction.atomic():
        for item, thresholds in due:
            for threshold in thresholds:
                ReminderLog.objects.create(
                    item=item, threshold_days=threshold, recipient=recipients[0]
                )
        send_email(subject, recipients, markdown_template=template, context=context)
