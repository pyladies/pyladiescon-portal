import logging

from celery import shared_task

from portal.models import Conference

from .constants import ProposalDecision
from .emails import (
    send_acceptance_email,
    send_added_to_session_email,
    send_copresenter_suggestion_email,
    send_invitation_email,
    send_proposal_approved_email,
    send_proposal_received_email,
    send_proposal_rejected_email,
    send_session_created_email,
)
from .models import (
    Invitation,
    Presenter,
    Proposal,
    Session,
    SessionPresenter,
    SpeakerSettings,
)
from .notices import send_checklist_change_notices
from .pretix import PretixError, reconcile, sync_order_by_code
from .readiness import refresh_for_conference
from .reminders import send_checklist_digests
from .rules import reevaluate_all

logger = logging.getLogger(__name__)


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
def send_added_to_session_email_task(link_id):
    """Tell an already-accepted presenter they were added to a session."""
    link = (
        SessionPresenter.objects.filter(pk=link_id, confirmed_at__isnull=False)
        .select_related("presenter", "role", "session", "session__slot", "conference")
        .first()
    )
    if link is None:
        return f"Session presenter {link_id} is not confirmed"
    send_added_to_session_email(link)
    return f"Sent added-to-session email for {link_id}"


@shared_task
def send_acceptance_email_task(invitation_id):
    """Send the welcome email once an invitation has been accepted."""
    invitation = (
        Invitation.objects.filter(pk=invitation_id, accepted_at__isnull=False)
        .select_related("presenter", "presenter__user", "conference")
        .first()
    )
    if invitation is None or invitation.presenter.user is None:
        return f"Invitation {invitation_id} is not accepted"
    send_acceptance_email(invitation)
    return f"Sent acceptance email for {invitation_id}"


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


@shared_task
def reevaluate_checklists_task():
    """Nightly safety net: re-run every auto-completion rule (design §9.3)
    and every readiness source (§9.3a).

    Readiness is refreshed when a gate flips and when a blocking item is
    finished, so this only catches what happens without either: a guide
    published, a slot booked, pretix configured.
    """
    changed = reevaluate_all()
    opened = refresh_for_conference()
    return (
        f"Re-evaluated checklists; {changed} item(s) changed, "
        f"{opened} item(s) changed readiness"
    )


@shared_task(
    autoretry_for=(PretixError,), retry_backoff=60, retry_jitter=True, max_retries=3
)
def sync_order_task(conference_id, code):
    """Webhook follow-up: re-fetch one order from pretix and record it.

    Retries with back-off when pretix is unavailable; the receiver already
    answered 202, so pretix is not waiting on this."""
    conference = Conference.objects.get(pk=conference_id)
    order = sync_order_by_code(conference, code)
    return f"{code}: {order.status}"


@shared_task(
    autoretry_for=(PretixError,), retry_backoff=60, retry_jitter=True, max_retries=3
)
def pretix_reconcile_task():
    """Nightly: refresh orders modified since the last run, per edition.

    Every edition is attempted; if any failed the error is re-raised at the
    end so Celery retries the task with back-off. Reconciliation is
    idempotent and ``pretix_last_synced_at`` advances only on success, so a
    retry redoes only the editions that failed."""
    results, failed = [], None
    for settings_row in SpeakerSettings.objects.select_related("conference"):
        if not settings_row.pretix_configured:
            continue
        try:
            seen = reconcile(settings_row.conference)
        except PretixError as exc:
            logger.exception(
                "Pretix reconciliation failed for %s", settings_row.conference
            )
            results.append(f"{settings_row.conference}: failed ({exc})")
            failed = exc
        else:
            results.append(f"{settings_row.conference}: {seen} order(s)")
    if failed is not None:
        raise failed
    return "; ".join(results) or "No edition has pretix configured"


@shared_task
def send_checklist_digests_task():
    """Daily: reminder digests for every edition with the module on."""
    results = []
    for settings_row in SpeakerSettings.objects.filter(
        speaker_module_enabled=True
    ).select_related("conference"):
        sent = send_checklist_digests(settings_row.conference)
        note = f" ({sent.failed} failed)" if sent.failed else ""
        results.append(f"{settings_row.conference}: {sent} email(s){note}")
    return "; ".join(results) or "No edition has the speaker module enabled"


@shared_task
def send_checklist_change_notices_task():
    """Daily: tell people about checklist items added or changed since the
    last notice, per edition with the module on."""
    results = []
    for settings_row in SpeakerSettings.objects.filter(
        speaker_module_enabled=True
    ).select_related("conference"):
        sent = send_checklist_change_notices(settings_row.conference)
        note = f"{settings_row.conference}: {sent} email(s)"
        if sent.failed:
            note += f" ({sent.failed} failed)"
        results.append(note)
    return "; ".join(results) or "No edition has the speaker module enabled"


@shared_task
def send_proposal_received_email_task(proposal_id):
    """Receipt to the proposer and a nudge to the organizers."""
    proposal = _proposal(proposal_id)
    if proposal is None:
        return f"Proposal {proposal_id} not found"
    sent = send_proposal_received_email(proposal)
    return f"Sent proposal receipt and notice to {sent} recipient(s)"


@shared_task
def send_proposal_approved_email_task(proposal_id):
    proposal = _proposal(proposal_id, decision=ProposalDecision.APPROVED)
    if proposal is None:
        return f"Proposal {proposal_id} is not approved"
    send_proposal_approved_email(proposal)
    return f"Sent proposal approval for {proposal_id}"


@shared_task
def send_proposal_rejected_email_task(proposal_id):
    proposal = _proposal(proposal_id, decision=ProposalDecision.REJECTED)
    if proposal is None:
        return f"Proposal {proposal_id} is not rejected"
    send_proposal_rejected_email(proposal)
    return f"Sent proposal answer for {proposal_id}"


@shared_task
def send_session_created_email_task(session_id):
    """Tell the organizing side that a speaker added a session."""
    session = (
        Session.objects.filter(pk=session_id)
        .select_related("conference", "kind")
        .first()
    )
    link = (
        SessionPresenter.objects.filter(session_id=session_id)
        .select_related("presenter", "presenter__liaison")
        .order_by("order", "id")
        .first()
    )
    if session is None or link is None:
        return f"Session {session_id} has nobody on it"
    sent = send_session_created_email(session, link.presenter)
    return f"Told {sent} organizer(s) about {session_id}"


def _proposal(proposal_id, decision=None):
    proposals = Proposal.objects.filter(pk=proposal_id).select_related(
        "presenter", "session", "session__kind", "conference"
    )
    if decision is not None:
        proposals = proposals.filter(decision=decision)
    return proposals.first()
