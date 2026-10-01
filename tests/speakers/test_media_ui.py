"""The upload UI and the file lists (design §4.1 and §8.8, task 5.2): the
performer's video card, the organizer's files section, the download
redirect, and the reviewer's note. The chunking itself is the browser's
job (static/js/media-upload.js) and is tried by hand against a bucket."""

from datetime import timedelta

import boto3
import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from moto import mock_aws

from speakers.constants import MediaKind, MediaStatus, UploadStatus
from speakers.media import (
    MediaBucket,
    asset_groups,
    can_download,
    open_uploads,
    session_assets,
    video_limit_minutes,
    video_panel,
)
from speakers.models import MediaAsset, MediaUpload

from .factories import add_presenter, make_presenter, make_session, make_settings

BUCKET = "test-speaker-media"


@pytest.fixture
def enabled(conference):
    return make_settings(conference, default_video_length_limit_minutes=10)


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
    return User.objects.create_user(username="org", email="org@x.org", is_staff=True)


@pytest.fixture
def performer(db):
    return User.objects.create_user(username="maria", email="maria@x.org")


@pytest.fixture
def liaison(db):
    return User.objects.create_user(username="lia", email="lia@x.org")


@pytest.fixture
def session(conference, enabled, performer, liaison):
    session = make_session(conference, title="A PyJam set", kind="PYJAM")
    presenter = make_presenter(
        conference, display_name="Maria", user=performer, liaison=liaison
    )
    add_presenter(session, presenter, confirmed=True)
    return session


def make_asset(session, user, **kwargs):
    kwargs.setdefault("kind", MediaKind.RAW_VIDEO)
    kwargs.setdefault("status", MediaStatus.READY)
    kwargs.setdefault("storage_key", f"speaker-media/{session.slug}/x/take.mp4")
    kwargs.setdefault("original_filename", "take.mp4")
    kwargs.setdefault("size_bytes", 12_000_000)
    return MediaAsset.objects.create(session=session, uploaded_by=user, **kwargs)


def my_page(session):
    return reverse("speakers:my_session_detail", args=[session.slug])


def org_page(session):
    return reverse("speakers:session_detail", args=[session.slug])


def download(session, asset):
    return reverse("speakers:media_download", args=[session.slug, asset.pk])


def notes(session, asset):
    return reverse("speakers:media_notes", args=[session.slug, asset.pk])


@pytest.mark.django_db
class TestPerformerCard:
    def test_no_bucket_no_panel(self, client, session, performer, settings):
        """Without storage the panel could only fail, so the page says
        nothing about video until the portal has a bucket."""
        settings.SPEAKER_MEDIA_BUCKET = ""
        client.force_login(performer)
        response = client.get(my_page(session))
        assert response.status_code == 200
        assert response.context["video"] is None
        assert "data-upload-panel" not in response.content.decode()

    def test_pre_recorded_session_gets_the_panel(
        self, client, session, performer, bucket
    ):
        client.force_login(performer)
        response = client.get(my_page(session))
        assert response.status_code == 200
        html = response.content.decode()
        assert response.context["video"]["current"] is None
        assert "data-upload-panel" in html and 'data-kind="RAW_VIDEO"' in html
        assert reverse("speakers:upload_start", args=[session.slug]) in html
        assert "js/media-upload" in html  # hashed name under the manifest storage
        assert "No video yet" in html

    def test_live_session_has_no_panel(self, client, conference, performer, enabled):
        session = make_session(conference, kind="TALK")
        add_presenter(
            session, make_presenter(conference, user=performer), confirmed=True
        )
        client.force_login(performer)
        response = client.get(my_page(session))
        assert response.context["video"] is None
        assert "data-upload-panel" not in response.content.decode()

    def test_current_version_history_and_the_length_bar(
        self, client, session, performer, bucket
    ):
        old = make_asset(session, performer, version=1, status=MediaStatus.SUPERSEDED)
        current = make_asset(session, performer, version=2, duration_seconds=11 * 60)
        client.force_login(performer)
        response = client.get(my_page(session))
        video = response.context["video"]
        assert video["current"] == current and video["history"] == [old]
        assert video["limit_minutes"] == 10
        assert video["duration_pct"] == 100 and video["over_by"] == 60
        html = response.content.decode()
        assert "over the 10-minute limit" in html
        assert "1 earlier version" in html
        assert download(session, current) in html and download(session, old) in html
        assert "Replace it" in html

    def test_bar_under_the_limit_and_without_a_probe(self, session, performer):
        current = make_asset(session, performer, duration_seconds=5 * 60)
        panel = video_panel(session, performer)
        assert panel["duration_pct"] == 50 and panel["over_by"] == 0
        current.duration_seconds = None
        current.save()
        panel = video_panel(session, performer)
        assert panel["duration_pct"] is None and panel["over_by"] is None

    def test_the_limit_comes_from_the_session_then_the_edition(
        self, session, conference
    ):
        assert video_limit_minutes(session) == 10
        session.video_length_limit_minutes = 25
        assert video_limit_minutes(session) == 25
        session.video_length_limit_minutes = None
        conference.speaker_settings.delete()
        assert video_limit_minutes(session) is None

    def test_open_uploads_are_mentioned(
        self, client, session, performer, organizer, bucket
    ):
        for user in (performer, organizer):
            MediaUpload.objects.create(
                session=session,
                kind=MediaKind.RAW_VIDEO,
                filename="take.mp4",
                size_bytes=1,
                part_size=1,
                parts_total=1,
                storage_key="k",
                upload_id="u",
                expires_at=timezone.now() + timedelta(hours=1),
                started_by=user,
            )
        MediaUpload.objects.create(
            session=session,
            kind=MediaKind.RAW_VIDEO,
            filename="stale.mp4",
            size_bytes=1,
            part_size=1,
            parts_total=1,
            storage_key="k2",
            upload_id="u2",
            status=UploadStatus.STARTED,
            expires_at=timezone.now() - timedelta(hours=1),
            started_by=performer,
        )
        # Only the caller's live uploads count; the expired one is not offered.
        assert [u.filename for u in open_uploads(session, performer)] == ["take.mp4"]
        client.force_login(performer)
        html = client.get(my_page(session)).content.decode()
        assert "One upload of yours is still open" in html


