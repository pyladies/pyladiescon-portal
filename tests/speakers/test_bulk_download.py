"""Bulk download (design §8.8, task 5.6): the scope, the layout, the
three ways to fetch, the zip's cap, the audit under Maintenance."""

import importlib
import io
import zipfile
from datetime import timedelta
from unittest.mock import patch

import boto3
import pytest
from django.contrib.auth.models import Group, Permission, User
from django.core import mail
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from moto import mock_aws

from common.models import SentEmail
from common.send_emails import WITHHELD
from speakers.constants import MediaKind, MediaStatus, ZipStatus
from speakers.exports import (
    ExportError,
    build_zip,
    clean_scope,
    create_export,
    export_entries,
    local_path,
    scope_summary,
    select_assets,
    write_aria2,
    write_manifest,
    write_script,
    zip_url,
)
from speakers.media import MediaBucket
from speakers.models import MediaAsset, MediaExport
from speakers.tasks import build_export_zip_task

from .factories import add_presenter, make_presenter, make_session, make_settings

BUCKET = "test-speaker-media"
EXPORT = reverse("speakers:media_export")
MAINTENANCE = reverse("maintenance_exports")


@pytest.fixture
def bucket(settings):
    settings.SPEAKER_MEDIA_BUCKET = BUCKET
    settings.SPEAKER_MEDIA_PREFIX = "speaker-media/"
    settings.SPEAKER_MEDIA_ENDPOINT_URL = None
    settings.SPEAKER_MEDIA_REGION = "us-east-1"
    settings.SPEAKER_MEDIA_ACCESS_KEY_ID = "testing"
    settings.SPEAKER_MEDIA_SECRET_ACCESS_KEY = "testing"
    settings.SPEAKER_MEDIA_BULK_URL_TTL = 12 * 3600
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield MediaBucket.from_settings()


@pytest.fixture
def organizer(db):
    return User.objects.create_user(
        "org", email="org@x.org", is_staff=True, first_name="Olga"
    )


@pytest.fixture
def maintainer(db):
    user = User.objects.create_user("maint", email="maint@x.org", is_staff=True)
    group, _ = Group.objects.get_or_create(name="Infra maintainers")
    group.permissions.add(Permission.objects.get(codename="view_maintenance"))
    user.groups.add(group)
    return user


@pytest.fixture
def world(conference, bucket, organizer):
    """Two PyJam sets with files in the bucket: Loud with two raw versions
    and an English transcript, Quiet with a raw video and a square poster."""
    make_settings(conference)
    loud = make_session(conference, title="Loud set", kind="PYJAM", slug="loud")
    quiet = make_session(conference, title="Quiet set", kind="PYJAM", slug="quiet")
    add_presenter(loud, make_presenter(conference, display_name="Ada"), confirmed=True)
    add_presenter(quiet, make_presenter(conference, display_name="Bea"), confirmed=True)
    assets = {}

    def put(session, kind, name, body, **kwargs):
        key = f"speaker-media/{conference.year}/{session.slug}/{kind.lower()}/x/{name}"
        bucket.client.put_object(Bucket=BUCKET, Key=key, Body=body)
        kwargs.setdefault("status", MediaStatus.READY)
        return MediaAsset.objects.create(
            session=session,
            kind=kind,
            storage_key=key,
            original_filename=name,
            size_bytes=len(body),
            uploaded_by=organizer,
            **kwargs,
        )

    assets["loud_v1"] = put(
        loud,
        MediaKind.RAW_VIDEO,
        "take1.mp4",
        b"a" * 10,
        version=1,
        status=MediaStatus.SUPERSEDED,
    )
    assets["loud_v2"] = put(
        loud,
        MediaKind.RAW_VIDEO,
        "take 2!.mp4",
        b"b" * 20,
        version=2,
        duration_seconds=125,
        title="Loud take",
    )
    assets["loud_en"] = put(
        loud,
        MediaKind.TRANSCRIPT,
        "loud.vtt",
        b"c" * 5,
        language="en",
        notes_md="=SUM(1)",
    )
    assets["quiet_raw"] = put(quiet, MediaKind.RAW_VIDEO, "quiet.mp4", b"d" * 30)
    assets["quiet_poster"] = put(
        quiet, MediaKind.PROMO, "poster.png", b"e" * 7, variant="square"
    )
    return {"loud": loud, "quiet": quiet, "assets": assets}


