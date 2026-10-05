"""Building the schedule editor's grid (design §10, task 4.2).

Rooms across, 15-minute steps down, one day at a time. Everything is
computed in UTC; the browser relabels the times in whatever timezone the
organizer picks (``static/js/schedule-editor.js`` reads the ``data-utc``
attributes this module's cards carry).
"""

from datetime import datetime, timedelta, timezone

from django.db.models import Q

from .clock import today
from .constants import OFF_SCHEDULE_STATUSES
from .models import (
    Presenter,
    Room,
    ScheduleSlot,
    Session,
    SessionPresenter,
    SpeakerSettings,
)

STEP_MINUTES = 15
ROWS_PER_DAY = 24 * 60 // STEP_MINUTES

# The grid's first two columns: the hour gutter and the all-rooms lane
# where the opening and the breaks go. Rooms start in the third.
GUTTER_COLUMN = 1
ALL_ROOMS_COLUMN = 2
FIRST_ROOM_COLUMN = 3

# The header row is row 1; the day's first quarter hour is row 2.
FIRST_TIME_ROW = 2


def schedule_days(conference):
    """The dates the editor offers as tabs.

    The conference's own span when it has one, plus any date a slot
    already sits on, so nothing scheduled can become unreachable. With
    neither, today, so an empty editor still renders a grid.
    """
    days = {
        moment.date()
        for moment in ScheduleSlot.objects.filter(conference=conference).datetimes(
            "start_utc", "day", tzinfo=timezone.utc
        )
    }
    if conference.start_date and conference.end_date:
        day = conference.start_date
        while day <= conference.end_date:
            days.add(day)
            day += timedelta(days=1)
    elif conference.conference_date:
        days.add(conference.conference_date)
    if not days:
        days.add(today())
    return sorted(days)


def day_bounds(day):
    """Midnight to midnight, UTC."""
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def _row_of(moment, day_start):
    """The grid row a UTC moment falls in, clamped to the day."""
    offset = (moment - day_start).total_seconds() // (STEP_MINUTES * 60)
    return FIRST_TIME_ROW + int(max(0, min(ROWS_PER_DAY, offset)))


