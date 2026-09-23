"""Checklist instances: creating them from templates and moving them along.

Instantiation copies every template field onto the instance, so editing a
template later changes nothing already created unless an organizer
back-fills (design §9.2). Status changes go through the functions here so
every completion lands in the ActivityLog with its actor.
"""

from django.db.models import Q
from django.utils import timezone

from volunteer.models import Team

from .constants import (
    OPEN_ITEM_STATUSES,
    SESSION_LANGUAGE,
    AssigneeDefault,
    ChecklistScope,
    ItemOwner,
    ItemStatus,
    NoticeKind,
)
from .lifecycle import confirm_session_if_ready
from .models import (
    ActivityLog,
    ChecklistItem,
    ChecklistTemplate,
    ChecklistTemplateItem,
    Presenter,
    SessionPresenter,
    SpeakerSettings,
)


class ChecklistError(ValueError):
    """A status change that is not allowed (ticking an automatic item)."""


def _anchors(session, presenter=None, accepted_at=None):
    """Due-date anchors; ``session`` is None for items not tied to one."""
    conference = session.conference if session is not None else presenter.conference
    slot = getattr(session, "slot", None) if session is not None else None
    return {
        "invitation_accepted": accepted_at,
        "conference_start": conference.start_date or conference.conference_date,
        "session_start": slot.start_utc if slot is not None else None,
    }


def _accepted_at(presenter):
    """When the presenter first accepted, for anchoring general items."""
    first = (
        presenter.invitations.filter(accepted_at__isnull=False)
        .order_by("accepted_at")
        .values_list("accepted_at", flat=True)
        .first()
    )
    if first is not None:
        return first
    return (
        presenter.session_presenters.filter(confirmed_at__isnull=False)
        .order_by("confirmed_at")
        .values_list("confirmed_at", flat=True)
        .first()
    )


def _default_owner(template_item, session, presenter):
    """``(assignee, team)`` an organizer item starts with."""
    if template_item.owner != ItemOwner.ORGANIZER:
        return None, None
    if template_item.assignee_default == AssigneeDefault.LIAISON and presenter:
        return presenter.liaison, None
    if template_item.assignee_default == AssigneeDefault.TEAM:
        conference_id = (session or presenter).conference_id
        team = Team.objects.filter(
            conference_id=conference_id,
            short_name=template_item.default_team_name,
        ).first()
        return None, team
    return None, None


def _create_instance(template_item, *, session, presenter, anchors, language=""):
    """Create one instance unless the same one already exists. Returns
    the item, or None when it was already there."""
    lookup = {
        "template_item": template_item,
        "presenter": presenter,
        "session": session,
        "requires_asset_language": language,
    }
    if ChecklistItem.objects.filter(**lookup).exists():
        return None
    title = template_item.title
    if template_item.per_translation_language and language:
        title = f"{title} ({language})"
    assignee, team = _default_owner(template_item, session, presenter)
    return ChecklistItem.objects.create(
        conference_id=(session or presenter).conference_id,
        order=template_item.order,
        owner=template_item.owner,
        title=title,
        description_md=template_item.description_md,
        due_date=template_item.due_date(**anchors),
        assignee=assignee,
        team=team,
        is_required=template_item.is_required,
        auto_complete_rule=template_item.auto_complete_rule,
        requires_asset_kind=template_item.requires_asset_kind,
        requires_handbook=template_item.requires_handbook,
        **lookup,
    )


def _languages_for(template_item, session):
    """Which language values a template line expands to on this session."""
    if template_item.per_translation_language:
        settings_row = SpeakerSettings.objects.filter(
            conference_id=session.conference_id
        ).first()
        return list(settings_row.translation_languages) if settings_row else []
    if template_item.requires_asset_language == SESSION_LANGUAGE:
        return [session.language]
    return [template_item.requires_asset_language]


def instantiate_presenter_checklist(link, accepted_at=None):
    """Create the presenter-scope items for one SessionPresenter row.

    Returns the items created; nothing when no template matches or the
    items already exist.
    """
    template = ChecklistTemplate.for_presenter(link.session, link.role)
    if template is None:
        return []
    accepted = accepted_at or link.confirmed_at
    anchors = _anchors(link.session, link.presenter, accepted)
    general_anchors = _anchors(None, link.presenter, accepted)
    created = []
    for template_item in template.items.all():
        once = template_item.once_per_presenter
        item = _create_instance(
            template_item,
            session=None if once else link.session,
            presenter=link.presenter,
            anchors=general_anchors if once else anchors,
        )
        if item is not None:
            created.append(item)
    return created


