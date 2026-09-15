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

from .constants import SessionStatus
from .emails import INVITATION_SALT
from .models import ActivityLog, Invitation, InvitationStatus, TransitionError
from .signals import invitation_accepted
from .tasks import send_invitation_email_task


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


def confirm_session_if_ready(session, actor=None):
    """Advance a DRAFT/INVITED session once every required presenter accepted."""
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
