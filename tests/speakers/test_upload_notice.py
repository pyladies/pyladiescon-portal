"""A speaker's upload is news to their liaison, or to the team (design
§13.2, task 5.12): one email per completed upload, sent once the row is
committed, and nothing for what the team or a job put there."""

import logging
from unittest import mock

import boto3
import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.urls import reverse
from moto import mock_aws

from common.models import SentEmail
from speakers.constants import MediaKind
from speakers.emails import send_upload_notice_email
from speakers.media import (
    MediaBucket,
    complete_upload,
    record_asset,
    start_upload,
    uploading_presenter,
)
from speakers.models import MediaAsset
from speakers.tasks import send_upload_notice_task

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
def organizer(db):
    return User.objects.create_user("org", email="org@x.org", is_staff=True)


@pytest.fixture
def performer(db):
    return User.objects.create_user("maria", email="maria@x.org")


@pytest.fixture
def liaison(db):
    return User.objects.create_user("lia", email="lia@x.org")


@pytest.fixture
def world(conference, performer, liaison):
    """Maria on a PyJam set, with Lia as her liaison; the edition has a
    team address."""
    make_settings(conference, organizers_email="team@x.org")
    session = make_session(conference, title="A PyJam set", kind="PYJAM")
    presenter = make_presenter(
        conference, display_name="Maria", user=performer, liaison=liaison
    )
    add_presenter(session, presenter, confirmed=True)
    return {"session": session, "presenter": presenter}


def upload(bucket, session, user, filename="take.mp4", commits=None):
    """A completed one-part raw video upload; ``commits`` runs the commit
    hooks the way a request's commit would, so the notice goes out."""
    started = start_upload(
        session=session,
        kind=MediaKind.RAW_VIDEO,
        language="",
        filename=filename,
        size_bytes=3,
        content_type="video/mp4",
        user=user,
    )
    part = bucket.client.upload_part(
        Bucket=BUCKET,
        Key=started.storage_key,
        UploadId=started.upload_id,
        PartNumber=1,
        Body=b"abc",
    )
    parts = [{"number": 1, "etag": part["ETag"]}]
    if commits is None:
        return complete_upload(started, parts)
    with commits(execute=True):
        return complete_upload(started, parts)


@pytest.mark.django_db
class TestWhoIsTold:
    def test_the_liaison_hears_of_the_first_video(
        self, bucket, world, performer, django_capture_on_commit_callbacks
    ):
        session = world["session"]
        mail.outbox.clear()
        asset = upload(
            bucket, session, performer, commits=django_capture_on_commit_callbacks
        )
        assert len(mail.outbox) == 1
        message = mail.outbox[0]
        assert message.to == ["lia@x.org"]
        assert message.subject.endswith("Maria uploaded a video for A PyJam set")
        assert message.reply_to == [world["presenter"].email]
        body = message.body
        assert "has uploaded their video for A PyJam set" in body
        assert "take.mp4 (3" in body and "v1, the first" in body
        assert "being checked" in body
        assert f"{session.get_absolute_url()}#files" in body
        assert reverse("speakers:checklist_board") in body
        assert "as Maria's liaison" in body and "no liaison" not in body
        record = SentEmail.objects.get()
        # On the session's trail, but not the speaker's: an email to their
        # liaison is not theirs to read under "Emails we sent you".
        assert record.session == session and record.presenter is None
        assert asset.uploaded_by == performer

    def test_a_second_take_says_what_it_replaces(
        self, bucket, world, performer, django_capture_on_commit_callbacks
    ):
        session = world["session"]
        upload(bucket, session, performer, commits=django_capture_on_commit_callbacks)
        mail.outbox.clear()
        upload(
            bucket,
            session,
            performer,
            filename="take2.mp4",
            commits=django_capture_on_commit_callbacks,
        )
        body = mail.outbox[0].body
        assert "a new version of their video" in body
        assert "v2, replacing v1" in body and "take2.mp4" in body

    def test_without_a_liaison_the_team_hears(
        self, bucket, world, performer, organizer, django_capture_on_commit_callbacks
    ):
        """The team address when the edition has one, else the staff
        accounts, the way every organizer-facing email falls back."""
        presenter = world["presenter"]
        presenter.liaison = None
        presenter.save(update_fields=["liaison"])
        mail.outbox.clear()
        upload(
            bucket,
            world["session"],
            performer,
            commits=django_capture_on_commit_callbacks,
        )
        assert mail.outbox[0].to == ["team@x.org"]
        assert "no liaison yet, so this goes to the team" in mail.outbox[0].body
        settings_row = world["session"].conference.speaker_settings
        settings_row.organizers_email = ""
        settings_row.save(update_fields=["organizers_email"])
        mail.outbox.clear()
        upload(
            bucket,
            world["session"],
            performer,
            filename="take3.mp4",
            commits=django_capture_on_commit_callbacks,
        )
        assert mail.outbox[0].to == ["org@x.org"]


