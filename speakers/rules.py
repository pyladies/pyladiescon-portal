"""Auto-completion rules (design §9.3).

Each rule is a callable taking a ChecklistItem and answering whether the
portal can tell the item is done: ``True`` (done), ``False`` (not yet) or a
``Blocked`` carrying the note to show. Templates reference rules by name
only; ``AutoRule`` lists the names and this registry supplies the code, so
a template naming an unknown rule fails validation and a rule missing
here fails the registry test.
"""

from django.db.models import Q

from attendee.models import PretixOrder, PretixOrderstatus

from .checklists import block_item, complete_item, reopen_item
from .constants import AutoRule, ItemStatus, MediaKind
from .models import (
    ChecklistItem,
    Handbook,
    HandbookReadReceipt,
    Invitation,
    MediaAsset,
    ScheduleSlot,
    SessionPresenter,
    SpeakerSettings,
)


class Blocked:
    """The rule found a problem a person has to fix; ``note`` says what."""

    def __init__(self, note):
        self.note = note


RULES = {}


def rule(name):
    def register(func):
        RULES[name] = func
        return func

    return register


@rule(AutoRule.BIO_AND_HEADSHOT)
def bio_and_headshot(item):
    presenter = item.presenter
    return bool(presenter and presenter.bio_md.strip() and presenter.headshot)


@rule(AutoRule.HANDBOOK_READ)
def handbook_read(item):
    current = Handbook.current(item.conference)
    if current is None or item.presenter_id is None:
        return False
    return HandbookReadReceipt.objects.filter(
        presenter_id=item.presenter_id, handbook=current
    ).exists()


def _invitations(item):
    queryset = Invitation.objects.filter(presenter_id=item.presenter_id)
    if item.session_id is not None:
        queryset = queryset.filter(
            Q(session_id=item.session_id) | Q(session__isnull=True)
        )
    return queryset


@rule(AutoRule.INVITATION_SENT)
def invitation_sent(item):
    return _invitations(item).filter(sent_at__isnull=False).exists()


@rule(AutoRule.INVITATION_ACCEPTED)
def invitation_accepted(item):
    if _invitations(item).filter(accepted_at__isnull=False).exists():
        return True
    return SessionPresenter.objects.filter(
        presenter_id=item.presenter_id,
        session_id=item.session_id,
        confirmed_at__isnull=False,
    ).exists()


@rule(AutoRule.SESSION_SCHEDULED)
def session_scheduled(item):
    return ScheduleSlot.objects.filter(session_id=item.session_id).exists()


@rule(AutoRule.PRETIX_REGISTERED)
def pretix_registered(item):
    presenter = item.presenter
    if presenter is None:
        return False
    if presenter.pretix_order_id is not None:
        # A manual link wins, whatever the email says.
        return presenter.pretix_order.status == PretixOrderstatus.PAID
    email = presenter.email
    return (
        PretixOrder.objects.filter(
            conference_id=presenter.conference_id, status=PretixOrderstatus.PAID
        )
        .filter(
            Q(email__iexact=email)
            | Q(raw_data__positions__contains=[{"attendee_email": email}])
        )
        .exists()
    )


@rule(AutoRule.ASSET_EXISTS)
def asset_exists(item):
    if not item.requires_asset_kind or item.session_id is None:
        return False
    return (
        MediaAsset.latest_ready(
            item.session, item.requires_asset_kind, item.requires_asset_language
        )
        is not None
    )


def _video_limit_minutes(session):
    if session.video_length_limit_minutes:
        return session.video_length_limit_minutes
    settings_row = SpeakerSettings.objects.filter(
        conference_id=session.conference_id
    ).first()
    return settings_row.default_video_length_limit_minutes if settings_row else None


@rule(AutoRule.VIDEO_LENGTH_OK)
def video_length_ok(item):
    session = item.session
    video = MediaAsset.latest_ready(session, MediaKind.RAW_VIDEO)
    if video is None or video.duration_seconds is None:
        return False
    limit = _video_limit_minutes(session)
    if limit is None:
        return True
    overage = video.duration_seconds - limit * 60
    if overage <= 0:
        return True
    minutes, seconds = divmod(overage, 60)
    return Blocked(
        f"Video is {minutes}:{seconds:02d} over the {limit}-minute limit "
        f"(v{video.version})."
    )


@rule(AutoRule.YOUTUBE_PUBLISHED)
def youtube_published(item):
    session = item.session
    return bool(session.youtube_url and session.youtube_publish_at)


def evaluate_item(item):
    """Apply the item's rule. Returns the new status when it changed, else None.

    Items a person skipped are left alone. An item the rule completed is
    re-opened when the rule stops holding (the bio was cleared, a new guide
    version was published); one a person completed by hand is not.
    """
    func = RULES.get(item.auto_complete_rule)
    if func is None or item.status == ItemStatus.SKIPPED:
        return None
    result = func(item)
    if isinstance(result, Blocked):
        if item.status != ItemStatus.BLOCKED or item.note != result.note:
            block_item(item, result.note)
            return ItemStatus.BLOCKED
        return None
    if result:
        if item.status in (ItemStatus.TODO, ItemStatus.BLOCKED):
            complete_item(item, manual=False, note="")
            return ItemStatus.DONE
        return None
    if item.status == ItemStatus.BLOCKED or (
        item.status == ItemStatus.DONE and item.completed_by_id is None
    ):
        reopen_item(item, manual=False)
        item.note = ""
        item.save(update_fields=["note", "modified_date"])
        return ItemStatus.TODO
    return None


def evaluate_items(items):
    """Evaluate each item; returns how many changed status."""
    changed = 0
    for item in items:
        if evaluate_item(item) is not None:
            changed += 1
    return changed


def _automatic(queryset, rules):
    return queryset.filter(
        auto_complete_rule__in=[str(r) for r in rules]
    ).select_related("presenter", "session", "conference")


def items_for_presenter(presenter, rules):
    return _automatic(ChecklistItem.objects.filter(presenter=presenter), rules)


def items_for_session(session, rules):
    return _automatic(ChecklistItem.objects.filter(session=session), rules)


def items_for_conference(conference, rules):
    return _automatic(ChecklistItem.objects.filter(conference=conference), rules)


def reevaluate_all(conference=None):
    """Every automatic item (the nightly safety net). Returns changes made."""
    queryset = ChecklistItem.objects.exclude(auto_complete_rule="")
    if conference is not None:
        queryset = queryset.filter(conference=conference)
    return evaluate_items(queryset.select_related("presenter", "session", "conference"))
