"""Email rendering for the speaker portal.

Kept apart from ``services`` so the Celery tasks can import it without a
cycle: services enqueue tasks, tasks send emails, emails import neither.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core import signing
from django.db.models import Q
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


FENCE = "`" * 3  # a note may not close the code block it is shown in


def organizer_recipients(presenter=None):
    """Organizer inboxes: staff and superusers, plus the presenter's liaison."""
    users = get_user_model().objects.filter(
        Q(is_staff=True) | Q(is_superuser=True), is_active=True
    )
    emails = {user.email for user in users if user.email}
    if presenter is not None and presenter.liaison and presenter.liaison.email:
        emails.add(presenter.liaison.email)
    return sorted(emails)


def send_copresenter_suggestion_email(presenter, session, name, email, note):
    """Tell the organizers a presenter suggested someone for their session."""
    recipients = organizer_recipients(presenter)
    if not recipients:
        return 0
    context = {
        "presenter": presenter,
        "session": session,
        "suggested_name": name,
        "suggested_email": email,
        # Presenter-written text goes into the email as a literal block:
        # no links, headings or markup of theirs reach the organizers.
        "note": note.replace(FENCE, "'" * 3).strip(),
        "session_url": f"https://{Site.objects.get_current().domain}"
        f"{session.get_absolute_url()}",
    }
    # One message per organizer, as the sponsorship emails do, so a liaison
    # does not see every staff address.
    for recipient in recipients:
        send_email(
            f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Co-presenter suggested for "
            f"{session.title}",
            [recipient],
            markdown_template="emails/speakers/copresenter_suggestion.md",
            context=context,
        )
    return len(recipients)
