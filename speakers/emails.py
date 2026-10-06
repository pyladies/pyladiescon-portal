"""Email rendering for the speaker portal.

Kept apart from ``services`` so the Celery tasks can import it without a
cycle: services enqueue tasks, tasks send emails, emails import neither.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core import signing
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from common.markdown_emails import MarkdownEmailRenderer
from common.models import SentEmail, SentEmailStatus
from common.send_emails import send_email

from .constants import SessionStatus
from .models import MediaAsset, SpeakerSettings
from .people import user_label

INVITATION_SALT = "speakers.invitation"
INVITATION_TEMPLATE = "emails/speakers/invitation.md"
ACCEPTED_TEMPLATE = "emails/speakers/accepted.md"
ADDED_TO_SESSION_TEMPLATE = "emails/speakers/added_to_session.md"
PROPOSAL_APPROVED_TEMPLATE = "emails/speakers/proposal_approved.md"
PROPOSAL_REJECTED_TEMPLATE = "emails/speakers/proposal_rejected.md"
# The web and the worker keep their own clocks.
RECORD_CLOCK_SLACK = timedelta(minutes=1)
# Stands in for the signed token in a preview of an email not yet sent.
PREVIEW_LINK_PLACEHOLDER = "personal-link"


logger = logging.getLogger(__name__)


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


def email_recorded(template, since, **about):
    """Whether an email of this kind, about these records, already has a
    successful record from the action stamped at ``since``.

    Every email task that is acknowledged late can run twice (a worker that
    dies after the mail server accepted the message is given the task back),
    so each asks this before sending. ``about`` names the digest keys the
    email's context carries (``common.send_emails.DIGEST_KEYS``), and
    ``since`` is when the action it answers happened, so a record of an
    earlier action for the same records does not count.

    A record counts only if it is no older than ``since``, with no allowance
    for clock skew. Maintenance > Invitations forgives a minute (a wrong
    "recorded" only hides a row there), but here a wrong "recorded" would
    skip a real email: a resend made within a minute of the last send would
    find the last send's record and never go out. A worker whose clock runs
    behind can only cause a harmless second copy.
    """
    if since is None:
        return False
    keyed = {f"context_digest__{key}": row.pk for key, row in about.items()}
    return SentEmail.objects.filter(
        template=template,
        status=SentEmailStatus.SENT,
        sent_at__gte=since,
        **keyed,
    ).exists()


def invitation_email_recorded(invitation):
    """Whether the current send of this invitation already went out."""
    return email_recorded(
        INVITATION_TEMPLATE, invitation.sent_at, invitation=invitation
    )


def acceptance_email_recorded(invitation):
    """Whether this acceptance's welcome email already went out. Its context
    carries no invitation, so the record is matched by presenter."""
    return email_recorded(
        ACCEPTED_TEMPLATE, invitation.accepted_at, presenter=invitation.presenter
    )


def added_to_session_email_recorded(link):
    """Whether this session-presenter link's email already went out. Removing
    and re-adding a presenter makes a new link, hence the link's own
    creation date as the anchor."""
    return email_recorded(
        ADDED_TO_SESSION_TEMPLATE,
        link.creation_date,
        presenter=link.presenter,
        session=link.session,
    )


def proposal_reply_recorded(proposal, template):
    """Whether the reply to this proposal's decision already went out."""
    return email_recorded(
        template,
        proposal.decided_at,
        presenter=proposal.presenter,
        session=proposal.session,
    )


