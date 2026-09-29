"""Object storage for speaker media, and the multipart upload lifecycle
(design §8.8, task 5.1).

Performance videos are routinely several gigabytes, so the browser sends
the parts straight to a private bucket with presigned URLs; the portal only
starts the upload, hands out URLs in batches, finalizes it and records the
``MediaAsset``. ``MediaBucket`` is the one place that talks to the bucket;
everything else here is the lifecycle around a ``MediaUpload`` row.
"""

import math
import re
import uuid
from datetime import timedelta

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .constants import UPLOAD_PART_URL_BATCH, MediaKind, MediaStatus, UploadStatus
from .models import MediaAsset, MediaUpload, SpeakerSettings
from .permissions import is_speaker_organizer
from .signals import asset_ready

# S3 limits: at least 5 MiB per part except the last, at most 10,000 parts.
MIN_PART_SIZE = 5 * 1024 * 1024
MAX_PARTS = 10_000


class MediaStorageNotConfigured(Exception):
    """No bucket is configured: uploads are off for this deployment."""


class UploadError(ValueError):
    """A request the lifecycle refuses; the message is for the caller."""


class MediaBucket:
    """The private bucket, through boto3. Built from settings, or handed a
    client and bucket name by a test."""

    def __init__(self, bucket, prefix, client):
        self.bucket = bucket
        self.prefix = prefix
        self.client = client

    @classmethod
    def from_settings(cls):
        bucket = settings.SPEAKER_MEDIA_BUCKET
        if not bucket:
            raise MediaStorageNotConfigured("SPEAKER_MEDIA_BUCKET is not set.")
        client = boto3.client(
            "s3",
            endpoint_url=settings.SPEAKER_MEDIA_ENDPOINT_URL or None,
            region_name=settings.SPEAKER_MEDIA_REGION or None,
            aws_access_key_id=settings.SPEAKER_MEDIA_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.SPEAKER_MEDIA_SECRET_ACCESS_KEY or None,
            config=Config(signature_version="s3v4"),
        )
        return cls(bucket, settings.SPEAKER_MEDIA_PREFIX, client)

    def key_for(self, session, kind, filename):
        """Where the object lives: edition, session, kind, a fresh id, and
        the file's own name reduced to safe characters."""
        safe = re.sub(r"[^A-Za-z0-9._-]+", "-", filename)
        safe = re.sub(r"-+", "-", safe)
        safe = re.sub(r"-?\.-?", ".", safe).strip("-.") or "upload"
        return (
            f"{self.prefix}{session.conference.year}/{session.slug}/"
            f"{kind.lower()}/{uuid.uuid4().hex}/{safe[-150:]}"
        )

    def start(self, key, content_type):
        response = self.client.create_multipart_upload(
            Bucket=self.bucket, Key=key, ContentType=content_type
        )
        return response["UploadId"]

    def part_urls(self, key, upload_id, numbers, ttl=None):
        ttl = ttl or settings.SPEAKER_MEDIA_URL_TTL
        return [
            {
                "number": number,
                "url": self.client.generate_presigned_url(
                    "upload_part",
                    Params={
                        "Bucket": self.bucket,
                        "Key": key,
                        "UploadId": upload_id,
                        "PartNumber": number,
                    },
                    ExpiresIn=ttl,
                    HttpMethod="PUT",
                ),
            }
            for number in numbers
        ]

    def received_parts(self, key, upload_id):
        """The parts the bucket already holds, ``[{number, etag, size}]`` in
        part order, for a browser resuming an upload: it skips those and
        hands their ETags back when it completes."""
        parts = []
        kwargs = {"Bucket": self.bucket, "Key": key, "UploadId": upload_id}
        while True:
            response = self.client.list_parts(**kwargs)
            parts.extend(
                {
                    "number": part["PartNumber"],
                    "etag": part.get("ETag", ""),
                    "size": part.get("Size", 0),
                }
                for part in response.get("Parts", [])
            )
            if not response.get("IsTruncated"):
                return sorted(parts, key=lambda part: part["number"])
            kwargs["PartNumberMarker"] = response["NextPartNumberMarker"]

    def complete(self, key, upload_id, parts):
        self.client.complete_multipart_upload(
            Bucket=self.bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={
                "Parts": [
                    {"ETag": part["etag"], "PartNumber": part["number"]}
                    for part in sorted(parts, key=lambda part: part["number"])
                ]
            },
        )
        return self.client.head_object(Bucket=self.bucket, Key=key)["ContentLength"]

    def abort(self, key, upload_id):
        """Abort, and treat an upload the bucket no longer knows as aborted:
        the lifecycle rule may have got there first."""
        try:
            self.client.abort_multipart_upload(
                Bucket=self.bucket, Key=key, UploadId=upload_id
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "NoSuchUpload":
                raise

    def download_url(self, key, filename=None, ttl=None):
        params = {"Bucket": self.bucket, "Key": key}
        if filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
        return self.client.generate_presigned_url(
            "get_object", Params=params, ExpiresIn=ttl or settings.SPEAKER_MEDIA_URL_TTL
        )


def can_upload(user, session, kind):
    """Who may put a file of ``kind`` on ``session``: organizers any kind,
    a presenter on the session their raw video only (design §8.8)."""
    if not user.is_authenticated:
        return False
    if is_speaker_organizer(user):
        return True
    if kind != MediaKind.RAW_VIDEO:
        return False
    return session.session_presenters.filter(presenter__user=user).exists()


def can_download(user, session):
    """Who may fetch a session's files: whoever may open the session, on
    either side. Organizers and the session's liaisons see it on the
    organizer side; a presenter on it sees it on theirs, and needs the
    processed video to approve the final cut (design §4.1)."""
    if not user.is_authenticated:
        return False
    if is_speaker_organizer(user):
        return True
    if session.session_presenters.filter(presenter__user=user).exists():
        return True
    return session.session_presenters.filter(presenter__liaison=user).exists()


def video_limit_minutes(session):
    """The session's own length limit, else the edition's default, else None."""
    if session.video_length_limit_minutes:
        return session.video_length_limit_minutes
    settings_row = SpeakerSettings.objects.filter(
        conference_id=session.conference_id
    ).first()
    return settings_row.default_video_length_limit_minutes if settings_row else None


def session_assets(session):
    """Every asset on the session, newest version first within each kind
    and language, with the uploader for the history table."""
    return list(
        session.media_assets.select_related("uploaded_by").order_by(
            "kind", "language", "-version", "-id"
        )
    )


def asset_groups(assets):
    """``[{kind, label, language, current, history}]`` for the organizer's
    file list: one group per kind and language, the newest READY asset as
    ``current`` and the rest as ``history``."""
    groups = {}
    for asset in assets:
        group = groups.setdefault(
            (asset.kind, asset.language),
            {
                "kind": asset.kind,
                "label": asset.get_kind_display(),
                "language": asset.language,
                "current": None,
                "history": [],
            },
        )
        if group["current"] is None and asset.is_ready:
            group["current"] = asset
        else:
            group["history"].append(asset)
    return list(groups.values())


def open_uploads(session, user):
    """The caller's uploads on this session still in flight, newest first:
    the page tells them which file to pick again to carry on."""
    return list(
        session.media_uploads.filter(
            started_by=user, status=UploadStatus.STARTED, expires_at__gt=timezone.now()
        ).order_by("-id")
    )


def video_panel(session, user):
    """What the performer's video card shows (design §4.1): the current raw
    video, its duration against the limit, the versions so far, and any
    upload of theirs to resume."""
    assets = [a for a in session_assets(session) if a.kind == MediaKind.RAW_VIDEO]
    current = next((a for a in assets if a.is_ready), None)
    limit = video_limit_minutes(session)
    duration_pct = None
    over_by = None
    if current is not None and current.duration_seconds is not None and limit:
        duration_pct = min(100, round(current.duration_seconds * 100 / (limit * 60)))
        over_by = max(0, current.duration_seconds - limit * 60)
    return {
        "current": current,
        "history": [a for a in assets if a is not current],
        "limit_minutes": limit,
        "duration_pct": duration_pct,
        "over_by": over_by,
        "open_uploads": [
            u for u in open_uploads(session, user) if u.kind == MediaKind.RAW_VIDEO
        ],
    }


def plan_parts(size_bytes):
    """``(part_size, parts_total)`` for a file of this size, or raise."""
    if size_bytes <= 0:
        raise UploadError("The file is empty.")
    if size_bytes > settings.SPEAKER_MEDIA_MAX_BYTES:
        raise UploadError("The file is larger than the portal accepts.")
    part_size = max(settings.SPEAKER_MEDIA_PART_SIZE, MIN_PART_SIZE)
    parts_total = math.ceil(size_bytes / part_size)
    if parts_total > MAX_PARTS:
        raise UploadError("The file needs more parts than the bucket allows.")
    return part_size, parts_total


def start_upload(*, session, kind, language, filename, size_bytes, content_type, user):
    """Open a multipart upload and record it; returns the ``MediaUpload``."""
    if kind not in MediaKind.values:
        raise UploadError("Unknown kind of file.")
    if not filename:
        raise UploadError("The file needs a name.")
    part_size, parts_total = plan_parts(size_bytes)
    bucket = MediaBucket.from_settings()
    key = bucket.key_for(session, kind, filename)
    upload_id = bucket.start(key, content_type or "application/octet-stream")
    return MediaUpload.objects.create(
        session=session,
        kind=kind,
        language=language or "",
        filename=filename[:255],
        content_type=content_type or "application/octet-stream",
        size_bytes=size_bytes,
        part_size=part_size,
        parts_total=parts_total,
        storage_key=key,
        upload_id=upload_id,
        expires_at=timezone.now()
        + timedelta(hours=settings.SPEAKER_MEDIA_UPLOAD_TTL_HOURS),
        started_by=user,
    )


def part_urls(upload, start=1, count=UPLOAD_PART_URL_BATCH):
    """Presigned URLs for parts ``start`` onwards, at most a batch."""
    if not upload.is_open:
        raise UploadError("This upload is no longer open.")
    start = max(1, start)
    stop = min(upload.parts_total, start + min(count, UPLOAD_PART_URL_BATCH) - 1)
    numbers = list(range(start, stop + 1))
    return MediaBucket.from_settings().part_urls(
        upload.storage_key, upload.upload_id, numbers
    )


def received_parts(upload):
    if not upload.is_open:
        return []
    return MediaBucket.from_settings().received_parts(
        upload.storage_key, upload.upload_id
    )


def complete_upload(upload, parts):
    """Finalize the object and record the asset.

    The new asset takes the next version for its session, kind and
    language, the previous READY one becomes SUPERSEDED, and
    ``asset_ready`` is sent once everything is saved.
    """
    if not upload.is_open:
        raise UploadError("This upload is no longer open.")
    numbers = sorted(part.get("number") for part in parts)
    if numbers != list(range(1, upload.parts_total + 1)):
        raise UploadError(
            f"Expected parts 1 to {upload.parts_total}; got {len(numbers)}."
        )
    if any(not part.get("etag") for part in parts):
        raise UploadError("Every part needs its ETag.")
    size = MediaBucket.from_settings().complete(
        upload.storage_key, upload.upload_id, parts
    )
    with transaction.atomic():
        previous = MediaAsset.objects.filter(
            session=upload.session, kind=upload.kind, language=upload.language
        )
        version = (
            previous.order_by("-version").first() or MediaAsset(version=0)
        ).version + 1
        asset = MediaAsset.objects.create(
            session=upload.session,
            kind=upload.kind,
            language=upload.language,
            version=version,
            status=MediaStatus.READY,
            storage_key=upload.storage_key,
            original_filename=upload.filename,
            content_type=upload.content_type,
            size_bytes=size,
            uploaded_by=upload.started_by,
        )
        previous.filter(status=MediaStatus.READY).exclude(pk=asset.pk).update(
            status=MediaStatus.SUPERSEDED
        )
        upload.status = UploadStatus.COMPLETED
        upload.completed_at = timezone.now()
        upload.asset = asset
        upload.save(update_fields=["status", "completed_at", "asset", "modified_date"])
    asset_ready.send(sender=MediaAsset, asset=asset)
    return asset


def abort_upload(upload, status=UploadStatus.ABORTED):
    if not upload.is_open:
        raise UploadError("This upload is no longer open.")
    MediaBucket.from_settings().abort(upload.storage_key, upload.upload_id)
    upload.status = status
    upload.save(update_fields=["status", "modified_date"])
    return upload


def expire_abandoned_uploads(now=None):
    """Abort every open upload past its expiry; returns how many.

    The bucket's own lifecycle rule (README) clears incomplete multipart
    uploads too; this keeps the portal's rows honest and reclaims parts
    sooner.
    """
    now = now or timezone.now()
    count = 0
    for upload in MediaUpload.objects.filter(
        status=UploadStatus.STARTED, expires_at__lt=now
    ).select_related("session"):
        abort_upload(upload, status=UploadStatus.EXPIRED)
        count += 1
    return count
