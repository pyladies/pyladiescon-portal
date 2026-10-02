"""Deleting a file line, every version of it (design §8.8, "Deleting a
file"): organizers any line, a performer their own raw video, both after
typing the file's name back; what a cancelled session keeps and what the
admin's session delete takes with it. The view's client runs the commit
hooks; a direct delete runs them with ``commits``."""

import logging

import boto3
import pytest
from botocore.exceptions import ClientError
from django.contrib.auth.models import AnonymousUser, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from moto import mock_aws

from speakers.constants import MediaKind, MediaStatus, TranscriptionStatus
from speakers.media import (
    MediaBucket,
    MediaDeleteError,
    can_delete,
    complete_upload,
    confirmation_name,
    delete_line,
    start_upload,
    video_panel,
)
from speakers.models import (
    ActivityLog,
    MediaAsset,
    MediaUpload,
    Session,
    TranscriptionJob,
)
from speakers.transcription import transcript_variant

from .factories import add_presenter, make_presenter, make_session, make_settings

BUCKET = "test-speaker-media"


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
def commits(django_capture_on_commit_callbacks):
    """Run the commit hooks after a direct delete, the way a request's
    commit would: the bucket work waits for them."""

    def _within(action):
        with django_capture_on_commit_callbacks(execute=True):
            return action()

    return _within


@pytest.fixture
def organizer(db):
    return User.objects.create_user("org", email="org@x.org", is_staff=True)


@pytest.fixture
def performer(db):
    return User.objects.create_user("maria", email="maria@x.org")


@pytest.fixture
def liaison(db):
    return User.objects.create_user("lia", email="lia@x.org")


@pytest.fixture
def enabled(conference):
    return make_settings(conference)


@pytest.fixture
def session(conference, enabled, performer, liaison):
    session = make_session(conference, title="A PyJam set", kind="PYJAM")
    presenter = make_presenter(
        conference, display_name="Maria", user=performer, liaison=liaison
    )
    add_presenter(session, presenter, confirmed=True)
    return session


def upload(bucket, session, user, kind=MediaKind.RAW_VIDEO, filename=None, **kw):
    """A completed one-part upload with a thumbnail object beside it."""
    kind = MediaKind(kind)
    started = start_upload(
        session=session,
        kind=kind,
        language=kw.pop("language", ""),
        variant=kw.pop("variant", ""),
        filename=filename or f"{kind.lower()}.{'mp4' if 'VIDEO' in kind else 'png'}",
        size_bytes=3,
        content_type="video/mp4" if "VIDEO" in kind else "image/png",
        user=user,
        **kw,
    )
    part = bucket.client.upload_part(
        Bucket=BUCKET,
        Key=started.storage_key,
        UploadId=started.upload_id,
        PartNumber=1,
        Body=b"abc",
    )
    asset = complete_upload(started, [{"number": 1, "etag": part["ETag"]}])
    asset.thumbnail_key = f"{asset.storage_key}.thumb.jpg"
    asset.save(update_fields=["thumbnail_key"])
    bucket.client.put_object(Bucket=BUCKET, Key=asset.thumbnail_key, Body=b"jpg")
    return asset


def in_bucket(bucket, key):
    try:
        bucket.client.head_object(Bucket=BUCKET, Key=key)
    except ClientError:
        return False
    return True


def delete_url(session, asset):
    return reverse("speakers:media_delete", args=[session.slug, asset.pk])


def organizer_page(session):
    return reverse("speakers:session_detail", args=[session.slug])


def my_page(session):
    return reverse("speakers:my_session_detail", args=[session.slug])


def flashed(response):
    return [str(m) for m in response.context["messages"]]


