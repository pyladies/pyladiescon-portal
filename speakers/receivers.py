"""Signal receivers: checklists follow the invitation and session lifecycle.

Registered from ``SpeakersConfig.ready()``.
"""

import logging

from botocore.exceptions import ClientError
from django.db import connection, transaction
from django.db.models import Q
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from attendee.models import PretixOrder
from volunteer.models import VolunteerProfile

from .api import invalidate as invalidate_public_api
from .checklists import (
    instantiate_general_checklist,
    instantiate_presenter_checklist,
    instantiate_session_checklist,
)
from .constants import VIDEO_KINDS, AutoRule
from .media import MediaBucket, MediaStorageNotConfigured, uploading_presenter
from .models import (
    ChecklistItem,
    Handbook,
    HandbookReadReceipt,
    Invitation,
    MediaAsset,
    MediaUpload,
    Presenter,
    PresenterRole,
    PublishedSlot,
    Room,
    Session,
    SessionPresenter,
    SessionType,
    SpeakerSettings,
)
from .readiness import refresh_readiness
from .rules import (
    evaluate_items,
    items_for_conference,
    items_for_presenter,
    items_for_session,
)
from .signals import asset_ready, invitation_accepted, session_confirmed
from .transcription import should_transcribe, start_job

logger = logging.getLogger(__name__)


@receiver(invitation_accepted, dispatch_uid="speakers.checklists.on_accept")
def create_presenter_checklists(
    sender, invitation, session_presenters, presenter=None, **kwargs
):
    """Instantiate, then run the rules once so "invitation sent" and friends
    are already ticked the moment the checklist exists.

    Due dates anchored on the acceptance use the invitation's own timestamp,
    unless the sender passes ``accepted_at``: a session added long after a
    general acceptance starts its clock when the link is confirmed.

    An approved proposal sends this with ``invitation=None``, because
    nobody invited them: the approval is the acceptance, and it passes both
    the presenter and the moment.
    """
    presenter = presenter or invitation.presenter
    accepted_at = kwargs.get("accepted_at") or (
        invitation.accepted_at if invitation is not None else None
    )
    evaluate_items(instantiate_general_checklist(presenter, accepted_at=accepted_at))
    for link in session_presenters:
        created = instantiate_presenter_checklist(link, accepted_at=accepted_at)
        evaluate_items(created)


@receiver(session_confirmed, dispatch_uid="speakers.checklists.on_confirm")
def create_session_checklist(sender, session, **kwargs):
    evaluate_items(instantiate_session_checklist(session))


# ---- Rule re-evaluation: the record a rule looks at changed -----------------
#
# A save with ``update_fields`` that touches none of the fields a rule reads
# (the engine's own ``status`` saves, for one) is skipped outright, so the
# receivers cost nothing on the saves they cause themselves.


def _touches(kwargs, *fields):
    update_fields = kwargs.get("update_fields")
    return update_fields is None or not set(fields).isdisjoint(update_fields)


@receiver(post_save, sender=VolunteerProfile, dispatch_uid="speakers.discord.follow")
def follow_volunteer_discord(sender, instance, **kwargs):
    """The volunteer profile is where a volunteer who also speaks keeps
    their Discord username (it is required there); their presenter rows
    follow it, so the organizer side never shows a stale one."""
    if not instance.discord_username:
        return
    for presenter in Presenter.objects.filter(user=instance.user_id).exclude(
        discord_username=instance.discord_username
    ):
        presenter.discord_username = instance.discord_username
        presenter.save(update_fields=["discord_username", "modified_date"])


@receiver(post_save, sender=Presenter, dispatch_uid="speakers.rules.presenter")
def presenter_changed(sender, instance, **kwargs):
    if not _touches(
        kwargs, "bio_md", "headshot", "email", "pretix_order", "pretix_order_id"
    ):
        return
    evaluate_items(
        items_for_presenter(
            instance, [AutoRule.BIO_AND_HEADSHOT, AutoRule.PRETIX_REGISTERED]
        )
    )


@receiver(post_save, sender=Invitation, dispatch_uid="speakers.rules.invitation")
def invitation_changed(sender, instance, **kwargs):
    if not _touches(kwargs, "sent_at", "accepted_at"):
        return
    evaluate_items(
        items_for_presenter(
            instance.presenter, [AutoRule.INVITATION_SENT, AutoRule.INVITATION_ACCEPTED]
        )
    )


