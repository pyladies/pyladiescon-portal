"""Who the organizer side is made of, and how to name a user.

Shared by forms, filters and template tags so the rule lives in one place.
"""

from django.contrib.auth.models import User
from django.db.models import Q

from volunteer.constants import ApplicationStatus


def user_label(user):
    """Full name, or the username when the profile has none."""
    return user.get_full_name() or user.username


def organizer_side_candidates(conference):
    """Who can be a liaison or take an organizer item: any active staff or
    superuser account, and every approved volunteer of the edition (pending
    or waitlisted volunteers are not offered until they are onboarded)."""
    return (
        User.objects.filter(
            Q(is_staff=True)
            | Q(is_superuser=True)
            | Q(
                volunteerprofile__conference=conference,
                volunteerprofile__application_status=ApplicationStatus.APPROVED,
            ),
            is_active=True,
        )
        .distinct()
        .order_by("first_name", "last_name", "username")
    )


# Both roles draw on the same people; the wrappers let each call site say
# which one it means.


def liaison_candidates(conference):
    """Who may be set as a presenter's liaison."""
    return organizer_side_candidates(conference)


def assignee_candidates(conference):
    """Who an organizer item may be handed to."""
    return organizer_side_candidates(conference)
