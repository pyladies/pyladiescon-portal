"""Object storage for speaker media, and the multipart upload lifecycle
(design §8.8, task 5.1).

Performance videos are routinely several gigabytes, so the browser sends
the parts straight to a private bucket with presigned URLs; the portal only
starts the upload, hands out URLs in batches, finalizes it and records the
``MediaAsset``. ``MediaBucket`` is the one place that talks to the bucket;
everything else here is the lifecycle around a ``MediaUpload`` row.
"""

import math
import os
import re
import uuid
from datetime import timedelta
from urllib.parse import quote

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .constants import (
    UPLOAD_PART_URL_BATCH,
    VIDEO_KINDS,
    MediaKind,
    MediaStatus,
    UploadStatus,
)
from .models import MediaAsset, MediaUpload, SpeakerSettings
from .permissions import is_speaker_organizer
from .signals import asset_ready

# S3 limits: at least 5 MiB per part except the last, at most 10,000 parts.
MIN_PART_SIZE = 5 * 1024 * 1024
MAX_PARTS = 10_000

# A download link is minted on the click and followed at once. A minute is
# plenty, and what the address bar, the history and any proxy log keep is
# then a credential that has already expired.
DOWNLOAD_LINK_TTL = 60

# A language tag the way BCP 47 writes one: a language, then at most two
# more pieces ("pt", "pt-BR", "zh-Hant-TW"); the column holds ten.
LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8}){0,2}$")
# A media type is two tokens; anything else is stored as octet-stream.
CONTENT_TYPE_RE = re.compile(r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+$")
# What a video kind accepts when the browser offers no video/* type.
VIDEO_EXTENSIONS = frozenset(
    {".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi", ".mpg", ".mpeg", ".mts", ".m2ts"}
)
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


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

    def delete(self, key):
        """Remove an object. The bucket answers the same for one it does not
        have, so a repeat is harmless."""
        self.client.delete_object(Bucket=self.bucket, Key=key)

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
            params["ResponseContentDisposition"] = content_disposition(filename)
        return self.client.generate_presigned_url(
            "get_object", Params=params, ExpiresIn=ttl or settings.SPEAKER_MEDIA_URL_TTL
        )


def content_disposition(filename):
    """``attachment`` with the file's own name, reduced to what a header may
    carry: quotes, backslashes and control characters dropped, an ASCII
    name in ``filename`` and, when the name has more, the whole of it
    percent-encoded in ``filename*`` (RFC 6266). This is the one string a
    client typed that reaches a response header."""
    cleaned = CONTROL_CHARS.sub("", filename).replace("\\", "").replace('"', "")
    ascii_name = cleaned.encode("ascii", "ignore").decode() or "download"
    header = f'attachment; filename="{ascii_name}"'
    if cleaned != ascii_name:
        header += f"; filename*=UTF-8''{quote(cleaned)}"
    return header


def can_upload(user, session, kind):
    """Who may put a file of ``kind`` on ``session``: organizers any kind,
    a presenter on the session their raw video only (design §8.8), and
    only once the session is theirs: a proposal still waiting for an
    answer, or turned down, has no channel into the bucket."""
    if not user.is_authenticated:
        return False
    if is_speaker_organizer(user):
        return True
    if kind != MediaKind.RAW_VIDEO or session.is_a_proposal:
        return False
    return session.session_presenters.filter(presenter__user=user).exists()


def can_download(user, session, asset=None):
    """Who may fetch a session's files. Organizers and the session's
    liaisons: everything. A presenter on an accepted session (a proposal
    has no files for them): their own raw video, and whatever the team
    has shared with them (design §8.6); with no ``asset`` given, whether
    they may fetch anything at all."""
    if not user.is_authenticated:
        return False
    if is_speaker_organizer(user):
        return True
    if session.session_presenters.filter(presenter__liaison=user).exists():
        return True
    if session.is_a_proposal:
        return False
    if not session.session_presenters.filter(presenter__user=user).exists():
        return False
    if asset is None:
        return True
    return asset.kind == MediaKind.RAW_VIDEO or asset.shared_with_speaker


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
            "kind", "language", "variant", "-version", "-id"
        )
    )


def asset_groups(assets):
    """``[{kind, label, language, variant, current, history}]`` for the
    organizer's file list: one group per kind, language and variant, the
    newest READY asset as ``current`` and the rest as ``history``."""
    groups = {}
    for asset in assets:
        group = groups.setdefault(
            (asset.kind, asset.language, asset.variant),
            {
                "kind": asset.kind,
                "label": asset.get_kind_display(),
                "language": asset.language,
                "variant": asset.variant,
                "current": None,
                "history": [],
            },
        )
        if group["current"] is None and asset.is_ready:
            group["current"] = asset
        else:
            group["history"].append(asset)
    return list(groups.values())


