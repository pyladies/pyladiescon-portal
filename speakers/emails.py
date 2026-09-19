"""Email rendering for the speaker portal.

Kept apart from ``services`` so the Celery tasks can import it without a
cycle: services enqueue tasks, tasks send emails, emails import neither.
"""

from django.conf import settings
from django.contrib.sites.models import Site
from django.core import signing
from django.urls import reverse

from common.send_emails import send_email

INVITATION_SALT = "speakers.invitation"


def signed_invitation_token(invitation):
    """The opaque value that goes in the invitation URL."""
    return signing.dumps(
        {"i": invitation.pk, "t": invitation.token}, salt=INVITATION_SALT
    )


def invitation_url(invitation):
    domain = Site.objects.get_current().domain
    path = reverse("speakers:invitation", args=[signed_invitation_token(invitation)])
    return f"https://{domain}{path}"


def send_invitation_email(invitation):
    """Render and send the invitation email, text and HTML parts."""
    session = invitation.session
    subject = (
        f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} You're invited to "
        f"{invitation.conference.name}"
    )
    if session is not None:
        subject += f": {session.title}"
    send_email(
        subject,
        [invitation.presenter.email],
        markdown_template="emails/speakers/invitation.md",
        context={
            "invitation": invitation,
            "presenter": invitation.presenter,
            "session": session,
            "conference": invitation.conference,
            "accept_url": invitation_url(invitation),
            "expires_at": invitation.expires_at,
        },
    )
