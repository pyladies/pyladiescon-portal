"""Thumbnails made by the worker (design §8.8, task 5.8): a scaled image
for pictures, a frame for videos, an icon for the rest; the failure on
the row; shown on the files table, the speaker's files, the board and the
sessions list in a fixed number of queries."""

import io
import shutil
from pathlib import Path

import boto3
import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from moto import mock_aws
from PIL import Image

from speakers.checklists import instantiate_session_checklist
from speakers.constants import MediaKind, MediaStatus
from speakers.media import MediaBucket
from speakers.models import MediaAsset
from speakers.seeds import seed_checklists
from speakers.signals import asset_ready
from speakers.tasks import make_thumbnail_task
from speakers.thumbnails import (
    ThumbnailError,
    image_thumbnail,
    make_thumbnail,
)
from speakers.thumbnails import run_ffmpeg as real_run_ffmpeg
from speakers.thumbnails import (
    video_thumbnail,
)

from .factories import add_presenter, make_presenter, make_session, make_settings

BUCKET = "test-speaker-media"
FIXTURE_VIDEO = Path(__file__).parent / "fixtures" / "two-seconds.mp4"


def png_bytes(size=(1200, 800), mode="RGBA"):
    out = io.BytesIO()
    color = 120 if mode == "L" else (200, 30, 80, 255)
    Image.new(mode, size, color).save(out, "PNG")
    return out.getvalue()


@pytest.fixture
def bucket(settings):
    settings.SPEAKER_MEDIA_BUCKET = BUCKET
    settings.SPEAKER_MEDIA_PREFIX = "speaker-media/"
    settings.SPEAKER_MEDIA_ENDPOINT_URL = None
    settings.SPEAKER_MEDIA_REGION = "us-east-1"
    settings.SPEAKER_MEDIA_ACCESS_KEY_ID = "testing"
    settings.SPEAKER_MEDIA_SECRET_ACCESS_KEY = "testing"
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield MediaBucket.from_settings()


@pytest.fixture
def organizer(db):
    return User.objects.create_user("org", email="org@x.org", is_staff=True)


@pytest.fixture
def speaker(db):
    return User.objects.create_user("ada", email="ada@x.org")


@pytest.fixture
def session(conference, speaker):
    make_settings(conference)
    session = make_session(conference, title="A PyJam set", kind="PYJAM")
    add_presenter(
        session,
        make_presenter(conference, display_name="Ada", user=speaker),
        confirmed=True,
    )
    return session


def put(bucket, session, kind, name, body, content_type, **kwargs):
    key = f"speaker-media/x/{session.slug}/{kind.lower()}/{name}"
    bucket.client.put_object(Bucket=BUCKET, Key=key, Body=body)
    kwargs.setdefault("status", MediaStatus.READY)
    return MediaAsset.objects.create(
        session=session,
        kind=kind,
        storage_key=key,
        original_filename=name,
        content_type=content_type,
        size_bytes=len(body),
        **kwargs,
    )