@pytest.mark.django_db
class TestOrganizerFiles:
    def test_groups_by_kind_and_language(self, session, organizer):
        raw_old = make_asset(
            session, organizer, version=1, status=MediaStatus.SUPERSEDED
        )
        raw = make_asset(session, organizer, version=2)
        failed = make_asset(session, organizer, version=3, status=MediaStatus.FAILED)
        en = make_asset(session, organizer, kind=MediaKind.TRANSCRIPT, language="en")
        pt = make_asset(session, organizer, kind=MediaKind.TRANSCRIPT, language="pt")
        groups = asset_groups(session_assets(session))
        assert [(g["kind"], g["language"]) for g in groups] == [
            (MediaKind.RAW_VIDEO, ""),
            (MediaKind.TRANSCRIPT, "en"),
            (MediaKind.TRANSCRIPT, "pt"),
        ]
        # The newest READY one is current; a failed newer attempt is history.
        assert groups[0]["current"] == raw
        assert groups[0]["history"] == [failed, raw_old]
        assert groups[1]["current"] == en and groups[2]["current"] == pt
        assert groups[1]["label"] == "Transcript"

    def test_the_page_lists_files_and_offers_the_panel(
        self, client, session, organizer, bucket
    ):
        asset = make_asset(session, organizer, notes_md="audio clips at 4:10")
        client.force_login(organizer)
        response = client.get(org_page(session))
        assert response.status_code == 200
        html = response.content.decode()
        assert response.context["can_upload_media"] is True
        assert 'id="files-raw_video----"' in html
        assert download(session, asset) in html
        assert notes(session, asset) in html and "audio clips at 4:10" in html
        assert 'data-role="kind"' in html and 'data-role="language"' in html
        assert "js/media-upload" in html  # hashed name under the manifest storage

    def test_a_liaison_reads_but_does_not_upload_or_annotate(
        self, client, session, liaison, organizer
    ):
        asset = make_asset(session, organizer, notes_md="a note")
        client.force_login(liaison)
        response = client.get(org_page(session))
        assert response.status_code == 200
        html = response.content.decode()
        assert response.context["can_upload_media"] is False
        assert download(session, asset) in html
        assert "a note" in html and notes(session, asset) not in html
        assert "data-upload-panel" not in html

    def test_no_files_yet(self, client, session, organizer):
        client.force_login(organizer)
        assert "No files yet" in client.get(org_page(session)).content.decode()


