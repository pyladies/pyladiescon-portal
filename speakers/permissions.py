"""Read-side predicates for the speaker module.

Organizer access follows the portal-wide convention (``AdminRequiredMixin`` in
``common/mixins.py``): superusers and staff are organizers. Liaison and
presenter access are object-level checks on the data model and arrive with
the models that carry them (Stage 1).
"""


def is_speaker_organizer(user):
    """Whether ``user`` may run the program: add sessions, invite, schedule."""
    return bool(user.is_authenticated and (user.is_superuser or user.is_staff))
