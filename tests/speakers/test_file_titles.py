"""A title for each file line (design §8.8, task 5.9): asked once, carried
onto every later version and variant, edited for the whole line, shown
where the file is."""

import re

import boto3
import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from moto import mock_aws

from speakers.board import build_post_production_board, write_post_production_csv
from speakers.constants import VIDEO_KINDS, MediaKind, MediaStatus
from speakers.media import (
    MediaBucket,
    asset_groups,
    complete_upload,
    line_title,
    line_titles,
    session_assets,
    set_line_title,
    start_upload,
)
from speakers.models import MediaAsset

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
def speaker(db):
    return User.objects.create_user("ada", email="ada@x.org")


@pytest.fixture
def session(conference, speaker):
    make_settings(conference)
    session = make_session(conference, title="A PyJam set", kind="PYJAM")
    add_presenter(
        session,
        make_presenter(conference, display_name="Ada", user=speaker),
        confirmed=True,
    )
    return session


def upload(bucket, session, user, kind, variant="", language="", title=""):
    started = start_upload(
        session=session,
        kind=kind,
        language=language,
        variant=variant,
        title=title,
        filename=f"{variant or kind.lower()}.{'mp4' if kind in VIDEO_KINDS else 'bin'}",
        size_bytes=3,
        content_type="application/octet-stream",
        user=user,
    )
    part = bucket.client.upload_part(
        Bucket=BUCKET,
        Key=started.storage_key,
        UploadId=started.upload_id,
        PartNumber=1,
        Body=b"abc",
    )
    return complete_upload(started, [{"number": 1, "etag": part["ETag"]}])


def title_url(session, asset):
    return reverse("speakers:media_title", args=[session.slug, asset.pk])


@pytest.mark.django_db
class TestInheritance:
    def test_later_versions_and_variants_inherit_the_first_title(
        self, bucket, session, organizer
    ):
        square = upload(
            bucket,
            session,
            organizer,
            MediaKind.PROMO,
            "square",
            title="Poster for the set",
        )
        landscape = upload(bucket, session, organizer, MediaKind.PROMO, "landscape")
        square2 = upload(bucket, session, organizer, MediaKind.PROMO, "square")
        assert landscape.title == square2.title == "Poster for the set"
        assert line_title(session, MediaKind.PROMO, "") == "Poster for the set"
        # Another line is another matter.
        cut = upload(bucket, session, organizer, MediaKind.PROCESSED_VIDEO)
        assert (
            cut.title == "" and line_title(session, MediaKind.PROCESSED_VIDEO, "") == ""
        )
        # A title of its own is kept, and becomes the newest one on the line.
        gif = upload(
            bucket,
            session,
            organizer,
            MediaKind.PROMO,
            "gif",
            title="  The animated one  ",
        )
        assert gif.title == "The animated one"
        assert line_title(session, MediaKind.PROMO, "") == "The animated one"
        assert line_titles(session) == {"PROMO|": "The animated one"}
        assert square.display_title == "Poster for the set"
        assert cut.display_title == "Processed video (final cut)"

    def test_the_endpoint_takes_and_truncates_the_title(
        self, client, bucket, session, organizer
    ):
        client.force_login(organizer)
        response = client.post(
            reverse("speakers:upload_start", args=[session.slug]),
            {
                "kind": "PROMO",
                "title": "x" * 250,
                "filename": "poster.png",
                "size_bytes": 3,
            },
            content_type="application/json",
        )
        assert response.status_code == 201
        assert response.json()["title"] == "x" * 200


