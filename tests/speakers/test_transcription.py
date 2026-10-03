"""Machine transcription (design §8.8, task 5.7): the trigger, the
pipeline with a fake engine, the draft as an asset that ticks the item,
every failure on the row, the watchdog, and the controls on the page."""

import importlib
import subprocess
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import boto3
import numpy as np
import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from django_celery_beat.models import PeriodicTask
from moto import mock_aws

from speakers.checklists import instantiate_session_checklist
from speakers.constants import ItemStatus, MediaKind, MediaStatus, TranscriptionStatus
from speakers.media import MediaBucket, line_variants, record_asset
from speakers.models import (
    ActivityLog,
    ChecklistItem,
    MediaAsset,
    SpeakerSettings,
    TranscriptionJob,
)
from speakers.seeds import seed_checklists
from speakers.signals import asset_ready
from speakers.tasks import fail_stale_transcription_jobs_task, transcribe_asset_task
from speakers.transcription import (
    Engine,
    FasterWhisperEngine,
    TranscriptionError,
    extract_audio,
    fail_stale_jobs,
    get_engine,
    human_transcript_exists,
    load_samples,
    should_transcribe,
    start_job,
    transcribe,
    transcript_variant,
    write_vtt,
)

from .factories import add_presenter, make_presenter, make_session, make_settings

BUCKET = "test-speaker-media"
migration = importlib.import_module(
    "speakers.migrations.0015_exports_thumbnails_transcription"
)


class FakeEngine(Engine):
    name = "fake/tiny"

    def __init__(self, segments=None, language="en"):
        self.segments = (
            segments
            if segments is not None
            else [
                (0.0, 2.5, "Hello everyone."),
                (2.5, 5.0, "Welcome to PyJam."),
            ]
        )
        self.language = language
        self.calls = []

    def transcribe(self, audio_path, language):
        self.calls.append((audio_path, language))
        return self.segments, self.language


@pytest.fixture
def engine(settings, monkeypatch):
    """The portal has an engine, and it is a fake; ffmpeg's audio step
    writes a tiny file instead of running."""
    settings.SPEAKER_TRANSCRIBE_ENGINE = "local"
    fake = FakeEngine()
    monkeypatch.setattr("speakers.transcription.get_engine", lambda: fake)

    def fake_extract(source, out_path, timeout=0):
        with open(out_path, "wb") as f:
            f.write(b"\x00\x10" * 800)
        return out_path

    monkeypatch.setattr("speakers.transcription.extract_audio", fake_extract)
    return fake


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
def world(conference, bucket, organizer):
    """A PyJam set in English with the seeded post-production items and the
    edition's switch on."""
    make_settings(conference, auto_transcribe=True)
    seed_checklists(conference)
    session = make_session(conference, title="A PyJam set", kind="PYJAM", language="en")
    add_presenter(
        session, make_presenter(conference, display_name="Ada"), confirmed=True
    )
    instantiate_session_checklist(session)
    return {"session": session}


def video(session, **kwargs):
    kwargs.setdefault("kind", MediaKind.RAW_VIDEO)
    kwargs.setdefault("status", MediaStatus.READY)
    kwargs.setdefault(
        "storage_key", f"speaker-media/x/{session.slug}/raw_video/u/take.mp4"
    )
    kwargs.setdefault("original_filename", "take.mp4")
    kwargs.setdefault("content_type", "video/mp4")
    return MediaAsset.objects.create(session=session, **kwargs)


def item(session, title):
    return ChecklistItem.objects.get(session=session, presenter=None, title=title)


