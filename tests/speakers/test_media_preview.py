"""Previews (design §8.8): images, video and audio shown in a closed fold
straight from the private bucket through an inline presigned link; every
other type only ever downloads."""

from unittest.mock import patch

import boto3
import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from moto import mock_aws

from speakers.constants import MediaKind, MediaStatus
from speakers.media import MediaBucket, start_upload
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


def asset(session, **kwargs):
    kwargs.setdefault("kind", MediaKind.PROMO)
    kwargs.setdefault("status", MediaStatus.READY)
    kwargs.setdefault("storage_key", "speaker-media/x/poster.png")
    kwargs.setdefault("original_filename", "poster.png")
    kwargs.setdefault("content_type", "image/png")
    return MediaAsset.objects.create(session=session, **kwargs)


def preview(session, a):
    return reverse("speakers:media_preview", args=[session.slug, a.pk])


@pytest.mark.django_db
class TestWhatPreviews:
    def test_kind_from_the_content_type_or_the_name(self, session):
        cases = [
            ({"content_type": "image/png"}, "image"),
            ({"content_type": "video/mp4"}, "video"),
            ({"content_type": "audio/mpeg"}, "audio"),
            ({"content_type": "text/vtt", "original_filename": "t.vtt"}, "text"),
            (
                {
                    "content_type": "application/octet-stream",
                    "original_filename": "t.srt",
                },
                "text",
            ),
            ({"content_type": "text/plain", "original_filename": "notes.txt"}, "text"),
            (
                {
                    "content_type": "text/plain",
                    "original_filename": "big.txt",
                    "size_bytes": 3 * 1024 * 1024,
                },
                "",
            ),
            ({"content_type": "text/html", "original_filename": "x.html"}, ""),
            (
                {
                    "content_type": "application/octet-stream",
                    "original_filename": "take.mov",
                },
                "video",
            ),
            ({"content_type": "", "original_filename": "card.jpg"}, "image"),
            ({"content_type": "", "original_filename": "mystery"}, ""),
            # An allowlist of bitmap types: SVG carries script, so it only
            # ever downloads, whatever the name or the declared type.
            ({"content_type": "image/svg+xml", "original_filename": "x.svg"}, ""),
            ({"content_type": "", "original_filename": "logo.svg"}, ""),
            ({"content_type": "image/webp"}, "image"),
        ]
        for fields, expected in cases:
            a = asset(session, **fields)
            assert a.preview_kind == expected, fields
            a.delete()

    def test_no_file_no_preview(self, session):
        a = asset(session, storage_key="", content_type="image/png")
        assert a.preview_kind == "image" and a.preview_url() == ""
        text = asset(session, content_type="text/vtt", original_filename="t.vtt")
        assert text.preview_url() == ""


