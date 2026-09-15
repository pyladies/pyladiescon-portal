"""Signal receivers: checklists follow the invitation and session lifecycle.

Registered from ``SpeakersConfig.ready()``.
"""

from django.dispatch import receiver

from .checklists import instantiate_presenter_checklist, instantiate_session_checklist
from .signals import invitation_accepted, session_confirmed


@receiver(invitation_accepted, dispatch_uid="speakers.checklists.on_accept")
def create_presenter_checklists(sender, invitation, session_presenters, **kwargs):
    for link in session_presenters:
        instantiate_presenter_checklist(link, accepted_at=invitation.accepted_at)


@receiver(session_confirmed, dispatch_uid="speakers.checklists.on_confirm")
def create_session_checklist(sender, session, **kwargs):
    instantiate_session_checklist(session)
