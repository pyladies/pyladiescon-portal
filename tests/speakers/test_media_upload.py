"""The multipart upload backend (design §8.8, task 5.1), against moto's S3:
start, parts, resume, complete, abort, expiry, versioning, the permission
rule, and the endpoints' error shapes."""

import importlib
import json
import logging
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import boto3
import pytest
from botocore.exceptions import ClientError
from django.apps import apps
from django.contrib.auth.models import AnonymousUser, User
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from django_celery_beat.models import PeriodicTask
from moto import mock_aws

from speakers.constants import (
    AutoRule,
    ItemStatus,
    MediaKind,
    MediaStatus,
    UploadStatus,
)
from speakers.media import (
    MediaBucket,
    MediaStorageNotConfigured,
    UploadError,
    abort_upload,
    can_upload,
    complete_upload,
    content_disposition,
    expire_abandoned_uploads,
    plan_parts,
    received_parts,
    start_upload,
)
from speakers.models import MediaAsset, MediaUpload, SpeakerSettings
from speakers.signals import asset_ready
from speakers.tasks import expire_abandoned_uploads_task

from .factories import add_presenter, make_presenter, make_session, make_settings
from .test_rules import auto_item

migration = importlib.import_module("speakers.migrations.0012_media_uploads")

MIB = 1024 * 1024
BUCKET = "test-speaker-media"


@pytest.fixture
def enabled(conference):
    return make_settings(conference)


@pytest.fixture
def bucket(settings):
    """A mocked S3 with the bucket the settings name; parts of 5 MiB so a
    two-part file is small."""
    settings.SPEAKER_MEDIA_BUCKET = BUCKET
    settings.SPEAKER_MEDIA_PREFIX = "speaker-media/"
    settings.SPEAKER_MEDIA_ENDPOINT_URL = None
    settings.SPEAKER_MEDIA_REGION = "us-east-1"
    settings.SPEAKER_MEDIA_ACCESS_KEY_ID = "testing"
    settings.SPEAKER_MEDIA_SECRET_ACCESS_KEY = "testing"
    settings.SPEAKER_MEDIA_PART_SIZE = 5 * MIB
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield MediaBucket.from_settings()


@pytest.fixture
def organizer(db):
    return User.objects.create_user(username="org", email="org@x.org", is_staff=True)


@pytest.fixture
def performer(db):
    return User.objects.create_user(username="maria", email="maria@x.org")


@pytest.fixture
def session(conference, enabled, performer):
    session = make_session(conference, title="A PyJam set", kind="PYJAM")
    presenter = make_presenter(conference, display_name="Maria", user=performer)
    add_presenter(session, presenter, confirmed=True)
    return session


def start_url(session):
    return reverse("speakers:upload_start", args=[session.slug])


def url(name, session, upload):
    return reverse(f"speakers:upload_{name}", args=[session.slug, upload.pk])


def post_json(client, url, payload):
    return client.post(url, json.dumps(payload), content_type="application/json")


def upload_parts(bucket, upload, sizes):
    """Play the browser: PUT each part to the bucket and collect the ETags."""
    parts = []
    for number, size in enumerate(sizes, start=1):
        response = bucket.client.upload_part(
            Bucket=BUCKET,
            Key=upload.storage_key,
            UploadId=upload.upload_id,
            PartNumber=number,
            Body=b"v" * size,
        )
        parts.append({"number": number, "etag": response["ETag"]})
    return parts


def multipart_uploads(bucket):
    return bucket.client.list_multipart_uploads(Bucket=BUCKET).get("Uploads", [])