class TestPieces:
    def test_vtt(self):
        text = write_vtt(
            [
                (0, 2.5, " Hello "),
                (2.5, 2.6, "Short"),
                (3, 4, ""),
                (3661.5, 3663, "Late"),
            ]
        )
        assert text.startswith(
            "WEBVTT\n\n1\n00:00:00.000 --> 00:00:02.500\nHello\n\n2\n"
        )
        assert (
            "00:00:02.500 --> 00:00:03.000\nShort" in text
        )  # never shorter than half a second
        assert "01:01:01.500 --> 01:01:03.000\nLate" in text
        assert text.count("-->") == 3

    def test_engine_factory(self, settings):
        settings.SPEAKER_TRANSCRIBE_ENGINE = ""
        assert get_engine() is None
        settings.SPEAKER_TRANSCRIBE_ENGINE = "local"
        settings.SPEAKER_TRANSCRIBE_MODEL = "tiny"
        engine = get_engine()
        assert (
            isinstance(engine, FasterWhisperEngine)
            and engine.name == "faster-whisper/tiny"
        )
        settings.SPEAKER_TRANSCRIBE_ENGINE = "cloud"
        with pytest.raises(TranscriptionError, match="Unknown transcription engine"):
            get_engine()

    def test_faster_whisper_engine_with_the_library_mocked(self, settings, tmp_path):
        segment = SimpleNamespace(start=0.0, end=1.0, text=" hi ")
        model = MagicMock()
        model.transcribe.return_value = (
            iter([segment]),
            SimpleNamespace(language="pt"),
        )
        raw = tmp_path / "a.raw"
        raw.write_bytes(np.array([0, 16384, -16384], dtype=np.int16).tobytes())
        with patch("speakers.transcription._load_model", return_value=model) as load:
            engine = FasterWhisperEngine("small", "/opt/whisper")
            assert engine.transcribe(str(raw), "") == ([(0.0, 1.0, "hi")], "pt")
            assert engine.transcribe(str(raw), "en")[1] == "en"
        load.assert_called_once_with("small", "/opt/whisper")
        args, kwargs = model.transcribe.call_args
        assert kwargs == {"language": "en", "vad_filter": True, "beam_size": 5}
        assert list(args[0]) == pytest.approx([0.0, 0.5, -0.5])
        (tmp_path / "empty.raw").write_bytes(b"")
        with pytest.raises(TranscriptionError, match="audio is empty"):
            load_samples(str(tmp_path / "empty.raw"))

    def test_loading_the_model_names_what_is_missing(self, tmp_path):
        from speakers.transcription import _load_model

        # The library missing, the model folder missing, the model broken.
        with patch.dict("sys.modules", {"faster_whisper": None}):
            with pytest.raises(TranscriptionError, match="not installed"):
                _load_model("small", str(tmp_path))
        fake_module = SimpleNamespace(WhisperModel=MagicMock(return_value="model"))
        with patch.dict("sys.modules", {"faster_whisper": fake_module}):
            with pytest.raises(TranscriptionError, match="is not in the image"):
                _load_model("small", str(tmp_path))
            (tmp_path / "small").mkdir()
            assert _load_model("small", str(tmp_path)) == "model"
            fake_module.WhisperModel.assert_called_with(
                str(tmp_path / "small"), device="cpu", compute_type="int8"
            )
            fake_module.WhisperModel.side_effect = RuntimeError("corrupt")
            with pytest.raises(
                TranscriptionError, match="could not be loaded: corrupt"
            ):
                _load_model("small", str(tmp_path))

    def test_audio_extraction_failures_are_named(self, tmp_path):
        with patch(
            "speakers.transcription.subprocess.run", side_effect=FileNotFoundError
        ):
            with pytest.raises(TranscriptionError, match="not installed"):
                extract_audio("x.mp4", str(tmp_path / "a.ogg"))
        with patch(
            "speakers.transcription.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=1),
        ):
            with pytest.raises(TranscriptionError, match="no audio within"):
                extract_audio("x.mp4", str(tmp_path / "a.ogg"), timeout=1)
        failed = subprocess.CompletedProcess(
            args=[], returncode=1, stdout=b"", stderr=b"bad input\n"
        )
        with patch("speakers.transcription.subprocess.run", return_value=failed):
            with pytest.raises(
                TranscriptionError, match="could not extract the audio: bad input"
            ):
                extract_audio("x.mp4", str(tmp_path / "a.ogg"))
        ok = subprocess.CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b"")
        with patch("speakers.transcription.subprocess.run", return_value=ok) as run:
            assert extract_audio("x.mp4", str(tmp_path / "a.ogg")).endswith("a.ogg")
        assert "s16le" in run.call_args.args[0] and "16000" in run.call_args.args[0]