def team_files(session, assets=None):
    """What the team has shared with the speaker, for their session page:
    the newest READY asset of every kind, language and variant that is
    marked shared (the final cut, each promo format, the transcript),
    newest first. Unshared files and reviewer notes stay with the team."""
    if assets is None:
        assets = session_assets(session)
    newest = {}
    for asset in assets:
        if (
            asset.kind == MediaKind.RAW_VIDEO
            or not asset.is_ready
            or not asset.shared_with_speaker
        ):
            continue
        newest.setdefault((asset.kind, asset.language, asset.variant), asset)
    return sorted(newest.values(), key=lambda a: (a.creation_date, a.pk), reverse=True)


def open_uploads(session, user):
    """The caller's uploads on this session still in flight, newest first:
    the page tells them which file to pick again to carry on."""
    return list(
        session.media_uploads.filter(
            started_by=user, status=UploadStatus.STARTED, expires_at__gt=timezone.now()
        ).order_by("-id")
    )


def video_panel(session, user, assets=None):
    """What the performer's video card shows (design §4.1): the current raw
    video, its duration against the limit, the versions so far, and any
    upload of theirs to resume. Pass ``assets`` (``session_assets``) when
    the page already loaded them."""
    if assets is None:
        assets = session_assets(session)
    assets = [a for a in assets if a.kind == MediaKind.RAW_VIDEO]
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


def clean_language(kind, language):
    """The language an upload is filed under, or raise.

    The raw video is the session's own recording, one line per session
    whatever the tongue, so it carries no language: a second line under
    another tag would escape the versioning and the length rule. Other
    kinds take a well-formed tag or none.
    """
    if kind == MediaKind.RAW_VIDEO:
        return ""
    language = (language or "").strip()
    if language and not LANGUAGE_RE.match(language):
        raise UploadError("The language must be a tag such as en or pt-BR.")
    return language


def clean_content_type(kind, filename, content_type):
    """The type the object is stored with, or raise.

    The browser's guess is kept when it is a well-formed media type, else
    the object is an octet-stream. A video kind must look like a video, by
    type or by extension: the panel's ``accept`` attribute is only a hint
    to the file picker.
    """
    content_type = (content_type or "").strip()
    if not CONTENT_TYPE_RE.match(content_type):
        content_type = "application/octet-stream"
    if kind in VIDEO_KINDS and not content_type.startswith("video/"):
        if os.path.splitext(filename)[1].lower() not in VIDEO_EXTENSIONS:
            raise UploadError("A video is expected here; choose a video file.")
    return content_type


def start_upload(
    *, session, kind, language, filename, size_bytes, content_type, user, variant=""
):
    """Open a multipart upload and record it; returns the ``MediaUpload``."""
    if kind not in MediaKind.values:
        raise UploadError("Unknown kind of file.")
    if not filename:
        raise UploadError("The file needs a name.")
    if CONTROL_CHARS.search(filename):
        raise UploadError("The file's name has characters a name cannot carry.")
    language = clean_language(kind, language)
    content_type = clean_content_type(kind, filename, content_type)
    part_size, parts_total = plan_parts(size_bytes)
    bucket = MediaBucket.from_settings()
    key = bucket.key_for(session, kind, filename)
    upload_id = bucket.start(key, content_type)
    try:
        return MediaUpload.objects.create(
            session=session,
            kind=kind,
            language=language,
            variant=(variant or "")[:40],
            filename=filename[:255],
            content_type=content_type,
            size_bytes=size_bytes,
            part_size=part_size,
            parts_total=parts_total,
            storage_key=key,
            upload_id=upload_id,
            expires_at=timezone.now()
            + timedelta(hours=settings.SPEAKER_MEDIA_UPLOAD_TTL_HOURS),
            started_by=user,
        )
    except Exception:
        # The row is how the portal finds the multipart again; without it
        # only the bucket's lifecycle rule would, so it goes at once.
        bucket.abort(key, upload_id)
        raise


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

    The new asset takes the next version for its session, kind, language
    and variant, the previous READY one becomes SUPERSEDED, and
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
    bucket = MediaBucket.from_settings()
    size = bucket.complete(upload.storage_key, upload.upload_id, parts)
    if size != upload.size_bytes:
        # The declared size is what the cap was checked against; the object
        # is the truth. One that disagrees is thrown away before anything
        # records it, so a declared byte cannot buy a part slot to fill.
        bucket.delete(upload.storage_key)
        upload.status = UploadStatus.ABORTED
        upload.save(update_fields=["status", "modified_date"])
        raise UploadError(
            f"The file that arrived is {size} bytes, not the {upload.size_bytes} "
            "declared; it was removed. Upload it again."
        )
    with transaction.atomic():
        previous = MediaAsset.objects.filter(
            session=upload.session,
            kind=upload.kind,
            language=upload.language,
            variant=upload.variant,
        )
        version = (
            previous.order_by("-version").first() or MediaAsset(version=0)
        ).version + 1
        asset = MediaAsset.objects.create(
            session=upload.session,
            kind=upload.kind,
            language=upload.language,
            variant=upload.variant,
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