@pytest.mark.django_db
class TestScope:
    def test_clean_scope(self):
        scope = clean_scope(
            {"kinds": ["RAW_VIDEO", "NOPE"], "since": "2026-09-01T10:00"}
        )
        assert scope["kinds"] == ["RAW_VIDEO"] and scope["versions"] == "latest"
        assert scope["since"].startswith("2026-09-01T10:00")
        assert clean_scope({})["kinds"] == ["RAW_VIDEO"]
        with pytest.raises(ExportError):
            clean_scope({"versions": "some"})

    def test_selection(self, world, organizer, conference):
        a = world["assets"]
        latest = select_assets(
            conference, organizer, clean_scope({"kinds": ["RAW_VIDEO"]})
        )
        assert latest == [a["loud_v2"], a["quiet_raw"]]
        every = select_assets(
            conference,
            organizer,
            clean_scope({"kinds": ["RAW_VIDEO"], "versions": "all"}),
        )
        assert every == [a["loud_v2"], a["loud_v1"], a["quiet_raw"]]
        one = select_assets(
            conference,
            organizer,
            clean_scope({"kinds": ["RAW_VIDEO", "PROMO"], "sessions": ["quiet"]}),
        )
        assert one == [a["quiet_raw"], a["quiet_poster"]]
        en = select_assets(
            conference,
            organizer,
            clean_scope({"kinds": ["TRANSCRIPT"], "language": "en"}),
        )
        assert en == [a["loud_en"]]
        later = timezone.now() + timedelta(hours=1)
        assert (
            select_assets(
                conference,
                organizer,
                clean_scope({"kinds": ["RAW_VIDEO"], "since": later.isoformat()}),
            )
            == []
        )

    def test_layout(self, world):
        a = world["assets"]
        year = world["loud"].conference.year
        assert (
            local_path(a["loud_v2"])
            == f"pyladiescon-{year}/loud/raw_video/v2-take-2-.mp4"
        )
        assert (
            local_path(a["loud_en"])
            == f"pyladiescon-{year}/loud/transcript/v1-en-loud.vtt"
        )
        assert (
            local_path(a["quiet_poster"])
            == f"pyladiescon-{year}/quiet/promo/v1-square-poster.png"
        )

    def test_summary(self):
        text = scope_summary(
            clean_scope(
                {"kinds": ["RAW_VIDEO", "PROMO"], "sessions": ["a"], "language": "en"}
            )
        )
        assert "Raw video" in text and "Promo material" in text
        assert (
            "language en" in text and "1 session" in text and "latest versions" in text
        )
        assert "every version" in scope_summary(
            {"kinds": [], "versions": "all", "sessions": ["a", "b"]}
        )


