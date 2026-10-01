import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from common.send_emails import send_email
from portal.models import Conference

from .constants import ProposalDecision, ZipStatus
from .emails import (
    send_acceptance_email,
    send_added_to_session_email,
    send_copresenter_suggestion_email,
    send_invitation_email,
    send_proposal_approved_email,
    send_proposal_received_email,
    send_proposal_rejected_email,
)
from .exports import build_zip, expire_zips, zip_url
from .media import expire_abandoned_uploads
from .models import (
    Invitation,
    MediaAsset,
    MediaExport,
    Presenter,
    Proposal,
    Session,
    SessionPresenter,
    SpeakerSettings,
)
from .notices import send_checklist_change_notices
from .pretix import PretixError, reconcile, sync_order_by_code
from .probe import probe_asset
from .readiness import refresh_for_conference
from .reminders import send_checklist_digests
from .rules import reevaluate_all
from .thumbnails import make_thumbnail
from .transcription import fail_stale_jobs, transcribe

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


def _proposal(proposal_id, decision=None):
    proposals = Proposal.objects.filter(pk=proposal_id).select_related(
        "presenter", "session", "session__kind", "conference"
    )
    if decision is not None:
        proposals = proposals.filter(decision=decision)
    return proposals.first()


@shared_task
def expire_abandoned_uploads_task():
    """Abort multipart uploads nobody finished (design §8.8).

    Scheduled through django-celery-beat (the "Expire abandoned uploads"
    periodic task seeded by migration 0012); the bucket's lifecycle rule is
    the backstop.
    """
    count = expire_abandoned_uploads()
    return f"Expired {count} abandoned upload(s)"


@shared_task(time_limit=2 * 3600)
def build_export_zip_task(export_id):
    """Build an export's zip in the bucket and tell the person who asked
    (design §8.8, bulk download). On the media queue: a zip of a few
    hundred megabytes takes minutes. A failure is written on the export,
    where the page shows it, and logged."""
    export = (
        MediaExport.objects.select_related("conference", "created_by")
        .filter(pk=export_id)
        .first()
    )
    if export is None or export.created_by is None:
        return "No such export"
    export.zip_status = ZipStatus.RUNNING
    export.save(update_fields=["zip_status", "modified_date"])
    try:
        export.zip_key = build_zip(export, export.created_by)
    except Exception as exc:
        # Anything, an object gone from the bucket included: a zip left
        # RUNNING could never be asked for again, so every failure is
        # written on the row, where the page shows it and offers a retry.
        export.zip_status = ZipStatus.FAILED
        export.zip_error = str(exc)[:500] or exc.__class__.__name__
        export.save(update_fields=["zip_status", "zip_error", "modified_date"])
        logger.exception("Export %s zip failed", export.pk)
        return f"Export {export_id} zip failed: {exc}"
    export.zip_status = ZipStatus.DONE
    export.zip_built_at = timezone.now()
    export.zip_error = ""
    export.save(
        update_fields=[
            "zip_key",
            "zip_status",
            "zip_built_at",
            "zip_error",
            "modified_date",
        ]
    )
    link = zip_url(export)
    if export.created_by.email:
        send_email(
            f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Your {export.conference.name} "
            "file export is ready",
            [export.created_by.email],
            markdown_template="emails/speakers/export_ready.md",
            context={
                "export": export,
                "link": link,
                "expires_at": export.expires_at,
                "conference": export.conference,
                "user": export.created_by,
            },
            conference=export.conference,
            user=export.created_by,
            secrets=[link],
        )
    return f"Export {export_id} zip ready"


@shared_task(acks_late=True, time_limit=2 * 3600)
def transcribe_asset_task(job_id):
    """Run one transcription job (design §8.8) on the media queue.
    ``acks_late`` so a job a killed worker was running is delivered again,
    where the row, already RUNNING, marks itself FAILED rather than
    running twice."""
    return transcribe(job_id)


@shared_task
def expire_export_zips_task():
    """Nightly: drop the zips of exports whose links have expired (design
    §8.8, bulk download). The zip was bounded per export by
    SPEAKER_MEDIA_ZIP_MAX_BYTES; this bounds it in aggregate, since nothing
    else ever deletes one. Seeded by migration 0015."""
    count = expire_zips()
    return f"Dropped {count} expired export zip(s)"


@shared_task
def fail_stale_transcription_jobs_task():
    """Nightly: jobs nobody picked up say so on the page."""
    count = fail_stale_jobs()
    return f"Failed {count} stale transcription job(s)"


@shared_task(time_limit=600)
def make_thumbnail_task(asset_id):
    """A small image for a file that just landed (design §8.8, task 5.8),
    on the media queue beside the probe."""
    asset = MediaAsset.objects.filter(pk=asset_id).first()
    if asset is None:
        return "No such asset"
    key = make_thumbnail(asset)
    if key is None:
        return f"No thumbnail for asset {asset_id}: {asset.thumbnail_error}"
    return f"Thumbnail for asset {asset_id} at {key}"


# How many times a video is probed before its failure stands, and the
# wait before each try again: two minutes, then four.
PROBE_ATTEMPTS = 3
PROBE_RETRY_SECONDS = 120


@shared_task
def probe_asset_task(asset_id, attempt=1):
    """Measure a video that just landed (design §8.8, task 5.3).

    Routed to the ``media`` queue (settings ``CELERY_TASK_ROUTES``), served
    by the ``worker-media`` process, so a probe over a slow link never
    holds up an email. Saving the duration re-runs the length rule.

    A probe that fails is queued again, ``PROBE_ATTEMPTS`` tries in all a
    few minutes apart, before the failure stands on the asset: a dropped
    connection to the bucket should not hold a checklist item until
    someone uploads the file again. ``manage.py probe_media`` re-queues
    the ones that stood.
    """
    asset = MediaAsset.objects.filter(pk=asset_id).first()
    if asset is None:
        return "No such asset"
    duration = probe_asset(asset)
    if duration is None:
        message = f"Probe failed for asset {asset_id}: {asset.probe_error}"
        if attempt < PROBE_ATTEMPTS:
            probe_asset_task.apply_async(
                args=(asset_id, attempt + 1),
                countdown=PROBE_RETRY_SECONDS * attempt,
            )
            return f"{message}; try {attempt + 1} of {PROBE_ATTEMPTS} queued"
        return message
    return f"Asset {asset_id} runs {duration} s"
