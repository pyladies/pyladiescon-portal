"""The speaker side of the media pipeline is a per-edition switch (design
§8.8): off, speakers see and can do nothing new; organizers are untouched."""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from speakers.constants import MediaKind, MediaStatus
from speakers.media import can_download, can_upload
from speakers.models import MediaAsset, SpeakerSettings, media_for_speakers

from .factories import add_presenter, make_presenter, make_session, make_settings


@pytest.fixture
def organizer(db):
    return User.objects.create_user("org", email="org@x.org", is_staff=True)


@pytest.fixture
def speaker(db):
    return User.objects.create_user("ada", email="ada@x.org")


@pytest.fixture
def session(conference, speaker):
    make_settings(conference, media_for_speakers=False)
    session = make_session(conference, title="A PyJam set", kind="PYJAM")
    add_presenter(
        session,
        make_presenter(conference, display_name="Ada", user=speaker),
        confirmed=True,
    )
    return session


def shared(session, **kwargs):
    kwargs.setdefault("kind", MediaKind.PROCESSED_VIDEO)
    return MediaAsset.objects.create(
        session=session,
        status=MediaStatus.READY,
        storage_key="k",
        original_filename="cut.mp4",
        content_type="video/mp4",
        shared_with_speaker=True,
        **kwargs,
    )


@pytest.mark.django_db
class TestSwitchOff:
    def test_the_helper(self, conference, session):
        assert media_for_speakers(conference) is False
        assert media_for_speakers(None) is False
        SpeakerSettings.objects.filter(conference=conference).update(
            media_for_speakers=True
        )
        assert media_for_speakers(conference) is True

    def test_speaker_page_has_no_media(self, client, session, speaker):
        shared(session)
        client.force_login(speaker)
        response = client.get(
            reverse("speakers:my_session_detail", args=[session.slug])
        )
        assert response.status_code == 200
        assert response.context["media_for_speakers"] is False
        assert (
            response.context["video"] is None and response.context["team_files"] == []
        )
        html = response.content.decode()
        assert 'id="tab-files"' not in html and "Upload video" not in html
        assert "Your video" not in html and "Files from the team" not in html
        assert 'id="tab-checklist"' in html  # the rest of the page stands

    def test_presenters_neither_upload_nor_fetch(
        self, client, session, speaker, organizer
    ):
        cut = shared(session)
        assert not can_upload(speaker, session, MediaKind.RAW_VIDEO)
        assert not can_download(speaker, session, cut)
        assert not can_download(speaker, session)
        # Organizers keep everything.
        assert can_upload(organizer, session, MediaKind.RAW_VIDEO)
        assert can_download(organizer, session, cut)
        client.force_login(speaker)
        response = client.post(
            reverse("speakers:upload_start", args=[session.slug]),
            {"kind": "RAW_VIDEO", "filename": "take.mp4", "size_bytes": 3},
            content_type="application/json",
        )
        assert response.status_code == 403
        assert (
            client.get(
                reverse("speakers:media_download", args=[session.slug, cut.pk])
            ).status_code
            == 403
        )

    def test_organizer_page_is_unchanged(self, client, session, organizer, settings):
        settings.SPEAKER_MEDIA_BUCKET = "test-speaker-media"
        shared(session)
        client.force_login(organizer)
        html = client.get(session.get_absolute_url()).content.decode()
        assert 'id="tab-files"' in html and "data-upload-panel" in html

    def test_switching_on_restores_the_speaker_side(
        self, client, session, speaker, conference
    ):
        cut = shared(session)
        SpeakerSettings.objects.filter(conference=conference).update(
            media_for_speakers=True
        )
        client.force_login(speaker)
        html = client.get(
            reverse("speakers:my_session_detail", args=[session.slug])
        ).content.decode()
        assert 'id="tab-files"' in html and "Files from the team" in html
        assert can_download(speaker, session, cut)

    def test_admin_form_offers_the_switch(self, client, conference, session):
        admin = User.objects.create_superuser("root", "root@x.org", "pw")
        client.force_login(admin)
        row = SpeakerSettings.objects.get(conference=conference)
        html = client.get(
            reverse("admin:speakers_speakersettings_change", args=[row.pk])
        ).content.decode()
        assert 'name="media_for_speakers"' in html and "Media" in html