@pytest.mark.django_db
class TestPreviewLink:
    def test_inline_with_the_type_for_whoever_may_download(
        self, client, bucket, session, organizer, speaker
    ):
        shared = asset(session, shared_with_speaker=True)
        client.force_login(organizer)
        response = client.get(preview(session, shared))
        assert response.status_code == 302
        location = response["Location"]
        assert "response-content-disposition=inline" in location
        assert "response-content-type=image%2Fpng" in location
        assert "attachment" not in location
        client.force_login(speaker)
        assert client.get(preview(session, shared)).status_code == 302
        private = asset(session, kind=MediaKind.TITLE_CARD)
        assert client.get(preview(session, private)).status_code == 403

    def test_a_transcript_is_shown_as_plain_text(
        self, client, bucket, session, organizer, speaker
    ):
        body = "WEBVTT\n\n1\n00:00:00.000 --> 00:00:02.000\nHello\n"
        bucket.client.put_object(
            Bucket=BUCKET, Key="speaker-media/x/t.vtt", Body=body.encode()
        )
        text = asset(
            session,
            kind=MediaKind.TRANSCRIPT,
            language="en",
            content_type="text/vtt",
            original_filename="t.vtt",
            storage_key="speaker-media/x/t.vtt",
            size_bytes=len(body),
            shared_with_speaker=True,
        )
        client.force_login(organizer)
        response = client.get(preview(session, text))
        assert response.status_code == 200
        assert response["Content-Type"] == "text/plain; charset=utf-8"
        assert response["Content-Disposition"] == "inline"
        # Shown in an iframe on the page: DENY, the middleware's default,
        # would leave the fold empty.
        assert response["X-Frame-Options"] == "SAMEORIGIN"
        assert response.content.decode() == body
        html = client.get(session.get_absolute_url()).content.decode()
        assert f'<iframe src="{preview(session, text)}"' in html
        assert "Open as text in a new tab" in html
        client.force_login(speaker)
        assert client.get(preview(session, text)).status_code == 200
        html = client.get(
            reverse("speakers:my_session_detail", args=[session.slug])
        ).content.decode()
        assert f'<iframe src="{preview(session, text)}"' in html
        # Bytes that are not UTF-8 still show, replaced rather than refused.
        bucket.client.put_object(
            Bucket=BUCKET, Key="speaker-media/x/t.vtt", Body=b"caf\xe9"
        )
        assert client.get(preview(session, text)).content.decode() == "caf\ufffd"

    def test_a_file_the_browser_cannot_show_is_404_and_so_is_no_storage(
        self, client, bucket, session, organizer, settings
    ):
        client.force_login(organizer)
        html = asset(session, content_type="text/html", original_filename="x.html")
        assert client.get(preview(session, html)).status_code == 404
        image = asset(session)
        text = asset(session, content_type="text/vtt", original_filename="t.vtt")
        settings.SPEAKER_MEDIA_BUCKET = ""
        assert client.get(preview(session, image)).status_code == 404
        assert client.get(preview(session, text)).status_code == 404

    def test_an_admin_attached_text_file_is_read_from_disk(
        self, client, session, organizer
    ):
        note = MediaAsset.objects.create(
            session=session,
            kind=MediaKind.OTHER,
            status=MediaStatus.READY,
            file=SimpleUploadedFile("notes.txt", b"hello"),
            original_filename="notes.txt",
            size_bytes=5,
        )
        empty = asset(
            session,
            storage_key="",
            content_type="text/plain",
            original_filename="e.txt",
        )
        client.force_login(organizer)
        assert client.get(preview(session, note)).content == b"hello"
        assert client.get(preview(session, empty)).status_code == 404

    def test_an_asset_with_nothing_behind_it_is_404(
        self, client, bucket, session, organizer
    ):
        client.force_login(organizer)
        empty = asset(session, storage_key="")
        assert client.get(preview(session, empty)).status_code == 404

    def test_the_link_lives_a_minute_like_a_download(
        self, client, bucket, session, organizer
    ):
        """A bearer URL to a multi-gigabyte video should not sit in the
        history and the proxy logs for an hour; the fold loads through
        the endpoint, so a fresh link is minted for every request."""
        client.force_login(organizer)
        location = client.get(preview(session, asset(session)))["Location"]
        assert "X-Amz-Expires=60" in location and "inline" in location

    def test_a_video_kind_is_stored_as_a_video_whatever_was_declared(
        self, bucket, session, organizer
    ):
        """The declared type decides how the file is served back, so a raw
        video declared image/svg+xml is stored as what its name says."""
        upload = start_upload(
            session=session,
            kind=MediaKind.RAW_VIDEO,
            language="",
            filename="talk.mp4",
            size_bytes=3,
            content_type="image/svg+xml",
            user=organizer,
        )
        assert upload.content_type == "video/mp4"
        # A video extension the platform's type table does not know is
        # stored as an octet-stream: still never the declared text/html.
        with patch("speakers.media.mimetypes.guess_type", return_value=(None, None)):
            unknown = start_upload(
                session=session,
                kind=MediaKind.PROCESSED_VIDEO,
                language="",
                filename="cut.mts",
                size_bytes=3,
                content_type="text/html",
                user=organizer,
            )
        assert unknown.content_type == "application/octet-stream"

    def test_an_admin_attached_file_previews_by_its_url(
        self, client, session, organizer
    ):
        a = MediaAsset.objects.create(
            session=session,
            kind=MediaKind.THUMBNAIL,
            status=MediaStatus.READY,
            file=SimpleUploadedFile("thumb.png", b"png"),
        )
        assert a.preview_kind == "image"
        client.force_login(organizer)
        response = client.get(preview(session, a))
        assert response.status_code == 302 and "thumb" in response["Location"]


@pytest.mark.django_db
class TestTheFold:
    def test_rows_carry_a_closed_fold_only_for_showable_files(
        self, client, session, organizer, speaker
    ):
        image = asset(session, shared_with_speaker=True)
        video = asset(
            session,
            kind=MediaKind.PROCESSED_VIDEO,
            storage_key="k2",
            original_filename="cut.mp4",
            content_type="video/mp4",
            shared_with_speaker=True,
        )
        text = asset(
            session,
            kind=MediaKind.TRANSCRIPT,
            language="en",
            storage_key="k3",
            original_filename="t.vtt",
            content_type="text/vtt",
            shared_with_speaker=True,
        )
        # An earlier version is for the record, not for watching: no fold.
        old = asset(
            session,
            version=0,
            status=MediaStatus.SUPERSEDED,
            storage_key="k0",
            original_filename="poster-old.png",
        )
        client.force_login(organizer)
        html = client.get(session.get_absolute_url()).content.decode()
        assert "poster-old.png" in html and preview(session, old) not in html
        assert html.count('<details class="media-preview') == 3
        assert (
            f'<img src="{preview(session, image)}"' in html and 'loading="lazy"' in html
        )
        assert (
            f'<video src="{preview(session, video)}"' in html
            and 'preload="none"' in html
        )
        assert f'<iframe src="{preview(session, text)}"' in html
        client.force_login(speaker)
        html = client.get(
            reverse("speakers:my_session_detail", args=[session.slug])
        ).content.decode()
        assert html.count('<details class="media-preview') == 3
        assert preview(session, image) in html and preview(session, text) in html
