"""The duration probe (design §8.8, task 5.3).

A video that has just landed in the bucket is asked how long it is, with
``ffprobe`` reading the object's headers over a presigned link (a few
megabytes of a multi-gigabyte file), and the answer goes on the asset as
``duration_seconds``. Saving it re-runs the length rule, so "Check video
length is within limit" ticks or blocks within seconds of the upload.

The probe never fails quietly: a missing ``ffprobe``, a file it cannot
read, or an answer it cannot parse is recorded on the asset as
``probe_error`` (which the file rows show) and logged as an error, and the
asset stays READY with no duration, so nothing else about the file is in
doubt.
"""

import json
import logging
import subprocess

logger = logging.getLogger(__name__)

PROBE_TIMEOUT = 120


class ProbeError(Exception):
    """The probe could not answer; the message is fit to show on the page."""


def run_ffprobe(source, timeout=PROBE_TIMEOUT):
    """Return ``ffprobe``'s JSON for ``source`` (a path or a URL)."""
    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                source,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        raise ProbeError("ffprobe is not installed on the worker.")
    except subprocess.TimeoutExpired:
        raise ProbeError(f"ffprobe gave no answer within {timeout} seconds.")
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip().splitlines()
        raise ProbeError(
            "ffprobe could not read the file"
            + (f": {detail[-1][:300]}" if detail else ".")
        )
    return completed.stdout


def probe_duration(source):
    """How long the media at ``source`` runs, in whole seconds (rounded)."""
    output = run_ffprobe(source)
    try:
        seconds = float(json.loads(output)["format"]["duration"])
    except (ValueError, KeyError, TypeError):
        raise ProbeError("ffprobe answered without a duration.")
    return int(round(seconds))


def probe_asset(asset):
    """Probe one asset and record the answer, or the reason there is none.

    Returns the duration, or None when the probe failed (the failure is on
    the asset and in the log). Raised errors are reserved for the
    unexpected: a bug, not a bad file.
    """
    from .media import MediaStorageNotConfigured

    try:
        source = asset.download_url()
        if not source:
            raise ProbeError("The asset has no file to probe.")
        if not asset.storage_key and asset.file:
            # An admin-attached file on disk: probe the file itself, not
            # its URL, which is a bare path only a browser could resolve.
            # A remote storage has no path and its URL is complete.
            try:
                source = asset.file.path
            except NotImplementedError:
                pass
        duration = probe_duration(source)
    except (ProbeError, MediaStorageNotConfigured) as exc:
        message = str(exc)
        logger.error("Duration probe failed for asset %s: %s", asset.pk, message)
        asset.probe_error = message[:500]
        asset.save(update_fields=["probe_error", "modified_date"])
        return None
    asset.duration_seconds = duration
    asset.probe_error = ""
    asset.save(update_fields=["duration_seconds", "probe_error", "modified_date"])
    return duration
