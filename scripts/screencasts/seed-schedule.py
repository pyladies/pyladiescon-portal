"""Put the sample data into the state the scheduling takes expect.

Runs after the snapshot is restored, like ``seed-team.py``: the base
snapshot keeps only the performer, and the schedule takes need a program
to place. With ``python manage.py shell < scripts/screencasts/seed-schedule.py``
it:

- re-creates the sample sessions and presenters from
  ``generate_speaker_sample_data`` (people, sessions, presenters and their
  invitation states), but not the sample schedule,
- drops the sample performance, which the snapshot already has under the
  screencast title, and the sample coffee break, which the take creates,
- names the rooms: ``Main stage`` stays, and the take adds ``Workshop room``
  in the admin,
- gives the people made-up names (the sample data borrows famous ones) and
  the sessions titles nobody will mistake for a real program,
- adds more sessions and people than the sample data has, two of them not
  confirmed, and places the Opening, the Closing and the later afternoon on
  the grid already, so it opens trimmed with the Unscheduled list in view
  and the day looks like a conference,
- gives every headshot a real file, a disc with initials, where the sample
  data points at a file that is not there,
- gives one speaker a known login, Juno Kwargs (``juno_kwargs``), whose New
  York timezone makes the timezone switcher worth showing, and
- marks every account's email verified, so everyone can sign in.
"""

import os
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from io import BytesIO

from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from portal.models import Conference
from speakers.constants import Delivery, SessionStatus
from speakers.management.commands.generate_speaker_sample_data import (
    PRESENTERS,
    SESSIONS,
    Command,
)
from speakers.models import Presenter, PublishedSlot, Room, ScheduleSlot, Session
from speakers.readiness import refresh_for_conference
from speakers.rules import reevaluate_all

YEAR = int(os.environ.get("SCREENCAST_YEAR", "2026"))
PASSWORD = os.environ.get("SAMPLE_PASSWORD", "password123")
SAMPLE_PERFORMANCE = "Live-coded music with Python"
DAY = os.environ.get("SCREENCAST_DAY", "2026-12-05")
SPEAKER_EMAIL = "juno@example.com"
SPEAKER_USERNAME = "juno_kwargs"

# The sample data's people, by email, and who they are on screen.
PEOPLE = {
    "ada@example.com": ("Lupe Lambdagiri", "lupe@example.com"),
    "grace@example.com": ("Juno Kwargs", SPEAKER_EMAIL),
    "dex@example.com": ("Tessa Tupleton", "tessa@example.com"),
    "sam@example.com": ("Ravi Yieldsen", "ravi@example.com"),
    "nina@example.com": ("Nova Dunderton", "nova@example.com"),
}

# The sample sessions, and the program the takes show.
TITLES = {
    "Testing Django applications": "Pandas Are Bears: A Zoology Workshop",
    "The future of PyLadies": "There Should Be One Obvious Way to Keynote",
    "Careers in open source": "The GIL: A Support Group",
    "Type hints in practice": "My Code Works and Nobody Knows Why",
}

# More program than the sample data has, so the grid, the confirmation and
# the Publishing page look like a conference: title, type code, delivery.
EXTRA_SESSIONS = [
    ("Exceptions Are Just Spicy Return Values", "TALK", Delivery.LIVE),
    ("Async Await: A Love Story With No Resolution", "TALK", Delivery.LIVE),
    ("Indentation Errors and Other Life Choices", "WORKSHOP", Delivery.LIVE),
    ("Global Variables Anonymous", "PANEL", Delivery.LIVE),
    ("The Walrus Operator: Fact or Mammal?", "TALK", Delivery.LIVE),
    ("Pickle Rick: Serializing Your Regrets", "TALK", Delivery.LIVE),
    ("Yield to Pedestrians: Generators in Traffic", "TALK", Delivery.LIVE),
    ("Closing", "CLOSING", Delivery.LIVE),
]
# Their people: name, email, timezone, sessions with roles, state, liaison.
# Two are not confirmed on purpose (one invited, one not even invited), so
# the Publishing page has rows it cannot tick yet.
EXTRA_PRESENTERS = [
    (
        "Bea Backslash",
        "bea@example.com",
        "Europe/Lisbon",
        [
            ("Exceptions Are Just Spicy Return Values", "PRESENTER"),
            ("Yield to Pedestrians: Generators in Traffic", "PRESENTER"),
        ],
        "onboarded",
        "organizer_lena",
    ),
    (
        "Ines Iterable",
        "ines@example.com",
        "Asia/Kolkata",
        [("Async Await: A Love Story With No Resolution", "PRESENTER")],
        "onboarded",
        None,
    ),
    (
        "Teo Tracebacker",
        "teo@example.com",
        "Australia/Sydney",
        [("Indentation Errors and Other Life Choices", "PRESENTER")],
        "onboarded",
        "vol_kim",
    ),
    (
        "Nadia Nonetype",
        "nadia@example.com",
        "Africa/Nairobi",
        [("Global Variables Anonymous", "MODERATOR")],
        "onboarded",
        None,
    ),
    (
        "Omar Offbyone",
        "omar@example.com",
        "America/Mexico_City",
        [
            ("Global Variables Anonymous", "PANELIST"),
            ("The Walrus Operator: Fact or Mammal?", "PRESENTER"),
        ],
        "invited",
        None,
    ),
    (
        "Sol Slicewright",
        "sol@example.com",
        "Europe/Berlin",
        [("Pickle Rick: Serializing Your Regrets", "PRESENTER")],
        "not_invited",
        None,
    ),
]
# Already on the grid when the take starts: title, day offset, UTC time,
# room name (None for the all-rooms lane). Only the Main stage exists at this
# point; the take adds the Workshop room.
PLACED = [
    ("Opening", 0, "14:00", None),
    ("Exceptions Are Just Spicy Return Values", 0, "16:30", "Main stage"),
    ("Async Await: A Love Story With No Resolution", 0, "17:00", "Main stage"),
    ("Global Variables Anonymous", 0, "17:30", "Main stage"),
    ("Yield to Pedestrians: Generators in Traffic", 1, "14:00", "Main stage"),
    ("Indentation Errors and Other Life Choices", 1, "14:30", "Main stage"),
    ("Closing", 1, "17:00", None),
]
AVATAR_COLOURS = ["#b5177a", "#2d6a4f", "#1d4e89", "#b35c00", "#5b3fa0", "#9c2f2f"]

