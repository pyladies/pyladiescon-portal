"""Put the sample data into the state the screencasts expect.

Run after ``generate_sample_data`` and ``generate_speaker_sample_data``, with
``python manage.py shell < scripts/screencasts/seed.py``. It:

- makes 2026 the active edition, with the speaker module on and proposals open,
- offers only Workshop and PyJam performance for proposals,
- marks every sample account's email verified (a returning volunteer has
  verified theirs), and
- points the Site at the local server, so emailed links open it.

It also removes any speakers data from the 2026 edition, so a take never meets
what an earlier one left behind.
"""

import os

from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.contrib.sites.models import Site

from portal.models import Conference
from speakers.models import (
    Presenter,
    Session,
    SessionType,
    SpeakerSettings,
)
from speakers.seeds import seed_checklists

YEAR = int(os.environ.get("SCREENCAST_YEAR", "2026"))
DOMAIN = os.environ.get("SCREENCAST_DOMAIN", "127.0.0.1:8002")

conference = Conference.objects.get(year=YEAR)
conference.is_active = True
conference.save()

Session.objects.filter(conference=conference).delete()
Presenter.objects.filter(conference=conference).delete()

settings_row, _ = SpeakerSettings.objects.get_or_create(conference=conference)
settings_row.speaker_module_enabled = True
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

for user in User.objects.all():
    EmailAddress.objects.update_or_create(
        user=user,
        email=user.email,
        defaults={"verified": True, "primary": True},
    )

Site.objects.update_or_create(
    pk=1, defaults={"domain": DOMAIN, "name": "PyLadiesCon Portal"}
)
print(f"Screencast data ready for {conference} on {DOMAIN}.")
