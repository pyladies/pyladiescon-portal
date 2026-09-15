from celery import shared_task

from .emails import send_invitation_email
from .models import Invitation


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_invitation_email_task(self, invitation_id):
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
