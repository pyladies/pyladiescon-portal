"""Invitation lifecycle: send, resolve a link, accept, decline (design §8.4).

Views and admin actions call these; they never touch the email or the
account machinery directly.
"""

import re

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from common.tasks import enqueue

from .checklists import instantiate_presenter_checklist
from .constants import (
    MAX_PENDING_PROPOSALS,
    OPEN_ITEM_STATUSES,
    ChecklistScope,
    ProposalDecision,
    SessionStatus,
)
from .emails import INVITATION_SALT
from .lifecycle import confirm_session_if_ready
from .models import (
    ActivityLog,
    ChecklistItem,
    Invitation,
    InvitationStatus,
    Presenter,
    Proposal,
    SessionPresenter,
    SessionType,
    SpeakerSettings,
)
from .rules import evaluate_items
from .signals import invitation_accepted
from .tasks import (
    send_acceptance_email_task,
    send_added_to_session_email_task,
    send_invitation_email_task,
    send_proposal_approved_email_task,
    send_proposal_received_email_task,
    send_proposal_rejected_email_task,
)


class InvitationError(Exception):
    """A link that cannot be used; ``reason`` names why for the template."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def send_invitation(invitation, actor=None):
    """Issue a fresh token, queue the email, and log it.

    Marks the session INVITED when it was still a draft. An accepted
    invitation is never resent: the presenter is already confirmed.
    """
    if invitation.status == InvitationStatus.ACCEPTED:
        raise ValueError("This invitation has already been accepted.")
    with transaction.atomic():
        invitation.issue_token()
        invitation.save()
        session = invitation.session
        if session is not None and session.status == SessionStatus.DRAFT:
            session.mark_invited()
        ActivityLog.record(
            invitation.conference,
            "invitation.sent",
            target=invitation,
            actor=actor,
            message=f"Invitation sent to {invitation.sent_to}",
            presenter_id=invitation.presenter_id,
            session_id=invitation.session_id,
        )
        # Only once the token is durably stored, so the email never carries
        # a link the database rolled back.
        transaction.on_commit(
            lambda: enqueue(send_invitation_email_task, invitation.pk)
        )


def resolve_invitation(signed, conference):
    """Turn a URL token into a usable Invitation or raise InvitationError."""
    try:
        payload = signing.loads(
            signed, salt=INVITATION_SALT, max_age=Invitation.TOKEN_MAX_AGE
        )
    except signing.SignatureExpired as exc:
        raise InvitationError("expired") from exc
    except signing.BadSignature as exc:
        raise InvitationError("invalid") from exc
    invitation = (
        Invitation.objects.filter(pk=payload["i"], conference=conference)
        .select_related("presenter", "session", "conference")
        .first()
    )
    if invitation is None:
        raise InvitationError("invalid")
    if invitation.token != payload["t"]:
        # A newer link was sent since this one.
        raise InvitationError("superseded")
    status = invitation.status
    if status in (InvitationStatus.SENT, InvitationStatus.OPENED):
        return invitation
    raise InvitationError(status.lower())


def _unique_username(base):
    User = get_user_model()
    local_part = base.split("@")[0].lower()
    base = re.sub(r"[^a-z0-9._-]+", ".", local_part).strip(".")[:140] or "speaker"
    candidate = base
    counter = 2
    while User.objects.filter(username=candidate).exists():
        candidate = f"{base}{counter}"
        counter += 1
    return candidate


def link_presenter_user(presenter, email=None):
    """Attach the account for ``email`` (the address the invitation went
    to), creating one if needed.

    The token proves control of that address, so only an *active* account
    that has already *verified* it may be linked. An unverified claim on another
    account (someone signed up with the address but never confirmed it) is
    dropped, exactly as allauth's own confirmation does under
    ``ACCOUNT_UNIQUE_EMAIL``; linking to it would hand that account, and its
    password, a verified address it never proved. A user whose ``User.email``
    merely matches is not enough either.
    """
    if presenter.user is not None:
        return presenter.user
    email = (email or presenter.email).strip().lower()
    User = get_user_model()
    verified = (
        EmailAddress.objects.filter(
            email__iexact=email, verified=True, user__is_active=True
        )
        .select_related("user")
        .first()
    )
    if verified is not None:
        user = verified.user
    else:
        # Unverified claims, and a verified one on a deactivated account (it
        # cannot sign in, and allauth allows one verified row per address),
        # are dropped so a fresh account can hold the address.
        EmailAddress.objects.filter(email__iexact=email).filter(
            Q(verified=False) | Q(user__is_active=False)
        ).delete()
        first, _, last = presenter.display_name.partition(" ")
        user = User.objects.create_user(
            username=_unique_username(email),
            email=email,
            first_name=first[:150],
            last_name=last[:150],
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])
    address, _ = EmailAddress.objects.get_or_create(
        user=user, email__iexact=email, defaults={"email": email, "primary": True}
    )
    if not address.verified:
        address.verified = True
        address.save(update_fields=["verified"])
    presenter.user = user
    presenter.save(update_fields=["user", "modified_date"])
    return user


def accept_invitation(invitation):
    """Link the account, confirm the presenter, advance the session, signal.

    Returns the user to log in. An invitation with no session (a general
    conference invitation) confirms every session the presenter is on.
    """
    presenter = invitation.presenter
    # All or nothing: a receiver of ``invitation_accepted`` that fails must
    # not leave the account linked and the session half confirmed.
    with transaction.atomic():
        user = link_presenter_user(presenter, email=invitation.sent_to)
        now = timezone.now()
        links = presenter.session_presenters.select_related("session").filter(
            confirmed_at__isnull=True
        )
        if invitation.session_id is not None:
            links = links.filter(session=invitation.session)
        confirmed_links = []
        for link in links:
            link.confirm(when=now)
            confirmed_links.append(link)
        invitation.accepted_at = now
        invitation.save(update_fields=["accepted_at", "modified_date"])
        ActivityLog.record(
            invitation.conference,
            "invitation.accepted",
            target=invitation,
            actor=user,
            presenter_id=presenter.pk,
            session_id=invitation.session_id,
        )
        # Checklists first (the receiver creates them), then the confirm
        # attempt, so required items created here already gate the session.
        invitation_accepted.send(
            sender=Invitation,
            invitation=invitation,
            presenter=presenter,
            user=user,
            session_presenters=confirmed_links,
        )
        for link in confirmed_links:
            confirm_session_if_ready(link.session)
        # On commit, not here: enqueue() publishes straight away, so a
        # worker could read the invitation before this transaction commits,
        # and a rollback would leave the welcome email already sent.
        transaction.on_commit(
            lambda: enqueue(send_acceptance_email_task, invitation.pk)
        )
    return user


def decline_invitation(invitation):
    invitation.declined_at = timezone.now()
    invitation.save(update_fields=["declined_at", "modified_date"])
    ActivityLog.record(
        invitation.conference,
        "invitation.declined",
        target=invitation,
        presenter_id=invitation.presenter_id,
        session_id=invitation.session_id,
    )


def cancel_invitation(invitation, actor=None):
    """Withdraw an open invitation so its link stops working."""
    invitation.cancelled_at = timezone.now()
    invitation.save(update_fields=["cancelled_at", "modified_date"])
    ActivityLog.record(
        invitation.conference,
        "invitation.cancelled",
        target=invitation,
        actor=actor,
        presenter_id=invitation.presenter_id,
        session_id=invitation.session_id,
    )


def has_accepted_generally(presenter):
    """Whether the presenter accepted an invitation to the conference in
    general (no session), which covers sessions they are added to later."""
    return presenter.invitations.filter(
        session__isnull=True, accepted_at__isnull=False
    ).exists()


def presenter_added_to_session(link, actor=None):
    """After a SessionPresenter row is created by an organizer.

    A presenter who already accepted a general invitation is confirmed on
    the new session straight away, gets that session's checklist and an
    email saying so, and the session's confirmation is re-tried. Returns
    whether that happened.
    """
    if link.is_confirmed or not has_accepted_generally(link.presenter):
        return False
    # All or nothing, as accept_invitation is: a receiver that fails must not
    # leave the link confirmed with half a checklist behind it.
    with transaction.atomic():
        _confirm_from_general_acceptance(link, actor)
    confirm_session_if_ready(link.session)
    return True


def _confirm_from_general_acceptance(link, actor):
    link.confirm()
    ActivityLog.record(
        link.conference,
        "session.presenter_confirmed",
        target=link.session,
        actor=actor,
        message="Confirmed from their accepted general invitation",
        presenter_id=link.presenter_id,
    )
    invitation_accepted.send(
        sender=Invitation,
        invitation=link.presenter.invitations.filter(
            session__isnull=True, accepted_at__isnull=False
        ).latest("accepted_at"),
        presenter=link.presenter,
        user=link.presenter.user,
        session_presenters=[link],
        # The clock for this session starts now, not when they accepted the
        # general invitation: anchoring to an acceptance months ago would
        # hand them a checklist born overdue and fire every reminder
        # threshold on the first digest.
        accepted_at=link.confirmed_at,
    )
    # Only once the confirmation is durably stored: a worker on another
    # connection would otherwise look for a row this transaction has not
    # committed and log the email as a legitimate skip.
    transaction.on_commit(lambda: enqueue(send_added_to_session_email_task, link.pk))


def change_presenter_role(link, role, *, is_required=None, actor=None):
    """Change a presenter's role on a session and move their checklist with it.

    Open items that came from the old role's template are dropped, blocked
    ones included: the note on a blocked item is about work this presenter
    is no longer down for. Anything done or skipped stays, so the record of
    what they did survives the change, and the new role's template is
    instantiated (for a confirmed presenter) with its rules run once.
    Returns ``(removed, created)`` counts.
    """
    # Compare with what is stored: a bound ModelForm has usually already put
    # the new role on the instance before this is called.
    stored = (
        SessionPresenter.objects.filter(pk=link.pk)
        .values_list("role_id", "role__name")
        .first()
    )
    old_role_id, old_role_name = stored or (None, "")
    with transaction.atomic():
        return _swap_role(link, role, old_role_id, old_role_name, is_required, actor)


def _swap_role(link, role, old_role_id, old_role_name, is_required, actor):
    link.role = role
    if is_required is not None:
        link.is_required = is_required
    link.save()
    removed = created = 0
    if old_role_id != role.pk:
        from_old_role = ChecklistItem.objects.filter(
            presenter=link.presenter,
            status__in=list(OPEN_ITEM_STATUSES),
            template_item__template__scope=ChecklistScope.PRESENTER,
            template_item__template__role_id=old_role_id,
        )
        removed, _ = from_old_role.filter(session=link.session).delete()
        # A once-per-presenter line of the old role (its guide, say) hangs
        # off no session, so it only goes when they have stopped holding
        # that role anywhere in the edition.
        still_holds = (
            link.presenter.session_presenters.filter(role_id=old_role_id)
            .exclude(pk=link.pk)
            .exists()
        )
        if not still_holds:
            dropped, _ = from_old_role.filter(
                session__isnull=True, template_item__once_per_presenter=True
            ).delete()
            removed += dropped
        if link.is_confirmed:
            new_items = instantiate_presenter_checklist(link)
            evaluate_items(new_items)
            created = len(new_items)
        ActivityLog.record(
            link.conference,
            "session.presenter_role_changed",
            target=link.session,
            actor=actor,
            message=(
                f"{link.presenter.display_name}: " f"{old_role_name} is now {role.name}"
            ),
            presenter_id=link.presenter_id,
            removed_items=removed,
            created_items=created,
        )
    return removed, created


# ---- Proposals: people asking to give a session -----------------------------


class ProposalError(ValueError):
    """A proposal that may not be made, changed or decided."""


def proposals_open(conference):
    """Whether this edition is taking proposals at all."""
    settings_row = SpeakerSettings.objects.filter(conference=conference).first()
    return bool(settings_row and settings_row.proposals_open)


def proposable_types(conference):
    """The session types someone may propose or add themselves."""
    return SessionType.objects.filter(
        conference=conference, is_active=True, open_for_proposals=True
    ).order_by("sort_order", "name")


def pending_proposals(presenter):
    return presenter.proposals.filter(decision=ProposalDecision.PENDING)


def _refuse_when_full(presenter, closing):
    """The three-pending cap, counted with the proposer's row locked.

    Two posts a moment apart would otherwise each read two pending and
    each write a third. Nothing in the database backs the cap, so the lock
    is what makes it one answer at a time per person.
    """
    Presenter.objects.select_for_update().filter(pk=presenter.pk).first()
    if pending_proposals(presenter).count() >= MAX_PENDING_PROPOSALS:
        raise ProposalError(
            f"You already have {MAX_PENDING_PROPOSALS} proposals waiting for "
            f"an answer. {closing}"
        )


def submit_proposal(presenter, session, actor=None):
    """Record a proposal for a session that was just created.

    The session, the presenter and the link are real rows from the start:
    the session sits in ``PROPOSED``, which keeps it off the schedule, the
    public side and every speaker page, and the proposal carries the
    review. Approving is then the same path an accepted invitation takes.
    """
    with transaction.atomic():
        _refuse_when_full(presenter, "Withdraw one to send another.")
        # The session becomes a proposal here, so every caller gets it:
        # a session left in DRAFT would sit on the organizers' program
        # list as though they had made it.
        session.propose()
        proposal = Proposal.objects.create(
            conference=session.conference, session=session, presenter=presenter
        )
        ActivityLog.record(
            session.conference,
            "proposal.submitted",
            target=session,
            actor=actor,
            message=session.title,
            presenter_id=presenter.pk,
            proposal_id=proposal.pk,
        )
        transaction.on_commit(
            lambda: enqueue(send_proposal_received_email_task, proposal.pk)
        )
    return proposal


def withdraw_proposal(proposal, actor=None):
    """The proposer taking it back while nobody has answered.

    The rows stay. Someone who withdraws often means "not like this"
    rather than "forget it": keeping the proposal lets them edit what
    they wrote and send it again, and it stops a mis-click destroying an
    afternoon's writing. The session stays in ``PROPOSED``, so it is on
    nobody's program, and the organizers' queue leaves it out.
    """
    if not proposal.is_pending:
        raise ProposalError("That proposal has already been answered.")
    with transaction.atomic():
        proposal.decide(ProposalDecision.WITHDRAWN, actor=actor)
        ActivityLog.record(
            proposal.conference,
            "proposal.withdrawn",
            target=proposal.presenter,
            actor=actor,
            message=proposal.session.title,
            presenter_id=proposal.presenter_id,
            proposal_id=proposal.pk,
        )
    return proposal


def resubmit_proposal(proposal, actor=None):
    """Send a withdrawn proposal back for an answer.

    It counts as a new arrival: the submitted date moves, the cap applies
    again, and the organizers hear about it the way they do for any
    proposal.
    """
    if not proposal.is_withdrawn:
        raise ProposalError("Only a withdrawn proposal can be sent again.")
    presenter = proposal.presenter
    with transaction.atomic():
        _refuse_when_full(presenter, "Withdraw one to send this again.")
        proposal.decision = ProposalDecision.PENDING
        proposal.decided_at = None
        proposal.decided_by = None
        proposal.submitted_at = timezone.now()
        proposal.save(
            update_fields=[
                "decision",
                "decided_at",
                "decided_by",
                "submitted_at",
                "modified_date",
            ]
        )
        ActivityLog.record(
            proposal.conference,
            "proposal.resubmitted",
            target=proposal.session,
            actor=actor,
            message=proposal.session.title,
            presenter_id=presenter.pk,
            proposal_id=proposal.pk,
        )
        transaction.on_commit(
            lambda: enqueue(send_proposal_received_email_task, proposal.pk)
        )
    return proposal


def approve_proposal(proposal, actor=None):
    """Yes: the session becomes an ordinary draft and the proposer a speaker.

    Everything after the status change is the acceptance path an invitation
    takes, with the approval standing in for the acceptance: the link is
    confirmed, the checklists are created and anchored at this moment, and
    the session confirms itself when nothing blocks it.

    One already turned down can be approved later. Slots open up when
    something is cancelled, and "not this time" should not mean the
    organizers have to ask the person to send it all again.
    """
    if not proposal.can_be_approved:
        raise ProposalError("That proposal cannot be approved as it stands.")
    presenter = proposal.presenter
    session = proposal.session
    was_rejected = proposal.is_rejected
    with transaction.atomic():
        session.approve()
        proposal.decide(ProposalDecision.APPROVED, actor=actor)
        link = session.session_presenters.get(presenter=presenter)
        link.confirm(when=proposal.decided_at)
        ActivityLog.record(
            proposal.conference,
            "proposal.reconsidered" if was_rejected else "proposal.approved",
            target=session,
            actor=actor,
            message=session.title,
            presenter_id=presenter.pk,
            proposal_id=proposal.pk,
        )
        # The same receiver an accepted invitation uses, so the checklists
        # are the ones a speaker always gets, anchored at the approval
        # rather than at some earlier moment.
        invitation_accepted.send(
            sender=Proposal,
            invitation=None,
            presenter=presenter,
            user=presenter.user,
            session_presenters=[link],
            accepted_at=proposal.decided_at,
        )
        confirm_session_if_ready(session)
        transaction.on_commit(
            lambda: enqueue(send_proposal_approved_email_task, proposal.pk)
        )
    return proposal


def reject_proposal(proposal, actor=None):
    """No, kindly and without a reason: the answer the user asked for.

    The rows stay. The proposer can still read what they sent, and the
    organizers have a record of an answer given.
    """
    if not proposal.is_pending:
        raise ProposalError("That proposal has already been answered.")
    with transaction.atomic():
        proposal.session.reject()
        proposal.decide(ProposalDecision.REJECTED, actor=actor)
        ActivityLog.record(
            proposal.conference,
            "proposal.rejected",
            target=proposal.session,
            actor=actor,
            message=proposal.session.title,
            presenter_id=proposal.presenter_id,
            proposal_id=proposal.pk,
        )
        transaction.on_commit(
            lambda: enqueue(send_proposal_rejected_email_task, proposal.pk)
        )
    return proposal
