"""Files the team shares with the speaker (design §8.6): the share flag,
what the speaker's page lists and what they may fetch, promo materials in
several variants with their own version chains, and the two seeded promo
lines that tick themselves."""

import importlib

import boto3
import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.urls import reverse
from moto import mock_aws

from speakers.checklists import instantiate_presenter_checklist
from speakers.constants import VIDEO_KINDS, ItemStatus, MediaKind, MediaStatus
from speakers.media import (
    MediaBucket,
    asset_groups,
    can_download,
    complete_upload,
    session_assets,
    start_upload,
    team_files,
)
from speakers.models import ChecklistItem, ChecklistTemplateItem, MediaAsset
from speakers.rules import asset_shared
from speakers.seeds import seed_checklists

from .factories import add_presenter, make_presenter, make_session, make_settings
from .test_rules import auto_item

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
def organizer(db):
    return User.objects.create_user("org", email="org@x.org", is_staff=True)


@pytest.fixture
def speaker(db):
    return User.objects.create_user("ada", email="ada@x.org")


@pytest.fixture
def world(conference, speaker):
    """Ada on a panel and a workshop, with the seeded organizer lines, so
    each session has its own promo items."""
    make_settings(conference)
    seed_checklists(conference)
    ada = make_presenter(conference, display_name="Ada", user=speaker)
    panel = make_session(conference, title="The panel", kind="PANEL")
    workshop = make_session(conference, title="The workshop", kind="WORKSHOP")
    for session in (panel, workshop):
        instantiate_presenter_checklist(add_presenter(session, ada, confirmed=True))
    return {"panel": panel, "workshop": workshop, "ada": ada}


def upload(bucket, session, user, kind, variant="", language=""):
    started = start_upload(
        session=session,
        kind=kind,
        language=language,
        variant=variant,
        filename=f"{variant or kind.lower()}.{'mp4' if kind in VIDEO_KINDS else 'png'}",
        size_bytes=3,
        content_type="video/mp4" if kind in VIDEO_KINDS else "image/png",
        user=user,
    )
    part = bucket.client.upload_part(
        Bucket=BUCKET,
        Key=started.storage_key,
        UploadId=started.upload_id,
        PartNumber=1,
        Body=b"png",
    )
    return complete_upload(started, [{"number": 1, "etag": part["ETag"]}])


def item(session, title):
    return ChecklistItem.objects.get(session=session, title=title)


def my_page(session):
    return reverse("speakers:my_session_detail", args=[session.slug])


def share_url(session, asset):
    return reverse("speakers:media_share", args=[session.slug, asset.pk])


def download(session, asset):
    return reverse("speakers:media_download", args=[session.slug, asset.pk])


@pytest.mark.django_db
class TestVariants:
    def test_each_variant_keeps_its_own_versions(self, bucket, world, organizer):
        panel = world["panel"]
        square = upload(bucket, panel, organizer, MediaKind.PROMO, variant="square")
        landscape = upload(
            bucket, panel, organizer, MediaKind.PROMO, variant="landscape"
        )
        square2 = upload(bucket, panel, organizer, MediaKind.PROMO, variant="square")
        for asset in (square, landscape, square2):
            asset.refresh_from_db()
        assert (square.version, square.status) == (1, MediaStatus.SUPERSEDED)
        assert (square2.version, square2.status) == (2, MediaStatus.READY)
        assert (landscape.version, landscape.status) == (1, MediaStatus.READY)
        groups = asset_groups(session_assets(panel))
        assert [(g["variant"], g["current"].version) for g in groups] == [
            ("landscape", 1),
            ("square", 2),
        ]
        assert square2.label == "Promo material (square)"
        assert (
            MediaAsset.latest_ready(panel, MediaKind.PROMO, variant="square") == square2
        )

    def test_the_endpoint_takes_the_variant(self, client, bucket, world, organizer):
        client.force_login(organizer)
        response = client.post(
            reverse("speakers:upload_start", args=[world["panel"].slug]),
            {
                "kind": "PROMO",
                "variant": "  gif ",
                "filename": "loop.gif",
                "size_bytes": 3,
            },
            content_type="application/json",
        )
        assert response.status_code == 201
        assert response.json()["variant"] == "gif"

    def test_the_organizer_panel_offers_the_field(
        self, client, world, organizer, bucket
    ):
        client.force_login(organizer)
        html = client.get(world["panel"].get_absolute_url()).content.decode()
        assert 'data-role="variant"' in html and 'value="landscape"' in html


