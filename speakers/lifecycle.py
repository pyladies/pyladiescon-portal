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
        return False  # a required checklist item is still open
    ActivityLog.record(
        session.conference,
        "session.confirmed",
        target=session,
        actor=actor,
        message="All required presenters accepted their invitations",
    )
    return True