def send_invitation_email(invitation):
    """Render and send the invitation email, text and HTML parts.

    The accept link is the presenter's credential (opening it signs them
    in), so it is withheld from the sent-email record that maintainers read.
    """
    accept_url = invitation_url(invitation)
    return send_email(
        invitation_subject(invitation, invitation.conference),
        [invitation.presenter.email],
        markdown_template=INVITATION_TEMPLATE,
        context=invitation_context(
            invitation,
            conference=invitation.conference,
            accept_url=accept_url,
            expires_at=invitation.expires_at,
        ),
        secrets=[accept_url],
        reply_to=team_reply_to(invitation.conference),
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

# What turns text into a link, an image, a code span or raw HTML. Emphasis
# is left alone: a slanted word in an organizer's inbox is not the problem,
# a clickable "Approve now" pointing somewhere else is.
MARKUP_CHARS = str.maketrans({ch: "\\" + ch for ch in "\\`[]<>!"})


def as_written(value):
    """Presenter-typed text, shown to organizers as typed.

    The co-presenter note is fenced for the same reason (no links,
    headings or markup of theirs reach the organizers); a title and a name
    are read inline, so they are escaped instead of fenced.
    """
    return (value or "").translate(MARKUP_CHARS)


def organizer_inbox(conference, presenter=None):
    """Where organizer-facing mail for this edition goes.

    The team's own address when they have set one: a proposal is work for
    whoever runs the program, not news for everybody who happens to hold
    ``is_staff`` (which is not per edition and outlives the year someone
    helped). With the field blank it falls back to the staff accounts, so
    nothing sits unread in the queue while nobody is told.
    """
    settings_row = SpeakerSettings.objects.filter(conference=conference).first()
    if settings_row and settings_row.organizers_email:
        emails = {settings_row.organizers_email}
        # The liaison is this presenter's person, not part of the team
        # address, so they are told either way.
        if presenter is not None and presenter.liaison_email:
            emails.add(presenter.liaison_email)
        return sorted(emails)
    return organizer_recipients(presenter)


def team_reply_to(conference):
    """Where a speaker's reply to the portal goes: the team address set in
    this edition's speaker settings (``organizers_email``).

    Unlike ``organizer_inbox`` it never falls back to staff accounts, whose
    addresses are personal: with the field blank it returns nothing and the
    reply goes to ``DEFAULT_FROM_EMAIL``, as for any other portal email.
    """
    settings_row = SpeakerSettings.objects.filter(conference=conference).first()
    if settings_row and settings_row.organizers_email:
        return [settings_row.organizers_email]
    return None


def organizer_recipients(presenter=None):
    """Organizer inboxes: staff and superusers, plus the presenter's liaison."""
    users = get_user_model().objects.filter(
        Q(is_staff=True) | Q(is_superuser=True), is_active=True
    )
    emails = {user.email for user in users if user.email}
    if presenter is not None and presenter.liaison_email:
        emails.add(presenter.liaison_email)
    return sorted(emails)


def send_copresenter_suggestion_email(presenter, session, name, email, note):
    """Tell the organizers a presenter suggested someone for their session."""
    recipients = organizer_inbox(session.conference, presenter)
    if not recipients:
        return 0
    context = {
        "presenter": presenter,
        "session": session,
        "title": as_written(session.title),
        "proposer": as_written(presenter.display_name),
        "suggested_name": as_written(name),
        "suggested_email": as_written(email),
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
        markdown_template=ACCEPTED_TEMPLATE,
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
        reply_to=team_reply_to(invitation.conference),
    )


def send_added_to_session_email(link):
    """An organizer added an already-accepted presenter to a session."""
    presenter, session = link.presenter, link.session
    slot = getattr(session, "slot", None)
    send_email(
        f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} You've been added to "
        f"{session.title}",
        [presenter.email],
        markdown_template=ADDED_TO_SESSION_TEMPLATE,
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
        reply_to=team_reply_to(link.conference),
    )


UPLOAD_NOTICE_TEMPLATE = "emails/speakers/upload_notice.md"


def upload_notice_recorded(asset):
    """Whether this upload's notice already went out: a record of this
    template about this asset, no older than the asset itself."""
    return email_recorded(UPLOAD_NOTICE_TEMPLATE, asset.creation_date, asset=asset)


SCHEDULE_UPDATE_TEMPLATE = "emails/speakers/schedule_update.md"


def schedule_update_recorded(presenter, published_at):
    """Whether this publish's update already reached this presenter."""
    return email_recorded(SCHEDULE_UPDATE_TEMPLATE, published_at, presenter=presenter)


def send_schedule_update_email(presenter, session_changes, published_at):
    """The schedule was published and this presenter's sessions moved on
    it (design §10.1): one email listing their placed, moved and removed
    sessions, times in their own timezone. Returns the record.
    """
    lines = []
    for session, _ in session_changes:
        # Worded from the snapshot as it stands NOW, not as it stood at
        # publish time: a later publish may have put a removed session
        # back before this email went out (review of #461).
        row = getattr(session, "published_slot", None)
        if row is None:
            lines.append(
                {
                    "title": session.title,
                    "when": "",
                    "removed": True,
                    # Cancelling sends nothing itself, so this line is how
                    # the speaker hears; it must not promise a new time.
                    "cancelled": session.status == SessionStatus.CANCELLED,
                }
            )
            continue
        start = row.start_utc.astimezone(presenter.tzinfo)
        end = row.end_utc.astimezone(presenter.tzinfo)
        where = row.room.name if row.room_id else "all rooms"
        lines.append(
            {
                "title": session.title,
                "when": (
                    f"{start:%A %d %B}, {start:%H:%M}–{end:%H:%M} "
                    f"({presenter.timezone}) · {where}"
                ),
                "removed": False,
            }
        )
    return send_email(
        "The conference schedule was updated",
        [presenter.email],
        markdown_template=SCHEDULE_UPDATE_TEMPLATE,
        context={
            # The row itself rides along for the record's context digest,
            # which is what schedule_update_recorded keys the resend
            # guard on.
            "presenter": presenter,
            "presenter_name": presenter.display_name,
            "lines": lines,
            "schedule_url": absolute_url(reverse("speakers:my_schedule")),
        },
        conference=presenter.conference,
        presenter=presenter,
        user=presenter.user,
    )