@pytest.mark.django_db
class TestWhoMayUpload:
    def test_the_rule(self, session, performer, organizer, conference):
        stranger = User.objects.create_user(username="sam")
        assert not can_upload(AnonymousUser(), session, MediaKind.RAW_VIDEO)
        assert can_upload(performer, session, MediaKind.RAW_VIDEO)
        assert not can_upload(performer, session, MediaKind.PROCESSED_VIDEO)
        assert not can_upload(stranger, session, MediaKind.RAW_VIDEO)
        assert can_upload(organizer, session, MediaKind.PROCESSED_VIDEO)
        other = make_session(conference, title="Not hers")
        assert not can_upload(performer, other, MediaKind.RAW_VIDEO)

    def test_endpoints_refuse_by_the_rule(self, client, bucket, session, performer):
        client.force_login(performer)
        payload = {
            "kind": MediaKind.PROCESSED_VIDEO,
            "filename": "final.mp4",
            "size_bytes": 10,
        }
        assert post_json(client, start_url(session), payload).status_code == 403
        client.force_login(User.objects.create_user(username="sam"))
        payload["kind"] = MediaKind.RAW_VIDEO
        assert post_json(client, start_url(session), payload).status_code == 403

    def test_anonymous_module_off_and_wrong_edition(
        self, client, bucket, session, performer, conference
    ):
        response = post_json(client, start_url(session), {})
        assert response.status_code == 302 and "login" in response.url
        client.force_login(performer)
        from portal.models import Conference

        other = Conference.objects.create(year=2020, name="2020", slug="2020")
        elsewhere = make_session(other, title="Old")
        assert (
            post_json(client, start_url(elsewhere), {"kind": "RAW_VIDEO"}).status_code
            == 404
        )
        from speakers.models import SpeakerSettings

        SpeakerSettings.objects.filter(conference=conference).update(
            speaker_module_enabled=False
        )
        assert (
            post_json(client, start_url(session), {"kind": "RAW_VIDEO"}).status_code
            == 404
        )