@pytest.mark.django_db
class TestOrganizerDeletes:
    def test_every_version_goes_with_its_objects_and_thumbnails(
        self, client, bucket, session, organizer, performer
    ):
        """Two versions of the raw video and one poster. Deleting the video
        line takes both versions, their objects and their thumbnails, and
        leaves the poster; the session page says so and the log has it."""
        v1 = upload(bucket, session, performer, filename="take1.mp4")
        v2 = upload(bucket, session, organizer, filename="take2.mp4")
        poster = upload(bucket, session, organizer, MediaKind.PROMO, variant="square")
        client.force_login(organizer)
        response = client.post(
            delete_url(session, v1), {"confirm": "take2.mp4"}, follow=True
        )
        assert response.redirect_chain[-1][0].endswith(
            f"{session.get_absolute_url()}#files"
        )
        assert flashed(response) == [
            "Deleted Raw video (performer upload) (take2.mp4), 2 version(s), "
            "from the portal and from storage."
        ]
        assert not MediaAsset.objects.filter(pk__in=[v1.pk, v2.pk]).exists()
        assert MediaAsset.objects.filter(pk=poster.pk).exists()
        for asset in (v1, v2):
            assert not in_bucket(bucket, asset.storage_key)
            assert not in_bucket(bucket, asset.thumbnail_key)
        assert in_bucket(bucket, poster.storage_key)
        assert in_bucket(bucket, poster.thumbnail_key)
        entry = ActivityLog.objects.get(action="media.deleted")
        assert entry.actor == organizer and entry.target == session
        assert entry.message == (
            "Raw video (performer upload): take2.mp4, 2 version(s)"
        )
        assert entry.data["filenames"] == ["take2.mp4", "take1.mp4"]
        assert entry.data["versions"] == 2

    def test_the_name_must_match_the_one_shown(
        self, client, bucket, session, organizer
    ):
        """The newest ready version's name is the one on the row, so that
        is the one to type; an older version's name, or none, deletes
        nothing. Surrounding spaces are forgiven."""
        v1 = upload(bucket, session, organizer, filename="take1.mp4")
        upload(bucket, session, organizer, filename="take2.mp4")
        client.force_login(organizer)
        for wrong in ("take1.mp4", "", "TAKE2.MP4"):
            response = client.post(
                delete_url(session, v1), {"confirm": wrong}, follow=True
            )
            assert flashed(response) == [
                "Type the file name exactly as shown to confirm."
            ]
        assert MediaAsset.objects.filter(session=session).count() == 2
        response = client.post(
            delete_url(session, v1), {"confirm": "  take2.mp4 "}, follow=True
        )
        assert flashed(response)[0].startswith("Deleted ")
        assert not MediaAsset.objects.filter(session=session).exists()

    def test_a_titled_line_is_named_by_its_title(
        self, client, bucket, session, organizer
    ):
        asset = upload(
            bucket,
            session,
            organizer,
            MediaKind.PROMO,
            variant="square",
            title="Poster",
        )
        client.force_login(organizer)
        response = client.post(
            delete_url(session, asset), {"confirm": "promo.png"}, follow=True
        )
        assert flashed(response) == [
            "Deleted Poster (promo.png), 1 version(s), from the portal and "
            "from storage."
        ]

    def test_a_video_being_transcribed_waits(self, bucket, session, organizer):
        """The job would write a transcript for a file that is gone."""
        video = upload(bucket, session, organizer)
        job = TranscriptionJob.objects.create(
            asset=video, status=TranscriptionStatus.RUNNING, started_by=organizer
        )
        with pytest.raises(MediaDeleteError, match="under way"):
            delete_line(video, organizer, "raw_video.mp4")
        assert MediaAsset.objects.filter(pk=video.pk).exists()
        job.status = TranscriptionStatus.DONE
        job.save(update_fields=["status"])
        assert delete_line(video, organizer, "raw_video.mp4") == (
            "Raw video (performer upload)",
            "raw_video.mp4",
            1,
            0,
        )
        assert not TranscriptionJob.objects.filter(pk=job.pk).exists()

    def test_others_may_not(self, client, bucket, session, organizer, liaison):
        """A liaison reads the files but does not delete them; a GET is
        not a delete; a file on another session is not found here."""
        video = upload(bucket, session, organizer)
        client.force_login(liaison)
        response = client.post(delete_url(session, video), {"confirm": "x"})
        assert response.status_code == 403
        client.force_login(organizer)
        assert client.get(delete_url(session, video)).status_code == 405
        other = make_session(session.conference, title="Other", kind="PYJAM")
        response = client.post(delete_url(other, video), {"confirm": "x"})
        assert response.status_code == 404
        assert MediaAsset.objects.filter(pk=video.pk).exists()

    def test_the_page_offers_it_to_organizers_only(
        self, client, bucket, session, organizer, liaison
    ):
        """The More row carries the button with what the dialog needs, and
        the page has the one dialog and its script; the liaison's page has
        none of it."""
        video = upload(bucket, session, organizer)
        upload(bucket, session, organizer)
        client.force_login(organizer)
        html = client.get(organizer_page(session)).content.decode()
        assert f'data-action="{delete_url(session, video)}"' not in html
        current = MediaAsset.objects.get(session=session, status=MediaStatus.READY)
        assert f'data-action="{delete_url(session, current)}"' in html
        assert 'data-name="raw_video.mp4"' in html
        assert 'data-versions="2 versions"' in html
        assert html.count('id="media-delete-modal"') == 1
        assert "js/media-delete" in html
        client.force_login(liaison)
        html = client.get(organizer_page(session)).content.decode()
        assert "media-delete" not in html

    def test_a_rollback_keeps_the_files(
        self, bucket, session, organizer, monkeypatch, commits
    ):
        """The bucket answers after the commit, not before: a deletion
        that fails after the rows are gone restores the rows and, with
        them, the files their download links point at."""
        video = upload(bucket, session, organizer)

        def refuse(*args, **kwargs):
            raise RuntimeError("the log table is away")

        monkeypatch.setattr(ActivityLog, "record", refuse)
        with pytest.raises(RuntimeError):
            commits(lambda: delete_line(video, organizer, "raw_video.mp4"))
        assert MediaAsset.objects.filter(pk=video.pk).exists()
        assert in_bucket(bucket, video.storage_key)
        assert in_bucket(bucket, video.thumbnail_key)
        assert MediaUpload.objects.filter(asset=video).exists()

    def test_a_name_stored_with_spaces_around_it(
        self, client, bucket, session, organizer
    ):
        """The typed value is trimmed, so the name to type is too; a name
        that kept its spaces would match nothing anyone can type."""
        video = upload(bucket, session, organizer, filename=" take.mp4 ")
        assert confirmation_name(video) == "take.mp4"
        client.force_login(organizer)
        html = client.get(organizer_page(session)).content.decode()
        assert 'data-name="take.mp4"' in html
        response = client.post(
            delete_url(session, video), {"confirm": "take.mp4"}, follow=True
        )
        assert flashed(response)[0].startswith("Deleted ")
        assert not MediaAsset.objects.filter(pk=video.pk).exists()

    def test_a_machine_transcript_goes_with_its_video(
        self, client, bucket, session, organizer
    ):
        """The draft's line is keyed to the video's row, so nothing could
        replace it once the video is gone; a transcript a person uploaded
        on that line stays, and so does the upload row's absence."""
        video = upload(bucket, session, organizer)
        draft = upload(
            bucket,
            session,
            organizer,
            MediaKind.TRANSCRIPT,
            filename="draft.vtt",
            language="en",
            variant=transcript_variant(video),
        )
        draft.generated_by = "faster-whisper/small"
        draft.save(update_fields=["generated_by"])
        TranscriptionJob.objects.create(
            asset=video, status=TranscriptionStatus.DONE, output=draft
        )
        reviewed = upload(
            bucket,
            session,
            organizer,
            MediaKind.TRANSCRIPT,
            filename="reviewed.vtt",
            language="en",
            variant=transcript_variant(video),
        )
        client.force_login(organizer)
        response = client.post(
            delete_url(session, video), {"confirm": "raw_video.mp4"}, follow=True
        )
        assert flashed(response) == [
            "Deleted Raw video (performer upload) (raw_video.mp4), 1 version(s) "
            "and 1 machine transcript(s) made from it, from the portal and from "
            "storage."
        ]
        assert not MediaAsset.objects.filter(pk__in=[video.pk, draft.pk]).exists()
        assert MediaAsset.objects.filter(pk=reviewed.pk).exists()
        assert not in_bucket(bucket, draft.storage_key)
        assert in_bucket(bucket, reviewed.storage_key)
        assert not MediaUpload.objects.filter(storage_key=video.storage_key).exists()
        assert MediaUpload.objects.filter(storage_key=reviewed.storage_key).exists()
        entry = ActivityLog.objects.get(action="media.deleted")
        assert entry.data["drafts"] == ["draft.vtt"]

    def test_an_attached_file_goes_from_storage(
        self, session, organizer, commits, monkeypatch, caplog
    ):
        """A file attached through the admin lives in the default storage,
        not the bucket; it goes the same way, and a storage that refuses
        is logged, not raised."""
        attached = MediaAsset.objects.create(
            session=session,
            kind=MediaKind.OTHER,
            status=MediaStatus.READY,
            file=SimpleUploadedFile("notes.txt", b"hello"),
        )
        storage, name = attached.file.storage, attached.file.name
        assert storage.exists(name)
        commits(lambda: delete_line(attached, organizer, "notes.txt"))
        assert not storage.exists(name)
        stubborn = MediaAsset.objects.create(
            session=session,
            kind=MediaKind.OTHER,
            file=SimpleUploadedFile("more.txt", b"hello"),
        )

        def refuse(name):
            raise OSError("read-only")

        monkeypatch.setattr(stubborn.file.storage, "delete", refuse)
        stubborn_pk = stubborn.pk
        with caplog.at_level(logging.ERROR):
            commits(stubborn.delete)
        assert f"Deleted asset {stubborn_pk} leaves" in caplog.text
        assert "more.txt in storage: read-only" in caplog.text

    def test_no_dialog_without_files(self, client, session, organizer):
        client.force_login(organizer)
        html = client.get(organizer_page(session)).content.decode()
        assert 'id="media-delete-modal"' not in html