@pytest.mark.django_db
class TestExport:
    def test_entries_links_and_files(self, world, organizer, conference, settings):
        scope = clean_scope({"kinds": ["RAW_VIDEO", "TRANSCRIPT", "PROMO"]})
        export = create_export(conference, organizer, scope)
        assert export.file_count == 4 and export.total_bytes == 20 + 5 + 30 + 7
        assert export.expires_at > timezone.now() + timedelta(hours=11)
        entries = export_entries(export, organizer)
        assert [e["path"].split("/")[1:3] for e in entries] == [
            ["loud", "raw_video"],
            ["loud", "transcript"],
            ["quiet", "raw_video"],
            ["quiet", "promo"],
        ]
        # Links live as long as the export, not as long as a page link.
        assert "X-Amz-Expires=43" in entries[0]["url"]
        manifest = write_manifest(entries, io.StringIO()).getvalue()
        assert manifest.startswith(
            "path,session,presenters,kind,language,variant,version,title"
        )
        assert "Loud set,Ada,RAW_VIDEO,,,2,Loud take,125,20," in manifest
        assert "'=SUM(1)" in manifest  # never a formula
        script = write_script(export, entries, io.StringIO()).getvalue()
        assert script.startswith("#!/bin/sh\n") and "set -e" in script
        assert "cat > pyladiescon-" in script and "MANIFEST\n" in script
        assert script.count("curl -fL -C - --create-dirs -o ") == 4
        aria = write_aria2(entries, io.StringIO()).getvalue()
        assert aria.count("\n  out=pyladiescon-") == 4
        export.expires_at = timezone.now() - timedelta(minutes=1)
        export.save()
        with pytest.raises(ExportError):
            export_entries(export, organizer)

    def test_pages_and_files(self, client, world, organizer, conference):
        client.force_login(organizer)
        response = client.get(EXPORT, {"kinds": ["RAW_VIDEO", "TRANSCRIPT"]})
        assert response.status_code == 200
        html = response.content.decode()
        assert "<strong>3</strong> files" in html and "55" in html
        response = client.post(
            EXPORT, {"kinds": ["RAW_VIDEO", "TRANSCRIPT"], "versions": "all"}
        )
        export = MediaExport.objects.get()
        assert response["Location"] == export.get_absolute_url()
        assert export.file_count == 4 and export.created_by == organizer
        html = client.get(export.get_absolute_url()).content.decode()
        assert (
            "every version" in html
            and "download.sh" in html
            and "Build the zip" in html
        )
        assert "js/media-export" in html
        for name, marker in (
            ("download.sh", "#!/bin/sh"),
            ("aria2.txt", "  out=pyladiescon-"),
            ("manifest.csv", "path,session,presenters"),
        ):
            response = client.get(
                reverse("speakers:media_export_file", args=[export.pk, name])
            )
            assert response.status_code == 200, name
            assert marker in response.content.decode()
            assert name in response["Content-Disposition"]
        data = client.get(
            reverse("speakers:media_export_file", args=[export.pk, "entries.json"])
        ).json()
        assert len(data["files"]) == 4 and data["files"][0]["url"].startswith(
            "https://"
        )
        assert data["manifest_path"].endswith("/manifest.csv")
        assert (
            client.get(
                reverse("speakers:media_export_file", args=[export.pk, "x"])
            ).status_code
            == 404
        )
        # The board's tab, the sessions list and a session's files link here.
        assert (
            EXPORT
            in client.get(
                reverse("speakers:checklist_board"), {"tab": "post_production"}
            ).content.decode()
        )
        assert EXPORT in client.get(reverse("speakers:session_list")).content.decode()
        assert (
            f"{EXPORT}?sessions=loud"
            in client.get(world["loud"].get_absolute_url()).content.decode()
        )

    def test_expired_export_says_so(self, client, world, organizer, conference):
        client.force_login(organizer)
        export = create_export(conference, organizer, clean_scope({}))
        MediaExport.objects.filter(pk=export.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        html = client.get(export.get_absolute_url()).content.decode()
        assert "has expired" in html and "start again" in html
        assert (
            client.get(
                reverse("speakers:media_export_file", args=[export.pk, "download.sh"])
            ).status_code
            == 404
        )
        response = client.post(reverse("speakers:media_export_zip", args=[export.pk]))
        assert response.status_code == 302
        export.refresh_from_db()
        assert export.zip_status == ""

    def test_bad_scope_and_empty_selection(self, client, world, organizer):
        client.force_login(organizer)
        assert client.get(EXPORT, {"versions": "some"}).status_code == 302
        assert client.post(EXPORT, {"versions": "some"}).status_code == 302
        response = client.post(EXPORT, {"kinds": ["OUTRO"]}, follow=True)
        assert "Nothing matches" in response.content.decode()

    def test_only_organizers(self, client, world, conference):
        speaker = User.objects.create_user("ada", email="ada@x.org")
        add_presenter(
            world["loud"], make_presenter(conference, user=speaker), confirmed=True
        )
        client.force_login(speaker)
        assert client.get(EXPORT).status_code == 403
        export = create_export(
            conference, User.objects.get(username="org"), clean_scope({})
        )
        assert client.get(export.get_absolute_url()).status_code == 403
        assert (
            client.get(
                reverse("speakers:media_export_file", args=[export.pk, "download.sh"])
            ).status_code
            == 403
        )

    def test_query_count_does_not_grow(self, client, world, organizer, conference):
        client.force_login(organizer)
        export = create_export(
            conference,
            organizer,
            clean_scope({"kinds": ["RAW_VIDEO", "TRANSCRIPT", "PROMO"]}),
        )
        url = reverse("speakers:media_export_file", args=[export.pk, "manifest.csv"])
        with CaptureQueriesContext(connection) as before:
            client.get(EXPORT, {"kinds": ["RAW_VIDEO"]})
            client.get(url)
        for n in range(4):
            session = make_session(conference, title=f"Set {n}", kind="PYJAM")
            add_presenter(session, make_presenter(conference), confirmed=True)
            MediaAsset.objects.create(
                session=session,
                kind=MediaKind.RAW_VIDEO,
                status=MediaStatus.READY,
                storage_key=f"k{n}",
                size_bytes=1,
            )
        with CaptureQueriesContext(connection) as after:
            client.get(EXPORT, {"kinds": ["RAW_VIDEO"]})
            client.get(url)
        assert len(after) == len(before)

    def test_storage_not_configured(
        self, client, world, organizer, conference, settings
    ):
        client.force_login(organizer)
        export = create_export(conference, organizer, clean_scope({}))
        settings.SPEAKER_MEDIA_BUCKET = ""
        html = client.get(export.get_absolute_url()).content.decode()
        assert "not configured" in html
        assert (
            client.get(
                reverse("speakers:media_export_file", args=[export.pk, "download.sh"])
            ).status_code
            == 404
        )


@pytest.mark.django_db
class TestZip:
    def test_built_by_the_worker_and_mailed(
        self, client, world, organizer, conference, settings
    ):
        client.force_login(organizer)
        export = create_export(
            conference, organizer, clean_scope({"kinds": ["TRANSCRIPT", "PROMO"]})
        )
        mail.outbox.clear()
        response = client.post(reverse("speakers:media_export_zip", args=[export.pk]))
        assert response.status_code == 302
        export.refresh_from_db()
        # Eager Celery in tests: the task already ran.
        assert export.zip_status == ZipStatus.DONE and export.zip_key.endswith(
            f"export-{export.pk}.zip"
        )
        assert "X-Amz-Signature" in zip_url(export)
        body = world["assets"]["loud_en"]  # noqa: F841  (the transcript is in the zip)
        bucket = MediaBucket.from_settings()
        archive = zipfile.ZipFile(
            io.BytesIO(
                bucket.client.get_object(Bucket=BUCKET, Key=export.zip_key)[
                    "Body"
                ].read()
            )
        )
        names = archive.namelist()
        assert any(n.endswith("/manifest.csv") for n in names)
        assert any(n.endswith("/transcript/v1-en-loud.vtt") for n in names)
        assert (
            archive.read([n for n in names if n.endswith("poster.png")][0]) == b"e" * 7
        )
        assert len(mail.outbox) == 1 and "export is ready" in mail.outbox[0].subject
        assert "X-Amz-Signature" in mail.outbox[0].body
        record = SentEmail.objects.get()
        assert WITHHELD in record.body_md and "X-Amz-Signature" not in record.body_md
        html = client.get(export.get_absolute_url()).content.decode()
        assert "Download the zip" in html
        # Asking again while it is done just builds again; while queued it is refused.
        MediaExport.objects.filter(pk=export.pk).update(zip_status=ZipStatus.RUNNING)
        response = client.post(
            reverse("speakers:media_export_zip", args=[export.pk]), follow=True
        )
        assert "already being built" in response.content.decode()

    def test_the_cap(self, client, world, organizer, conference, settings):
        settings.SPEAKER_MEDIA_ZIP_MAX_BYTES = 10
        client.force_login(organizer)
        export = create_export(
            conference, organizer, clean_scope({"kinds": ["RAW_VIDEO"]})
        )
        html = client.get(export.get_absolute_url()).content.decode()
        assert "too large for a zip" in html and "Build the zip" not in html
        response = client.post(
            reverse("speakers:media_export_zip", args=[export.pk]), follow=True
        )
        assert "too large" in response.content.decode()
        with pytest.raises(ExportError):
            build_zip(export, organizer)
        # The task records a failure rather than raising.
        assert "failed" in build_export_zip_task(export.pk)
        export.refresh_from_db()
        assert export.zip_status == ZipStatus.FAILED and "too large" in export.zip_error
        assert zip_url(export) == ""
        assert build_export_zip_task(10**6) == "No such export"

    def test_storage_failure_is_recorded(self, world, organizer, conference, settings):
        export = create_export(conference, organizer, clean_scope({"kinds": ["PROMO"]}))
        settings.SPEAKER_MEDIA_BUCKET = ""
        build_export_zip_task(export.pk)
        export.refresh_from_db()
        assert (
            export.zip_status == ZipStatus.FAILED
            and "SPEAKER_MEDIA_BUCKET" in export.zip_error
        )


@pytest.mark.django_db
class TestMaintenance:
    def test_the_list(self, client, world, organizer, maintainer, conference):
        export = create_export(
            conference, organizer, clean_scope({"kinds": ["RAW_VIDEO"]})
        )
        client.force_login(maintainer)
        response = client.get(MAINTENANCE)
        assert response.status_code == 200
        html = response.content.decode()
        assert "Olga" in html and "Raw video" in html and "50" in html
        assert 'href="{}"'.format(MAINTENANCE) in html
        export.created_by = None
        export.save()
        assert "account removed" in client.get(MAINTENANCE).content.decode()
        client.force_login(organizer)
        assert client.get(MAINTENANCE).status_code == 403

    def test_migration_creates_the_table(self):
        migration = importlib.import_module("speakers.migrations.0012_media_uploads")
        assert any(
            getattr(op, "name", "") == "MediaExport"
            for op in migration.Migration.operations
        )

    def test_write_script_quotes(self, world, organizer, conference):
        export = create_export(
            conference, organizer, clean_scope({"kinds": ["RAW_VIDEO"]})
        )
        with patch(
            "speakers.exports.MediaBucket.download_url",
            return_value="https://x/a?b=c&d=e",
        ):
            entries = export_entries(export, organizer)
        script = write_script(export, entries, io.StringIO()).getvalue()
        assert "'https://x/a?b=c&d=e'" in script