@receiver(post_save, sender=SessionPresenter, dispatch_uid="speakers.rules.link")
def session_presenter_changed(sender, instance, **kwargs):
    if not _touches(kwargs, "confirmed_at"):
        return
    evaluate_items(
        items_for_presenter(instance.presenter, [AutoRule.INVITATION_ACCEPTED])
    )


@receiver(post_save, sender=PublishedSlot, dispatch_uid="speakers.rules.slot_saved")
@receiver(post_delete, sender=PublishedSlot, dispatch_uid="speakers.rules.slot_deleted")
def published_slot_changed(sender, instance, **kwargs):
    """Publishing the schedule is what schedules a session (§10.1)."""
    evaluate_items(items_for_session(instance.session, [AutoRule.SESSION_SCHEDULED]))


@receiver(post_save, sender=Session, dispatch_uid="speakers.rules.session")
def session_changed(sender, instance, **kwargs):
    if not _touches(
        kwargs, "youtube_url", "youtube_publish_at", "video_length_limit_minutes"
    ):
        return
    evaluate_items(
        items_for_session(
            instance, [AutoRule.YOUTUBE_PUBLISHED, AutoRule.VIDEO_LENGTH_OK]
        )
    )


def _asset_moved(session):
    """A file arrived, changed or went: the items that wait for one and the
    length check are answered, and the items that cannot start until a file
    is in (the performer's final-cut approval) are re-read."""
    evaluate_items(
        items_for_session(
            session,
            [AutoRule.ASSET_EXISTS, AutoRule.ASSET_SHARED, AutoRule.VIDEO_LENGTH_OK],
        )
    )
    refresh_readiness(ChecklistItem.objects.filter(session=session))


@receiver(post_save, sender=MediaAsset, dispatch_uid="speakers.rules.asset_saved")
@receiver(post_delete, sender=MediaAsset, dispatch_uid="speakers.rules.asset_deleted")
def asset_changed(sender, instance, **kwargs):
    _asset_moved(instance.session)


@receiver(post_save, sender=HandbookReadReceipt, dispatch_uid="speakers.rules.receipt")
def receipt_changed(sender, instance, **kwargs):
    evaluate_items(items_for_presenter(instance.presenter, [AutoRule.HANDBOOK_READ]))


@receiver(post_save, sender=Handbook, dispatch_uid="speakers.rules.handbook")
def handbook_changed(sender, instance, **kwargs):
    """Sweeps the edition: a new guide version reopens everyone's "read the
    guide" item. Guides are published a handful of times a year."""
    if not _touches(kwargs, "published_at", "version"):
        return
    evaluate_items(items_for_conference(instance.conference, [AutoRule.HANDBOOK_READ]))


def _order_emails(order):
    """The buyer email and every attendee email on the order, lower-cased."""
    emails = {order.email or ""}
    positions = (order.raw_data or {}).get("positions") or []
    emails.update(str(pos.get("attendee_email") or "") for pos in positions)
    return {email.strip().lower() for email in emails if email and email.strip()}


@receiver(post_save, sender=PretixOrder, dispatch_uid="speakers.rules.pretix")
def pretix_order_changed(sender, instance, **kwargs):
    """Only the presenters this order can be about: linked to it by hand, or
    sharing one of its emails. Ticket sales save orders in bursts, inside
    the webhook request; the nightly task does the broad sweep."""
    if not _touches(kwargs, "status", "email", "raw_data"):
        return
    presenters = Presenter.objects.filter(conference_id=instance.conference_id).filter(
        Q(pretix_order=instance) | Q(email__in=_order_emails(instance))
    )
    evaluate_items(
        items_for_conference(instance.conference, [AutoRule.PRETIX_REGISTERED]).filter(
            presenter__in=presenters
        )
    )


@receiver(asset_ready, dispatch_uid="speakers.rules.asset_ready")
def on_asset_ready(sender, asset, **kwargs):
    """A file arrived: the items that wait for one, and the length check,
    are answered now rather than at the nightly pass. A video is also
    measured, once the row is committed, by the media worker."""
    _asset_moved(asset.session)
    if asset.kind in VIDEO_KINDS:
        from .tasks import probe_asset_task

        transaction.on_commit(lambda: probe_asset_task.delay(asset.pk))
    if asset.preview_kind in ("image", "video"):
        from .tasks import make_thumbnail_task

        transaction.on_commit(lambda: make_thumbnail_task.delay(asset.pk))
    # A raw video gets a draft transcript when the edition asked for one
    # and no reviewed transcript is in the way (transcription.py).
    if should_transcribe(asset):
        start_job(asset)
    # A speaker's own upload is news to their liaison, or to the team
    # (design §13.2); sent once the row is committed. Checked here so the
    # team's uploads and a job's outputs queue nothing, and again in the
    # task, which re-reads the row because it may have changed since.
    if uploading_presenter(asset) is not None:
        from .tasks import send_upload_notice_task

        transaction.on_commit(lambda: send_upload_notice_task.delay(asset.pk))