@pytest.mark.django_db
class TestLifecycle:
    def test_start_parts_resume_complete(self, client, bucket, session, performer):
        client.force_login(performer)
        response = post_json(
            client,
            start_url(session),
            {
                "kind": "RAW_VIDEO",
                "filename": "my set (final).mov",
                "size_bytes": 5 * MIB + 1,
                "content_type": "video/quicktime",
            },
        )
        assert response.status_code == 201, response.content
        data = response.json()
        upload = MediaUpload.objects.get(pk=data["upload"])
        assert data["parts_total"] == 2 and data["part_size"] == 5 * MIB
        assert [p["number"] for p in data["parts"]] == [1, 2]
        assert upload.storage_key.startswith(
            f"speaker-media/{session.conference.year}/{session.slug}/raw_video/"
        )
        assert upload.storage_key.endswith("/my-set-final.mov")
        assert (
            "partNumber=1" in data["parts"][0]["url"]
            and upload.storage_key in data["parts"][0]["url"]
        )
        assert upload.started_by == performer and upload.is_open
        assert len(multipart_uploads(bucket)) == 1

        # The browser drops after part 1; coming back, it learns what landed.
        parts = upload_parts(bucket, upload, [5 * MIB])
        detail = client.get(url("detail", session, upload)).json()
        assert detail["status"] == UploadStatus.STARTED
        # What landed, with the ETag the browser hands back on completion.
        assert [(p["number"], p["size"]) for p in detail["received"]] == [(1, 5 * MIB)]
        assert detail["received"][0]["etag"] == parts[0]["etag"]
        batch = client.get(url("parts", session, upload), {"from": 2}).json()["parts"]
        assert [p["number"] for p in batch] == [2]
        parts += [
            {
                "number": 2,
                "etag": bucket.client.upload_part(
                    Bucket=BUCKET,
                    Key=upload.storage_key,
                    UploadId=upload.upload_id,
                    PartNumber=2,
                    Body=b"!",
                )["ETag"],
            }
        ]

        heard = []
        asset_ready.connect(
            lambda sender, asset, **kw: heard.append(asset),
            weak=False,
            dispatch_uid="test.heard",
        )
        try:
            response = post_json(
                client, url("complete", session, upload), {"parts": parts}
            )
        finally:
            asset_ready.disconnect(dispatch_uid="test.heard")
        assert response.status_code == 200, response.content
        asset = MediaAsset.objects.get(pk=response.json()["asset"]["id"])
        assert asset.status == MediaStatus.READY and asset.version == 1
        assert (
            asset.size_bytes == 5 * MIB + 1
            and asset.original_filename == "my set (final).mov"
        )
        assert (
            asset.content_type == "video/quicktime" and asset.uploaded_by == performer
        )
        assert asset.storage_key == upload.storage_key
        assert heard == [asset]
        upload.refresh_from_db()
        assert upload.status == UploadStatus.COMPLETED and upload.asset == asset
        assert upload.completed_at is not None
        assert multipart_uploads(bucket) == []
        assert (
            bucket.client.head_object(Bucket=BUCKET, Key=asset.storage_key)[
                "ContentLength"
            ]
            == 5 * MIB + 1
        )
        link = asset.download_url()
        assert asset.storage_key in link and "my%20set" in link or "my set" in link

    def test_the_admin_names_an_upload(self, bucket, session, performer):
        upload = start_upload(
            session=session,
            kind="RAW_VIDEO",
            language="",
            filename="a.mp4",
            size_bytes=3,
            content_type="",
            user=performer,
        )
        assert str(upload) == f"Upload {upload.pk}: a.mp4 for {session}"

    def test_a_new_version_supersedes_the_last(self, bucket, session, performer):
        first = start_upload(
            session=session,
            kind="RAW_VIDEO",
            language="",
            filename="a.mp4",
            size_bytes=3,
            content_type="",
            user=performer,
        )
        one = complete_upload(first, upload_parts(bucket, first, [3]))
        second = start_upload(
            session=session,
            kind="RAW_VIDEO",
            language="",
            filename="b.mp4",
            size_bytes=4,
            content_type="",
            user=performer,
        )
        two = complete_upload(second, upload_parts(bucket, second, [4]))
        one.refresh_from_db()
        assert (one.version, one.status) == (1, MediaStatus.SUPERSEDED)
        assert (two.version, two.status) == (2, MediaStatus.READY)
        assert MediaAsset.latest_ready(session, MediaKind.RAW_VIDEO) == two
        # A transcript in another language is its own line of versions.
        en = start_upload(
            session=session,
            kind="TRANSCRIPT",
            language="en",
            filename="t.vtt",
            size_bytes=2,
            content_type="",
            user=performer,
        )
        assert complete_upload(en, upload_parts(bucket, en, [2])).version == 1

    def test_a_ready_asset_answers_the_waiting_items(
        self, bucket, session, performer, conference
    ):
        presenter = session.session_presenters.get().presenter
        waiting = auto_item(
            conference,
            AutoRule.ASSET_EXISTS,
            presenter=presenter,
            session=session,
            requires_asset_kind=MediaKind.RAW_VIDEO,
        )
        assert waiting.status != ItemStatus.DONE
        upload = start_upload(
            session=session,
            kind="RAW_VIDEO",
            language="",
            filename="a.mp4",
            size_bytes=3,
            content_type="",
            user=performer,
        )
        complete_upload(upload, upload_parts(bucket, upload, [3]))
        waiting.refresh_from_db()
        assert waiting.status == ItemStatus.DONE

    def test_abort(self, client, bucket, session, performer, organizer):
        client.force_login(performer)
        upload = MediaUpload.objects.get(
            pk=post_json(
                client,
                start_url(session),
                {"kind": "RAW_VIDEO", "filename": "a.mp4", "size_bytes": 3},
            ).json()["upload"]
        )
        # Not theirs: another presenter is refused, an organizer may.
        other = User.objects.create_user(username="other")
        client.force_login(other)
        assert client.post(url("abort", session, upload)).status_code == 403
        client.force_login(organizer)
        response = client.post(url("abort", session, upload))
        assert (
            response.status_code == 200
            and response.json()["status"] == UploadStatus.ABORTED
        )
        assert multipart_uploads(bucket) == []
        # Nothing further happens to a closed upload.
        assert client.post(url("abort", session, upload)).status_code == 400
        assert (
            client.post(
                url("complete", session, upload),
                json.dumps({"parts": []}),
                content_type="application/json",
            ).status_code
            == 400
        )
        assert client.get(url("parts", session, upload)).status_code == 400
        assert client.get(url("detail", session, upload)).json()["received"] == []

    def test_complete_refuses_the_wrong_parts(self, client, bucket, session, performer):
        client.force_login(performer)
        upload = MediaUpload.objects.get(
            pk=post_json(
                client,
                start_url(session),
                {"kind": "RAW_VIDEO", "filename": "a.mp4", "size_bytes": 5 * MIB + 1},
            ).json()["upload"]
        )
        parts = upload_parts(bucket, upload, [5 * MIB, 1])
        assert (
            post_json(
                client, url("complete", session, upload), {"parts": parts[:1]}
            ).status_code
            == 400
        )
        assert (
            post_json(
                client,
                url("complete", session, upload),
                {"parts": [{"number": 1, "etag": ""}, {"number": 2, "etag": ""}]},
            ).status_code
            == 400
        )
        assert (
            post_json(
                client, url("complete", session, upload), {"parts": "no"}
            ).status_code
            == 400
        )
        assert (
            client.post(
                url("complete", session, upload),
                "not json",
                content_type="application/json",
            ).status_code
            == 400
        )
        assert (
            client.get(url("parts", session, upload), {"from": "x"}).status_code == 400
        )
        assert client.get(url("parts", session, upload), {"from": 9}).status_code == 404
        upload.refresh_from_db()
        assert upload.is_open


