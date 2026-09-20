"""The one place that decides what "today" is for due dates.

Due dates are calendar dates. Organizer pages compare them against the
server's UTC date; the speaker dashboard against the presenter's own
timezone, so an item due "today" is not overdue at breakfast in Lima
because it is already tomorrow in Berlin.
"""

from django.utils import timezone


def today(tzinfo=None):
    """The current date, in ``tzinfo`` when given, else UTC."""
    now = timezone.now()
    return (now.astimezone(tzinfo) if tzinfo else now).date()