def send_upload_notice_email(asset, presenter):
    """A speaker's upload just completed: tell their liaison, or the team
    when they have none (design §13.2, task 5.12). The length is probed on
    the media queue after this goes out, so the email says the page will
    show it. Recorded against the session; a reply goes to the speaker.

    With no liaison, no team address and no staff account that has an
    address, there is nobody to tell: nothing is sent, nothing is recorded
    as sent, and the gap is logged. Returns the record, or None then.
    """
    session = asset.session
    liaison = presenter.liaison_email
    recipients = [liaison] if liaison else organizer_inbox(session.conference)
    if not recipients:
        logger.warning(
            "Upload notice for asset %s on session %s has nobody to go to: no "
            "liaison, no organizers address, no staff address",
            asset.pk,
            session.slug,
        )
        return None
    # The version this one replaced: the highest below it still on the
    # line, which is the row record_asset just superseded. Not version - 1,
    # which after a deletion by hand would name a version long gone.
    earlier = (
        MediaAsset.objects.filter(
            session=session,
            kind=asset.kind,
            language=asset.language,
            variant=asset.variant,
            version__lt=asset.version,
        )
        .order_by("-version")
        .values_list("version", flat=True)
        .first()
    )
    return send_email(
        f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} {presenter.display_name} "
        f"uploaded a video for {session.title}",
        recipients,
        markdown_template=UPLOAD_NOTICE_TEMPLATE,
        context={
            "presenter": presenter,
            "session": session,
            "conference": session.conference,
            "asset": asset,
            "previous": earlier,
            "to_liaison": bool(liaison),
            "files_url": absolute_url(session.get_absolute_url() + "#files"),
            "board_url": absolute_url(reverse("speakers:checklist_board")),
        },
        reply_to=[presenter.email] if presenter.email else None,
    )


def presenter_email_context(presenter):
    """The common preface for emails to a presenter: what to call them and
    their sessions with the scheduled time in their timezone, if any."""
    links = list(
        presenter.session_presenters.select_related(
            "session", "session__kind", "session__published_slot", "role"
        ).order_by("session__title")
    )
    # Each role carries the word to call its people by (PresenterRole.
    # email_word), so a new role an organizer adds reads properly too.
    roles = {link.role.email_word or "speaker" for link in links}
    sessions = []
    for link in links:
        slot = getattr(link.session, "published_slot", None)
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
        reply_to=team_reply_to(proposal.conference),
    )
    # With the presenter: an edition's team address does not include this
    # proposer's liaison, and the liaison is their person.
    recipients = organizer_inbox(proposal.conference, presenter)
    if recipients:
        send_email(
            f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} New session proposal: "
            f"{session.title}",
            recipients,
            markdown_template="emails/speakers/proposal_for_organizers.md",
            context={
                **context,
                "review_url": absolute_url(reverse("speakers:proposal_queue")),
                # Their words, shown as words: see ``as_written``.
                "title": as_written(session.title),
                "proposer": as_written(presenter.display_name),
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
        markdown_template=PROPOSAL_APPROVED_TEMPLATE,
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
        reply_to=team_reply_to(proposal.conference),
    )


def send_proposal_rejected_email(proposal):
    """No. Short, kind, and without a reason, which is what was asked for."""
    presenter = proposal.presenter
    send_email(
        f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} About your proposal: "
        f"{proposal.session.title}",
        [presenter.email],
        markdown_template=PROPOSAL_REJECTED_TEMPLATE,
        context={
            "presenter": presenter,
            "conference": proposal.conference,
            "session": proposal.session,
        },
        reply_to=team_reply_to(proposal.conference),
    )
