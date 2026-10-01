"""Bulk download of an edition's files (design §8.8, "Bulk download").

An export is a scope (kinds, language, sessions, latest or every version,
newer than a moment) over the READY assets an organizer may see, recorded
as a ``MediaExport`` row. From it come three ways to fetch the same set:
a manifest with presigned links for the browser's folder download, a
shell script with resumable curl lines and an aria2 input file, and a
zip the media worker builds when the selection is small enough. Every
path lays files out the same way, mirroring the bucket without the
upload ids:

    pyladiescon-<year>/<session-slug>/<kind>/v<n>[-<lang>][-<variant>]-<filename>
    pyladiescon-<year>/manifest.csv
"""

import csv
import io
import re
import secrets
import shlex
import tempfile
import zipfile
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .constants import MediaKind, MediaStatus, ZipStatus
from .media import MediaBucket
from .models import MediaAsset, MediaExport, Session
from .spreadsheet import safe_cell

VERSIONS = ("latest", "all")
MANIFEST_COLUMNS = [
    "path",
    "session",
    "presenters",
    "kind",
    "language",
    "variant",
    "version",
    "title",
    "duration_seconds",
    "size_bytes",
    "uploaded_at",
    "uploaded_by",
    "notes",
]


class ExportError(ValueError):
    """A scope or a request the export cannot serve; the message is fit
    to show."""


def clean_scope(data):
    """A scope dict from a form's or a query's values, validated."""
    kinds = [k for k in data.get("kinds", []) if k in MediaKind.values]
    if not kinds:
        raise ExportError("Choose at least one kind of file.")
    versions = data.get("versions") or "latest"
    if versions not in VERSIONS:
        raise ExportError("versions must be latest or all.")
    since = data.get("since") or ""
    if since:
        parsed = timezone.datetime.fromisoformat(str(since))
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed)
        since = parsed.isoformat()
    return {
        "kinds": kinds,
        "language": str(data.get("language") or "")[:10],
        "sessions": [s for s in data.get("sessions", []) if s],
        "versions": versions,
        "since": since,
    }


def select_assets(conference, user, scope, as_of=None):
    """The assets the scope names, among the sessions ``user`` may see,
    session by session then by kind, language, variant and version: the
    newest READY one per line, or every version still in the bucket
    (READY and SUPERSEDED) when the scope asks for all. ``as_of`` pins
    the set to what existed when an export was made, so its count, its
    script and its zip agree."""
    sessions = Session.objects.for_conference(conference).visible_to(user)
    if scope.get("sessions"):
        sessions = sessions.filter(slug__in=scope["sessions"])
    statuses = [MediaStatus.READY]
    if scope.get("versions", "latest") == "all":
        statuses.append(MediaStatus.SUPERSEDED)
    queryset = (
        MediaAsset.objects.filter(
            session__in=sessions, status__in=statuses, kind__in=scope["kinds"]
        )
        .exclude(storage_key="")
        .select_related("session", "session__conference", "uploaded_by")
        .prefetch_related("session__session_presenters__presenter")
    )
    if scope.get("language"):
        queryset = queryset.filter(language=scope["language"])
    if scope.get("since"):
        queryset = queryset.filter(creation_date__gt=scope["since"])
    if as_of is not None:
        queryset = queryset.filter(creation_date__lte=as_of)
    kind_order = {kind: index for index, kind in enumerate(MediaKind.values)}
    assets = sorted(
        queryset,
        key=lambda a: (
            a.session.title.lower(),
            a.session_id,
            kind_order.get(a.kind, len(kind_order)),
            a.language,
            a.variant,
            -a.version,
            -a.pk,
        ),
    )
    if scope.get("versions", "latest") == "latest":
        seen = set()
        newest = []
        for asset in assets:
            line = (asset.session_id, asset.kind, asset.language, asset.variant)
            if line not in seen:
                seen.add(line)
                newest.append(asset)
        assets = newest
    return assets


def _safe(text):
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", text or "")
    text = re.sub(r"-+", "-", text).strip("-.")
    return text or "file"