@pytest.mark.django_db
class TestStartValidation:
    def test_sizes_and_names(self, client, bucket, session, organizer, settings):
        client.force_login(organizer)

        def start(**payload):
            base = {
                "kind": "PROCESSED_VIDEO",
                "filename": "final.mp4",
                "size_bytes": 10,
            }
            base.update(payload)
            return post_json(client, start_url(session), base)

        assert start(size_bytes=0).status_code == 400
        assert start(size_bytes="ten").status_code == 400
        assert start(size_bytes=settings.SPEAKER_MEDIA_MAX_BYTES + 1).status_code == 400
        assert start(filename="").status_code == 400
        # An organizer may upload any kind, so an unknown kind is a bad
        # request rather than a refusal.
        assert start(kind="MOVIE").status_code == 400
        assert client.get(start_url(session)).status_code == 405
        settings.SPEAKER_MEDIA_MAX_BYTES = 10**13
        with pytest.raises(UploadError):
            plan_parts(10_001 * 5 * MIB)
        assert start(size_bytes=10, content_type="").status_code == 201

    def test_storage_not_configured(self, client, session, performer, settings):
        settings.SPEAKER_MEDIA_BUCKET = ""
        client.force_login(performer)
        response = post_json(
            client,
            start_url(session),
            {"kind": "RAW_VIDEO", "filename": "a.mp4", "size_bytes": 3},
        )
        assert response.status_code == 503
        with pytest.raises(MediaStorageNotConfigured):
            MediaBucket.from_settings()


@pytest.mark.django_db
class TestBucket:
    def test_key_names_are_safe(self, bucket, session):
        key = bucket.key_for(session, "RAW_VIDEO", "../../etc/passwd; rm -rf ~.mov")
        assert key.endswith("/etc-passwd-rm-rf.mov")
        assert ".." not in key.split("/")[-1]
        assert bucket.key_for(session, "OTHER", "###").endswith("/upload")

    def test_abort_tolerates_an_upload_the_bucket_forgot(
        self, bucket, session, performer
    ):
        upload = start_upload(
            session=session,
            kind="RAW_VIDEO",
            language="",
            filename="a.mp4",
            size_bytes=3,
            content_type="",
            user=performer,
        )
        bucket.abort(upload.storage_key, upload.upload_id)
        bucket.abort(upload.storage_key, upload.upload_id)  # NoSuchUpload: fine
        with pytest.raises(ClientError):
            MediaBucket("no-such-bucket", "x/", bucket.client).abort("k", "u")

    def test_received_parts_follows_pages(self, bucket):
        pages = [
            {
                "Parts": [{"PartNumber": 2, "ETag": '"b"', "Size": 5}],
                "IsTruncated": True,
                "NextPartNumberMarker": 2,
            },
            {
                "Parts": [{"PartNumber": 1, "ETag": '"a"', "Size": 5}],
                "IsTruncated": False,
            },
        ]
        with patch.object(bucket.client, "list_parts", side_effect=pages):
            assert bucket.received_parts("k", "u") == [
                {"number": 1, "etag": '"a"', "size": 5},
                {"number": 2, "etag": '"b"', "size": 5},
            ]

    def test_download_url_without_a_key(self, session):
        asset = MediaAsset(session=session, kind="OTHER")
        assert asset.download_url() == ""


