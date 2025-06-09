import re

from django.core.exceptions import ValidationError


def validate_linked_in_pattern(value):
    """Validate that the passed in value matches the LinkedIn URL pattern.

    Support personal, school, and company urls.
    For now, just check if it starts with the linkedin url.
    """

    linkedin_pattern = r"^(https?://)?(www\.)?linkedin\.com/(in|company|school)/"
    return re.match(linkedin_pattern, value)