def local_path(asset):
    """Where the file lands on disk, mirroring the bucket: edition, session,
    kind, then version, language and variant in the name."""
    name = f"v{asset.version}"
    if asset.language:
        name += f"-{_safe(asset.language)}"
    if asset.variant:
        name += f"-{_safe(asset.variant)}"
    name += "-" + _safe(asset.original_filename or asset.storage_key.rsplit("/", 1)[-1])
    return (
        f"pyladiescon-{asset.session.conference.year}/{asset.session.slug}/"
        f"{asset.kind.lower()}/{name}"
    )


def create_export(conference, user, scope):
    """Record an export of ``scope``: the count and bytes of what it names
    now, and how long its links will live."""
    assets = select_assets(conference, user, scope)
    return MediaExport.objects.create(
        conference=conference,
        created_by=user,
        scope=scope,
        file_count=len(assets),
        total_bytes=sum(a.size_bytes or 0 for a in assets),
        expires_at=timezone.now()
        + timedelta(seconds=settings.SPEAKER_MEDIA_BULK_URL_TTL),
    )


def export_entries(export, user, with_urls=True):
    """One dict per file: the asset, its local path, its presigned link
    (living until the export expires) and the manifest's columns."""
    if export.is_expired:
        raise ExportError("This export has expired; make a new one.")
    ttl = max(60, int((export.expires_at - timezone.now()).total_seconds()))
    bucket = MediaBucket.from_settings() if with_urls else None
    entries = []
    for asset in select_assets(
        export.conference, user, export.scope, as_of=export.creation_date
    ):
        url = (
            bucket.download_url(
                asset.storage_key,
                asset.original_filename or None,
                ttl=ttl,
            )
            if with_urls
            else ""
        )
        entries.append(
            {
                "asset": asset,
                "path": local_path(asset),
                "url": url,
                "size": asset.size_bytes or 0,
                "row": {
                    "path": local_path(asset),
                    "session": asset.session.title,
                    "presenters": ", ".join(
                        link.presenter.display_name
                        for link in asset.session.session_presenters.all()
                        if link.confirmed_at
                    ),
                    "kind": asset.kind,
                    "language": asset.language,
                    "variant": asset.variant,
                    "version": asset.version,
                    "title": asset.title,
                    "duration_seconds": (
                        "" if asset.duration_seconds is None else asset.duration_seconds
                    ),
                    "size_bytes": asset.size_bytes or "",
                    "uploaded_at": asset.creation_date.isoformat(),
                    "uploaded_by": (
                        asset.uploaded_by.get_full_name() or asset.uploaded_by.username
                        if asset.uploaded_by
                        else ""
                    ),
                    "notes": asset.notes_md,
                },
            }
        )
    return entries


def manifest_path(export):
    return f"pyladiescon-{export.conference.year}/manifest.csv"


def write_manifest(entries, stream):
    writer = csv.writer(stream)
    writer.writerow(MANIFEST_COLUMNS)
    for entry in entries:
        writer.writerow(
            [safe_cell(entry["row"][column]) for column in MANIFEST_COLUMNS]
        )
    return stream


def write_script(export, entries, stream):
    """A shell script: one resumable curl per file, the manifest written
    first, so it runs unattended and continues after an interruption."""
    manifest = write_manifest(entries, io.StringIO()).getvalue()
    # Every cell is one line (safe_cell), so no line of the manifest can be
    # the delimiter; should one ever be, a delimiter nothing contains
    # keeps the heredoc closed where it is meant to close.
    delimiter = "MANIFEST"
    while delimiter in manifest.splitlines():
        delimiter = f"MANIFEST_{secrets.token_hex(4)}"
    stream.write("#!/bin/sh\n")
    stream.write(
        f"# PyLadiesCon {export.conference.year} media export {export.pk}: "
        f"{len(entries)} files. Links expire at {export.expires_at:%Y-%m-%d %H:%M} UTC.\n"
        "# Keep this file to yourself: every link fetches the file it names.\n"
        "set -e\n"
    )
    stream.write(f"mkdir -p {shlex.quote(manifest_path(export).rsplit('/', 1)[0])}\n")
    stream.write(f"cat > {shlex.quote(manifest_path(export))} <<'{delimiter}'\n")
    stream.write(manifest)
    stream.write(f"{delimiter}\n")
    for entry in entries:
        stream.write(
            f"curl -fL -C - --create-dirs -o {shlex.quote(entry['path'])} "
            f"{shlex.quote(entry['url'])}\n"
        )
    stream.write(f'echo "Done: {len(entries)} files."\n')
    return stream


