"""Read-side predicates for the speaker module.

Organizer access follows the portal-wide convention (``AdminRequiredMixin`` in
``common/mixins.py``): superusers and staff are organizers. Liaison access is
an object-level check on the data model (``Presenter.liaison``), which is
the same shape as ``TeamLeadRequiredMixin`` looking at ``team.team_leads``.
"""

from .models import Presenter


def is_speaker_organizer(user):
    """Whether ``user`` may run the program: add sessions, invite, schedule."""
    return bool(user.is_authenticated and (user.is_superuser or user.is_staff))


def is_speaker_liaison(user, conference):
    """Whether ``user`` looks after at least one presenter in ``conference``."""
    if not user.is_authenticated or conference is None:
        return False
    return Presenter.objects.filter(conference=conference, liaison=user).exists()


def can_work_sessions(user, conference):
    """Organizer or liaison: may open the organizer side of the module."""
    return is_speaker_organizer(user) or is_speaker_liaison(user, conference)