@pytest.mark.django_db
class TestPipeline:
    def test_a_ready_video_becomes_a_draft_transcript(
        self, world, engine, bucket, django_capture_on_commit_callbacks
    ):
        session = world["session"]
        transcribe_item = item(session, "Transcribe")
        review = item(session, "Review transcript")
        raw = video(session)
        with django_capture_on_commit_callbacks(execute=True):
            asset_ready.send(sender=MediaAsset, asset=raw)
        job = TranscriptionJob.objects.get()
        assert job.status == TranscriptionStatus.DONE and job.engine == "fake/tiny"
        draft = job.output
        assert draft.kind == MediaKind.TRANSCRIPT and draft.language == "en"
        assert draft.version == 1 and draft.generated_by == "fake/tiny"
        assert draft.original_filename == "take-en.vtt"
        assert draft.variant == f"take-{raw.pk}"
        assert draft.title == "Machine transcript of take.mp4"
        stored = bucket.client.get_object(Bucket=BUCKET, Key=draft.storage_key)
        assert stored["ContentType"] == "text/vtt"
        assert b"Welcome to PyJam." in stored["Body"].read()
        assert engine.calls[0][1] == "en" and engine.calls[0][0].endswith("audio.raw")
        transcribe_item.refresh_from_db()
        review.refresh_from_db()
        assert transcribe_item.status == ItemStatus.DONE
        assert review.status == ItemStatus.TODO

    def test_detected_language_when_the_session_has_none(self, world, engine, bucket):
        session = world["session"]
        session.language = ""
        session.save()
        engine.language = "pt"
        job = start_job(video(session))
        assert str(job) == f"Transcription {job.pk} of {job.asset}"
        transcribe(job.pk)
        job.refresh_from_db()
        assert job.output.language == "pt" and job.output.original_filename.endswith(
            "-pt.vtt"
        )

    def test_each_video_gets_its_own_transcript(self, world, engine, bucket):
        session = world["session"]
        videos = [
            video(session, original_filename=name)
            for name in ("video1.mpg", "video2.mpg")
        ]
        drafts = []
        for raw in videos:
            job = start_job(raw)
            transcribe(job.pk)
            job.refresh_from_db()
            drafts.append(job.output)
        assert [d.original_filename for d in drafts] == [
            "video1-en.vtt",
            "video2-en.vtt",
        ]
        assert [d.variant for d in drafts] == [
            f"video1-{videos[0].pk}",
            f"video2-{videos[1].pk}",
        ]
        assert [d.version for d in drafts] == [1, 1]
        assert all(d.status == MediaStatus.READY for d in drafts)
        # Transcribing the same video again is the next version of its own file.
        job = start_job(videos[0])
        transcribe(job.pk)
        job.refresh_from_db()
        drafts[0].refresh_from_db()
        assert job.output.version == 2 and job.output.variant == drafts[0].variant
        assert drafts[0].status == MediaStatus.SUPERSEDED

    def test_names_that_agree_past_the_column_or_across_kinds_stay_apart(
        self, world, engine, bucket
    ):
        session = world["session"]
        long_a = "PyLadiesCon-2026-keynote-recording-final-v2.mp4"
        long_b = "PyLadiesCon-2026-keynote-recording-final-v3.mp4"
        raws = [
            video(session, original_filename=long_a),
            video(session, original_filename=long_b),
            video(session, original_filename="take.mp4"),
            video(
                session, original_filename="take.mp4", kind=MediaKind.PROCESSED_VIDEO
            ),
        ]
        variants = []
        for raw in raws:
            job = start_job(raw)
            transcribe(job.pk)
            job.refresh_from_db()
            assert job.output.version == 1 and len(job.output.variant) <= 40
            variants.append(job.output.variant)
        assert len(set(variants)) == 4
        assert not MediaAsset.objects.filter(status=MediaStatus.SUPERSEDED).exists()

    def test_a_video_without_a_file_name_is_named_after_the_session(
        self, world, engine, bucket
    ):
        session = world["session"]
        raw = video(session, original_filename="")
        job = start_job(raw)
        transcribe(job.pk)
        job.refresh_from_db()
        assert job.output.original_filename == f"{session.slug}-en.vtt"
        assert job.output.variant == f"video-{raw.pk}"

    def test_a_reviewed_transcript_replaces_the_draft_on_its_line(
        self, world, engine, bucket
    ):
        session = world["session"]
        first = video(session, original_filename="video1.mpg")
        second = video(session, original_filename="video2.mpg")
        job = start_job(first)
        transcribe(job.pk)
        job.refresh_from_db()
        draft = job.output
        # The reviewer picks the draft's variant in the panel: the next version.
        reviewed = record_asset(
            session=session,
            kind=MediaKind.TRANSCRIPT,
            language="en",
            variant=draft.variant,
            storage_key="k",
            filename="corrected.vtt",
            content_type="text/vtt",
            size_bytes=1,
        )
        draft.refresh_from_db()
        assert reviewed.version == 2 and draft.status == MediaStatus.SUPERSEDED
        assert not should_transcribe(first)
        assert should_transcribe(second)

    def test_a_session_wide_reviewed_transcript_bars_no_video(
        self, world, engine, bucket
    ):
        session = world["session"]
        MediaAsset.objects.create(
            session=session,
            kind=MediaKind.TRANSCRIPT,
            language="en",
            status=MediaStatus.READY,
            storage_key="k",
            version=1,
        )
        assert should_transcribe(video(session, original_filename="video2.mpg"))

    def test_a_reviewed_transcript_is_never_overwritten(self, world, engine, bucket):
        session = world["session"]
        raw = video(session)
        variant = transcript_variant(raw)
        assert should_transcribe(raw)
        MediaAsset.objects.create(
            session=session,
            kind=MediaKind.TRANSCRIPT,
            language="en",
            variant=variant,
            status=MediaStatus.READY,
            storage_key="k",
            version=1,
        )
        assert human_transcript_exists(
            session, "en", variant
        ) and not should_transcribe(raw)
        # A machine draft in the way is no bar: the next video gets a fresh draft.
        MediaAsset.objects.filter(kind=MediaKind.TRANSCRIPT).update(
            generated_by="fake/tiny"
        )
        assert should_transcribe(raw)
        # And a reviewed second version on top of a draft is again a bar.
        MediaAsset.objects.create(
            session=session,
            kind=MediaKind.TRANSCRIPT,
            language="en",
            variant=variant,
            status=MediaStatus.READY,
            storage_key="k2",
            version=2,
        )
        assert not should_transcribe(raw)

    def test_switch_off_or_no_engine_means_no_job(
        self, world, engine, bucket, settings, django_capture_on_commit_callbacks
    ):
        session = world["session"]
        SpeakerSettings.objects.filter(conference=session.conference).update(
            auto_transcribe=False
        )
        with django_capture_on_commit_callbacks(execute=True):
            asset_ready.send(sender=MediaAsset, asset=video(session))
        assert not TranscriptionJob.objects.exists()
        SpeakerSettings.objects.filter(conference=session.conference).update(
            auto_transcribe=True
        )
        settings.SPEAKER_TRANSCRIBE_ENGINE = ""
        # Asked for, but no engine: a failed job says so on the row rather
        # than nothing happening at all.
        asked = video(session, storage_key="k2")
        assert should_transcribe(asked)
        with patch("speakers.transcription.get_engine", return_value=None):
            with django_capture_on_commit_callbacks(execute=True):
                asset_ready.send(sender=MediaAsset, asset=asked)
        job = TranscriptionJob.objects.get()
        assert job.status == TranscriptionStatus.FAILED
        assert "no transcription engine" in job.error.lower()
        job.delete()
        # A processed video or an image never triggers the automatic run.
        settings.SPEAKER_TRANSCRIBE_ENGINE = "local"
        assert not should_transcribe(
            video(session, kind=MediaKind.PROCESSED_VIDEO, storage_key="k3")
        )

    def test_failures_land_on_the_row_and_in_the_activity(
        self, world, engine, bucket, monkeypatch
    ):
        session = world["session"]
        raw = video(session)
        # Silence is a failure too, not an empty file.
        engine.segments = []
        job = start_job(raw)
        assert "failed" in transcribe(job.pk)
        job.refresh_from_db()
        assert job.status == TranscriptionStatus.FAILED
        assert "heard no speech" in job.error
        assert ActivityLog.objects.filter(action="transcription.failed").exists()
        assert item(session, "Transcribe").status == ItemStatus.TODO
        # A missing ffmpeg.
        monkeypatch.setattr(
            "speakers.transcription.extract_audio",
            MagicMock(
                side_effect=TranscriptionError("ffmpeg is not installed on the worker.")
            ),
        )
        job2 = start_job(raw)
        transcribe(job2.pk)
        job2.refresh_from_db()
        assert job2.error == "ffmpeg is not installed on the worker."
        # And no engine after all.
        job3 = start_job(raw)
        with patch("speakers.transcription.get_engine", return_value=None):
            transcribe(job3.pk)
        job3.refresh_from_db()
        assert "No transcription engine" in job3.error
        # A bug inside the engine is a failure on the row, never a job left RUNNING.
        job4 = start_job(raw)
        with patch(
            "speakers.transcription.run_job", side_effect=TypeError("bad kwarg")
        ):
            assert "crashed" in transcribe(job4.pk)
        job4.refresh_from_db()
        assert (
            job4.status == TranscriptionStatus.FAILED
            and "TypeError: bad kwarg" in job4.error
        )

    def test_a_job_delivered_twice_does_not_run_twice(self, world, engine, bucket):
        raw = video(world["session"])
        job = start_job(raw)
        TranscriptionJob.objects.filter(pk=job.pk).update(
            status=TranscriptionStatus.RUNNING
        )
        assert "had died" in transcribe_asset_task(job.pk)
        job.refresh_from_db()
        assert (
            job.status == TranscriptionStatus.FAILED and "worker stopped" in job.error
        )
        assert engine.calls == []
        assert transcribe(job.pk) == f"Job {job.pk} is FAILED"
        assert transcribe(10**6) == "No such job"

    def test_the_watchdog(self, world, engine, bucket):
        raw = video(world["session"])
        stale = start_job(raw)
        fresh = start_job(raw)
        TranscriptionJob.objects.filter(pk=stale.pk).update(
            creation_date=timezone.now() - timedelta(hours=13)
        )
        assert (
            fail_stale_transcription_jobs_task()
            == "Failed 1 stale transcription job(s)"
        )
        stale.refresh_from_db()
        fresh.refresh_from_db()
        assert (
            stale.status == TranscriptionStatus.FAILED and "worker-media" in stale.error
        )
        assert fresh.status == TranscriptionStatus.QUEUED
        assert fail_stale_jobs() == 0
        migration.seed_stale_jobs_task(apps, None)
        migration.seed_stale_jobs_task(apps, None)
        task = PeriodicTask.objects.get(name=migration.STALE_TASK_NAME)
        assert task.task == fail_stale_transcription_jobs_task.name
        migration.unseed_stale_jobs_task(apps, None)
        assert not PeriodicTask.objects.filter(name=migration.STALE_TASK_NAME).exists()

    def test_routing(self):
        from django.conf import settings as django_settings

        assert django_settings.CELERY_TASK_ROUTES[
            "speakers.tasks.transcribe_asset_task"
        ] == {"queue": "media"}
        # The queue is declared once, in the routes; acks_late on the task.
        assert transcribe_asset_task.acks_late


