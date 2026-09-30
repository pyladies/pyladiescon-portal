"""Task 5.4, the parts that were not there yet: the performer's "Approve
the final cut" item waits until the edited video is in, and a transcript
or translation ticks only the item for its language, end to end through
the upload backend."""

import importlib

import boto3
import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.db.models import Q
from moto import mock_aws

from speakers.checklists import (
    instantiate_presenter_checklist,
    instantiate_session_checklist,
)
from speakers.constants import (
    VIDEO_KINDS,
    ItemStatus,
    MediaKind,
    MediaStatus,
    ReadyRule,
)
from speakers.media import MediaBucket, complete_upload, start_upload
from speakers.models import ChecklistItem, ChecklistTemplateItem, MediaAsset
from speakers.readiness import final_cut_ready
from speakers.seeds import seed_checklists

from .factories import add_presenter, make_presenter, make_session, make_settings

migration = importlib.import_module("speakers.migrations.0013_post_production")
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
def performer(db):
    return User.objects.create_user(username="maria", email="maria@x.org")


@pytest.fixture
def world(conference, performer):
    """A PyJam set in English with the seeded lines on both sides, and
    pt-br and es as the edition's translation languages."""
    make_settings(conference, translation_languages=["pt-br", "es"])
    seed_checklists(conference)
    session = make_session(conference, title="A PyJam set", kind="PYJAM", language="en")
    presenter = make_presenter(conference, display_name="Maria", user=performer)
    link = add_presenter(session, presenter, confirmed=True)
    instantiate_presenter_checklist(link)
    instantiate_session_checklist(session)
    return {"session": session, "presenter": presenter}


def upload(bucket, session, user, kind, language="", body=b"x" * 16):
    """Play the browser: a one-part upload of ``kind`` completed."""
    started = start_upload(
        session=session,
        kind=kind,
        language=language,
        filename=f"{kind.lower()}.{'mp4' if kind in VIDEO_KINDS else 'bin'}",
        size_bytes=len(body),
        content_type="application/octet-stream",
        user=user,
    )
    part = bucket.client.upload_part(
        Bucket=BUCKET,
        Key=started.storage_key,
        UploadId=started.upload_id,
        PartNumber=1,
        Body=body,
    )
    return complete_upload(started, [{"number": 1, "etag": part["ETag"]}])


def by_title(session, title):
    return ChecklistItem.objects.get(session=session, title=title)


@pytest.mark.django_db
class TestFinalCutApproval:
    def test_the_seed_makes_the_line_wait_for_the_final_cut(self, world):
        line = ChecklistTemplateItem.objects.get(title="Approve the final cut")
        assert line.ready_rule == ReadyRule.FINAL_CUT_READY
        assert line.waiting_note == "we are still editing your video"

    def test_it_waits_until_the_processed_video_is_ready(
        self, world, performer, bucket
    ):
        session = world["session"]
        item = by_title(session, "Approve the final cut")
        assert (
            item.is_waiting and item.waiting_reason == "we are still editing your video"
        )
        # A raw video is not the final cut.
        upload(bucket, session, performer, MediaKind.RAW_VIDEO)
        item.refresh_from_db()
        assert item.is_waiting
        organizer = User.objects.create_user("org", email="o@x.org", is_staff=True)
        final = upload(bucket, session, organizer, MediaKind.PROCESSED_VIDEO)
        item.refresh_from_db()
        # In, but the team has not released it: nothing to watch yet.
        assert item.is_waiting
        final.shared_with_speaker = True
        final.save()
        item.refresh_from_db()
        assert not item.is_waiting and item.status == ItemStatus.TODO
        assert final_cut_ready(item)
        # The team pulls the cut back: the approval waits again.
        final.delete()
        item.refresh_from_db()
        assert item.is_waiting

    def test_an_admin_attached_cut_counts_too(self, world):
        session = world["session"]
        item = by_title(session, "Approve the final cut")
        assert item.is_waiting
        MediaAsset.objects.create(
            session=session,
            kind=MediaKind.PROCESSED_VIDEO,
            status=MediaStatus.READY,
            shared_with_speaker=True,
        )
        item.refresh_from_db()
        assert not item.is_waiting

    def test_the_rule_needs_a_session(self, world):
        general = ChecklistItem(conference=world["session"].conference, session=None)
        assert final_cut_ready(general) is False

    def test_the_backfill_reaches_seeded_editions(self, world):
        line = ChecklistTemplateItem.objects.get(title="Approve the final cut")
        item = by_title(world["session"], "Approve the final cut")
        # An edition seeded before the rule: the line and its item have none.
        ChecklistTemplateItem.objects.filter(pk=line.pk).update(
            ready_rule="", waiting_note=""
        )
        ChecklistItem.objects.filter(pk=item.pk).update(
            ready_rule="", template_waiting_note=""
        )
        # A line an organizer pointed at a gate keeps that choice.
        kept = ChecklistTemplateItem.objects.create(
            template=line.template,
            title="Approve the final cut",
            owner=line.owner,
            ready_gate_code="tech_check",
        )
        migration.wait_for_the_final_cut(apps, None)
        line.refresh_from_db()
        item.refresh_from_db()
        kept.refresh_from_db()
        assert (
            line.ready_rule == "final_cut_ready"
            and item.ready_rule == "final_cut_ready"
        )
        assert item.template_waiting_note == "we are still editing your video"
        assert kept.ready_rule == ""
        migration.stop_waiting_for_the_final_cut(apps, None)
        line.refresh_from_db()
        item.refresh_from_db()
        assert line.ready_rule == "" and item.ready_rule == "" and not item.is_waiting


@pytest.mark.django_db
class TestLanguages:
    def test_a_transcript_ticks_only_its_language(self, world, performer, bucket):
        session = world["session"]
        transcribe = by_title(session, "Transcribe")
        pt = by_title(session, "Translate (pt-br)")
        es = by_title(session, "Translate (es)")
        assert transcribe.requires_asset_language == "en"
        organizer = User.objects.create_user("org", email="o@x.org", is_staff=True)
        upload(bucket, session, organizer, MediaKind.TRANSCRIPT, language="en")
        for item in (transcribe, pt, es):
            item.refresh_from_db()
        assert transcribe.status == ItemStatus.DONE
        assert pt.status == ItemStatus.TODO and es.status == ItemStatus.TODO
        upload(bucket, session, organizer, MediaKind.TRANSLATION, language="pt-br")
        pt.refresh_from_db()
        es.refresh_from_db()
        assert pt.status == ItemStatus.DONE and es.status == ItemStatus.TODO
        # A transcript in the wrong language answers nothing.
        assert not ChecklistItem.objects.filter(
            Q(title="Translate (es)"), session=session, status=ItemStatus.DONE
        ).exists()