@pytest.mark.django_db
class TestEditing:
    def test_the_whole_line_and_nothing_else(
        self, client, bucket, session, organizer, speaker
    ):
        square = upload(
            bucket, session, organizer, MediaKind.PROMO, "square", title="Old"
        )
        landscape = upload(bucket, session, organizer, MediaKind.PROMO, "landscape")
        square2 = upload(bucket, session, organizer, MediaKind.PROMO, "square")
        other = upload(bucket, session, organizer, MediaKind.TITLE_CARD, title="Card")
        client.force_login(speaker)
        assert (
            client.post(title_url(session, square2), {"title": "Nope"}).status_code
            == 403
        )
        client.force_login(organizer)
        response = client.post(title_url(session, square2), {"title": " New poster "})
        assert response.status_code == 302
        for asset in (square, landscape, square2):
            asset.refresh_from_db()
            assert asset.title == "New poster"
        other.refresh_from_db()
        assert other.title == "Card"
        # htmx gets the group back, retitled.
        response = client.post(
            title_url(session, landscape),
            {"title": "Newer"},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        html = response.content.decode()
        assert html.strip().startswith('<tbody id="files-promo----landscape"')
        assert "Newer" in html and 'value="Newer"' in html
        assert set_line_title(square, "") == ""
        assert (
            not MediaAsset.objects.filter(kind=MediaKind.PROMO)
            .exclude(title="")
            .exists()
        )


@pytest.mark.django_db
class TestWhereItShows:
    def test_organizer_page_speaker_page_and_the_panel(
        self, client, bucket, session, organizer, speaker
    ):
        poster = upload(
            bucket,
            session,
            organizer,
            MediaKind.PROMO,
            "square",
            title="Poster for the set",
        )
        poster.shared_with_speaker = True
        poster.save()
        upload(bucket, session, organizer, MediaKind.TITLE_CARD)
        client.force_login(organizer)
        html = client.get(session.get_absolute_url()).content.decode()
        groups = {g["id"]: g for g in asset_groups(session_assets(session))}
        assert groups["files-promo----square"]["title"] == "Poster for the set"
        assert groups["files-title_card----"]["title"] == ""
        assert "Poster for the set" in html
        assert (
            'id="title-files-promo----square"' in html
            and 'id="title-files-title_card----"' in html
        )
        assert 'data-role="title"' in html
        assert 'id="upload-titles-files"' in html
        assert '"PROMO|": "Poster for the set"' in html
        client.force_login(speaker)
        html = client.get(
            reverse("speakers:my_session_detail", args=[session.slug])
        ).content.decode()
        assert "Poster for the set" in html and "Promo material (square)" in html
        assert 'id="upload-titles-video"' in html

    def test_board_and_csv_carry_it(self, session, organizer):
        MediaAsset.objects.create(
            session=session,
            kind=MediaKind.RAW_VIDEO,
            status=MediaStatus.READY,
            storage_key="k",
            title="Take two, quieter room",
            duration_seconds=90,
        )
        board = build_post_production_board(session.conference, organizer)
        assert board["rows"][0]["raw"].title == "Take two, quieter room"
        from io import StringIO

        csv = write_post_production_csv(board, StringIO()).getvalue()
        assert "v1 (1:30) Take two, quieter room" in csv


@pytest.mark.django_db
class TestGroupIds:
    def test_no_two_lines_share_an_id(self, session, organizer):
        """The id is the htmx target and the More row's toggle, so language
        and variant must not run together: "" + "en" and "en" + "" were one
        id, and "en-US" + "" met "en" + "US" by case alone."""
        rows = [("", "en"), ("en", ""), ("en-US", ""), ("en", "US"), ("", "")]
        # Slugs are not one-to-one: rows written past the upload's
        # normalisation (the admin, say) must still get their own ids.
        rows += [("", "GIF"), ("", "gif"), ("", "a b"), ("", "a-b")]
        rows += [("", "square"), ("", "square!"), ("", "café"), ("", "cafe")]
        for language, variant in rows:
            MediaAsset.objects.create(
                session=session,
                kind=MediaKind.PROMO,
                status=MediaStatus.READY,
                language=language,
                variant=variant,
                storage_key=f"k/{language}/{variant}",
            )
        ids = [g["id"] for g in asset_groups(session_assets(session))]
        assert len(ids) == len(set(ids)) == len(rows)
        assert "files-promo----en" in ids and "files-promo--en--" in ids
        assert "files-promo----gif" in ids and "files-promo----a-b" in ids
        # Not its own slug, so it carries the hash and cannot meet "en-US".
        assert any(i.startswith("files-promo--en--us--") for i in ids)
        assert all(re.fullmatch(r"[A-Za-z0-9_-]+", i) for i in ids)

    def test_a_variant_is_one_lower_case_line(self, bucket, session, organizer):
        """ "GIF" and "gif" were two lines; the upload files them as one."""
        first = upload(bucket, session, organizer, MediaKind.PROMO, variant=" GIF ")
        second = upload(bucket, session, organizer, MediaKind.PROMO, variant="gif")
        assert first.variant == "gif" and second.variant == "gif"
        first.refresh_from_db()
        assert first.status == MediaStatus.SUPERSEDED and second.version == 2

    def test_a_title_is_one_line(self, bucket, session, organizer):
        poster = upload(bucket, session, organizer, MediaKind.PROMO, variant="square")
        assert set_line_title(poster, " line one\nline two\ttabbed ") == (
            "line one line two tabbed"
        )
        titled = upload(
            bucket, session, organizer, MediaKind.TITLE_CARD, title="a\n\nb"
        )
        assert titled.title == "a b"

    def test_the_board_shows_both_titles_when_they_differ(
        self, client, bucket, session, organizer
    ):
        upload(bucket, session, organizer, MediaKind.RAW_VIDEO, title="The take")
        upload(bucket, session, organizer, MediaKind.PROCESSED_VIDEO, title="The cut")
        client.force_login(organizer)
        html = client.get(
            reverse("speakers:checklist_board"), {"tab": "post_production"}
        ).content.decode()
        assert "The take" in html and "final cut: The cut" in html
