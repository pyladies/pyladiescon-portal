from celery import shared_task

from .emails import send_copresenter_suggestion_email, send_invitation_email
from .models import Invitation, Presenter, Session
from .rules import reevaluate_all


@shared_task
def send_invitation_email_task(invitation_id):
    """Send the invitation email for ``invitation_id``."""
    invitation = (
        Invitation.objects.filter(pk=invitation_id)
        .select_related("presenter", "session", "conference")
        .first()
    )
    if invitation is None:
        return f"Invitation with id {invitation_id} not found"
    send_invitation_email(invitation)
    return f"Sent invitation email for {invitation_id}"


@shared_task
def send_copresenter_suggestion_task(presenter_id, session_id, name, email, note):
    """Email the organizers a presenter's co-presenter suggestion."""
    presenter = (
        Presenter.objects.filter(pk=presenter_id).select_related("liaison").first()
    )
    session = Session.objects.filter(pk=session_id).first()
    if presenter is None or session is None:
        return "Presenter or session not found"
    sent = send_copresenter_suggestion_email(presenter, session, name, email, note)
    return f"Sent co-presenter suggestion to {sent} organizer(s)"


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def reevaluate_checklists_task(self):
    """Nightly safety net: re-run every auto-completion rule (design §9.3)."""
    changed = reevaluate_all()
    return f"Re-evaluated checklists; {changed} item(s) changed"
