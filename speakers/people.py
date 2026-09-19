"""Who the organizer side is made of, and how to name a user.

Shared by forms, filters and template tags so the rule lives in one place.
"""

from django.contrib.auth.models import User
from django.db.models import Q

from volunteer.constants import ApplicationStatus


def user_label(user):
    """Full name, or the username when the profile has none."""
    return user.get_full_name() or user.username


def liaison_candidates(conference):
    """Who can be a liaison: staff, or an approved volunteer of the edition."""
    return (
        User.objects.filter(
            Q(is_staff=True)
            | Q(
                volunteerprofile__conference=conference,
                volunteerprofile__application_status=ApplicationStatus.APPROVED,
            )
        )
        .distinct()
        .order_by("first_name", "last_name", "username")
    )
