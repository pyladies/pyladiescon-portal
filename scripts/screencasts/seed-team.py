"""Put the team's files on the performer's session, for the "team" take and
the announcement screenshots.

Run on a restored screencast database, with the media environment set
(SPEAKER_MEDIA_BUCKET and the AWS_* pair, see run.sh), after ``seed.py``:
``python manage.py shell < scripts/screencasts/seed-team.py``. It uploads
the sample files from ``out/media`` to the bucket and records them the way
a finished upload would, so previews and thumbnails work:

- the performer's own video (version 1, her upload),
- a square poster, a transcript and the final cut, each shared with her,

then re-evaluates readiness so "Approve the final cut" opens, and sends
today's checklist digests so the "new files from the team" email is in
maildev for the take to open.
"""

import mimetypes
import os
from pathlib import Path

from django.utils import timezone

from portal.models import Conference
from speakers.media import MediaBucket, record_asset
from speakers.models import MediaKind, Presenter, Session
from speakers.readiness import refresh_for_conference
from speakers.reminders import send_checklist_digests

YEAR = int(os.environ.get("SCREENCAST_YEAR", "2026"))
MEDIA = Path(os.environ["SCREENCAST_MEDIA"])
PERFORMANCE = os.environ.get("SCREENCAST_SESSION_TITLE", "Duck Typing the Blues")

conference = Conference.objects.get(year=YEAR)
session = Session.objects.get(conference=conference, title=PERFORMANCE)
performer = Presenter.objects.get(conference=conference, email="maria@example.com")
bucket = MediaBucket.from_settings()

FILES = [
    # file, kind, language, variant, title, uploaded by, shared
    ("performance.mp4", MediaKind.RAW_VIDEO, "", "", "", performer.user, False),
    (
        "poster-square.png",
        MediaKind.PROMO,
        "",
        "square",
        "Poster for your performance",
        None,
        True,
    ),
    (
        "transcript-en.vtt",
        MediaKind.TRANSCRIPT,
        "en",
        "",
        "Transcript, reviewed by the team",
        None,
        True,
    ),
    (
        "final-cut.webm",
        MediaKind.PROCESSED_VIDEO,
        "",
        "",
        "Final cut, with the intro and outro",
        None,
        True,
    ),
]

for name, kind, language, variant, title, uploader, shared in FILES:
    path = MEDIA / name
    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    if name.endswith(".vtt"):
        content_type = "text/vtt"
    key = bucket.key_for(session, kind, name)
    with path.open("rb") as handle:
        bucket.client.put_object(
            Bucket=bucket.bucket, Key=key, Body=handle, ContentType=content_type
        )
    asset = record_asset(
        session=session,
        kind=kind,
        language=language,
        variant=variant,
        storage_key=key,
        filename=name,
        content_type=content_type,
        size_bytes=path.stat().st_size,
        uploaded_by=uploader,
        title=title,
    )
    if shared:
        asset.shared_with_speaker = True
        asset.shared_at = timezone.now()
        asset.save(update_fields=["shared_with_speaker", "shared_at", "modified_date"])
    print(f"{asset.get_kind_display()} v{asset.version}: {name}")

refresh_for_conference(conference)
count = send_checklist_digests(conference)
print(f"Team files are on {session.title}; {int(count)} digest email(s) sent.")
