"""Machine transcription (design §8.8, "Machine transcription", task 5.7).

A raw video that lands gets a draft transcript: ffmpeg pulls the audio
from the presigned link into a small Opus file, the engine turns it into
timed segments, and the segments become a WebVTT ``TRANSCRIPT`` asset
on the session, marked as machine-made. The "Transcribe" checklist item
ticks itself on the asset like any other; "Review transcript" stays a
person's job, and the reviewed file goes up as the next version.

The engine is Whisper running in the portal's own worker (faster-whisper,
CPU, int8), reading a model baked into the image; nothing leaves the
portal's infrastructure. It sits behind a small interface so another
engine could be added, but none is.
"""

import logging
import os
import subprocess
import tempfile
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .constants import MediaKind, MediaStatus, TranscriptionStatus
from .media import MediaBucket, MediaStorageNotConfigured, record_asset
from .models import ActivityLog, MediaAsset, SpeakerSettings, TranscriptionJob

logger = logging.getLogger(__name__)

FFMPEG_TIMEOUT = 30 * 60


class TranscriptionError(Exception):
    """The job could not finish; the message is fit to show on the row."""


# ---- Engines --------------------------------------------------------------


class Engine:
    """What the pipeline needs from a transcriber: a name for the record,
    and ``transcribe(audio_path, language)`` returning ``(segments,
    language)``, segments being ``(start, end, text)`` in seconds."""

    name = ""

    def transcribe(self, audio_path, language):  # pragma: no cover - interface
        raise NotImplementedError


def model_path(model_name, model_dir):
    """Where the image keeps a model: its own folder under the model
    directory, as the Dockerfile's download puts it."""
    return os.path.join(model_dir, model_name)


