"""The duration probe (design §8.8, task 5.3): ffprobe over a presigned
link, the answer on the asset, the length rule re-run, and every failure
recorded where people look rather than swallowed."""

import shutil
import subprocess
from pathlib import Path
from unittest.mock import PropertyMock, patch

import boto3
import pytest
from django.conf import settings as django_settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.fields.files import FieldFile
from moto import mock_aws

from speakers.constants import AutoRule, ItemStatus, MediaKind, MediaStatus
from speakers.media import MediaBucket
from speakers.models import MediaAsset
from speakers.probe import ProbeError, probe_asset, probe_duration
from speakers.probe import run_ffprobe as real_run_ffprobe
from speakers.signals import asset_ready
from speakers.tasks import probe_asset_task

from .factories import add_presenter, make_presenter, make_session, make_settings
from .test_rules import auto_item

FIXTURE = Path(__file__).parent / "fixtures" / "two-seconds.mp4"
BUCKET = "test-speaker-media"


@pytest.fixture
def enabled(conference):
    return make_settings(conference, default_video_length_limit_minutes=1)


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
def session(conference, enabled):
    session = make_session(conference, kind="PYJAM")
    add_presenter(session, make_presenter(conference), confirmed=True)
    return session


def make_video(session, **kwargs):
    kwargs.setdefault("kind", MediaKind.RAW_VIDEO)
    kwargs.setdefault("status", MediaStatus.READY)
    kwargs.setdefault("storage_key", f"speaker-media/{session.slug}/x/take.mp4")
    return MediaAsset.objects.create(session=session, **kwargs)


class TestFfprobe:
    def test_missing_binary_is_named(self):
        with patch("speakers.probe.subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(ProbeError, match="ffprobe is not installed"):
                real_run_ffprobe("x.mp4")

    def test_timeout(self):
        error = subprocess.TimeoutExpired(cmd="ffprobe", timeout=1)
        with patch("speakers.probe.subprocess.run", side_effect=error):
            with pytest.raises(ProbeError, match="no answer within"):
                real_run_ffprobe("x.mp4", timeout=1)

    def test_unreadable_file_quotes_ffprobe(self):
        failed = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="x.mp4: Invalid data\n"
        )
        with patch("speakers.probe.subprocess.run", return_value=failed):
            with pytest.raises(ProbeError, match="could not read the file: x.mp4"):
                real_run_ffprobe("x.mp4")
        failed.stderr = ""
        with patch("speakers.probe.subprocess.run", return_value=failed):
            with pytest.raises(ProbeError, match=r"could not read the file\.$"):
                real_run_ffprobe("x.mp4")

    def test_an_answer_without_a_duration(self, ffprobe):
        for output in ("not json", "{}", '{"format": {"duration": "soon"}}'):
            ffprobe.return_value = output
            with pytest.raises(ProbeError, match="without a duration"):
                probe_duration("x.mp4")

    def test_rounds_to_whole_seconds(self, ffprobe):
        ffprobe.return_value = '{"format": {"duration": "91.6"}}'
        assert probe_duration("x.mp4") == 92

    @pytest.mark.skipif(shutil.which("ffprobe") is None, reason="needs ffprobe")
    def test_the_fixture_video(self, monkeypatch):
        """The real binary on a real file: two seconds of black."""
        monkeypatch.setattr("speakers.probe.run_ffprobe", real_run_ffprobe)
        assert probe_duration(str(FIXTURE)) == 2


