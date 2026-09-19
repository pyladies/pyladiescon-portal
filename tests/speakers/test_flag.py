import pytest
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from portal.models import Conference
from speakers.models import SpeakerSettings, speaker_module_enabled
from speakers.permissions import is_speaker_organizer


@pytest.mark.django_db
class TestSpeakerModuleFlag:
    def test_off_when_no_settings_row(self, conference):
        assert speaker_module_enabled(conference) is False

    def test_off_when_no_conference(self):
        assert speaker_module_enabled(None) is False

    def test_off_when_row_disabled(self, conference):
        SpeakerSettings.objects.create(conference=conference)
        assert speaker_module_enabled(conference) is False

    def test_on_when_enabled(self, conference):
        SpeakerSettings.objects.create(
            conference=conference, speaker_module_enabled=True
        )
        assert speaker_module_enabled(conference) is True

    def test_flag_is_per_edition(self, conference):
        other = Conference.objects.create(
            year=2024, name="PyLadiesCon 2024", slug="2024"
        )
        SpeakerSettings.objects.create(conference=other, speaker_module_enabled=True)
        assert speaker_module_enabled(other) is True
        assert speaker_module_enabled(conference) is False

    def test_str(self, conference):
        settings = SpeakerSettings.objects.create(conference=conference)
        assert str(settings) == "Speaker settings (PyLadiesCon 2025)"


@pytest.mark.django_db
class TestSpeakerPortalIndex:
    def test_requires_login(self, client):
        response = client.get(reverse("speakers:index"))
        assertRedirects(response, reverse("account_login") + "?next=/speakers/")

    def test_404_when_disabled(self, client, portal_user):
        client.force_login(portal_user)
        assert client.get(reverse("speakers:index")).status_code == 404

    def test_404_when_no_active_conference(self, client, portal_user, conference):
        SpeakerSettings.objects.create(
            conference=conference, speaker_module_enabled=True
        )
        conference.is_active = False
        conference.save()
        client.force_login(portal_user)
        assert client.get(reverse("speakers:index")).status_code == 404

    def test_renders_when_enabled(self, client, portal_user, conference):
        SpeakerSettings.objects.create(
            conference=conference, speaker_module_enabled=True
        )
        client.force_login(portal_user)
        response = client.get(reverse("speakers:index"))
        assert response.status_code == 200
        assert response.context["conference"] == conference
        assert "PyLadiesCon 2025" in response.content.decode()


@pytest.mark.django_db
class TestSpeakerSettingsAdmin:
    def test_changelist_renders(self, client, admin_user, conference):
        SpeakerSettings.objects.create(conference=conference)
        client.force_login(admin_user)
        response = client.get(reverse("admin:speakers_speakersettings_changelist"))
        assert response.status_code == 200
        assert "PyLadiesCon 2025" in response.content.decode()


@pytest.mark.django_db
class TestIsSpeakerOrganizer:
    def test_anonymous(self):
        assert is_speaker_organizer(AnonymousUser()) is False

    def test_plain_user(self, portal_user):
        assert is_speaker_organizer(portal_user) is False

    def test_staff(self, portal_user):
        portal_user.is_staff = True
        assert is_speaker_organizer(portal_user) is True

    def test_superuser(self, admin_user):
        assert is_speaker_organizer(admin_user) is True
