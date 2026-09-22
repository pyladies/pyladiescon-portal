"""Signal receivers: checklists follow the invitation and session lifecycle.

Registered from ``SpeakersConfig.ready()``.
"""

from django.db.models import Q
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from attendee.models import PretixOrder

from .checklists import instantiate_presenter_checklist, instantiate_session_checklist
from .constants import AutoRule
from .models import (
    Handbook,
    HandbookReadReceipt,
    Invitation,
    MediaAsset,
    Presenter,
    ScheduleSlot,
    Session,
    SessionPresenter,
)
from .rules import (
    evaluate_items,
    items_for_conference,
    items_for_presenter,
    items_for_session,
)
from .signals import invitation_accepted, session_confirmed


@receiver(invitation_accepted, dispatch_uid="speakers.checklists.on_accept")
def create_presenter_checklists(sender, invitation, session_presenters, **kwargs):
    """Instantiate, then run the rules once so "invitation sent" and friends
    are already ticked the moment the checklist exists.

    Due dates anchored on the acceptance use the invitation's own timestamp,
    unless the sender passes ``accepted_at``: a session added long after a
    general acceptance starts its clock when the link is confirmed.
    """
    accepted_at = kwargs.get("accepted_at") or invitation.accepted_at
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


@receiver(post_save, sender=ScheduleSlot, dispatch_uid="speakers.rules.slot_saved")
@receiver(post_delete, sender=ScheduleSlot, dispatch_uid="speakers.rules.slot_deleted")
def slot_changed(sender, instance, **kwargs):
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


@receiver(post_save, sender=MediaAsset, dispatch_uid="speakers.rules.asset_saved")
@receiver(post_delete, sender=MediaAsset, dispatch_uid="speakers.rules.asset_deleted")
def asset_changed(sender, instance, **kwargs):
    evaluate_items(
        items_for_session(
            instance.session, [AutoRule.ASSET_EXISTS, AutoRule.VIDEO_LENGTH_OK]
        )
    )


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
