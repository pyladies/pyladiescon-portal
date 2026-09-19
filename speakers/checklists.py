"""Checklist instances: creating them from templates and moving them along.

Instantiation copies every template field onto the instance, so editing a
template later changes nothing already created unless an organizer
back-fills (design §9.2). Status changes go through the functions here so
every completion lands in the ActivityLog with its actor.
"""

from django.utils import timezone

from .constants import (
    SESSION_LANGUAGE,
    AssigneeDefault,
    ChecklistScope,
    ItemOwner,
    ItemStatus,
)
from .lifecycle import confirm_session_if_ready
from .models import (
    ActivityLog,
    ChecklistItem,
    ChecklistTemplate,
    SessionPresenter,
    SpeakerSettings,
)


class ChecklistError(ValueError):
    """A status change that is not allowed (ticking an automatic item)."""


def _anchors(session, accepted_at=None):
    conference = session.conference
    slot = getattr(session, "slot", None)
    return {
        "invitation_accepted": accepted_at,
        "conference_start": conference.start_date or conference.conference_date,
        "session_start": slot.start_utc if slot is not None else None,
    }


def _default_assignee(template_item, presenter):
    if (
        template_item.owner == ItemOwner.ORGANIZER
        and template_item.assignee_default == AssigneeDefault.LIAISON
        and presenter is not None
    ):
        return presenter.liaison
    return None


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
    return ChecklistItem.objects.create(
        conference_id=session.conference_id,
        order=template_item.order,
        owner=template_item.owner,
        title=title,
        description_md=template_item.description_md,
        due_date=template_item.due_date(**anchors),
        assignee=_default_assignee(template_item, presenter),
        is_required=template_item.is_required,
        auto_complete_rule=template_item.auto_complete_rule,
        requires_asset_kind=template_item.requires_asset_kind,
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
    anchors = _anchors(link.session, accepted_at or link.confirmed_at)
    created = []
    for template_item in template.items.all():
        item = _create_instance(
            template_item,
            session=link.session,
            presenter=link.presenter,
            anchors=anchors,
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


def backfill_template_item(template_item):
    """Add a template line to every checklist already created from its
    template, without duplicating. Returns the number of items created."""
    template = template_item.template
    created = 0
    if template.scope == ChecklistScope.PRESENTER:
        links = SessionPresenter.objects.filter(
            conference=template.conference,
            session__kind=template.kind,
            role=template.role,
            confirmed_at__isnull=False,
        ).select_related("session", "presenter", "presenter__liaison")
        for link in links:
            anchors = _anchors(link.session, link.confirmed_at)
            if _create_instance(
                template_item,
                session=link.session,
                presenter=link.presenter,
                anchors=anchors,
            ):
                created += 1
        return created
    sessions = (
        ChecklistItem.objects.filter(template_item__template=template)
        .values_list("session", flat=True)
        .distinct()
    )
    for session in template.conference.sessions.filter(pk__in=sessions):
        anchors = _anchors(session)
        for language in _languages_for(template_item, session):
            if _create_instance(
                template_item,
                session=session,
                presenter=None,
                anchors=anchors,
                language=language,
            ):
                created += 1
    return created


def add_adhoc_item(
    conference,
    title,
    owner,
    *,
    presenter=None,
    session=None,
    due_date=None,
    assignee=None,
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
        description_md=description_md,
        order=1000,
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


def assign_item(item, assignee, actor=None):
    """Change who is on an organizer item; logged so the presenter page shows it."""
    previous = item.assignee
    item.assignee = assignee
    item.save(update_fields=["assignee", "modified_date"])
    if previous != assignee:
        who = assignee.get_full_name() or assignee.username if assignee else "nobody"
        _log(item, "checklist.assigned", actor, f"{item.title} → {who}")
    return item
