"""Signal receivers: checklists follow the invitation and session lifecycle.

Registered from ``SpeakersConfig.ready()``.
"""

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
    are already ticked the moment the checklist exists."""
    for link in session_presenters:
        created = instantiate_presenter_checklist(
            link, accepted_at=invitation.accepted_at
        )
        evaluate_items(created)


@receiver(session_confirmed, dispatch_uid="speakers.checklists.on_confirm")
def create_session_checklist(sender, session, **kwargs):
    evaluate_items(instantiate_session_checklist(session))


# ---- Rule re-evaluation: the record a rule looks at changed -----------------


@receiver(post_save, sender=Presenter, dispatch_uid="speakers.rules.presenter")
def presenter_changed(sender, instance, **kwargs):
    evaluate_items(
        items_for_presenter(
            instance, [AutoRule.BIO_AND_HEADSHOT, AutoRule.PRETIX_REGISTERED]
        )
    )


@receiver(post_save, sender=Invitation, dispatch_uid="speakers.rules.invitation")
def invitation_changed(sender, instance, **kwargs):
    evaluate_items(
        items_for_presenter(
            instance.presenter, [AutoRule.INVITATION_SENT, AutoRule.INVITATION_ACCEPTED]
        )
    )


@receiver(post_save, sender=SessionPresenter, dispatch_uid="speakers.rules.link")
def session_presenter_changed(sender, instance, **kwargs):
    evaluate_items(
        items_for_presenter(instance.presenter, [AutoRule.INVITATION_ACCEPTED])
    )


@receiver(post_save, sender=ScheduleSlot, dispatch_uid="speakers.rules.slot_saved")
@receiver(post_delete, sender=ScheduleSlot, dispatch_uid="speakers.rules.slot_deleted")
def slot_changed(sender, instance, **kwargs):
    evaluate_items(items_for_session(instance.session, [AutoRule.SESSION_SCHEDULED]))


@receiver(post_save, sender=Session, dispatch_uid="speakers.rules.session")
def session_changed(sender, instance, **kwargs):
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
    evaluate_items(items_for_conference(instance.conference, [AutoRule.HANDBOOK_READ]))


@receiver(post_save, sender=PretixOrder, dispatch_uid="speakers.rules.pretix")
def pretix_order_changed(sender, instance, **kwargs):
    evaluate_items(
        items_for_conference(instance.conference, [AutoRule.PRETIX_REGISTERED])
    )
