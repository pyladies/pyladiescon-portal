"""Put the sample data into the state the screencasts expect.

Run after ``generate_sample_data`` and ``generate_speaker_sample_data``, with
``python manage.py shell < scripts/screencasts/seed.py``. It:

- makes 2026 the active edition, with the speaker module on, proposals open
  and the speaker side of the media pipeline on (the Files tab),
- offers only Workshop and PyJam performance for proposals,
- marks every sample account's email verified (a returning volunteer has
  verified theirs),
- keeps one confirmed PyJam performer, Maria Performer, with a password so
  the media takes can sign in as her, renames her session to
  ``SCREENCAST_SESSION_TITLE`` (run.sh sets it), and removes her sample
  video, and
- points the Site at the local server, so emailed links open it.

Every other session and presenter is removed from the 2026 edition, so a
take never meets what an earlier one left behind.
"""

import os

from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.contrib.sites.models import Site

from portal.models import Conference
from speakers.models import (
    MediaAsset,
    Presenter,
    Session,
    SessionType,
    SpeakerSettings,
)
from speakers.readiness import refresh_for_conference
from speakers.seeds import seed_checklists

YEAR = int(os.environ.get("SCREENCAST_YEAR", "2026"))
DOMAIN = os.environ.get("SCREENCAST_DOMAIN", "127.0.0.1:8002")
PASSWORD = os.environ.get("SAMPLE_PASSWORD", "password123")
PERFORMER_EMAIL = "maria@example.com"
PERFORMER_USERNAME = "maria_performer"
SAMPLE_PERFORMANCE = "Live-coded music with Python"
PERFORMANCE = os.environ.get("SCREENCAST_SESSION_TITLE", SAMPLE_PERFORMANCE)

conference = Conference.objects.get(year=YEAR)
conference.is_active = True
conference.save()

Session.objects.filter(conference=conference).exclude(
    title__in=[SAMPLE_PERFORMANCE, PERFORMANCE]
).delete()
Presenter.objects.filter(conference=conference).exclude(email=PERFORMER_EMAIL).delete()

settings_row, _ = SpeakerSettings.objects.get_or_create(conference=conference)
settings_row.speaker_module_enabled = True
settings_row.media_for_speakers = True
settings_row.conference_timezone = "UTC"
settings_row.organizers_email = "organizers@example.com"
settings_row.default_video_length_limit_minutes = 10
settings_row.proposals_open = True
settings_row.proposals_intro_md = (
    f"We are taking proposals for PyLadiesCon {YEAR}. "
    "A title and two sentences is enough to start."
)
settings_row.save()

SessionType.objects.filter(conference=conference).update(open_for_proposals=False)
SessionType.objects.filter(
    conference=conference, name__in=["Workshop", "PyJam performance"]
).update(open_for_proposals=True)
seed_checklists(conference)

# The performer: a known username and password, and no video yet (the
# sample data gives her a placeholder asset with no file behind it).
performance = Session.objects.get(
    conference=conference, title__in=[SAMPLE_PERFORMANCE, PERFORMANCE]
)
# The takes show this session by name, so give it the title the scripts
# expect, with a fresh slug to match.
performance.title = PERFORMANCE
performance.slug = ""
performance.summary_md = os.environ.get(
    "SCREENCAST_SESSION_SUMMARY",
    "A ten-minute blues set played live from a Python REPL. Every riff is a "
    "list, every chord a dictionary, and the drummer is a `while True` loop "
    "that has never once asked for a break. Expect twelve bars, a few "
    "bent notes, one dramatic `KeyboardInterrupt`, and a finale that walks "
    "the bass line straight through a generator.",
)
# A performance slot of 10 minutes, matching the video limit the page shows.
performance.duration_minutes = 10
performance.save()
performer = Presenter.objects.get(conference=conference, email=PERFORMER_EMAIL)
performer.user.username = PERFORMER_USERNAME
performer.user.first_name = "Maria"
performer.user.last_name = "Performer"
performer.user.set_password(PASSWORD)
performer.user.save()
MediaAsset.objects.filter(session=performance).delete()
refresh_for_conference(conference)

for user in User.objects.all():
    EmailAddress.objects.update_or_create(
        user=user,
        email=user.email,
        defaults={"verified": True, "primary": True},
    )

Site.objects.update_or_create(
    pk=1, defaults={"domain": DOMAIN, "name": "PyLadiesCon Portal"}
)
print(
    f"Screencast data ready for {conference} on {DOMAIN}: "
    f"{performance.title} is {performance.status}, "
    f"{performer.display_name} signs in as {PERFORMER_USERNAME}."
)
