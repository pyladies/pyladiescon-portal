"""Invitations the portal says it sent but has no email record of.

The presenter page calls an invitation sent as soon as an organizer sends it:
``Invitation.sent_at`` is stamped by the web process when the email is
queued. The record that an email actually went out, a ``SentEmail`` row, is
written later by the worker. When a worker is killed or restarted while
holding the task, the task is lost without an error, and the two disagree for
good. This module finds those invitations (expected to have been sent, no
record that they were) and sends one again at a time.

It judges only from ``SentEmail`` rows, so it cannot see an email the
provider accepted before the process died and the row was saved; sending
again in that case is a duplicate, never a miss.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.migrations.recorder import MigrationRecorder
from django.db.models import Min
from django.utils import timezone

from common.models import SentEmail, SentEmailStatus

from .emails import INVITATION_TEMPLATE, RECORD_CLOCK_SLACK
from .models import ActivityLog, Invitation, InvitationStatus
from .services import send_invitation

logger = logging.getLogger(__name__)

# An invitation sent less than this long ago may simply still be queued. It is
# listed, but cannot be sent again, so a second click does not mail twice.
GRACE = timedelta(minutes=5)

CLOCK_SLACK = RECORD_CLOCK_SLACK

RETRIGGERED = "invitation.retriggered"

# The migration whose application marks the start of email records. Pinned by
# a test, so squashing or renaming it fails loudly instead of leaving the page
# blind.
RECORDS_MIGRATION = ("common", "0001_sent_email")

# What ``retrigger`` did.
SENT = "sent"
WAITING = "waiting"
GONE = "gone"


@dataclass(frozen=True)
class Unrecorded:
    """One invitation marked sent with no sent-email record for that send."""

    invitation: Invitation
    # What the record says when there is one: the error of a failed send.
    # Empty when there is no record at all.
    failure: str
    # Sent within ``GRACE``: most likely still on its way.
    in_flight: bool


def records_began():
    """When the portal started recording sent emails, or None.

    The moment the migration that created the table was applied, never the
    age of the oldest row that survives. The oldest row moves forward on its
    own (the nightly prune deletes old editions' records), and a deployment
    whose worker was not running at first has no early row at all; either
    would hide an invitation that was lost without a trace, which is the case
    this page exists for.
    """
    app, name = RECORDS_MIGRATION
    return MigrationRecorder.Migration.objects.filter(app=app, name=name).aggregate(
        first=Min("applied")
    )["first"]


def unrecorded_invitations(conference, now=None, only=None):
    """The invitations of ``conference`` expected to have gone out, with no
    successful record for the send, oldest first. ``only`` limits it to one
    invitation by id.

    Only invitations still waiting on an answer are listed: one that was
    opened, accepted, declined or cancelled is not missing anything, since
    the presenter plainly has the link or no longer needs it.
    """
    now = now or timezone.now()
    began = records_began()
    if began is None:
        return []
    candidates = Invitation.objects.filter(
        conference=conference,
        sent_at__gte=began,
        opened_at__isnull=True,
        accepted_at__isnull=True,
        declined_at__isnull=True,
        cancelled_at__isnull=True,
    )
    if only is not None:
        candidates = candidates.filter(pk=only)
    invitations = list(
        candidates.select_related("presenter", "session").order_by("sent_at", "id")
    )
    records = {}
    for invitation_id, sent_at, status, error in SentEmail.objects.filter(
        template=INVITATION_TEMPLATE,
        context_digest__invitation__in=[i.pk for i in invitations],
    ).values_list("context_digest__invitation", "sent_at", "status", "error"):
        records.setdefault(invitation_id, []).append((sent_at, status, error))

    unrecorded = []
    for invitation in invitations:
        since = invitation.sent_at - CLOCK_SLACK
        mine = [r for r in records.get(invitation.pk, []) if r[0] >= since]
        if any(status == SentEmailStatus.SENT for _, status, _ in mine):
            continue
        failures = sorted(r for r in mine if r[1] == SentEmailStatus.FAILED)
        failure = failures[-1][2] if failures else ""
        in_flight = not failure and now - invitation.sent_at < GRACE
        unrecorded.append(Unrecorded(invitation, failure, in_flight))
    return unrecorded


def retriggered_history(conference, limit=20):
    """The latest sends made from Maintenance, newest first."""
    return list(
        ActivityLog.objects.filter(conference=conference, action=RETRIGGERED)
        .select_related("actor")
        .order_by("-creation_date", "-id")[:limit]
    )


def retrigger(conference, invitation_id, *, actor):
    """Send one invitation again, if it is still unrecorded.

    Returns ``(outcome, invitation)``: ``SENT``; ``WAITING`` when it was sent
    in the last few minutes (most likely another click, or still queued); or
    ``GONE`` when it is no longer on the list (recorded, answered, cancelled
    or not there), with no invitation.

    The invitation's row is locked first and the list worked out after, so
    two clicks on the same row cannot both send: the second waits for the
    first, then finds the invitation freshly sent. A fresh link makes the
    earlier one stop working, so a presenter must never get two emails of
    which one is dead. The page is a hint, not an authority; nothing it
    posted is trusted beyond the id.
    """
    with transaction.atomic():
        locked = (
            Invitation.objects.select_for_update()
            .filter(pk=invitation_id, conference=conference)
            .first()
        )
        if locked is None:
            return GONE, None
        listed = unrecorded_invitations(conference, only=invitation_id)
        if not listed:
            return GONE, None
        item = listed[0]
        if item.in_flight:
            return WAITING, item.invitation
        invitation = item.invitation
        previous = invitation.sent_at
        try:
            send_invitation(invitation, actor=actor)
        except ValueError:
            # Only an acceptance since the list was read is "gone". Any other
            # ValueError is a bug and must not be reported as that.
            invitation.refresh_from_db()
            if invitation.status != InvitationStatus.ACCEPTED:
                raise
            return GONE, None
        ActivityLog.record(
            conference,
            RETRIGGERED,
            target=invitation,
            actor=actor,
            message=(
                "Sent again from Maintenance: no email record for the send of "
                f"{previous:%Y-%m-%d %H:%M} UTC"
            ),
            presenter_id=invitation.presenter_id,
            session_id=invitation.session_id,
            previous_sent_at=previous.isoformat(),
            failure=item.failure,
        )
        logger.info(
            "Retriggered invitation %s for presenter %s by user %s; "
            "the send of %s had no email record%s",
            invitation.pk,
            invitation.presenter_id,
            actor.pk,
            previous.isoformat(),
            f" (failed: {item.failure})" if item.failure else "",
        )
    return SENT, invitation