def write_aria2(entries, stream):
    """An aria2c input file: the URL, then the local path, per file."""
    for entry in entries:
        stream.write(f"{entry['url']}\n  out={entry['path']}\n")
    return stream


def zip_key(export):
    return f"{settings.SPEAKER_MEDIA_PREFIX}exports/export-{export.pk}.zip"


def build_zip(export, user):
    """Stream the export's files into a zip in the bucket and record it.

    Refuses a selection over ``SPEAKER_MEDIA_ZIP_MAX_BYTES``: a zip of an
    edition's raw video would double the storage and hold a worker for an
    hour, and the script or the folder download serve that case.
    """
    if export.total_bytes > settings.SPEAKER_MEDIA_ZIP_MAX_BYTES:
        raise ExportError(
            "This selection is too large for a zip; use the folder download "
            "or the script."
        )
    entries = export_entries(export, user, with_urls=False)
    bucket = MediaBucket.from_settings()
    with tempfile.TemporaryFile() as spool:
        with zipfile.ZipFile(
            spool, "w", zipfile.ZIP_STORED, allowZip64=True
        ) as archive:
            archive.writestr(
                manifest_path(export), write_manifest(entries, io.StringIO()).getvalue()
            )
            for entry in entries:
                body = bucket.client.get_object(
                    Bucket=bucket.bucket, Key=entry["asset"].storage_key
                )["Body"]
                with archive.open(entry["path"], "w") as target:
                    for chunk in iter(lambda: body.read(8 * 1024 * 1024), b""):
                        target.write(chunk)
        spool.seek(0)
        key = zip_key(export)
        bucket.client.put_object(
            Bucket=bucket.bucket, Key=key, Body=spool, ContentType="application/zip"
        )
    return key


def zip_url(export):
    """A presigned link to the built zip, living until the export expires."""
    if export.zip_status != ZipStatus.DONE or not export.zip_key or export.is_expired:
        return ""
    ttl = max(60, int((export.expires_at - timezone.now()).total_seconds()))
    return MediaBucket.from_settings().download_url(
        export.zip_key, f"pyladiescon-{export.conference.year}-export.zip", ttl=ttl
    )


def expire_zips(now=None):
    """Delete the zip of every export past its expiry and forget its key;
    returns how many. The row stays, as the record of who pulled what;
    its page already says the export has expired."""
    now = now or timezone.now()
    expired = MediaExport.objects.filter(expires_at__lt=now).exclude(zip_key="")
    count = 0
    if not expired.exists():
        return count
    bucket = MediaBucket.from_settings()
    for export in expired:
        bucket.delete(export.zip_key)
        export.zip_key = ""
        export.save(update_fields=["zip_key", "modified_date"])
        count += 1
    return count


def exports_for_maintenance():
    """Every export, newest first, for the Maintenance list."""
    return MediaExport.objects.select_related("conference", "created_by").order_by(
        "-id"
    )


def scope_summary(scope):
    """The scope in words, for the pages and the Maintenance list."""
    labels = dict(MediaKind.choices)
    parts = [", ".join(labels.get(k, k) for k in scope.get("kinds", []))]
    if scope.get("language"):
        parts.append(f"language {scope['language']}")
    if scope.get("sessions"):
        count = len(scope["sessions"])
        parts.append("1 session" if count == 1 else f"{count} sessions")
    parts.append(
        "every version" if scope.get("versions") == "all" else "latest versions"
    )
    if scope.get("since"):
        parts.append(f"newer than {scope['since'][:16].replace('T', ' ')}")
    return " · ".join(parts)


def sessions_with_files(conference, user):
    """The sessions the scope form offers: those with a READY file, that
    ``user`` may see, grouped by session type for the picker:
    ``[{"kind": name, "sessions": [...]}]`` in the type's own order."""
    sessions = (
        Session.objects.for_conference(conference)
        .visible_to(user)
        .filter(Q(media_assets__status=MediaStatus.READY))
        .distinct()
        .select_related("kind")
        .order_by("kind__sort_order", "kind__name", "title")
    )
    groups = []
    for session in sessions:
        if not groups or groups[-1]["kind"] != session.kind.name:
            groups.append({"kind": session.kind.name, "sessions": []})
        groups[-1]["sessions"].append(session)
    return groups
