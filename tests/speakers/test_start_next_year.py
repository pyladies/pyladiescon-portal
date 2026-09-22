import pytest
from django.urls import reverse
from django.utils import timezone

from portal.models import Conference
from speakers.models import (
    ChecklistTemplate,
    Handbook,
    SpeakerSettings,
    speaker_module_enabled,
)
from speakers.seeds import DEFAULT_TEMPLATES, clone_speaker_setup, seed_checklists

from .factories import make_settings


def payload(**overrides):
    data = {"year": 2027, "name": "PyLadiesCon 2027", "slug": "2027"}
    data.update(overrides)
    return data


@pytest.fixture
def source(conference):
    """The previous edition with a full speaker setup."""
    make_settings(
        conference,
        conference_timezone="Europe/Lisbon",
        organizers_email="team@example.com",
        translation_languages=["pt-br"],
        pretix_organizer="pyladiescon",
        pretix_api_token="secret",
    )
    seed_checklists(conference)
    Handbook.objects.create(
        conference=conference,
        key="workshop",
        version=2,
        title="Workshop guide",
        url="https://example.org/w",
        published_at=timezone.now(),
    )
    Handbook.objects.create(
        conference=conference, key="speaker", version=1, title="Draft only"
    )
    return conference


@pytest.mark.django_db
class TestStartNextYear:
    def test_form_offers_the_speaker_options(self, client, admin_user, source):
        client.force_login(admin_user)
        content = client.get(reverse("start_new_year")).content.decode()
        assert "Copy the speaker portal setup" in content
        assert "Enable the speaker portal for this edition" in content

    def test_copies_setup_and_enables(self, client, admin_user, source):
        client.force_login(admin_user)
        response = client.post(
            reverse("start_new_year"),
            payload(copy_speaker_setup="on", speaker_portal="on"),
            follow=True,
        )
        content = response.content.decode()
        assert (
            f"{len(DEFAULT_TEMPLATES)} checklist template(s), 1 speaker guide(s)"
            in content
        )
        assert "The speaker portal is on." in content
        new = Conference.objects.get(year=2027)
        assert speaker_module_enabled(new) is True
        row = SpeakerSettings.objects.get(conference=new)
        assert row.conference_timezone == "Europe/Lisbon"
        assert row.organizers_email == "team@example.com"
        assert row.translation_languages == ["pt-br"]
        assert row.pretix_organizer == "pyladiescon" and row.pretix_api_token == ""
        assert ChecklistTemplate.objects.filter(conference=new).count() == len(
            DEFAULT_TEMPLATES
        )
        guide = Handbook.objects.get(conference=new, key="workshop")
        assert guide.version == 1 and not guide.is_published
        assert guide.url == "https://example.org/w"
        assert not Handbook.objects.filter(conference=new, key="speaker").exists()

    def test_copy_without_enabling(self, client, admin_user, source):
        client.force_login(admin_user)
        client.post(reverse("start_new_year"), payload(copy_speaker_setup="on"))
        new = Conference.objects.get(year=2027)
        assert speaker_module_enabled(new) is False
        assert SpeakerSettings.objects.filter(conference=new).exists()

    def test_enable_without_copy(self, client, admin_user, source):
        client.force_login(admin_user)
        response = client.post(
            reverse("start_new_year"), payload(speaker_portal="on"), follow=True
        )
        new = Conference.objects.get(year=2027)
        assert speaker_module_enabled(new) is True
        assert ChecklistTemplate.objects.filter(conference=new).count() == 0
        assert "checklist template" not in response.content.decode()

    def test_neither(self, client, admin_user, source):
        client.force_login(admin_user)
        client.post(reverse("start_new_year"), payload())
        new = Conference.objects.get(year=2027)
        assert not SpeakerSettings.objects.filter(conference=new).exists()

    def test_clone_is_idempotent_and_survives_missing_source_settings(self, conference):
        SpeakerSettings.objects.filter(conference=conference).delete()
        seed_checklists(conference)
        target = Conference.objects.create(year=2027, name="Next", slug="2027")
        first = clone_speaker_setup(target, conference)
        assert first == {
            "templates": len(DEFAULT_TEMPLATES),
            "items": first["items"],
            "guides": 0,
        }
        second = clone_speaker_setup(target, conference, enable=True)
        assert second["templates"] == 0 and second["guides"] == 0
        assert speaker_module_enabled(target) is True

    def test_existing_guide_key_in_target_is_kept(self, conference, source):
        target = Conference.objects.create(year=2027, name="Next", slug="2027")
        Handbook.objects.create(
            conference=target, key="workshop", version=1, title="Mine"
        )
        assert clone_speaker_setup(target, conference)["guides"] == 0
        assert Handbook.objects.get(conference=target, key="workshop").title == "Mine"
