"""Thumbnails made by the media worker (design §8.8, previews, task 5.8).

A file that has just landed gets a small JPEG next to it in the bucket:
an image is scaled with Pillow, a video yields one frame a few seconds
in through ffmpeg reading the presigned link. The key goes on the asset
and the pages that list files show it, with the preview fold opening
the full file. Audio gets no picture, only an icon.

Like the probe, it never fails quietly and never blocks the asset: what
went wrong is written on the row as ``thumbnail_error`` and logged.
"""

import io
import logging
import subprocess

from PIL import Image, UnidentifiedImageError

from .media import MediaBucket, MediaStorageNotConfigured

logger = logging.getLogger(__name__)

SIZE = 480
QUALITY = 78
FFMPEG_TIMEOUT = 180
FRAME_AT = 3  # seconds in: past any black lead-in, before the clip is over


class ThumbnailError(Exception):
    """No thumbnail could be made; the message is fit to show on the row."""


def run_ffmpeg(source, seek=FRAME_AT, timeout=FFMPEG_TIMEOUT):
    """One frame of ``source`` (a path or a URL) as JPEG bytes, ``seek``
    seconds in, scaled to the thumbnail width."""
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-ss",
        str(seek),
        "-i",
        source,
        "-frames:v",
        "1",
        "-vf",
        f"scale={SIZE}:-2",
        "-q:v",
        "6",
        "-f",
        "image2",
        "-c:v",
        "mjpeg",
        "pipe:1",
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, timeout=timeout, check=False
        )
    except FileNotFoundError:
        raise ThumbnailError("ffmpeg is not installed on the worker.")
    except subprocess.TimeoutExpired:
        raise ThumbnailError(f"ffmpeg gave no frame within {timeout} seconds.")
    if completed.returncode != 0 or not completed.stdout:
        detail = (completed.stderr or b"").decode("utf-8", "replace").strip()
        last = detail.splitlines()[-1][:300] if detail else ""
        raise ThumbnailError(
            "ffmpeg could not take a frame" + (f": {last}" if last else ".")
        )
    return completed.stdout


def video_thumbnail(source):
    """A frame a few seconds in, or the first one when the clip is shorter."""
    try:
        return run_ffmpeg(source, FRAME_AT)
    except ThumbnailError as first:
        if "could not take a frame" not in str(first):
            raise
        return run_ffmpeg(source, 0)


def image_thumbnail(data):
    """``data`` (an image file's bytes) scaled to fit the thumbnail box,
    as JPEG bytes."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            image.thumbnail((SIZE, SIZE))
            out = io.BytesIO()
            image.save(out, "JPEG", quality=QUALITY, optimize=True)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ThumbnailError(f"The image could not be read: {exc}"[:300])
    return out.getvalue()


def thumbnail_key(asset):
    return f"{asset.storage_key}.thumb.jpg"


def make_thumbnail(asset):
    """Make and store the asset's thumbnail, or record why there is none.

    Returns the key, or None when it failed (the reason is on the asset
    and in the log). Only images and videos in the bucket; anything else
    is left alone.
    """
    if asset.preview_kind not in ("image", "video") or not asset.storage_key:
        return None
    try:
        bucket = MediaBucket.from_settings()
        if asset.preview_kind == "image":
            body = bucket.client.get_object(Bucket=bucket.bucket, Key=asset.storage_key)
            data = image_thumbnail(body["Body"].read())
        else:
            data = video_thumbnail(asset.download_url())
        key = thumbnail_key(asset)
        bucket.client.put_object(
            Bucket=bucket.bucket, Key=key, Body=data, ContentType="image/jpeg"
        )
    except (ThumbnailError, MediaStorageNotConfigured) as exc:
        logger.error("Thumbnail failed for asset %s: %s", asset.pk, exc)
        asset.thumbnail_error = str(exc)[:500]
        asset.save(update_fields=["thumbnail_error", "modified_date"])
        return None
    asset.thumbnail_key = key
    asset.thumbnail_error = ""
    asset.save(update_fields=["thumbnail_key", "thumbnail_error", "modified_date"])
    return key