@pytest.mark.django_db
class TestPerformerDeletes:
    def test_their_own_video_every_version(self, client, bucket, session, performer):
        v1 = upload(bucket, session, performer, filename="take1.mp4")
        v2 = upload(bucket, session, performer, filename="take2.mp4")
        client.force_login(performer)
        html = client.get(my_page(session)).content.decode()
        assert f'data-action="{delete_url(session, v2)}"' in html
        assert 'data-name="take2.mp4"' in html
        assert "Delete my video" in html and "js/media-delete" in html
        response = client.post(
            delete_url(session, v2), {"confirm": "take2.mp4"}, follow=True
        )
        assert response.redirect_chain[-1][0].endswith(f"{my_page(session)}#video")
        assert flashed(response)[0].startswith("Deleted ")
        assert not MediaAsset.objects.filter(pk__in=[v1.pk, v2.pk]).exists()
        for asset in (v1, v2):
            assert not in_bucket(bucket, asset.storage_key)
        assert ActivityLog.objects.get(action="media.deleted").actor == performer

    def test_not_a_version_the_team_uploaded(
        self, client, bucket, session, performer, organizer
    ):
        """One version put there on their behalf makes the line the
        team's to remove: no button, and the endpoint refuses."""
        upload(bucket, session, performer)
        theirs = upload(bucket, session, organizer)
        client.force_login(performer)
        html = client.get(my_page(session)).content.decode()
        assert "Delete my video" not in html and "media-delete" not in html
        response = client.post(
            delete_url(session, theirs), {"confirm": "raw_video.mp4"}
        )
        assert response.status_code == 403
        assert MediaAsset.objects.filter(session=session).count() == 2

    def test_not_the_teams_files_nor_with_the_switch_off(
        self, client, bucket, session, performer, organizer, enabled
    ):
        poster = upload(bucket, session, organizer, MediaKind.PROMO, variant="square")
        poster.shared_with_speaker = True
        poster.save(update_fields=["shared_with_speaker"])
        video = upload(bucket, session, performer)
        client.force_login(performer)
        response = client.post(delete_url(session, poster), {"confirm": "square.png"})
        assert response.status_code == 403
        enabled.media_for_speakers = False
        enabled.save(update_fields=["media_for_speakers"])
        response = client.post(delete_url(session, video), {"confirm": "raw_video.mp4"})
        assert response.status_code == 403
        assert MediaAsset.objects.filter(session=session).count() == 2

    def test_who_may(self, bucket, session, performer, organizer, liaison):
        video = upload(bucket, session, performer)
        assert can_delete(organizer, session, video)
        assert can_delete(performer, session, video)
        assert not can_delete(liaison, session, video)
        assert not can_delete(AnonymousUser(), session, video)

    def test_the_panel_counts_the_shown_line_only(
        self, bucket, session, performer, organizer
    ):
        """A raw video under another variant is another line: the count
        the dialog shows is what the delete takes, and a team upload on
        that other line does not cost the performer their button."""
        upload(bucket, session, performer, filename="take1.mp4")
        upload(bucket, session, performer, filename="take2.mp4")
        upload(bucket, session, organizer, filename="angle.mp4", variant="angle2")
        panel = video_panel(session, performer)
        assert panel["confirm_name"] in ("take2.mp4", "angle.mp4")
        assert panel["versions"] == 2 if panel["confirm_name"] == "take2.mp4" else 1
        line = [
            a
            for a in MediaAsset.objects.filter(session=session)
            if a.variant == panel["delete_target"].variant
        ]
        assert panel["versions"] == len(line)
        assert panel["can_delete"] is all(a.uploaded_by == performer for a in line)

    def test_the_panel_without_a_video(self, session, performer):
        panel = video_panel(session, performer)
        assert panel["delete_target"] is None
        assert panel["can_delete"] is False
        assert panel["confirm_name"] == "" and panel["versions"] == 0


