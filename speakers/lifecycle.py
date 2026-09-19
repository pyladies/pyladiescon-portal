"""Session status helpers shared by invitations and checklists.

Lives below ``services`` and ``checklists`` so both can import it without
a cycle: it depends on the models only.
"""

from .constants import SessionStatus
from .models import ActivityLog, TransitionError


def confirm_session_if_ready(session, actor=None):
    """Advance a DRAFT/INVITED session once every required presenter accepted
    and no required checklist item is still open. Returns whether it did."""
    if session.status not in (SessionStatus.DRAFT, SessionStatus.INVITED):
        return False
    links = list(session.session_presenters.all())
    required = [link for link in links if link.is_required]
    if not required or any(not link.is_confirmed for link in required):
        return False
    try:
        session.confirm()
    except TransitionError:
        _record_blocked(session)
        return False
    ActivityLog.record(
        session.conference,
        "session.confirmed",
        target=session,
        actor=actor,
        message="All required presenters accepted their invitations",
    )
    return True


def waiting_on(session):
    """The open required items keeping ``session`` from CONFIRMED, as
    ``{"title", "presenter"}`` dicts (``presenter`` empty for session-level
    items), in checklist order."""
    return [
        {
            "title": item.title,
            "presenter": item.presenter.display_name if item.presenter_id else "",
        }
        for item in session.blocking_required_items.select_related("presenter")
    ]


def waiting_on_labels(session):
    """``waiting_on`` as display strings: "Sign the form (Ada)"."""
    return [_label(entry) for entry in waiting_on(session)]


def _record_blocked(session):
    """Log ``session.confirm_blocked`` naming the open required items, once
    per distinct set: a retry that finds the same items open logs nothing."""
    waiting = waiting_on(session)
    if not waiting:
        return
    previous = (
        ActivityLog.for_target(session).filter(action="session.confirm_blocked").first()
    )
    if previous is not None and previous.data.get("items") == waiting:
        return
    ActivityLog.record(
        session.conference,
        "session.confirm_blocked",
        target=session,
        message="Waiting on: " + ", ".join(_label(w) for w in waiting),
        items=waiting,
    )


def _label(waiting):
    if waiting["presenter"]:
        return f"{waiting['title']} ({waiting['presenter']})"
    return waiting["title"]