@pytest.mark.django_db
class TestOnThePage:
    def test_transcribe_this_retry_and_the_badge(
        self, client, world, engine, bucket, organizer
    ):
        session = world["session"]
        raw = video(session)
        url = reverse("speakers:media_transcribe", args=[session.slug, raw.pk])
        client.force_login(organizer)
        html = client.get(session.get_absolute_url()).content.decode()
        assert "Transcribe this" in html
        response = client.post(url, headers={"HX-Request": "true"})
        assert response.status_code == 200
        job = TranscriptionJob.objects.get()
        assert job.started_by == organizer and job.status == TranscriptionStatus.DONE
        html = client.get(session.get_absolute_url()).content.decode()
        assert "machine draft" in html and "fake/tiny" in html
        # A failed job offers a retry and shows why; an open one offers nothing.
        TranscriptionJob.objects.filter(pk=job.pk).update(
            status=TranscriptionStatus.FAILED,
            error="ffmpeg is not installed on the worker.",
        )
        html = client.get(session.get_absolute_url()).content.decode()
        assert "Retry the transcription" in html and "Transcription failed" in html
        TranscriptionJob.objects.filter(pk=job.pk).update(
            status=TranscriptionStatus.RUNNING, started_at=timezone.now()
        )
        html = client.get(session.get_absolute_url()).content.decode()
        assert "Transcribing, started" in html and "Transcribe this" not in html
        response = client.post(url, follow=True)
        assert "already under way" in response.content.decode()
        assert TranscriptionJob.objects.count() == 1

    def test_the_panel_offers_the_variants_already_on_the_session(
        self, client, world, engine, bucket, organizer
    ):
        session = world["session"]
        job = start_job(video(session, original_filename="video1.mpg"))
        transcribe(job.pk)
        job.refresh_from_db()
        assert line_variants(session) == [job.output.variant]
        client.force_login(organizer)
        html = client.get(session.get_absolute_url()).content.decode()
        assert f'<option value="{job.output.variant}">' in html
        assert "Pick a listed variant to replace a machine transcript" in html

    def test_refusals(self, client, world, engine, bucket, organizer, settings):
        session = world["session"]
        raw = video(session)
        url = reverse("speakers:media_transcribe", args=[session.slug, raw.pk])
        speaker = User.objects.create_user("ada", email="ada@x.org")
        client.force_login(speaker)
        assert client.post(url).status_code == 403
        client.force_login(organizer)
        poster = MediaAsset.objects.create(
            session=session,
            kind=MediaKind.PROMO,
            status=MediaStatus.READY,
            storage_key="p",
        )
        assert (
            client.post(
                reverse("speakers:media_transcribe", args=[session.slug, poster.pk])
            ).status_code
            == 404
        )
        settings.SPEAKER_TRANSCRIBE_ENGINE = ""
        html = client.get(session.get_absolute_url()).content.decode()
        assert "Transcribe this" not in html

    def test_no_engine_says_so(
        self, client, world, bucket, organizer, monkeypatch, settings
    ):
        session = world["session"]
        raw = video(session)
        settings.SPEAKER_TRANSCRIBE_ENGINE = "local"
        monkeypatch.setattr("speakers.transcription.get_engine", lambda: None)
        client.force_login(organizer)
        response = client.post(
            reverse("speakers:media_transcribe", args=[session.slug, raw.pk]),
            follow=True,
        )
        assert "no transcription engine" in response.content.decode()
        # The button leaves the same record the automatic trigger would:
        # a failed job that says why.
        job = raw.transcription_jobs.get()
        assert job.status == TranscriptionStatus.FAILED
        assert "SPEAKER_TRANSCRIBE_ENGINE" in job.error
        assert job.started_by == organizer

    def test_the_performer_reads_what_happens_to_the_recording(
        self, client, world, engine, conference
    ):
        session = world["session"]
        performer = User.objects.create_user("bea", email="bea@x.org")
        add_presenter(
            session, make_presenter(conference, user=performer), confirmed=True
        )
        client.force_login(performer)
        html = client.get(
            reverse("speakers:my_session_detail", args=[session.slug])
        ).content.decode()
        assert "transcribed by the portal's own tooling" in html
        SpeakerSettings.objects.filter(conference=conference).update(
            auto_transcribe=False
        )
        html = client.get(
            reverse("speakers:my_session_detail", args=[session.slug])
        ).content.decode()
        assert "transcribed by the portal's own tooling" not in html

    def test_admin_form_offers_the_switch(self, client, world, conference):
        admin = User.objects.create_superuser("root", "root@x.org", "pw")
        client.force_login(admin)
        row = SpeakerSettings.objects.get(conference=conference)
        html = client.get(
            reverse("admin:speakers_speakersettings_change", args=[row.pk])
        ).content.decode()
        assert 'name="auto_transcribe"' in html
