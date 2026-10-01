"""Invitations the portal says it sent but has no email record of.

The presenter page calls an invitation sent as soon as an organizer sends it:
``Invitation.sent_at`` is stamped by the web process when the email is
queued. The record that an email actually went out, a ``SentEmail`` row, is
written later by the worker. When a worker is killed or restarted while
holding the task, the task is lost without an error, and the two disagree for
good. This module finds those invitations (expected to have been sent, no
record that they were) and sends them again.

It judges only from ``SentEmail`` rows, so it cannot see an email the
provider accepted before the process died and the row was saved; sending
again in that case is a duplicate, never a miss.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Min
from django.utils import timezone

from common.models import SentEmail, SentEmailStatus

from .emails import INVITATION_TEMPLATE
from .models import ActivityLog, Invitation
from .services import send_invitation

logger = logging.getLogger(__name__)

# An invitation sent less than this long ago may simply still be queued. It is
# listed, but cannot be sent again, so a second click does not mail twice.
GRACE = timedelta(minutes=5)

# The web and the worker keep their own clocks.
CLOCK_SLACK = timedelta(minutes=1)

RETRIGGERED = "invitation.retriggered"


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
    """When the first sent-email record was written, or None.

    An invitation sent before records existed cannot be judged by them, so
    nothing older than this is listed.
    """
    return SentEmail.objects.aggregate(first=Min("sent_at"))["first"]


def unrecorded_invitations(conference, now=None):
    """The invitations of ``conference`` expected to have gone out, with no
    successful record for the send, oldest first.

    Only invitations still waiting on an answer are listed: one that was
    opened, accepted, declined or cancelled is not missing anything, since
    the presenter plainly has the link or no longer needs it.
    """
    now = now or timezone.now()
    began = records_began()
    if began is None:
        return []
    invitations = list(
        Invitation.objects.filter(
            conference=conference,
            sent_at__gte=began,
            opened_at__isnull=True,
            accepted_at__isnull=True,
            declined_at__isnull=True,
            cancelled_at__isnull=True,
        )
        .select_related("presenter", "session")
        .order_by("sent_at", "id")
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


def retrigger(conference, invitation_ids, *, actor, everything=False):
    """Send again the listed invitations that are still unrecorded.

    The list is worked out again here, not trusted from the page: one that
    was recorded, answered or sent a moment ago is skipped. Each goes through
    ``send_invitation``, as an organizer's resend does, so it gets a fresh
    link (the earlier one stops working) and a fresh expiry. Returns
    ``(sent, skipped)`` counts.
    """
    listed = unrecorded_invitations(conference)
    wanted = (
        {item.invitation.pk for item in listed} if everything else set(invitation_ids)
    )
    sent = 0
    skipped = len(wanted - {item.invitation.pk for item in listed})
    for item in listed:
        if item.invitation.pk not in wanted:
            continue
        if item.in_flight:
            skipped += 1
            continue
        invitation = item.invitation
        previous = invitation.sent_at
        send_invitation(invitation, actor=actor)
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
        sent += 1
    return sent, skipped
