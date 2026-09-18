"""Task numbers for dashboards and the public stats page.

Everything here reads ``ChecklistItem`` rows for one edition. The per-edition
totals are cached like the other public stats (``STATS_CACHE_TIMEOUT``); the
per-person numbers are cheap and always live.
"""

from datetime import timedelta

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from portal.constants import STATS_CACHE_TIMEOUT

from .constants import OPEN_ITEM_STATUSES, ItemOwner, ItemStatus
from .models import ChecklistItem, speaker_module_enabled
from .permissions import owned_by

CACHE_KEY_TASKS = "speaker_tasks"

# Keys the public stats page and JSON expose: totals only, no split by who
# does the work.
CACHE_KEY_TASKS_TOTAL = "tasks_total_count"
CACHE_KEY_TASKS_DONE = "tasks_done_count"
CACHE_KEY_TASKS_DONE_PERCENT = "tasks_done_percent"


def _percent(done, total):
    return round(100 * done / total) if total else 0


def edition_task_stats(conference, today=None):
    """Live numbers for one edition, for the organizer dashboard.

    Skipped items count as neither open nor done: they are out of scope,
    and an item that is waiting is counted but never chased, so it is in
    the totals and out of the overdue and due-soon numbers.
    """
    today = today or timezone.now().date()
    items = ChecklistItem.objects.filter(conference=conference)
    total = items.exclude(status=ItemStatus.SKIPPED).count()
    done = items.filter(status=ItemStatus.DONE).count()
    open_items = items.filter(status__in=OPEN_ITEM_STATUSES)
    # Nothing waiting is chased, so the pressing numbers read the items a
    # person could actually start (design §9.3a).
    startable = open_items.filter(is_waiting=False)
    speaker_total = (
        items.filter(owner=ItemOwner.SPEAKER).exclude(status=ItemStatus.SKIPPED).count()
    )
    speaker_done = items.filter(owner=ItemOwner.SPEAKER, status=ItemStatus.DONE).count()
    team_total = total - speaker_total
    team_done = done - speaker_done
    return {
        "total": total,
        "done": done,
        "open": open_items.count(),
        "done_percent": _percent(done, total),
        "waiting": open_items.filter(is_waiting=True).count(),
        "overdue": startable.filter(due_date__lt=today).count(),
        "due_this_week": startable.filter(
            due_date__gte=today, due_date__lte=today + timedelta(days=7)
        ).count(),
        "blocked": items.filter(status=ItemStatus.BLOCKED).count(),
        "unassigned": open_items.filter(
            owner=ItemOwner.ORGANIZER, assignee__isnull=True, team__isnull=True
        ).count(),
        "speaker_total": speaker_total,
        "speaker_done": speaker_done,
        "speaker_percent": _percent(speaker_done, speaker_total),
        "team_total": team_total,
        "team_done": team_done,
        "team_percent": _percent(team_done, team_total),
    }


def my_task_stats(user, conference, today=None):
    """One person's numbers for the volunteer hub: what is assigned to them
    or their teams, how much is done, and what is pressing."""
    today = today or timezone.now().date()
    items = ChecklistItem.objects.filter(
        owned_by(user, conference),
        conference=conference,
        owner=ItemOwner.ORGANIZER,
    )
    total = items.exclude(status=ItemStatus.SKIPPED).count()
    done = items.filter(status=ItemStatus.DONE).count()
    open_items = items.filter(status__in=OPEN_ITEM_STATUSES)
    startable = open_items.filter(is_waiting=False)
    return {
        "total": total,
        "done": done,
        "open": open_items.count(),
        "done_percent": _percent(done, total),
        "waiting": open_items.filter(is_waiting=True).count(),
        "overdue": startable.filter(due_date__lt=today).count(),
        "due_this_week": startable.filter(
            due_date__gte=today, due_date__lte=today + timedelta(days=7)
        ).count(),
        "blocked": open_items.filter(status=ItemStatus.BLOCKED).count(),
        "done_by_me": items.filter(
            Q(completed_by=user), status=ItemStatus.DONE
        ).count(),
    }


def get_task_stats_dict(conference):
    """Public totals for the stats page and JSON, cached per edition. Empty
    when the speaker module is off, so the page shows nothing for it."""
    if not speaker_module_enabled(conference):
        return {}
    cache_key = f"{CACHE_KEY_TASKS}_{conference.year}"
    values = cache.get(cache_key)
    if values is None:
        items = ChecklistItem.objects.filter(conference=conference)
        total = items.exclude(status=ItemStatus.SKIPPED).count()
        done = items.filter(status=ItemStatus.DONE).count()
        values = {
            CACHE_KEY_TASKS_TOTAL: total,
            CACHE_KEY_TASKS_DONE: done,
            CACHE_KEY_TASKS_DONE_PERCENT: _percent(done, total),
        }
        cache.set(cache_key, values, STATS_CACHE_TIMEOUT)
    return values