def instantiate_general_checklist(presenter, accepted_at=None):
    """Create the every-presenter items for one presenter, once."""
    template = ChecklistTemplate.for_general(presenter.conference)
    if template is None:
        return []
    anchors = _anchors(None, presenter, accepted_at or _accepted_at(presenter))
    created = []
    for template_item in template.items.all():
        item = _create_instance(
            template_item, session=None, presenter=presenter, anchors=anchors
        )
        if item is not None:
            created.append(item)
    return created


def instantiate_session_checklist(session):
    """Create the session-scope items (post-production) for a session."""
    template = ChecklistTemplate.for_session(session)
    if template is None:
        return []
    anchors = _anchors(session)
    created = []
    for template_item in template.items.all():
        for language in _languages_for(template_item, session):
            item = _create_instance(
                template_item,
                session=session,
                presenter=None,
                anchors=anchors,
                language=language,
            )
            if item is not None:
                created.append(item)
    return created


def _matching_targets(template_item):
    """``(session, presenter, anchors)`` for every checklist already created
    from the line's template. ``session`` is None for general lines and for
    once-per-presenter lines."""
    template = template_item.template
    if template.scope == ChecklistScope.GENERAL:
        # Everyone who has accepted, the same set instantiate_general_
        # checklist runs for: an invitation to the conference in general
        # carries no session, so filtering on a confirmed session link would
        # skip those presenters and quietly never give them the new line.
        presenters = Presenter.objects.filter(
            Q(session_presenters__confirmed_at__isnull=False)
            | Q(invitations__accepted_at__isnull=False),
            conference=template.conference,
        ).distinct()
        return [
            (None, presenter, _anchors(None, presenter, _accepted_at(presenter)))
            for presenter in presenters
        ]
    if template.scope == ChecklistScope.PRESENTER:
        links = SessionPresenter.objects.filter(
            conference=template.conference,
            session__kind=template.kind,
            role=template.role,
            confirmed_at__isnull=False,
        ).select_related("session", "presenter", "presenter__liaison")
        if template_item.once_per_presenter:
            first_link = {}
            for link in links:
                first_link.setdefault(link.presenter_id, link)
            # Anchored on when they accepted, not on whichever link happens
            # to sort first, so the line lands on the same day whether it is
            # created at acceptance or added to the template later.
            return [
                (
                    None,
                    link.presenter,
                    _anchors(None, link.presenter, _accepted_at(link.presenter)),
                )
                for link in first_link.values()
            ]
        return [
            (
                link.session,
                link.presenter,
                _anchors(link.session, link.presenter, link.confirmed_at),
            )
            for link in links
        ]
    sessions = (
        ChecklistItem.objects.filter(template_item__template=template)
        .values_list("session", flat=True)
        .distinct()
    )
    return [
        (session, None, _anchors(session))
        for session in template.conference.sessions.filter(pk__in=sessions)
    ]


def apply_new_template_item(template_item):
    """Add a new template line to every checklist already created from its
    template (design §9.2, as revised: no back-fill step). The new items
    are flagged for the daily update email. Returns the items created."""
    created = []
    for session, presenter, anchors in _matching_targets(template_item):
        for language in (
            _languages_for(template_item, session) if presenter is None else [""]
        ):
            item = _create_instance(
                template_item,
                session=session,
                presenter=presenter,
                anchors=anchors,
                language=language,
            )
            if item is not None:
                item.flag_notice(NoticeKind.NEW)
                item.save(
                    update_fields=["pending_notice", "pending_since", "modified_date"]
                )
                created.append(item)
    return created


NOTIFY_ON_CHANGE = ("title", "description_md", "due_date")

#: What an instance takes from its template line when the line is edited.
FOLLOWS_THE_TEMPLATE = (
    "title",
    "description_md",
    "due_date",
    "order",
    "owner",
    "is_required",
    "auto_complete_rule",
    "requires_asset_kind",
    "requires_handbook",
    "pending_notice",
    "pending_since",
    "modified_date",
)