conference = Conference.objects.get(year=YEAR)

# The sample data's own phases, minus the schedule, the proposals, the
# checklist states and the performer's placeholder video: the people and
# the program are what the takes need.
command = Command()
command.conference = conference
command.today = timezone.now().date()
SESSIONS.extend((title, code, delivery, "") for title, code, delivery in EXTRA_SESSIONS)
PRESENTERS.extend(EXTRA_PRESENTERS)
command._settings_and_seeds()
command.users = command._people()
command.sessions = command._sessions()
command.presenters = command._presenters()

Session.objects.filter(conference=conference, title=SAMPLE_PERFORMANCE).delete()
Session.objects.filter(conference=conference, title="Coffee break").delete()
# The snapshot gives the performance the 10 minutes of its video limit; a
# slot is at least one grid step.
Session.objects.filter(
    conference=conference,
    title=os.environ.get("SCREENCAST_SESSION_TITLE", "Duck Typing the Blues"),
).update(duration_minutes=15)
ScheduleSlot.objects.filter(conference=conference).delete()
PublishedSlot.objects.filter(conference=conference).delete()

Room.objects.filter(conference=conference, name="main-stage").update(name="Main stage")
Room.objects.filter(conference=conference, name="workshop-room").delete()

for old_email, (name, email) in PEOPLE.items():
    presenter = Presenter.objects.get(conference=conference, email=old_email)
    presenter.display_name = name
    presenter.email = email
    # An empty slug is rebuilt from the new name on save, so URLs and the
    # headshot file names carry the made-up name, not the borrowed one.
    presenter.slug = ""
    presenter.save()
    if presenter.user_id:
        first, last = name.split(" ", 1)
        presenter.user.first_name = first
        presenter.user.last_name = last
        presenter.user.email = email
        presenter.user.save()
        EmailAddress.objects.filter(user=presenter.user).delete()
for old_title, title in TITLES.items():
    session = Session.objects.get(conference=conference, title=old_title)
    session.title = title
    session.slug = ""
    session.save()

speaker = Presenter.objects.get(conference=conference, email=SPEAKER_EMAIL)
speaker.user.username = SPEAKER_USERNAME
speaker.user.set_password(PASSWORD)
speaker.user.save()

# The closing is the organizers' own, like the opening, and needs nobody.
closing = Session.objects.get(conference=conference, title="Closing")
if closing.status == SessionStatus.DRAFT:
    closing.confirm()

day_one = datetime.fromisoformat(DAY).date()
for title, offset, time, room_name in PLACED:
    ScheduleSlot.objects.create(
        session=Session.objects.get(conference=conference, title=title),
        room=(
            Room.objects.get(conference=conference, name=room_name)
            if room_name
            else None
        ),
        start_utc=datetime.combine(
            day_one + timedelta(days=offset),
            datetime.strptime(time, "%H:%M").time(),
            tzinfo=dt_timezone.utc,
        ),
    )


def avatar(name, colour):
    """A flat disc with the person's initials: a headshot that exists, where
    the sample data points at a file that does not (a broken image on the
    public widget)."""
    image = Image.new("RGB", (240, 240), colour)
    draw = ImageDraw.Draw(image)
    initials = "".join(part[0] for part in name.split()[:2]).upper()
    font = ImageFont.load_default(size=96)
    draw.text((120, 120), initials, fill="white", font=font, anchor="mm")
    out = BytesIO()
    image.save(out, "PNG")
    return ContentFile(out.getvalue())


for index, presenter in enumerate(
    Presenter.objects.filter(conference=conference).exclude(headshot="")
):
    presenter.headshot.save(
        f"{presenter.slug}.png",
        avatar(presenter.display_name, AVATAR_COLOURS[index % len(AVATAR_COLOURS)]),
        save=True,
    )

for user in User.objects.all():
    EmailAddress.objects.update_or_create(
        user=user,
        email=user.email,
        defaults={"verified": True, "primary": True},
    )

reevaluate_all(conference)
refresh_for_conference(conference)
placeable = Session.objects.filter(conference=conference, slot__isnull=True).count()
print(
    f"Schedule screencast data ready for {conference}: {placeable} sessions to "
    f"place in {Room.objects.filter(conference=conference).count()} room(s); "
    f"{speaker.display_name} signs in as {SPEAKER_USERNAME}."
)
