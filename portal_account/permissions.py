"""Read-side predicates for portal account capabilities.

Groups only hand permissions out; every check goes through ``has_perm`` so a
permission granted directly on a user, or to a superuser, counts too.
"""

MAINTENANCE_PERMISSION = "portal_account.view_maintenance"
MAINTAINERS_GROUP = "Infra maintainers"


def is_maintainer(user):
    """Whether ``user`` may open the Maintenance section."""
    return user.has_perm(MAINTENANCE_PERMISSION)
