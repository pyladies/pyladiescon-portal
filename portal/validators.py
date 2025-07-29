import re


def validate_linked_in_pattern(value):
    """Validate that the passed in value matches the LinkedIn URL pattern.

    Support personal, school, and company urls.
    For now, just check if it starts with the linkedin url.

    Returns True if it starts with the LinkedIn URL.
    Returns False otherwise.
    """

    linkedin_pattern = r"^(https?://)?(www\.)?linkedin\.com/(in|company|school)/"
    return re.match(linkedin_pattern, value)