@pytest.mark.django_db
class TestWhatIsNotNews:
    def test_the_teams_uploads_and_the_jobs_outputs(
        self, bucket, world, organizer, django_capture_on_commit_callbacks
    ):
        session = world["session"]
        mail.outbox.clear()
        theirs = upload(
            bucket, session, organizer, commits=django_capture_on_commit_callbacks
        )
        assert uploading_presenter(theirs) is None
        with django_capture_on_commit_callbacks(execute=True):
            draft = record_asset(
                session=session,
                kind=MediaKind.TRANSCRIPT,
                language="en",
                storage_key="speaker-media/x/draft.vtt",
                filename="draft.vtt",
                content_type="text/vtt",
                size_bytes=3,
                generated_by="faster-whisper/small",
            )
        assert uploading_presenter(draft) is None
        nobody = MediaAsset.objects.create(session=session, kind=MediaKind.OTHER)
        assert uploading_presenter(nobody) is None
        assert mail.outbox == []

    def test_a_user_who_is_not_on_the_session(self, world, liaison):
        """Uploaded by someone with no presenter link here (the row was
        attached by hand): nobody to name, nothing sent."""
        asset = MediaAsset.objects.create(
            session=world["session"], kind=MediaKind.RAW_VIDEO, uploaded_by=liaison
        )
        assert uploading_presenter(asset) is None
        assert (
            send_upload_notice_task.apply(args=(asset.pk,))
            .get()
            .endswith("is not a speaker's upload")
        )


@pytest.mark.django_db
class TestTheTask:
    def test_a_gone_asset_sends_nothing(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = send_upload_notice_task.apply(args=(999999,)).get()
        assert result == "Asset with id 999999 not found"
        assert "asset 999999 not found" in caplog.text

    def test_a_mail_failure_is_logged_and_raised(
        self, bucket, world, performer, caplog
    ):
        asset = upload(bucket, world["session"], performer)
        with (
            mock.patch(
                "speakers.tasks.send_upload_notice_email",
                side_effect=RuntimeError("smtp down"),
            ),
            caplog.at_level(logging.ERROR),
            pytest.raises(RuntimeError),
        ):
            send_upload_notice_task.apply(args=(asset.pk,)).get()
        assert f"asset {asset.pk} failed" in caplog.text


@pytest.mark.django_db
class TestNobodyToTell:
    def test_no_liaison_no_team_address_no_staff_address(
        self, bucket, world, performer, caplog
    ):
        """Nothing is sent and, above all, nothing is recorded as sent: the
        trail is what someone checks when a liaison says they heard nothing."""
        presenter = world["presenter"]
        presenter.liaison = None
        presenter.save(update_fields=["liaison"])
        settings_row = world["session"].conference.speaker_settings
        settings_row.organizers_email = ""
        settings_row.save(update_fields=["organizers_email"])
        User.objects.filter(is_staff=True).update(email="")
        asset = upload(bucket, world["session"], performer)
        mail.outbox.clear()
        with caplog.at_level(logging.WARNING):
            assert send_upload_notice_email(asset, presenter) is None
        assert mail.outbox == [] and not SentEmail.objects.exists()
        assert f"Upload notice for asset {asset.pk}" in caplog.text
        assert "nobody to go to" in caplog.text
        result = send_upload_notice_task.apply(args=(asset.pk,)).get()
        assert result == f"Upload notice for asset {asset.pk} had nobody to go to"
        assert not SentEmail.objects.exists()


@pytest.mark.django_db
class TestOnceOnly:
    def test_a_redelivered_task_finds_the_record_and_stops(
        self, bucket, world, performer, django_capture_on_commit_callbacks, caplog
    ):
        """Acknowledged late, the task can run twice; the second run finds
        the first's record and sends nothing more. A later take is a new
        asset and is announced on its own."""
        asset = upload(
            bucket,
            world["session"],
            performer,
            commits=django_capture_on_commit_callbacks,
        )
        assert len(mail.outbox) == 1 and SentEmail.objects.count() == 1
        assert SentEmail.objects.get().context_digest["asset"] == asset.pk
        with caplog.at_level(logging.INFO):
            result = send_upload_notice_task.apply(args=(asset.pk,)).get()
        assert result == f"Upload notice for asset {asset.pk} was already sent"
        assert "already has a successful record" in caplog.text
        assert len(mail.outbox) == 1
        upload(
            bucket,
            world["session"],
            performer,
            filename="take2.mp4",
            commits=django_capture_on_commit_callbacks,
        )
        assert len(mail.outbox) == 2

    def test_the_task_is_an_email_task(self):
        assert send_upload_notice_task.acks_late is True
        assert send_upload_notice_task.reject_on_worker_lost is True
        assert send_upload_notice_task.max_retries == 4


@pytest.mark.django_db
class TestWhichVersionItReplaced:
    def test_after_a_version_was_deleted_by_hand(
        self, bucket, world, performer, django_capture_on_commit_callbacks
    ):
        """The email names the highest version still on the line below the
        new one, the row record_asset just superseded, rather than assuming
        the numbers run without gaps."""
        session = world["session"]
        first = upload(
            bucket, session, performer, commits=django_capture_on_commit_callbacks
        )
        upload(
            bucket,
            session,
            performer,
            filename="take2.mp4",
            commits=django_capture_on_commit_callbacks,
        )
        first.delete()
        third = upload(
            bucket,
            session,
            performer,
            filename="take3.mp4",
            commits=django_capture_on_commit_callbacks,
        )
        assert third.version == 3
        assert "v3, replacing v2" in mail.outbox[-1].body
        fourth = MediaAsset.objects.create(
            session=session, kind=MediaKind.RAW_VIDEO, version=9, uploaded_by=performer
        )
        mail.outbox.clear()
        send_upload_notice_email(fourth, world["presenter"])
        assert "v9, replacing v3" in mail.outbox[0].body
