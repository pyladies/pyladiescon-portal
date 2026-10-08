"""What the rest of the portal may ask the speaker portal.

The registry lookup lives here so that callers outside this app do not
import its models (README: "The one dependency that points outward").
"""

from django.apps import apps


def presenter_discord_username(user):
    """The Discord username this person gave as a presenter, newest edition
    first, or "" when the speaker portal is not installed or they never
    gave one."""
    if user is None or not apps.is_installed("speakers"):
        return ""
    presenters = apps.get_model("speakers", "Presenter").objects
    return (
        presenters.filter(user=user)
        .exclude(discord_username="")
        .order_by("-conference__year", "-id")
        .values_list("discord_username", flat=True)
        .first()
        or ""
    )
