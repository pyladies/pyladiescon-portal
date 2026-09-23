"""When a checklist item can be started (design §9.3a).

An item exists long before it can be done: confirming a slot before the
schedule is built, reading a guide nobody has published, a tech check the
team has not opened booking for. Such an item waits, and the portal says
what it waits for rather than offering a tick box that does nothing.

A line waits on any of three sources, and an organizer override outranks
all of them:

* a **rule**, for something the database can answer. The registry below
  holds the predicates; ``ReadyRule`` names them.
* a **gate**, a switch organizers flip, for work the portal cannot see.
* **another item**, for the one piece of work that unblocks this one.

``apply_readiness`` writes the answer onto the item, so the digests, the
counts and the board can filter in SQL instead of asking every row.
"""

from django.db.models import Q

from .constants import ItemStatus, ReadyOverride, ReadyRule
from .models import ChecklistItem, Handbook, ScheduleSlot, SpeakerSettings

READY_RULES = {}


def ready_rule(name):
    def register(func):
        READY_RULES[name] = func
        return func

    return register


@ready_rule(ReadyRule.SESSION_SCHEDULED)
def session_scheduled(item):
    """The session has a slot, so there is a time to confirm."""
    if item.session_id is None:
        return False
    return ScheduleSlot.objects.filter(session_id=item.session_id).exists()


@ready_rule(ReadyRule.GUIDE_PUBLISHED)
def guide_published(item):
    """The guide this item points at has a published version."""
    return Handbook.current(item.conference, item.guide_key) is not None


@ready_rule(ReadyRule.REGISTRATION_OPEN)
def registration_open(item):
    """The edition has pretix set up, so there is somewhere to register."""
    settings_row = SpeakerSettings.objects.filter(
        conference_id=item.conference_id
    ).first()
    return bool(settings_row and settings_row.pretix_configured)


def _blocking_item(item):
    """The item this one waits for, resolved from the line it was made from.

    The blocking item may be created after this one (an organizer line
    instantiated later), so the link is resolved here rather than only at
    instantiation, and stored once it resolves.
    """
    if item.waits_for_id is not None:
        return item.waits_for
    if item.waits_for_line_id is None:
        return None
    candidates = ChecklistItem.objects.filter(
        template_item_id=item.waits_for_line_id,
        presenter_id=item.presenter_id,
    )
    if item.session_id is not None:
        # The blocking line may be general (no session) or per session.
        candidates = candidates.filter(
            Q(session_id=item.session_id) | Q(session__isnull=True)
        )
    return candidates.order_by("session_id", "id").first()


def evaluate_readiness(item):
    """``(waiting, reason)`` for one item, without saving anything."""
    if item.ready_override == ReadyOverride.OPEN:
        return False, ""
    if item.ready_override == ReadyOverride.HOLD:
        return True, item.template_waiting_note or "the organizers are holding this"
    note = item.template_waiting_note
    if item.ready_gate_id is not None and not item.ready_gate.is_open:
        return True, note or item.ready_gate.waiting_note
    func = READY_RULES.get(item.ready_rule)
    if func is not None and not func(item):
        return True, note or ReadyRule(item.ready_rule).label.lower()
    blocking = _blocking_item(item)
    if blocking is not None and blocking.status not in (
        ItemStatus.DONE,
        ItemStatus.SKIPPED,
    ):
        return True, note or f"we are still on “{blocking.title}”"
    return False, ""


def apply_readiness(item, save=True):
    """Evaluate and store. Returns whether the item's readiness moved."""
    waiting, reason = evaluate_readiness(item)
    blocking = _blocking_item(item)
    fields = []
    if blocking is not None and item.waits_for_id != blocking.pk:
        item.waits_for = blocking
        fields.append("waits_for")
    if (item.is_waiting, item.waiting_reason) != (waiting, reason):
        item.is_waiting, item.waiting_reason = waiting, reason
        fields += ["is_waiting", "waiting_reason"]
    if fields and save:
        item.save(update_fields=fields + ["modified_date"])
    return "is_waiting" in fields


def _waiting_capable(queryset):
    """Only items a wait source could apply to, so the pass reads few rows."""
    return queryset.filter(
        Q(ready_rule__gt="")
        | Q(ready_gate__isnull=False)
        | Q(waits_for_line__isnull=False)
        | Q(waits_for__isnull=False)
        | Q(ready_override__gt="")
        | Q(is_waiting=True)
    ).select_related("presenter", "session", "conference", "ready_gate", "waits_for")


def refresh_readiness(queryset):
    """Re-evaluate a set of items. Returns how many moved."""
    return sum(apply_readiness(item) for item in _waiting_capable(queryset))


def refresh_for_conference(conference=None):
    """Every item of an edition (the nightly safety net and the gate flip)."""
    queryset = ChecklistItem.objects.all()
    if conference is not None:
        queryset = queryset.filter(conference=conference)
    return refresh_readiness(queryset)


def refresh_dependents(item):
    """Items waiting on this one, after it was completed or reopened."""
    return refresh_readiness(
        ChecklistItem.objects.filter(
            Q(waits_for=item)
            | Q(waits_for_line_id=item.template_item_id, presenter_id=item.presenter_id)
        ).exclude(pk=item.pk)
    )