@pytest.mark.django_db
class TestExpiry:
    def test_expired_uploads_are_aborted(self, bucket, session, performer):
        stale = start_upload(
            session=session,
            kind="RAW_VIDEO",
            language="",
            filename="a.mp4",
            size_bytes=3,
            content_type="",
            user=performer,
        )
        fresh = start_upload(
            session=session,
            kind="RAW_VIDEO",
            language="",
            filename="b.mp4",
            size_bytes=3,
            content_type="",
            user=performer,
        )
        MediaUpload.objects.filter(pk=stale.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        assert expire_abandoned_uploads() == 1
        stale.refresh_from_db()
        fresh.refresh_from_db()
        assert stale.status == UploadStatus.EXPIRED and fresh.is_open
        assert len(multipart_uploads(bucket)) == 1
        assert expire_abandoned_uploads_task() == "Expired 0 abandoned upload(s)"
        out = StringIO()
        call_command("expire_abandoned_uploads", stdout=out)
        assert "Expired 0 abandoned upload(s)" in out.getvalue()

    def test_periodic_task_is_seeded_once(self):
        migration.seed_periodic_task(apps, None)
        migration.seed_periodic_task(apps, None)
        task = PeriodicTask.objects.get(name=migration.TASK_NAME)
        assert task.task == expire_abandoned_uploads_task.name
        assert (task.crontab.hour, task.crontab.minute) == ("4", "0")
        migration.unseed_periodic_task(apps, None)
        assert not PeriodicTask.objects.filter(name=migration.TASK_NAME).exists()

    def test_abort_of_a_closed_upload_is_refused(self, bucket, session, performer):
        upload = start_upload(
            session=session,
            kind="RAW_VIDEO",
            language="",
            filename="a.mp4",
            size_bytes=3,
            content_type="",
            user=performer,
        )
        abort_upload(upload)
        with pytest.raises(UploadError):
            abort_upload(upload)
        with pytest.raises(UploadError):
            complete_upload(upload, [])
        assert received_parts(upload) == []


def raw_upload(session, user, **kwargs):
    base = dict(
        session=session,
        kind="RAW_VIDEO",
        language="",
        filename="a.mp4",
        size_bytes=3,
        content_type="video/mp4",
        user=user,
    )
    base.update(kwargs)
    return start_upload(**base)


@pytest.mark.django_db
class TestWhatArrives:
    def test_an_object_that_is_not_the_declared_size_is_thrown_away(
        self, client, bucket, session, performer
    ):
        """The declared size is what the cap was checked against; the parts
        go to the bucket out of sight, so the object is measured when it
        is complete, and one that disagrees is removed before any row
        records it."""
        client.force_login(performer)
        upload = raw_upload(session, performer)
        parts = upload_parts(bucket, upload, [12])
        response = post_json(client, url("complete", session, upload), {"parts": parts})
        assert response.status_code == 400
        assert "12 bytes, not the 3 declared" in response.json()["error"]
        upload.refresh_from_db()
        assert upload.status == "ABORTED" and upload.asset is None
        assert not MediaAsset.objects.filter(session=session).exists()
        with pytest.raises(ClientError):
            bucket.client.head_object(Bucket=BUCKET, Key=upload.storage_key)


@pytest.mark.django_db
class TestProposalsHaveNoChannel:
    def test_the_rule_and_the_endpoint(
        self, client, bucket, session, performer, organizer
    ):
        client.force_login(performer)
        for status in ("PROPOSED", "REJECTED"):
            session.status = status
            session.save()
            assert not can_upload(performer, session, MediaKind.RAW_VIDEO)
            assert can_upload(organizer, session, MediaKind.RAW_VIDEO)
            payload = {"kind": "RAW_VIDEO", "filename": "a.mp4", "size_bytes": 3}
            assert post_json(client, start_url(session), payload).status_code == 403

    def test_an_upload_in_flight_goes_with_the_seat(
        self, client, bucket, session, performer
    ):
        """Every endpoint re-asks can_upload: a presenter taken off the
        session cannot finish, resume or even look at what they started."""
        client.force_login(performer)
        upload = raw_upload(session, performer)
        session.session_presenters.all().delete()
        assert client.get(url("detail", session, upload)).status_code == 403
        assert client.get(url("parts", session, upload)).status_code == 403
        complete = post_json(client, url("complete", session, upload), {"parts": []})
        assert complete.status_code == 403
        upload.refresh_from_db()
        assert upload.is_open
        # Giving it up only frees the bucket, so that stays theirs to do.
        assert post_json(client, url("abort", session, upload), {}).status_code == 200
        upload.refresh_from_db()
        assert not upload.is_open


@pytest.mark.django_db
class TestTheSwitchAndAnUploadInFlight:
    def test_switching_off_still_lets_them_give_it_up(
        self, client, bucket, session, performer, conference
    ):
        """With the speaker side switched off mid-upload the presenter can
        no longer finish, but need not wait for the nightly expiry to
        free the bucket: aborting their own upload stays theirs."""
        client.force_login(performer)
        upload = raw_upload(session, performer)
        SpeakerSettings.objects.filter(conference=conference).update(
            media_for_speakers=False
        )
        complete = post_json(client, url("complete", session, upload), {"parts": []})
        assert complete.status_code == 403
        assert post_json(client, url("abort", session, upload), {}).status_code == 200
        upload.refresh_from_db()
        assert not upload.is_open


@pytest.mark.django_db
class TestLanguageAndType:
    def test_the_raw_video_is_one_line_whatever_the_tag(
        self, bucket, session, performer
    ):
        upload = raw_upload(session, performer, language="zz", content_type="")
        assert upload.language == "" and upload.content_type == "video/mp4"

    def test_other_kinds_take_a_well_formed_tag(self, bucket, session, organizer):
        transcript = dict(kind="TRANSCRIPT", filename="t.vtt", content_type="text/vtt")
        tagged = raw_upload(session, organizer, language=" pt-BR ", **transcript)
        assert tagged.language == "pt-BR"
        with pytest.raises(UploadError, match="tag such as"):
            raw_upload(session, organizer, language="zz!", **transcript)

    def test_a_video_kind_wants_a_video(self, bucket, session, organizer):
        with pytest.raises(UploadError, match="choose a video file"):
            raw_upload(
                session,
                organizer,
                kind="PROCESSED_VIDEO",
                filename="poster.png",
                content_type="image/png",
            )
        by_extension = raw_upload(
            session,
            organizer,
            kind="PROCESSED_VIDEO",
            filename="final.MOV",
            content_type="not a type",
        )
        assert by_extension.content_type == "video/quicktime"
        by_type = raw_upload(
            session,
            organizer,
            kind="PROCESSED_VIDEO",
            filename="final",
            content_type="video/x-matroska",
        )
        assert by_type.content_type == "video/x-matroska"


@pytest.mark.django_db
class TestBadBodiesAndNames:
    def test_a_body_that_is_not_an_object_is_a_bad_request(
        self, client, bucket, session, performer
    ):
        client.force_login(performer)
        for body in ([1, 2, 3], "hi", None, 7):
            response = post_json(client, start_url(session), body)
            assert response.status_code == 400, body
            assert "JSON object" in response.json()["error"]

    def test_a_name_or_a_row_that_fails_leaves_no_multipart(
        self, bucket, session, performer
    ):
        with pytest.raises(UploadError, match="cannot carry"):
            raw_upload(session, performer, filename="a\x00.mp4")
        assert multipart_uploads(bucket) == []
        with patch(
            "speakers.media.MediaUpload.objects.create",
            side_effect=RuntimeError("the database went away"),
        ):
            with pytest.raises(RuntimeError):
                raw_upload(session, performer)
        assert multipart_uploads(bucket) == []

    def test_a_get_with_the_module_off_is_404_not_405(
        self, client, bucket, session, performer, conference
    ):
        client.force_login(performer)
        upload = raw_upload(session, performer)
        SpeakerSettings.objects.filter(conference=conference).update(
            speaker_module_enabled=False
        )
        assert client.get(start_url(session)).status_code == 404
        assert client.get(url("complete", session, upload)).status_code == 404
        assert client.get(url("abort", session, upload)).status_code == 404


@pytest.mark.django_db
class TestTheObjectGoesWithTheRow:
    def test_deleting_the_asset_deletes_the_object(
        self, bucket, session, performer, settings, caplog
    ):
        upload = raw_upload(session, performer)
        asset = complete_upload(upload, upload_parts(bucket, upload, [3]))
        bucket.client.head_object(Bucket=BUCKET, Key=asset.storage_key)
        asset.delete()
        with pytest.raises(ClientError):
            bucket.client.head_object(Bucket=BUCKET, Key=upload.storage_key)
        # Without storage the row still goes, and the log says what stays.
        orphan = MediaAsset.objects.create(
            session=session, kind=MediaKind.OTHER, storage_key="speaker-media/x/y"
        )
        settings.SPEAKER_MEDIA_BUCKET = ""
        with caplog.at_level(logging.ERROR):
            orphan.delete()
        assert "stays in the bucket" in caplog.text
        MediaAsset.objects.create(session=session, kind=MediaKind.OTHER).delete()


class TestContentDisposition:
    def test_the_header_the_bucket_is_told(self):
        assert content_disposition("take.mp4") == 'attachment; filename="take.mp4"'
        assert (
            content_disposition('my "set"\\final\r\n.mov')
            == 'attachment; filename="my setfinal.mov"'
        )
        assert content_disposition("sessão.mp4") == (
            "attachment; filename=\"sesso.mp4\"; filename*=UTF-8''sess%C3%A3o.mp4"
        )
        assert content_disposition("日本").startswith('attachment; filename="download"')