def _load_model(model_name, model_dir):
    """The faster-whisper model from the image's own folder, loaded by path
    so the library never looks at the network or a cache. Imported here so
    the web process never loads the library."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise TranscriptionError(
            "faster-whisper is not installed on the worker (requirements-media.txt)."
        )
    path = model_path(model_name, model_dir)
    if not os.path.isdir(path):
        raise TranscriptionError(
            f"The Whisper model '{model_name}' is not in the image at {path}; "
            "build it with WHISPER_MODEL set."
        )
    try:
        return WhisperModel(path, device="cpu", compute_type="int8")
    except Exception as exc:  # the library raises assorted types
        raise TranscriptionError(
            f"The Whisper model at {path} could not be loaded: {exc}"[:400]
        )


class FasterWhisperEngine(Engine):
    """Whisper on CTranslate2 in the worker."""

    def __init__(self, model_name, model_dir):
        self.model_name = model_name
        self.model_dir = model_dir
        self.name = f"faster-whisper/{model_name}"
        self._model = None

    def transcribe(self, audio_path, language):
        if self._model is None:
            self._model = _load_model(self.model_name, self.model_dir)
        segments, info = self._model.transcribe(
            load_samples(audio_path),
            language=language or None,
            vad_filter=True,
            beam_size=5,
        )
        rows = [(seg.start, seg.end, seg.text.strip()) for seg in segments]
        return rows, (language or getattr(info, "language", "") or "")


def load_samples(audio_path):
    """The raw file ``extract_audio`` wrote, as the float array the engine
    takes; imported here so the web process never loads numpy for it."""
    import numpy as np

    samples = np.fromfile(audio_path, dtype=np.int16)
    if samples.size == 0:
        raise TranscriptionError("The extracted audio is empty.")
    return samples.astype(np.float32) / 32768.0


def get_engine():
    """The configured engine, or None when the portal has none."""
    name = settings.SPEAKER_TRANSCRIBE_ENGINE
    if not name:
        return None
    if name == "local":
        return FasterWhisperEngine(
            settings.SPEAKER_TRANSCRIBE_MODEL, settings.SPEAKER_TRANSCRIBE_MODEL_DIR
        )
    raise TranscriptionError(f"Unknown transcription engine '{name}'.")


# ---- Audio and VTT ----------------------------------------------------------


SAMPLE_RATE = 16000


def extract_audio(source, out_path, timeout=FFMPEG_TIMEOUT):
    """The audio of ``source`` (a path or a URL) as raw 16 kHz mono 16-bit
    samples in ``out_path`` (about 57 MB for a 30-minute set, gone with
    the temp folder), without the video ever touching the disk. Raw
    samples, so the engine decodes nothing itself: its own decoder
    (PyAV) is the one piece whose versions drift under it."""
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-i",
        source,
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        "-f",
        "s16le",
        "-c:a",
        "pcm_s16le",
        out_path,
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, timeout=timeout, check=False
        )
    except FileNotFoundError:
        raise TranscriptionError("ffmpeg is not installed on the worker.")
    except subprocess.TimeoutExpired:
        raise TranscriptionError(f"ffmpeg gave no audio within {timeout} seconds.")
    if completed.returncode != 0:
        detail = (completed.stderr or b"").decode("utf-8", "replace").strip()
        last = detail.splitlines()[-1][:300] if detail else ""
        raise TranscriptionError(
            "ffmpeg could not extract the audio" + (f": {last}" if last else ".")
        )
    return out_path


def _stamp(seconds):
    seconds = max(0.0, float(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{secs:06.3f}"


def write_vtt(segments):
    """WebVTT text for ``(start, end, text)`` segments; empty text is
    skipped, a cue never ends before it starts."""
    lines = ["WEBVTT", ""]
    number = 0
    for start, end, text in segments:
        text = (text or "").strip()
        if not text:
            continue
        number += 1
        end = max(float(end), float(start) + 0.5)
        lines += [str(number), f"{_stamp(start)} --> {_stamp(end)}", text, ""]
    return "\n".join(lines)


# ---- Deciding and running ---------------------------------------------------


def auto_transcribe(conference):
    """Whether the edition asked for drafts. Whether the portal can make
    them is the engine's business: an edition that asked while no engine
    is set up gets a failed job that says so, not silence."""
    return SpeakerSettings.objects.filter(
        conference=conference, auto_transcribe=True
    ).exists()


def human_transcript_exists(session, language):
    """Whether the newest transcript on the line is a person's: a reviewed
    file is never overwritten by a re-upload of the video."""
    newest = (
        MediaAsset.objects.filter(
            session=session, kind=MediaKind.TRANSCRIPT, language=language
        )
        .exclude(status=MediaStatus.FAILED)
        .order_by("-version", "-id")
        .first()
    )
    return newest is not None and not newest.is_machine_made


def should_transcribe(asset):
    """The automatic trigger: a READY raw video, the switch on, and no
    reviewed transcript in the way."""
    return (
        asset.kind == MediaKind.RAW_VIDEO
        and asset.is_ready
        and bool(asset.storage_key)
        and auto_transcribe(asset.session.conference)
        and not human_transcript_exists(asset.session, asset.session.language)
    )


def start_job(asset, user=None):
    """Record a job and hand it to the media worker once the row is
    committed. Without an engine the job is recorded failed on the spot,
    so the row and the activity say why nothing happened."""
    engine = get_engine()
    if engine is None:
        return TranscriptionJob.objects.create(
            asset=asset,
            engine=settings.SPEAKER_TRANSCRIBE_ENGINE or "",
            language=asset.session.language,
            started_by=user,
            status=TranscriptionStatus.FAILED,
            error=(
                "This portal has no transcription engine set up "
                "(SPEAKER_TRANSCRIBE_ENGINE)."
            ),
        )
    job = TranscriptionJob.objects.create(
        asset=asset,
        engine=engine.name,
        language=asset.session.language,
        started_by=user,
    )
    from .tasks import transcribe_asset_task

    transaction.on_commit(lambda: transcribe_asset_task.delay(job.pk))
    return job


def run_job(job):
    """The pipeline for one job; the caller (the task) handles the row's
    state around it and every failure."""
    asset = job.asset
    engine = get_engine()
    if engine is None:
        raise TranscriptionError("No transcription engine is configured.")
    bucket = MediaBucket.from_settings()
    with tempfile.TemporaryDirectory() as folder:
        audio = extract_audio(asset.download_url(), f"{folder}/audio.raw")
        segments, language = engine.transcribe(audio, job.language)
    if not segments:
        raise TranscriptionError("The engine heard no speech in the video.")
    language = (language or job.language or "")[:10]
    vtt = write_vtt(segments).encode("utf-8")
    key = f"{asset.storage_key.rsplit('/', 1)[0]}/transcript-{job.pk}.vtt"
    bucket.client.put_object(
        Bucket=bucket.bucket, Key=key, Body=vtt, ContentType="text/vtt"
    )
    return record_asset(
        session=asset.session,
        kind=MediaKind.TRANSCRIPT,
        language=language,
        storage_key=key,
        filename=f"{asset.session.slug}-{language or 'transcript'}.vtt",
        content_type="text/vtt",
        size_bytes=len(vtt),
        generated_by=engine.name,
        title=f"Machine transcript of {asset.display_title}"[:200],
    )


def transcribe(job_id):
    """Run one job: RUNNING, then DONE with its output or FAILED with the
    reason on the row and in the session's activity. A job delivered
    again while RUNNING (a worker died) ends FAILED rather than running
    twice."""
    job = (
        TranscriptionJob.objects.select_related("asset__session__conference")
        .filter(pk=job_id)
        .first()
    )
    if job is None:
        return "No such job"
    if job.status == TranscriptionStatus.RUNNING:
        _fail(job, "The worker stopped while transcribing; try again.")
        return f"Job {job_id} had died"
    if job.status != TranscriptionStatus.QUEUED:
        return f"Job {job_id} is {job.status}"
    job.status = TranscriptionStatus.RUNNING
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at", "modified_date"])
    try:
        output = run_job(job)
    except (TranscriptionError, MediaStorageNotConfigured) as exc:
        _fail(job, str(exc))
        return f"Job {job_id} failed: {exc}"
    except Exception as exc:  # noqa: BLE001 - a bug must not leave the row RUNNING
        logger.exception("Transcription job %s crashed", job.pk)
        _fail(job, f"{type(exc).__name__}: {exc}"[:500])
        return f"Job {job_id} crashed: {exc}"
    job.status = TranscriptionStatus.DONE
    job.output = output
    job.finished_at = timezone.now()
    job.error = ""
    job.save(
        update_fields=["status", "output", "finished_at", "error", "modified_date"]
    )
    return f"Job {job_id} made asset {output.pk}"


def _fail(job, reason):
    logger.error("Transcription job %s failed: %s", job.pk, reason)
    job.status = TranscriptionStatus.FAILED
    job.error = reason[:500]
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "error", "finished_at", "modified_date"])
    ActivityLog.record(
        job.asset.session.conference,
        "transcription.failed",
        target=job.asset.session,
        message=f"Transcription failed for {job.asset.display_title}: {reason}"[:500],
    )


def fail_stale_jobs(now=None):
    """Jobs still QUEUED after ``SPEAKER_TRANSCRIBE_STALE_HOURS``: nobody is
    consuming the media queue (the process is at zero replicas), which is
    how a forgotten worker shows on the page. Returns how many."""
    now = now or timezone.now()
    limit = now - timedelta(hours=settings.SPEAKER_TRANSCRIBE_STALE_HOURS)
    count = 0
    for job in TranscriptionJob.objects.filter(
        status=TranscriptionStatus.QUEUED, creation_date__lt=limit
    ).select_related("asset__session"):
        _fail(job, "No media worker picked this up; is worker-media running?")
        count += 1
    return count
