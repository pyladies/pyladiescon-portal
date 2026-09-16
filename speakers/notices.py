"""Daily "your checklist changed" emails.

Whenever a template line is added or changed, or an organizer adds a
one-off item, the affected instances are flagged. Once a day, everyone with
flagged items gets one email listing what is new and what changed, and the
flags are cleared, so nothing is sent when nothing happened.
"""

from collections import defaultdict

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from common.send_emails import send_email

from .constants import ItemOwner, NoticeKind
from .emails import absolute_url
from .models import ChecklistItem
from .reminders import _team_emails


def _recipients(item):
    if item.owner == ItemOwner.SPEAKER:
        return (item.presenter.email,) if item.presenter_id else ()
    if item.assignee_id and item.assignee.email:
        return (item.assignee.email,)
    if item.team_id:
        return tuple(_team_emails(item.team))
    return ()


def send_checklist_change_notices(conference, now=None):
    """Send today's update emails for one edition. Returns the email count."""
    now = now or timezone.now()
    items = list(
        ChecklistItem.objects.filter(conference=conference)
        .exclude(pending_notice="")
        .select_related("presenter", "session", "assignee", "team")
        .order_by("presenter__display_name", "session__title", "order", "id")
    )
    by_recipient = defaultdict(list)
    orphaned = []
    for item in items:
        recipients = _recipients(item)
        if recipients:
            by_recipient[recipients].append(item)
        else:
            orphaned.append(item)
    emails = 0
    for recipients, group in by_recipient.items():
        speaker_side = group[0].owner == ItemOwner.SPEAKER
        with transaction.atomic():
            send_email(
                f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} {conference.name}: your "
                "checklist has changed",
                list(recipients),
                markdown_template="emails/speakers/checklist_changes.md",
                context={
                    "new_items": [
                        i for i in group if i.pending_notice == NoticeKind.NEW
                    ],
                    "changed_items": [
                        i for i in group if i.pending_notice == NoticeKind.CHANGED
                    ],
                    "for_organizer": not speaker_side,
                    "link": absolute_url(
                        reverse(
                            "speakers:my_dashboard"
                            if speaker_side
                            else "speakers:checklist_queue"
                        )
                    ),
                },
            )
            _clear(group)
        emails += 1
    _clear(orphaned)
    return emails


def _clear(items):
    ChecklistItem.objects.filter(pk__in=[i.pk for i in items]).update(
        pending_notice="", pending_since=None
    )