def apply_template_item_changes(template_item):
    """Push an edited line to its existing instances.

    Title, description, due date (recomputed), owner, required flag and the
    rule fields follow the template; the order does too but silently. Items
    whose title, description or due date changed are flagged for the daily
    update email. Returns the number of items changed."""
    changed = 0
    touched = []
    anchors_for = {
        (session.pk if session else None, presenter.pk if presenter else None): anchors
        for session, presenter, anchors in _matching_targets(template_item)
    }
    for item in ChecklistItem.objects.filter(
        template_item=template_item
    ).select_related("session", "presenter"):
        anchors = anchors_for.get((item.session_id, item.presenter_id))
        if anchors is None:
            # An instance the target list does not cover (a presenter whose
            # link was unconfirmed since, say). Work its anchors out rather
            # than leaving a stale due date behind with nothing to say so.
            anchors = _anchors(
                item.session,
                item.presenter,
                _accepted_at(item.presenter) if item.presenter_id else None,
            )
        title = template_item.title
        if template_item.per_translation_language and item.requires_asset_language:
            title = f"{title} ({item.requires_asset_language})"
        before = {field: getattr(item, field) for field in NOTIFY_ON_CHANGE}
        item.title = title
        item.description_md = template_item.description_md
        item.due_date = template_item.due_date(**anchors)
        item.order = template_item.order
        item.owner = template_item.owner
        item.is_required = template_item.is_required
        item.auto_complete_rule = template_item.auto_complete_rule
        item.requires_asset_kind = template_item.requires_asset_kind
        item.requires_handbook = template_item.requires_handbook
        if any(getattr(item, field) != before[field] for field in NOTIFY_ON_CHANGE):
            item.flag_notice(NoticeKind.CHANGED)
            changed += 1
        item.modified_date = timezone.now()
        touched.append(item)
    # One statement rather than a save per instance: a popular line can sit
    # on hundreds of checklists, and nothing listens for ChecklistItem saves.
    ChecklistItem.objects.bulk_update(touched, FOLLOWS_THE_TEMPLATE, batch_size=500)
    return changed


def retire_template_item(template_item):
    """Before a line is deleted: drop the open copies, keep done and skipped
    ones for the record. Returns the number removed.

    "Open" includes blocked, as it does when a presenter's role changes: a
    note about why an item is stuck is worth nothing once the line it came
    from is gone.
    """
    removed, _ = ChecklistItem.objects.filter(
        template_item=template_item, status__in=list(OPEN_ITEM_STATUSES)
    ).delete()
    return removed


def sync_template_order(template):
    """Reordering lines reorders their instances, silently."""
    for line in template.items.all():
        ChecklistItem.objects.filter(template_item=line).exclude(
            order=line.order
        ).update(order=line.order)


def add_adhoc_item(
    conference,
    title,
    owner,
    *,
    presenter=None,
    session=None,
    due_date=None,
    assignee=None,
    team=None,
    description_md="",
    actor=None,
):
    """A one-off item for a presenter or a session (design §9.2)."""
    item = ChecklistItem.objects.create(
        conference=conference,
        title=title,
        owner=owner,
        presenter=presenter,
        session=session,
        due_date=due_date,
        assignee=assignee,
        team=team if assignee is None else None,
        description_md=description_md,
        order=1000,
        pending_notice=NoticeKind.NEW,
        pending_since=timezone.now(),
    )
    ActivityLog.record(
        conference,
        "checklist.item_added",
        target=presenter or session,
        actor=actor,
        message=title,
        item_id=item.pk,
    )
    return item


def _log(item, action, actor, message=""):
    ActivityLog.record(
        item.conference,
        action,
        target=item.presenter or item.session,
        actor=actor,
        message=message or item.title,
        item_id=item.pk,
        status=item.status,
    )


def set_item_status(item, status, *, actor=None, note=None, manual=True):
    """Move an item to ``status``.

    A person may not tick or untick an automatic item (``manual=True`` with a
    rule set); the rules do that. Completing or skipping a required item
    re-tries the session's confirmation.
    """
    if manual and item.is_automatic and status in (ItemStatus.DONE, ItemStatus.TODO):
        raise ChecklistError("This item completes itself; it cannot be ticked by hand.")
    previous = item.status
    item.status = status
    if note is not None:
        item.note = note
    if status == ItemStatus.DONE:
        item.completed_by = actor
        item.completed_at = timezone.now()
    elif status == ItemStatus.TODO:
        item.completed_by = None
        item.completed_at = None
    item.save()
    if status != previous:
        _log(item, f"checklist.{status.lower()}", actor)
        if item.is_required and status in (ItemStatus.DONE, ItemStatus.SKIPPED):
            if item.session_id is not None:
                confirm_session_if_ready(item.session)
    return item