def grid_for_day(conference, day):
    """Everything the grid template needs for one day, in flat queries."""
    day_start, day_end = day_bounds(day)
    rooms = list(Room.objects.filter(conference=conference, is_active=True))
    slots = list(
        ScheduleSlot.objects.filter(
            conference=conference, start_utc__lt=day_end, end_utc__gt=day_start
        )
        .exclude(session__status__in=OFF_SCHEDULE_STATUSES)
        .select_related("session__kind", "room")
        .order_by("start_utc")
    )
    # A deactivated room that still holds a slot stays a lane, marked
    # retired, rather than its card being misdrawn in the all-rooms lane.
    known = {room.pk for room in rooms}
    for slot in slots:
        if slot.room_id and slot.room_id not in known:
            known.add(slot.room_id)
            rooms.append(slot.room)
    lanes = [{"pk": "", "name": "All rooms", "column": ALL_ROOMS_COLUMN}] + [
        {
            "pk": room.pk,
            "name": room.name if room.is_active else f"{room.name} (retired)",
            "column": FIRST_ROOM_COLUMN + i,
        }
        for i, room in enumerate(rooms)
    ]
    last_column = FIRST_ROOM_COLUMN + len(rooms)
    warnings = presenter_warnings(slots)
    column = {room.pk: FIRST_ROOM_COLUMN + i for i, room in enumerate(rooms)}
    cards = []
    for slot in slots:
        row = _row_of(slot.start_utc, day_start)
        span = max(1, _row_of(slot.end_utc, day_start) - row)
        if slot.room_id is None:
            start_column, end_column = ALL_ROOMS_COLUMN, last_column
        else:
            start_column = column[slot.room_id]
            end_column = start_column + 1
        cards.append(
            {
                "slot": slot,
                "session": slot.session,
                "row": row,
                "span": span,
                "start_column": start_column,
                "end_column": end_column,
                "is_band": slot.room_id is None,
                "minutes": int((slot.end_utc - slot.start_utc).total_seconds() // 60),
                "warnings": warnings.get(slot.pk, []),
            }
        )
    rows = [
        {
            "index": FIRST_TIME_ROW + i,
            "utc": day_start + timedelta(minutes=STEP_MINUTES * i),
            "is_hour": i % 4 == 0,
        }
        for i in range(ROWS_PER_DAY)
    ]
    return {
        "rooms": rooms,
        "lanes": lanes,
        "last_column": last_column,
        "rows": rows,
        "cards": cards,
        "day_start": day_start,
    }


def presenter_warnings(slots):
    """``{slot.pk: ["Ada Lovelace is also in “X”", ...]}`` for one day.

    The double-booking warning of design §8.5, computed over the day's
    slots in one query instead of one ``presenter_clashes()`` call per
    slot, so the grid's query count stays flat.
    """
    links = SessionPresenter.objects.filter(
        session_id__in={slot.session_id for slot in slots}
    ).select_related("presenter")
    people = {}
    for link in links:
        people.setdefault(link.session_id, []).append(link.presenter)
    warnings = {}
    for slot in slots:
        for other in slots:
            if other.pk == slot.pk:
                continue
            if other.start_utc >= slot.end_utc or other.end_utc <= slot.start_utc:
                continue
            shared = [
                presenter
                for presenter in people.get(slot.session_id, [])
                if presenter in people.get(other.session_id, [])
            ]
            for presenter in shared:
                warnings.setdefault(slot.pk, []).append(
                    f"{presenter.display_name} is also in " f"“{other.session.title}”"
                )
    return warnings


def presenter_schedule(conference, presenter):
    """The schedule as one presenter may see it, by their local day.

    Public sessions, plus the presenter's own whatever their status short
    of the off-schedule ones; an unpublished entry of their own carries a
    draft flag for the "not yet public" badge (design §2.4). Times are
    pre-formatted in the presenter's timezone, so the template never
    re-converts them (Django's date filter would pull aware datetimes
    back to UTC).
    """
    mine = set(
        SessionPresenter.objects.filter(presenter=presenter).values_list(
            "session_id", flat=True
        )
    )
    slots = (
        ScheduleSlot.objects.filter(conference=conference)
        .exclude(session__status__in=OFF_SCHEDULE_STATUSES)
        .filter(Q(session__is_public=True) | Q(session_id__in=mine))
        .select_related("session__kind", "room")
        .order_by("start_utc")
    )
    tz = presenter.tzinfo
    days = []
    for slot in slots:
        start = slot.start_utc.astimezone(tz)
        entry = {
            "session": slot.session,
            "room": slot.room,
            "start_label": start.strftime("%H:%M"),
            "end_label": slot.end_utc.astimezone(tz).strftime("%H:%M"),
            "is_mine": slot.session_id in mine,
            "is_draft": not slot.session.is_public,
        }
        if days and days[-1]["day"] == start.date():
            days[-1]["entries"].append(entry)
        else:
            days.append({"day": start.date(), "entries": [entry]})
    return days


def unscheduled_sessions(conference):
    """The sidebar: everything placeable that has no slot yet."""
    return (
        Session.objects.for_conference(conference)
        .filter(slot__isnull=True)
        .exclude(status__in=OFF_SCHEDULE_STATUSES)
        .select_related("kind")
        .order_by("kind__sort_order", "title")
    )


def timezone_options(conference):
    """What the timezone switcher offers besides the browser's own zone.

    UTC, the organizers' display timezone, and each distinct timezone of a
    presenter on a scheduled session, labelled with a name, which is how
    "we scheduled her at 3 a.m." gets caught (design §10).
    """
    options = [("UTC", "UTC")]
    settings_row = SpeakerSettings.objects.filter(conference=conference).first()
    if settings_row and settings_row.conference_timezone != "UTC":
        options.append(
            (settings_row.conference_timezone, settings_row.conference_timezone)
        )
    seen = {value for value, _ in options}
    presenters = (
        Presenter.objects.filter(
            conference=conference, session_presenters__session__slot__isnull=False
        )
        .distinct()
        .order_by("display_name")
    )
    for presenter in presenters:
        if presenter.timezone and presenter.timezone not in seen:
            seen.add(presenter.timezone)
            options.append(
                (
                    presenter.timezone,
                    f"{presenter.timezone} ({presenter.display_name})",
                )
            )
    return options