@pytest.mark.django_db
class TestWhatToType:
    def test_the_uploaded_name_else_the_attached_file_else_the_label(
        self, session, organizer
    ):
        uploaded = MediaAsset(
            session=session, kind=MediaKind.TRANSCRIPT, original_filename="a.vtt"
        )
        assert confirmation_name(uploaded) == "a.vtt"
        attached = MediaAsset.objects.create(
            session=session,
            kind=MediaKind.TRANSCRIPT,
            language="en",
            file=SimpleUploadedFile("notes/talk.vtt", b"WEBVTT"),
        )
        assert confirmation_name(attached) == "talk.vtt"
        bare = MediaAsset(session=session, kind=MediaKind.TRANSCRIPT, language="en")
        assert confirmation_name(bare) == "Transcript (en)"


@pytest.mark.django_db
class TestTheSessionItself:
    def test_cancelling_keeps_every_file(self, bucket, session, organizer):
        video = upload(bucket, session, organizer)
        session.cancel()
        assert MediaAsset.objects.filter(pk=video.pk).exists()
        assert in_bucket(bucket, video.storage_key)
        assert in_bucket(bucket, video.thumbnail_key)

    def test_deleting_it_takes_the_files_and_aborts_open_uploads(
        self, bucket, session, organizer, performer, commits
    ):
        """The admin's delete cascades: every asset row goes with its
        object and thumbnail, and an upload still in flight is aborted so
        the parts it received are freed; a finished upload's row just goes."""
        video = upload(bucket, session, organizer)
        poster = upload(bucket, session, organizer, MediaKind.PROMO, variant="square")
        open_upload = start_upload(
            session=session,
            kind=MediaKind.RAW_VIDEO,
            language="",
            filename="b.mp4",
            size_bytes=3,
            content_type="video/mp4",
            user=performer,
        )
        assert len(bucket.client.list_multipart_uploads(Bucket=BUCKET)["Uploads"]) == 1
        commits(lambda: Session.objects.filter(pk=session.pk).delete())
        assert not MediaAsset.objects.filter(pk__in=[video.pk, poster.pk]).exists()
        assert not MediaUpload.objects.filter(pk=open_upload.pk).exists()
        for asset in (video, poster):
            assert not in_bucket(bucket, asset.storage_key)
            assert not in_bucket(bucket, asset.thumbnail_key)
        assert "Uploads" not in bucket.client.list_multipart_uploads(Bucket=BUCKET)

    def test_without_storage_the_rows_still_go(
        self, bucket, session, performer, settings, caplog, commits
    ):
        open_upload = start_upload(
            session=session,
            kind=MediaKind.RAW_VIDEO,
            language="",
            filename="b.mp4",
            size_bytes=3,
            content_type="video/mp4",
            user=performer,
        )
        settings.SPEAKER_MEDIA_BUCKET = ""
        with caplog.at_level(logging.ERROR):
            commits(open_upload.delete)
        assert "stays open in the bucket" in caplog.text
        assert not MediaUpload.objects.filter(pk=open_upload.pk).exists()
