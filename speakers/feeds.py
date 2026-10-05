"""Calendar feeds (task 4.4, design §11.3), served from the published
schedule only (§10.1): a subscribed calendar learns about a move when the
organizers publish it, through the event's SEQUENCE, and never watches
the drafting.

The ICS writer is hand-rolled, like the VTT writer: the format needed
here is a header, one VEVENT per slot, text escaping and 75-octet line
folding, which is less code than a dependency pinned into three images.
"""

from django.core import signing

from .constants import PremiereLocation, SessionStatus
from .models import PublishedSlot

FEED_SALT = "speakers.presenter-feed"

CRLF = "\r\n"


def presenter_feed_token(presenter):
    """The signed key of a presenter's personal feed URL.

    Signed, not expiring: a calendar subscription that silently dies two
    weeks before the conference is worse than a long-lived token that
    only reveals that person's own schedule.
    """
    return signing.dumps({"presenter": presenter.pk}, salt=FEED_SALT)


def presenter_from_token(token):
    """The presenter a feed token names, or None for anything off."""
    try:
        payload = signing.loads(token, salt=FEED_SALT)
    except signing.BadSignature:
        return None
    from .models import Presenter

    return Presenter.objects.filter(pk=payload.get("presenter")).first()


def escape_text(value):
    """RFC 5545 TEXT escaping."""
    value = value.replace("\\", "\\\\")
    value = value.replace(";", "\\;")
    value = value.replace(",", "\\,")
    return value.replace("\n", "\\n")


def fold(line):
    """Fold a content line at 75 octets, continuation lines indented."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return [line]
    parts = []
    while raw:
        cut = min(75, len(raw))
        # Never split inside a UTF-8 sequence.
        while cut < len(raw) and (raw[cut] & 0xC0) == 0x80:
            cut -= 1
        parts.append(raw[:cut].decode("utf-8"))
        raw = raw[cut:]
    return [parts[0]] + [" " + part for part in parts[1:]]


def _stamp(moment):
    return moment.strftime("%Y%m%dT%H%M%SZ")


def event_lines(row):
    """One VEVENT from a published slot."""
    session = row.session
    conference = row.conference
    if (
        session.is_pre_recorded
        and session.effective_premiere_location == PremiereLocation.YOUTUBE
        and session.youtube_url
    ):
        location = session.youtube_url
    elif row.room_id:
        location = row.room.name
    else:
        location = "All rooms"
    lines = [
        "BEGIN:VEVENT",
        f"UID:session-{session.pk}@{conference.slug}.pyladiescon-portal",
        f"DTSTAMP:{_stamp(row.published_at)}",
        f"DTSTART:{_stamp(row.start_utc)}",
        f"DTEND:{_stamp(row.end_utc)}",
        f"SEQUENCE:{row.ics_sequence}",
        f"SUMMARY:{escape_text(session.title)}",
        f"LOCATION:{escape_text(location)}",
    ]
    if session.status == SessionStatus.CANCELLED:
        lines.append("STATUS:CANCELLED")
    lines.append("END:VEVENT")
    return lines


def render_calendar(name, rows):
    """A whole VCALENDAR, CRLF line endings, folded."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//PyLadiesCon portal//speakers//EN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{escape_text(name)}",
    ]
    for row in rows:
        lines.extend(event_lines(row))
    lines.append("END:VCALENDAR")
    folded = []
    for line in lines:
        folded.extend(fold(line))
    return CRLF.join(folded) + CRLF


def feed_rows(conference):
    """Everything a feed may draw from, ready for one-pass rendering."""
    return PublishedSlot.objects.filter(conference=conference).select_related(
        "session", "session__kind", "room", "conference"
    )


def public_rows(conference, sessions=None, kind=None, room=None):
    """The public feed: public sessions only until the §11.5 visibility
    rules arrive, filtered as §11.3 describes."""
    rows = feed_rows(conference).filter(session__is_public=True)
    if sessions:
        rows = rows.filter(session__slug__in=sessions)
    if kind:
        rows = rows.filter(session__kind__code=kind)
    if room:
        rows = rows.filter(room_id=room)
    return rows.order_by("start_utc")


def presenter_rows(conference, presenter):
    """A presenter's own feed: their sessions, public or not, including a
    cancelled one still on the snapshot so their calendar hears of it."""
    return (
        feed_rows(conference)
        .filter(session__session_presenters__presenter=presenter)
        .distinct()
        .order_by("start_utc")
    )