@pytest.mark.django_db
class TestDownload:
    def test_who_may(self, session, performer, liaison, organizer):
        stranger = User.objects.create_user("s", email="s@x.org")
        assert can_download(organizer, session)
        assert can_download(performer, session)
        assert can_download(liaison, session)
        assert not can_download(stranger, session)
        assert not can_download(AnonymousUser(), session)

    def test_redirects_to_a_fresh_presigned_link(
        self, client, bucket, session, performer, organizer, liaison
    ):
        asset = make_asset(session, organizer)
        for user in (performer, organizer, liaison):
            client.force_login(user)
            response = client.get(download(session, asset))
            assert response.status_code == 302
            assert asset.storage_key in response["Location"]
            assert "X-Amz-Signature" in response["Location"]
            assert "take.mp4" in response["Location"]

    def test_a_presenter_fetches_their_video_and_what_is_shared(
        self, client, bucket, session, performer, liaison, organizer
    ):
        cut = make_asset(
            session, organizer, kind=MediaKind.PROCESSED_VIDEO, shared_with_speaker=True
        )
        intro = make_asset(session, organizer, kind=MediaKind.INTRO)
        unshared = make_asset(session, organizer, kind=MediaKind.PROCESSED_VIDEO)
        assert can_download(performer, session, cut)
        assert not can_download(performer, session, intro)
        assert not can_download(performer, session, unshared)
        assert can_download(liaison, session, intro)
        assert can_download(organizer, session, intro)
        client.force_login(performer)
        assert client.get(download(session, cut)).status_code == 302
        assert client.get(download(session, intro)).status_code == 403
        session.status = "PROPOSED"
        session.save()
        assert not can_download(performer, session) and can_download(liaison, session)
        assert client.get(download(session, cut)).status_code == 403

    def test_the_link_lives_a_minute_and_carries_a_safe_name(
        self, client, bucket, session, organizer
    ):
        asset = make_asset(session, organizer, original_filename='my "set".mp4')
        client.force_login(organizer)
        location = client.get(download(session, asset))["Location"]
        assert "X-Amz-Expires=60" in location
        assert "my%20set.mp4" in location and "%22set%22" not in location

    def test_refusals(self, client, bucket, session, organizer, conference):
        asset = make_asset(session, organizer)
        stranger = User.objects.create_user("s", email="s@x.org")
        client.force_login(stranger)
        assert client.get(download(session, asset)).status_code == 403
        client.force_login(organizer)
        other = make_session(conference, kind="PYJAM")
        assert client.get(download(other, asset)).status_code == 404
        empty = MediaAsset.objects.create(session=session, kind=MediaKind.OTHER)
        assert client.get(download(session, empty)).status_code == 404

    def test_storage_not_configured_is_a_404_not_a_500(
        self, client, session, organizer, settings
    ):
        settings.SPEAKER_MEDIA_BUCKET = ""
        asset = make_asset(session, organizer)
        client.force_login(organizer)
        assert client.get(download(session, asset)).status_code == 404

    def test_an_admin_attached_file_still_downloads(self, client, session, organizer):
        asset = MediaAsset.objects.create(
            session=session,
            kind=MediaKind.THUMBNAIL,
            status=MediaStatus.READY,
            file=SimpleUploadedFile("thumb.png", b"png"),
        )
        client.force_login(organizer)
        response = client.get(download(session, asset))
        assert response.status_code == 302 and "thumb" in response["Location"]


@pytest.mark.django_db
class TestNotes:
    def test_organizer_saves_a_note(self, client, session, organizer):
        asset = make_asset(session, organizer)
        client.force_login(organizer)
        response = client.post(
            notes(session, asset), {"notes_md": "  audio clips at 4:10 "}
        )
        assert response.status_code == 302
        assert response["Location"] == f"{org_page(session)}#files"
        asset.refresh_from_db()
        assert asset.notes_md == "audio clips at 4:10"

    def test_others_may_not(self, client, session, organizer, performer, liaison):
        asset = make_asset(session, organizer)
        for user in (performer, liaison):
            client.force_login(user)
            assert (
                client.post(notes(session, asset), {"notes_md": "x"}).status_code == 403
            )
        client.force_login(organizer)
        assert client.get(notes(session, asset)).status_code == 405


class TestDurationFilter:
    def test_minutes_and_seconds(self):
        from speakers.templatetags.speakers_extras import duration

        assert duration(None) == ""
        assert duration(0) == "0 s"
        assert duration(45) == "45 s"
        assert duration(60) == "1 min 00 s"
        assert duration(119) == "1 min 59 s"
        assert duration(3723) == "1 h 02 min 03 s"
