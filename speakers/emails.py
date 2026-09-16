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
from django.utils import timezone

from common.markdown_emails import MarkdownEmailRenderer
from common.send_emails import send_email

from .people import user_label

INVITATION_SALT = "speakers.invitation"
INVITATION_TEMPLATE = "emails/speakers/invitation.md"
# Stands in for the signed token in a preview of an email not yet sent.
PREVIEW_LINK_PLACEHOLDER = "personal-link"


def signed_invitation_token(invitation):
    """The opaque value that goes in the invitation URL."""
    return signing.dumps(
        {"i": invitation.pk, "t": invitation.token}, salt=INVITATION_SALT
    )


def absolute_url(path):
    """An absolute link for an email: the current Site's domain, over https
    except for a DEBUG server (local maildev links must be http).

    Reads the Site row directly rather than through ``get_current()``, whose
    per-process cache would keep a Celery worker on the old domain after
    ``set_site_domain`` runs in another process.
    """
    scheme = "http" if settings.DEBUG else "https"
    domain = Site.objects.get(pk=settings.SITE_ID).domain
    return f"{scheme}://{domain}{path}"


def invitation_url(invitation):
    return absolute_url(
        reverse("speakers:invitation", args=[signed_invitation_token(invitation)])
    )


def invitation_subject(invitation, conference):
    subject = (
        f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} You're invited to {conference.name}"
    )
    if invitation.session is not None:
        subject += f": {invitation.session.title}"
    return subject


def invitation_context(invitation, *, conference, accept_url, expires_at):
    return {
        "invitation": invitation,
        "presenter": invitation.presenter,
        "session": invitation.session,
        "conference": conference,
        "accept_url": accept_url,
        "expires_at": expires_at,
        # Who signs the personal message; a resend by the system has nobody.
        "sender": (
            user_label(invitation.invited_by)
            if invitation.invited_by is not None
            else "the organizing team"
        ),
    }


def send_invitation_email(invitation):
    """Render and send the invitation email, text and HTML parts."""
    send_email(
        invitation_subject(invitation, invitation.conference),
        [invitation.presenter.email],
        markdown_template=INVITATION_TEMPLATE,
        context=invitation_context(
            invitation,
            conference=invitation.conference,
            accept_url=invitation_url(invitation),
            expires_at=invitation.expires_at,
        ),
    )


def render_invitation_preview(invitation):
    """The invitation email as the presenter will read it, for the sender.

    Works on an unsaved draft: the accept link is a placeholder (a real token
    is only minted when the email goes out) and the expiry is what a link
    issued now would get. Returns the recipient, the subject and the
    sanitized HTML body, wrapper included, exactly as ``send_email`` builds
    it.
    """
    conference = invitation.presenter.conference
    context = invitation_context(
        invitation,
        conference=conference,
        accept_url=absolute_url(
            reverse("speakers:invitation", args=[PREVIEW_LINK_PLACEHOLDER])
        ),
        expires_at=timezone.now() + type(invitation).TOKEN_MAX_AGE,
    )
    context["current_site"] = Site.objects.get_current()
    context["preview"] = True
    renderer = MarkdownEmailRenderer()
    body = renderer.render_template(INVITATION_TEMPLATE, context)
    return {
        "recipient": invitation.presenter.email,
        "subject": invitation_subject(invitation, conference),
        "html": renderer.markdown_to_html(body),
    }


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
        "session_url": absolute_url(session.get_absolute_url()),
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
