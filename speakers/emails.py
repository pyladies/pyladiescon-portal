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


def send_acceptance_email(invitation):
    """After accepting: account details, how to sign in, sessions, next steps."""
    presenter = invitation.presenter
    send_email(
        f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Welcome aboard, "
        f"{presenter.display_name}!",
        [presenter.email],
        markdown_template="emails/speakers/accepted.md",
        context={
            "presenter": presenter,
            "user": presenter.user,
            "conference": invitation.conference,
            "sessions": list(
                presenter.session_presenters.select_related("session").order_by(
                    "session__title"
                )
            ),
            "login_url": absolute_url(reverse("account_login")),
            "password_url": absolute_url(reverse("account_set_password")),
            "dashboard_url": absolute_url(reverse("speakers:my_dashboard")),
        },
    )


def send_added_to_session_email(link):
    """An organizer added an already-accepted presenter to a session."""
    presenter, session = link.presenter, link.session
    slot = getattr(session, "slot", None)
    send_email(
        f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} You've been added to "
        f"{session.title}",
        [presenter.email],
        markdown_template="emails/speakers/added_to_session.md",
        context={
            "presenter": presenter,
            "conference": link.conference,
            "session": session,
            "role": link.role.name.lower(),
            # The role row carries the word the emails use for it, so a role
            # an organizer adds later reads properly here too.
            "role_word": link.role.email_word,
            "starts": slot.start_utc.astimezone(presenter.tzinfo) if slot else None,
            "session_url": absolute_url(
                reverse("speakers:my_session_detail", kwargs={"slug": session.slug})
            ),
            "dashboard_url": absolute_url(reverse("speakers:my_dashboard")),
        },
    )


def presenter_email_context(presenter):
    """The common preface for emails to a presenter: what to call them and
    their sessions with the scheduled time in their timezone, if any."""
    links = list(
        presenter.session_presenters.select_related(
            "session", "session__kind", "session__slot", "role"
        ).order_by("session__title")
    )
    # Each role carries the word to call its people by (PresenterRole.
    # email_word), so a new role an organizer adds reads properly too.
    roles = {link.role.email_word or "speaker" for link in links}
    sessions = []
    for link in links:
        slot = getattr(link.session, "slot", None)
        sessions.append(
            {
                "title": link.session.title,
                "kind": link.session.kind.name,
                "role": link.role.name.lower(),
                "starts": slot.start_utc.astimezone(presenter.tzinfo) if slot else None,
            }
        )
    return {
        "presenter": presenter,
        "role_word": roles.pop() if len(roles) == 1 else "speaker",
        "sessions": sessions,
        "dashboard_url": absolute_url(reverse("speakers:my_dashboard")),
    }


# ---- Proposals --------------------------------------------------------------


def send_proposal_received_email(proposal):
    """Two emails at submission: a receipt, and a nudge to the organizers."""
    presenter, session = proposal.presenter, proposal.session
    context = {
        "presenter": presenter,
        "conference": proposal.conference,
        "session": session,
        "proposals_url": absolute_url(reverse("speakers:my_proposals")),
    }
    send_email(
        f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} We have your proposal: "
        f"{session.title}",
        [presenter.email],
        markdown_template="emails/speakers/proposal_received.md",
        context=context,
    )
    recipients = organizer_recipients()
    if recipients:
        send_email(
            f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} New session proposal: "
            f"{session.title}",
            recipients,
            markdown_template="emails/speakers/proposal_for_organizers.md",
            context={
                **context,
                "review_url": absolute_url(reverse("speakers:proposal_queue")),
            },
        )
    return len(recipients) + 1


def send_proposal_approved_email(proposal):
    """Yes. The onboarding email, for someone who already has an account."""
    presenter, session = proposal.presenter, proposal.session
    send_email(
        f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Your session is in: "
        f"{session.title}",
        [presenter.email],
        markdown_template="emails/speakers/proposal_approved.md",
        context={
            "presenter": presenter,
            "conference": proposal.conference,
            "session": session,
            "session_url": absolute_url(
                reverse("speakers:my_session_detail", kwargs={"slug": session.slug})
            ),
            "dashboard_url": absolute_url(reverse("speakers:my_dashboard")),
            "checklist_url": absolute_url(reverse("speakers:my_checklist")),
        },
    )


def send_proposal_rejected_email(proposal):
    """No. Short, kind, and without a reason, which is what was asked for."""
    presenter = proposal.presenter
    send_email(
        f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} About your proposal: "
        f"{proposal.session.title}",
        [presenter.email],
        markdown_template="emails/speakers/proposal_rejected.md",
        context={
            "presenter": presenter,
            "conference": proposal.conference,
            "session": proposal.session,
        },
    )