@pytest.mark.django_db
class TestSharing:
    def test_the_speaker_sees_only_what_is_shared(
        self, client, bucket, world, organizer, speaker
    ):
        panel, workshop = world["panel"], world["workshop"]
        square = upload(bucket, panel, organizer, MediaKind.PROMO, variant="square")
        gif = upload(bucket, panel, organizer, MediaKind.PROMO, variant="gif")
        draft = upload(bucket, panel, organizer, MediaKind.TITLE_CARD)
        upload(bucket, workshop, organizer, MediaKind.PROMO, variant="square")
        client.force_login(speaker)
        html = client.get(my_page(panel)).content.decode()
        assert "Files from the team" not in html
        client.force_login(organizer)
        for asset in (square, gif):
            assert (
                client.post(share_url(panel, asset), {"shared": "1"}).status_code == 302
            )
        assert [a.pk for a in team_files(panel)] == [gif.pk, square.pk]
        client.force_login(speaker)
        html = client.get(my_page(panel)).content.decode()
        assert "Files from the team" in html
        assert "Promo material (square)" in html and "Promo material (gif)" in html
        assert "Title card" not in html
        assert download(panel, square) in html and download(panel, draft) not in html
        # The workshop's poster is the workshop's: not on the panel page.
        assert (
            client.get(my_page(workshop)).content.decode().count("Files from the team")
            == 0
        )
        # Taken back: gone from the page.
        client.force_login(organizer)
        client.post(share_url(panel, gif), {"shared": "0"})
        client.force_login(speaker)
        assert "Promo material (gif)" not in client.get(my_page(panel)).content.decode()

    def test_who_may_share_and_fetch(self, client, bucket, world, organizer, speaker):
        panel = world["panel"]
        cut = upload(bucket, panel, organizer, MediaKind.PROCESSED_VIDEO)
        raw = upload(bucket, panel, organizer, MediaKind.RAW_VIDEO)
        assert can_download(speaker, panel, raw)  # their own kind of file
        assert not can_download(speaker, panel, cut)
        assert can_download(speaker, panel)  # something, at least
        assert can_download(organizer, panel, cut)
        client.force_login(speaker)
        assert client.get(download(panel, cut)).status_code == 403
        assert client.post(share_url(panel, cut), {"shared": "1"}).status_code == 403
        client.force_login(organizer)
        client.post(share_url(panel, cut), {"shared": "1"})
        cut.refresh_from_db()
        assert cut.shared_with_speaker
        client.force_login(speaker)
        assert client.get(download(panel, cut)).status_code == 302
        client.force_login(organizer)
        html = client.get(panel.get_absolute_url()).content.decode()
        assert 'name="shared" value="0"' in html and "Shared" in html

    def test_a_replaced_version_is_withdrawn_from_the_speaker(
        self, client, bucket, world, organizer, speaker
    ):
        """What the team shared was the line; a new version is shared
        again from its own row, and the old one is no longer reachable at
        its URL even though its flag once said so."""
        panel = world["panel"]
        first = upload(bucket, panel, organizer, MediaKind.PROMO, variant="square")
        client.force_login(organizer)
        client.post(share_url(panel, first), {"shared": "1"})
        second = upload(bucket, panel, organizer, MediaKind.PROMO, variant="square")
        first.refresh_from_db()
        assert first.status == MediaStatus.SUPERSEDED and not first.shared_with_speaker
        assert not second.shared_with_speaker
        assert not can_download(speaker, panel, first)
        # Even a flag left on a superseded row grants nothing.
        MediaAsset.objects.filter(pk=first.pk).update(shared_with_speaker=True)
        first.refresh_from_db()
        assert not can_download(speaker, panel, first)
        client.force_login(speaker)
        assert client.get(download(panel, first)).status_code == 403

    def test_reviewer_notes_stay_on_the_organizer_side(
        self, client, bucket, world, organizer, speaker
    ):
        """A note on an earlier raw video is for the team: the performer's
        history list shows the version, not the note; a liaison or an
        organizer reading the organizer page sees it."""
        panel = world["panel"]
        old = upload(bucket, panel, organizer, MediaKind.RAW_VIDEO)
        upload(bucket, panel, organizer, MediaKind.RAW_VIDEO)
        old.notes_md = "audio clips at 4:10"
        old.save(update_fields=["notes_md"])
        client.force_login(speaker)
        assert "audio clips at 4:10" not in client.get(my_page(panel)).content.decode()
        client.force_login(organizer)
        assert (
            "audio clips at 4:10"
            in client.get(panel.get_absolute_url()).content.decode()
        )

    def test_htmx_swaps_the_row_in_place(self, client, bucket, world, organizer):
        """From the page the buttons post through htmx and get the row back,
        so nothing reloads or jumps; a plain post still redirects."""
        panel = world["panel"]
        cut = upload(bucket, panel, organizer, MediaKind.PROCESSED_VIDEO)
        client.force_login(organizer)
        response = client.post(
            share_url(panel, cut), {"shared": "1"}, headers={"HX-Request": "true"}
        )
        assert response.status_code == 200
        html = response.content.decode()
        assert html.strip().startswith('<tbody id="files-processed_video----"')
        assert 'name="shared" value="0"' in html and "Shared" in html
        assert "<html" not in html
        response = client.post(
            reverse("speakers:media_notes", args=[panel.slug, cut.pk]),
            {"notes_md": "audio clips at 4:10"},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert 'value="audio clips at 4:10"' in response.content.decode()
        assert client.post(share_url(panel, cut), {"shared": "0"}).status_code == 302

    def test_the_share_forms_skip_the_raw_video(self, client, bucket, world, organizer):
        panel = world["panel"]
        raw = upload(bucket, panel, organizer, MediaKind.RAW_VIDEO)
        client.force_login(organizer)
        html = client.get(panel.get_absolute_url()).content.decode()
        assert share_url(panel, raw) not in html


@pytest.mark.django_db
class TestPromoLines:
    def test_prepared_ticks_on_the_first_file_and_shared_on_the_first_share(
        self, client, bucket, world, organizer
    ):
        panel, workshop = world["panel"], world["workshop"]
        prepared = item(panel, "Promo materials prepared")
        shared = item(panel, "Promo materials shared with presenter")
        assert prepared.status == ItemStatus.TODO and shared.status == ItemStatus.TODO
        square = upload(bucket, panel, organizer, MediaKind.PROMO, variant="square")
        prepared.refresh_from_db()
        shared.refresh_from_db()
        assert prepared.status == ItemStatus.DONE and shared.status == ItemStatus.TODO
        client.force_login(organizer)
        client.post(share_url(panel, square), {"shared": "1"})
        shared.refresh_from_db()
        assert shared.status == ItemStatus.DONE
        # The workshop's own lines are untouched by the panel's poster.
        assert item(workshop, "Promo materials prepared").status == ItemStatus.TODO

    def test_the_rule_needs_a_kind_and_a_session(self, world):
        """Like ``asset_exists``: an item that names no kind, or hangs on no
        session, is never ticked by the rule."""
        session = world["panel"]
        no_kind = auto_item(session.conference, "asset_shared", session=session)
        no_session = auto_item(
            session.conference,
            "asset_shared",
            presenter=world["ada"],
            requires_asset_kind="PROMO",
        )
        assert asset_shared(no_kind) is False
        assert asset_shared(no_session) is False

    def test_the_seed_lines(self, world):
        """Every presenter template carries the two lines with their rules."""
        prepared = ChecklistTemplateItem.objects.filter(
            title="Promo materials prepared"
        )
        shared = ChecklistTemplateItem.objects.filter(
            title="Promo materials shared with presenter"
        )
        assert prepared.count() == shared.count() > 1
        assert {(i.auto_complete_rule, i.requires_asset_kind) for i in prepared} == {
            ("asset_exists", "PROMO")
        }
        assert {(i.auto_complete_rule, i.requires_asset_kind) for i in shared} == {
            ("asset_shared", "PROMO")
        }

    def test_the_backfills_reach_seeded_editions(self, world):
        titles = ("Promo materials prepared", "Promo materials shared with presenter")
        ChecklistTemplateItem.objects.filter(title__in=titles).update(
            auto_complete_rule="", requires_asset_kind=""
        )
        ChecklistItem.objects.filter(title__in=titles).update(
            auto_complete_rule="", requires_asset_kind=""
        )
        done = item(world["workshop"], titles[0])
        done.status = ItemStatus.DONE
        done.save()
        migration.promo_ticks_on_the_first_file(apps, None)
        migration.shared_ticks_on_the_first_shared_file(apps, None)
        rules = {
            (i.session.title, i.title): (i.auto_complete_rule, i.requires_asset_kind)
            for i in ChecklistItem.objects.filter(title__in=titles)
        }
        assert rules[("The panel", titles[0])] == ("asset_exists", "PROMO")
        assert rules[("The panel", titles[1])] == ("asset_shared", "PROMO")
        # A finished item is left as it was.
        assert rules[("The workshop", titles[0])] == ("", "")
        migration.promo_back_to_a_tick(apps, None)
        migration.shared_back_to_a_tick(apps, None)
        assert (
            not ChecklistTemplateItem.objects.filter(title__in=titles)
            .exclude(auto_complete_rule="")
            .exists()
        )