class TestMaking:
    def test_an_image_is_scaled_to_a_small_jpeg(self):
        data = image_thumbnail(png_bytes())
        image = Image.open(io.BytesIO(data))
        assert image.format == "JPEG" and image.size == (480, 320)
        assert len(data) < 50 * 1024
        # Greyscale and palette images come out too.
        assert Image.open(
            io.BytesIO(image_thumbnail(png_bytes((10, 10), "L")))
        ).size == (10, 10)
        with pytest.raises(ThumbnailError, match="could not be read"):
            image_thumbnail(b"not an image")

    @pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
    def test_the_fixture_video_gives_a_frame(self, monkeypatch):
        monkeypatch.setattr("speakers.thumbnails.run_ffmpeg", real_run_ffmpeg)
        data = video_thumbnail(
            str(FIXTURE_VIDEO)
        )  # 2 s long: falls back to the first frame
        image = Image.open(io.BytesIO(data))
        assert image.format == "JPEG" and image.width <= 480
        assert len(data) < 50 * 1024

    def test_ffmpeg_failures_are_named(self, ffmpeg):
        import subprocess
        from unittest.mock import patch

        with patch("speakers.thumbnails.subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(ThumbnailError, match="not installed"):
                real_run_ffmpeg("x.mp4")
        with patch(
            "speakers.thumbnails.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=1),
        ):
            with pytest.raises(ThumbnailError, match="no frame within"):
                real_run_ffmpeg("x.mp4", timeout=1)
        failed = subprocess.CompletedProcess(
            args=[], returncode=1, stdout=b"", stderr=b"x: bad\n"
        )
        with patch("speakers.thumbnails.subprocess.run", return_value=failed):
            with pytest.raises(ThumbnailError, match="could not take a frame: x: bad"):
                real_run_ffmpeg("x.mp4")
        # The fallback to the first frame only covers a missing frame, not a broken tool.
        ffmpeg.side_effect = ThumbnailError("ffmpeg is not installed on the worker.")
        with pytest.raises(ThumbnailError, match="not installed"):
            video_thumbnail("x.mp4")
        ffmpeg.side_effect = [ThumbnailError("ffmpeg could not take a frame."), b"jpeg"]
        assert video_thumbnail("x.mp4") == b"jpeg"


@pytest.mark.django_db
class TestOnAssets:
    def test_image_and_video_get_thumbnails_when_ready(
        self, bucket, session, organizer, ffmpeg, django_capture_on_commit_callbacks
    ):
        poster = put(
            bucket, session, MediaKind.PROMO, "poster.png", png_bytes(), "image/png"
        )
        video = put(
            bucket, session, MediaKind.RAW_VIDEO, "take.mp4", b"mp4", "video/mp4"
        )
        audio = put(bucket, session, MediaKind.OTHER, "song.mp3", b"mp3", "audio/mpeg")
        with django_capture_on_commit_callbacks(execute=True):
            for asset in (poster, video, audio):
                asset_ready.send(sender=MediaAsset, asset=asset)
        for asset in (poster, video, audio):
            asset.refresh_from_db()
        assert poster.thumbnail_key == poster.storage_key + ".thumb.jpg"
        assert video.thumbnail_key == video.storage_key + ".thumb.jpg"
        assert audio.thumbnail_key == "" and audio.thumbnail_error == ""
        stored = bucket.client.get_object(Bucket=BUCKET, Key=poster.thumbnail_key)
        assert stored["ContentType"] == "image/jpeg"
        assert Image.open(io.BytesIO(stored["Body"].read())).size == (480, 320)
        assert (
            ffmpeg.call_args.args[0].startswith("https://")
            and "X-Amz-Signature" in ffmpeg.call_args.args[0]
        )
        assert "X-Amz-Signature" in poster.thumbnail_url()

    def test_failures_are_on_the_row_and_the_asset_stays_ready(
        self, bucket, session, ffmpeg, settings, caplog
    ):
        video = put(
            bucket, session, MediaKind.RAW_VIDEO, "take.mp4", b"mp4", "video/mp4"
        )
        ffmpeg.side_effect = ThumbnailError("ffmpeg is not installed on the worker.")
        assert make_thumbnail(video) is None
        video.refresh_from_db()
        assert video.status == MediaStatus.READY and video.thumbnail_key == ""
        assert video.thumbnail_error == "ffmpeg is not installed on the worker."
        assert "Thumbnail failed" in caplog.text
        assert "not installed" in make_thumbnail_task(video.pk)
        assert make_thumbnail_task(10**6) == "No such asset"
        broken = put(bucket, session, MediaKind.PROMO, "p.png", b"nope", "image/png")
        assert make_thumbnail(broken) is None
        broken.refresh_from_db()
        assert "could not be read" in broken.thumbnail_error
        settings.SPEAKER_MEDIA_BUCKET = ""
        assert make_thumbnail(video) is None
        video.refresh_from_db()
        assert "SPEAKER_MEDIA_BUCKET" in video.thumbnail_error
        assert video.thumbnail_url() == ""

    def test_only_showable_files_in_the_bucket(self, session):
        text = MediaAsset.objects.create(
            session=session,
            kind=MediaKind.TRANSCRIPT,
            storage_key="k",
            content_type="text/vtt",
            status=MediaStatus.READY,
        )
        assert make_thumbnail(text) is None
        attached = MediaAsset.objects.create(
            session=session,
            kind=MediaKind.THUMBNAIL,
            content_type="image/png",
            status=MediaStatus.READY,
        )
        assert make_thumbnail(attached) is None


@pytest.mark.django_db
class TestOnThePages:
    def test_no_storage_no_thumbnail(
        self, client, bucket, session, organizer, settings
    ):
        video = put(
            bucket, session, MediaKind.RAW_VIDEO, "take.mp4", b"mp4", "video/mp4"
        )
        make_thumbnail(video)
        thumb = reverse("speakers:media_thumbnail", args=[session.slug, video.pk])
        client.force_login(organizer)
        settings.SPEAKER_MEDIA_BUCKET = ""
        assert client.get(thumb).status_code == 404

    def test_rows_board_speaker_and_list_show_it(
        self, client, bucket, session, organizer, speaker, conference
    ):
        seed_checklists(conference)
        instantiate_session_checklist(session)
        video = put(
            bucket, session, MediaKind.RAW_VIDEO, "take.mp4", b"mp4", "video/mp4"
        )
        make_thumbnail(video)
        poster = put(
            bucket,
            session,
            MediaKind.PROMO,
            "poster.png",
            png_bytes(),
            "image/png",
            shared_with_speaker=True,
            thumbnail_error="ffmpeg could not take a frame.",
        )
        thumb = reverse("speakers:media_thumbnail", args=[session.slug, video.pk])
        client.force_login(organizer)
        html = client.get(session.get_absolute_url()).content.decode()
        assert f'<img src="{thumb}"' in html and "no thumbnail" in html
        assert "fa-regular fa-image" in html  # the poster's icon while it has none
        html = client.get(
            reverse("speakers:checklist_board"), {"tab": "post_production"}
        ).content.decode()
        assert f'<img src="{thumb}"' in html
        html = client.get(reverse("speakers:session_list")).content.decode()
        assert f'<img src="{thumb}"' in html
        assert client.get(thumb).status_code == 302
        location = client.get(thumb)["Location"]
        assert "X-Amz-Signature" in location and "X-Amz-Expires=60" in location
        assert (
            client.get(
                reverse("speakers:media_thumbnail", args=[session.slug, poster.pk])
            ).status_code
            == 404
        )
        client.force_login(speaker)
        html = client.get(
            reverse("speakers:my_session_detail", args=[session.slug])
        ).content.decode()
        assert "fa-regular fa-image" in html  # the shared poster, no thumbnail yet
        assert client.get(thumb).status_code == 302  # their own raw video
        stranger = User.objects.create_user("s", email="s@x.org")
        client.force_login(stranger)
        assert client.get(thumb).status_code == 403

    def test_query_counts_stay_flat(
        self, client, bucket, session, organizer, conference
    ):
        seed_checklists(conference)
        client.force_login(organizer)
        board = reverse("speakers:checklist_board")
        with CaptureQueriesContext(connection) as before:
            client.get(board, {"tab": "post_production"})
            client.get(reverse("speakers:session_list"))
        for n in range(3):
            other = make_session(conference, title=f"Set {n}", kind="PYJAM")
            add_presenter(other, make_presenter(conference), confirmed=True)
            instantiate_session_checklist(other)
            video = put(
                bucket, other, MediaKind.RAW_VIDEO, "take.mp4", b"mp4", "video/mp4"
            )
            make_thumbnail(video)
        with CaptureQueriesContext(connection) as after:
            client.get(board, {"tab": "post_production"})
            client.get(reverse("speakers:session_list"))
        assert len(after) == len(before)