def _drop_objects(pk, keys, attached):
    """Remove a deleted asset's files: its bucket objects (the upload and
    the thumbnail beside it) and an admin-attached file in the default
    storage. Storage that cannot be reached is logged, not raised."""
    if attached is not None:
        try:
            attached.storage.delete(attached.name)
        except OSError as exc:
            logger.error("Deleted asset %s leaves %s in storage: %s", pk, attached, exc)
    if not keys:
        return
    try:
        bucket = MediaBucket.from_settings()
        for key in keys:
            bucket.delete(key)
    except (MediaStorageNotConfigured, ClientError) as exc:
        logger.error("Deleted asset %s leaves %s in the bucket: %s", pk, keys, exc)


@receiver(post_delete, sender=MediaAsset, dispatch_uid="speakers.media.on_delete")
def drop_the_object(sender, instance, **kwargs):
    """A deleted row takes its files with it: the object, the thumbnail
    made next to it, and an admin-attached file; otherwise the bucket
    keeps a file nothing can reach again. Fires for every row of a line
    someone deletes on the page and for each row the admin's session
    delete cascades through. Superseded versions keep theirs for as long
    as their rows last: they are the history the pages show.

    The files go once the transaction commits (or at once, outside one):
    a deletion rolled back after the bucket had already answered would
    restore a row whose file is gone, with its download link on the page.
    """
    keys = [key for key in (instance.storage_key, instance.thumbnail_key) if key]
    attached = instance.file if instance.file else None
    if not keys and attached is None:
        return
    # Read now: the collector blanks the pk once the signals have run.
    pk = instance.pk
    transaction.on_commit(lambda: _drop_objects(pk, keys, attached))


def _abort_upload(pk, key, upload_id):
    try:
        MediaBucket.from_settings().abort(key, upload_id)
    except (MediaStorageNotConfigured, ClientError) as exc:
        logger.error(
            "Upload %s of deleted row %s stays open in the bucket: %s",
            upload_id,
            pk,
            exc,
        )


@receiver(post_delete, sender=MediaUpload, dispatch_uid="speakers.media.abort_upload")
def abort_the_upload(sender, instance, **kwargs):
    """An upload still in flight when its row goes (the admin deleted the
    session under it) is aborted in the bucket once the deletion commits,
    so the parts it received are freed now rather than when the lifecycle
    rule gets to them."""
    if not instance.is_open:
        return
    pk, key, upload_id = instance.pk, instance.storage_key, instance.upload_id
    transaction.on_commit(lambda: _abort_upload(pk, key, upload_id))


def public_api_changed(sender, instance, **kwargs):
    """Anything a public payload reads changed: the edition's cached API
    responses go (design §11.1), once, after the transaction commits, so a
    request racing the save cannot re-cache what was there before it."""
    conference_id = instance.conference_id
    # One bump per edition per transaction: a schedule publish saves a row
    # per moved session, and each must not add cache queries. Callbacks of
    # a rolled-back transaction or savepoint are dropped by Django, so this
    # check never skips a bump that is still owed.
    pending = connection.run_on_commit
    if any(
        getattr(entry[1], "public_api_for", None) == conference_id for entry in pending
    ):
        return

    def bump():
        invalidate_public_api(conference_id)

    bump.public_api_for = conference_id
    transaction.on_commit(bump)


# AllowedOrigin is left out on purpose: the CORS header is computed per
# request, never cached, so a change to the list needs no invalidation.
for _model in (
    Session,
    Presenter,
    SessionPresenter,
    PublishedSlot,
    Room,
    SessionType,
    PresenterRole,
    SpeakerSettings,
):
    for _signal in (post_save, post_delete):
        _signal.connect(
            public_api_changed,
            sender=_model,
            dispatch_uid=f"speakers.public_api.{_model.__name__}.{_signal is post_save}",
        )