@pytest.mark.django_db
class TestProbeAsset:
    def test_records_the_duration_from_a_presigned_link(self, bucket, session, ffprobe):
        asset = make_video(session, probe_error="old failure")
        assert probe_asset(asset) == 120
        asset.refresh_from_db()
        assert asset.duration_seconds == 120 and asset.probe_error == ""
        source = ffprobe.call_args.args[0]
        assert asset.storage_key in source and "X-Amz-Signature" in source

    def test_records_a_failure_on_the_asset(self, bucket, session, ffprobe, caplog):
        ffprobe.side_effect = ProbeError("ffprobe is not installed on the worker.")
        asset = make_video(session)
        assert probe_asset(asset) is None
        asset.refresh_from_db()
        assert asset.duration_seconds is None
        assert asset.probe_error == "ffprobe is not installed on the worker."
        assert asset.status == MediaStatus.READY
        assert "Duration probe failed" in caplog.text

    def test_storage_not_configured(self, session, settings):
        settings.SPEAKER_MEDIA_BUCKET = ""
        asset = make_video(session)
        assert probe_asset(asset) is None
        asset.refresh_from_db()
        assert asset.probe_error == "SPEAKER_MEDIA_BUCKET is not set."

    def test_no_file_at_all(self, session):
        asset = make_video(session, storage_key="")
        assert probe_asset(asset) is None
        asset.refresh_from_db()
        assert asset.probe_error == "The asset has no file to probe."

    def test_an_admin_attached_file_is_probed_by_path(self, session, ffprobe):
        asset = make_video(
            session, storage_key="", file=SimpleUploadedFile("clip.mp4", b"mp4")
        )
        assert probe_asset(asset) == 120
        assert ffprobe.call_args.args[0] == asset.file.path
        # A remote storage has no path: the URL is what there is.
        with patch.object(FieldFile, "path", new_callable=PropertyMock) as path:
            path.side_effect = NotImplementedError
            assert probe_asset(asset) == 120
        assert ffprobe.call_args.args[0] == asset.file.url


@pytest.mark.django_db
class TestTaskAndTrigger:
    def test_task_messages(self, bucket, session, ffprobe):
        assert probe_asset_task(10**6) == "No such asset"
        asset = make_video(session)
        assert probe_asset_task(asset.pk) == f"Asset {asset.pk} runs 120 s"
        ffprobe.side_effect = ProbeError("boom")
        assert probe_asset_task(asset.pk) == f"Probe failed for asset {asset.pk}: boom"

    def test_task_is_routed_to_the_media_queue(self):
        assert django_settings.CELERY_TASK_ROUTES[
            "speakers.tasks.probe_asset_task"
        ] == {"queue": "media"}
        assert probe_asset_task.queue == "media"

    def test_a_ready_video_is_measured_and_the_length_rule_answers(
        self, bucket, session, ffprobe, django_capture_on_commit_callbacks
    ):
        """The whole chain: asset_ready queues the probe after commit, the
        probe saves 120 s, and the 1-minute limit blocks the item."""
        item = auto_item(session.conference, AutoRule.VIDEO_LENGTH_OK, session=session)
        asset = make_video(session)
        with django_capture_on_commit_callbacks(execute=True):
            asset_ready.send(sender=MediaAsset, asset=asset)
        asset.refresh_from_db()
        assert asset.duration_seconds == 120
        item.refresh_from_db()
        assert item.status == ItemStatus.BLOCKED
        assert "1:00 over the 1-minute limit" in item.note

    def test_only_videos_are_probed(
        self, bucket, session, ffprobe, django_capture_on_commit_callbacks
    ):
        asset = make_video(session, kind=MediaKind.TRANSCRIPT, language="en")
        with django_capture_on_commit_callbacks(execute=True):
            asset_ready.send(sender=MediaAsset, asset=asset)
        ffprobe.assert_not_called()
        asset.refresh_from_db()
        assert asset.duration_seconds is None and asset.probe_error == ""


@pytest.mark.django_db
class TestOnThePage:
    def test_the_failure_shows_on_both_sides(self, client, session, conference, bucket):
        performer = User.objects.create_user("p", email="p@x.org")
        presenter = session.session_presenters.first().presenter
        presenter.user = performer
        presenter.save()
        organizer = User.objects.create_user("o", email="o@x.org", is_staff=True)
        make_video(session, probe_error="ffprobe is not installed on the worker.")
        client.force_login(performer)
        html = client.get(f"/speakers/me/sessions/{session.slug}/").content.decode()
        assert "could not be checked automatically" in html
        client.force_login(organizer)
        html = client.get(f"/speakers/sessions/{session.slug}/").content.decode()
        assert "Length not measured: ffprobe is not installed" in html
