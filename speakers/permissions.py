"""Read-side predicates for the speaker module.

Organizer access follows the portal-wide convention (``AdminRequiredMixin`` in
``common/mixins.py``): superusers and staff are organizers. Liaison access is
an object-level check on the data model (``Presenter.liaison``), which is
the same shape as ``TeamLeadRequiredMixin`` looking at ``team.team_leads``.
"""

from .constants import ItemOwner
from .models import ChecklistItem, Presenter


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


def is_speaker_assignee(user, conference):
    """Whether ``user`` carries an open organizer item in this edition.

    Organizer items are assigned to any approved volunteer, not only to
    liaisons (``people.organizer_side_candidates``), so carrying one is its
    own reason to reach the queue and tick the item off. It is an
    object-level check on the data, like the liaison one: the assignment is
    the grant.

    Any assigned item counts, not only an open one: ticking off the last
    one would otherwise 403 the very page the volunteer is standing on, and
    they still need the queue to reopen something they closed too early.
    """
    if not user.is_authenticated or conference is None:
        return False
    return ChecklistItem.objects.filter(
        conference=conference,
        owner=ItemOwner.ORGANIZER,
        assignee=user,
    ).exists()


def can_work_queue(user, conference):
    """Who may open the queue and act on an item: organizers, liaisons, and
    whoever an organizer item was handed to."""
    return can_work_sessions(user, conference) or is_speaker_assignee(user, conference)
