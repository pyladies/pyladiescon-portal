import re

from django.core.exceptions import ValidationError

DISCORD_USERNAME_RE = re.compile(r"^(?=.{2,32}$)(?!.*\.\.)[a-zA-Z0-9._]+$")


def validate_linked_in_pattern(value):
    """Validate that the passed in value matches the LinkedIn URL pattern.

    Support personal, school, and company urls.
    For now, just check if it starts with the linkedin url.

    Returns True if it starts with the LinkedIn URL.
    Returns False otherwise.
    """

    linkedin_pattern = r"^(https?://)?(www\.)?linkedin\.com/(in|company|school)/"
    return re.match(linkedin_pattern, value)


def validate_discord_username(value):
    """A Discord username: 2 to 32 letters, digits, periods and underscores,
    never two periods in a row. The rules the volunteer form applies, for a
    model field."""
    if DISCORD_USERNAME_RE.match(value):
        return
    if not 2 <= len(value) <= 32:
        raise ValidationError("Discord username must be between 2 and 32 characters.")
    raise ValidationError(
        "Discord username must consist of alphanumeric characters, periods, "
        "underscores, and cannot have two consecutive periods."
    )