def complete_item(item, actor=None, note=None, manual=True):
    return set_item_status(item, ItemStatus.DONE, actor=actor, note=note, manual=manual)


def reopen_item(item, actor=None, note=None, manual=True):
    return set_item_status(item, ItemStatus.TODO, actor=actor, note=note, manual=manual)


def skip_item(item, actor=None, note=None):
    return set_item_status(item, ItemStatus.SKIPPED, actor=actor, note=note)


def block_item(item, note, actor=None):
    return set_item_status(
        item, ItemStatus.BLOCKED, actor=actor, note=note, manual=False
    )


def assign_item(item, assignee=None, team=None, actor=None):
    """Hand an organizer item to a person or a team (never both); logged so
    the presenter page shows it."""
    previous = (item.assignee_id, item.team_id)
    item.assignee = assignee
    item.team = team if assignee is None else None
    item.save(update_fields=["assignee", "team", "modified_date"])
    if previous != (item.assignee_id, item.team_id):
        _log(
            item,
            "checklist.assigned",
            actor,
            f"{item.title} → {item.owner_label or 'nobody'}",
        )
    return item


def collapse_general_duplicates(conference):
    """Fold per-session copies of general lines into one session-less item.

    Two passes: lines of per-session templates whose title matches a line
    of the every-presenter template (they are moved and the redundant
    template lines deleted), and once-per-presenter lines that still have
    several copies. A done copy is preferred; open extras are dropped.
    Returns ``(moved, dropped, lines_deleted)``. Idempotent.
    """
    general = ChecklistTemplate.for_general(conference)
    moved = dropped = lines = 0
    if general is not None:
        general_by_title = {line.title: line for line in general.items.all()}
        stale_lines = ChecklistTemplateItem.objects.filter(
            template__conference=conference,
            template__scope=ChecklistScope.PRESENTER,
            title__in=general_by_title,
        )
        for line in list(stale_lines):
            m, d = _collapse_line(line, general_by_title[line.title])
            moved += m
            dropped += d
            line.delete()
            lines += 1
    for line in ChecklistTemplateItem.objects.filter(
        template__conference=conference, once_per_presenter=True
    ):
        m, d = _collapse_line(line, line)
        moved += m
        dropped += d
    return moved, dropped, lines


def _collapse_line(line, target_line):
    """Per presenter, leave exactly one copy of ``line``: the session-less
    item of ``target_line``, preferring one they have already done.

    Every other copy goes, whatever its status. Pass 1 deletes ``line``
    afterwards and ``ChecklistItem.template_item`` is SET_NULL, so anything
    left behind becomes a one-off item on a session with no line behind it,
    which nothing can collapse later: a blocked "Join the Discord" the
    speaker can never resolve. There is no second chance, so this takes them
    all.
    """
    moved = dropped = 0
    # A set, not .distinct(): the model's default ordering would make
    # DISTINCT include the order columns and repeat presenters.
    presenter_ids = set(
        ChecklistItem.objects.filter(template_item=line).values_list(
            "presenter_id", flat=True
        )
    )
    for presenter_id in presenter_ids:
        candidates = list(
            ChecklistItem.objects.filter(template_item=line, presenter_id=presenter_id)
        )
        # The general item may already exist, from an earlier collapse or
        # from the presenter accepting after the line became general.
        candidates += list(
            ChecklistItem.objects.filter(
                template_item=target_line,
                presenter_id=presenter_id,
                session__isnull=True,
            ).exclude(pk__in=[i.pk for i in candidates])
        )
        # Done wins: a speaker who finished this once should not be asked
        # again because the copy that survived happened to be open.
        candidates.sort(key=lambda i: (i.status != ItemStatus.DONE, i.pk))
        keep, extras = candidates[0], candidates[1:]
        for extra in extras:
            extra.delete()
            dropped += 1
        if keep.template_item_id != target_line.pk or keep.session_id is not None:
            keep.template_item = target_line
            keep.session = None
            keep.save()
            moved += 1
        # An item already where it belongs is left alone, so running this
        # twice reports nothing the second time and writes nothing either.
    return moved, dropped
