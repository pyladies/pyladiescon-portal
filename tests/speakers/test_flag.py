from pathlib import Path

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


@pytest.mark.django_db
class TestFlagOnConferenceForm:
    """The switch is also on Organize -> Conferences -> edit."""

    def payload(self, conference, **overrides):
        data = {
            "year": conference.year,
            "name": conference.name,
            "slug": conference.slug,
            "is_active": "on",
            "pretix_event_slug": conference.pretix_event_slug,
            "sponsorship_goal": "15000",
            "donation_goal": "2500",
            "proposals_count": "0",
            "accepting_donations": "on",
            "conference_date": conference.conference_date.isoformat(),
        }
        data.update(overrides)
        return data

    def test_shows_current_state(self, client, admin_user, conference):
        client.force_login(admin_user)
        url = reverse("conference_edit", kwargs={"pk": conference.pk})
        assert (
            client.get(url).context["form"]["speaker_module_enabled"].initial is False
        )
        SpeakerSettings.objects.create(
            conference=conference, speaker_module_enabled=True
        )
        assert client.get(url).context["form"]["speaker_module_enabled"].initial is True
        assert "Speaker portal enabled" in client.get(url).content.decode()

    def test_turning_on_creates_the_settings_row(self, client, admin_user, conference):
        client.force_login(admin_user)
        url = reverse("conference_edit", kwargs={"pk": conference.pk})
        response = client.post(
            url, self.payload(conference, speaker_module_enabled="on")
        )
        assert response.status_code == 302
        assert speaker_module_enabled(conference) is True
        assert client.get(reverse("speakers:index")).status_code == 302

    def test_turning_off_keeps_the_row(self, client, admin_user, conference):
        SpeakerSettings.objects.create(
            conference=conference, speaker_module_enabled=True, pretix_organizer="org"
        )
        client.force_login(admin_user)
        client.post(
            reverse("conference_edit", kwargs={"pk": conference.pk}),
            self.payload(conference),
        )
        row = SpeakerSettings.objects.get(conference=conference)
        assert row.speaker_module_enabled is False and row.pretix_organizer == "org"

    def test_saving_off_without_a_row_creates_nothing(
        self, client, admin_user, conference
    ):
        client.force_login(admin_user)
        client.post(
            reverse("conference_edit", kwargs={"pk": conference.pk}),
            self.payload(conference),
        )
        assert not SpeakerSettings.objects.filter(conference=conference).exists()


@pytest.mark.django_db
class TestFormWithoutTheSpeakersApp:
    """The core form reads the settings model through the app registry, so
    portal does not import speakers (review of #425)."""

    def test_the_field_disappears_when_the_app_is_absent(self, conference, monkeypatch):
        from django.apps import apps as django_apps

        from portal.forms import ConferenceForm

        monkeypatch.setattr(
            django_apps, "is_installed", lambda label: label != "speakers"
        )
        form = ConferenceForm(instance=conference)
        assert "speaker_module_enabled" not in form.fields
        saved = ConferenceForm(
            {
                "year": conference.year,
                "name": conference.name,
                "slug": conference.slug,
                "sponsorship_goal": "0",
                "donation_goal": "0",
                "proposals_count": "0",
            },
            instance=conference,
        )
        assert saved.is_valid(), saved.errors
        saved.save()
        assert SpeakerSettings.objects.filter(conference=conference).exists() is False

    def test_portal_forms_does_not_import_speakers(self):
        import portal.forms

        source = Path(portal.forms.__file__).read_text()
        assert "from speakers" not in source and "import speakers" not in source
