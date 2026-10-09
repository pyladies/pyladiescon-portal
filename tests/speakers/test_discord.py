"""The Discord username on a presenter, asked once of a volunteer who speaks."""

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from portal.models import Conference
from portal.validators import validate_discord_username
from speakers.models import Presenter, volunteer_discord_username
from speakers.program_types import session_type
from speakers.seeds import seed_checklists
from speakers.services import link_presenter_user
from speakers.shared import presenter_discord_username
from volunteer.forms import VolunteerProfileForm
from volunteer.models import VolunteerProfile

from .factories import add_presenter, make_presenter, make_session, make_settings

PROFILE = reverse("speakers:my_profile")
PROPOSE = reverse("speakers:propose")
FIELD = 'name="discord_username"'
NOTE = "from your volunteer profile"


@pytest.fixture
def enabled(conference):
    seed_checklists(conference)
    return make_settings(conference, proposals_open=True)


@pytest.fixture
def speaker(db):
    return User.objects.create_user(username="ada", email="ada@example.com")


@pytest.fixture
def presenter(conference, enabled, speaker):
    """On the program, so the speaker area opens."""
    presenter = make_presenter(
        conference, display_name="Ada", email="ada@example.com", user=speaker
    )
    add_presenter(make_session(conference), presenter, confirmed=True)
    return presenter


@pytest.fixture
def organizer(db):
    return User.objects.create_user(
        username="organizer", email="org@example.com", is_staff=True
    )


def volunteer(user, conference, username):
    return VolunteerProfile.objects.create(
        user=user, conference=conference, discord_username=username
    )


@pytest.mark.parametrize(
    "value, message",
    [
        ("ada_l.1", None),
        ("a", "between 2 and 32"),
        ("a" * 33, "between 2 and 32"),
        ("ada..l", "two consecutive periods"),
        ("ada#1234", "alphanumeric"),
    ],
)
def test_the_validator_is_the_volunteer_forms_rule(value, message):
    if message is None:
        validate_discord_username(value)
        return
    with pytest.raises(ValidationError, match=message):
        validate_discord_username(value)


@pytest.mark.django_db
class TestSpeakerProfile:
    def test_asked_once_on_the_profile_form(self, client, speaker, presenter):
        client.force_login(speaker)
        assert FIELD in client.get(PROFILE).content.decode()
        response = client.post(
            PROFILE,
            {"display_name": "Ada", "timezone": "UTC", "discord_username": "ada..l"},
        )
        assert "two consecutive periods" in response.content.decode()
        response = client.post(
            PROFILE,
            {"display_name": "Ada", "timezone": "UTC", "discord_username": "ada_l"},
        )
        assertRedirects(response, PROFILE)
        presenter.refresh_from_db()
        assert presenter.discord_username == "ada_l"

    def test_not_asked_again_when_the_volunteer_profile_has_one(
        self, client, conference, speaker, presenter
    ):
        volunteer(speaker, conference, "ada_vol")
        # The row already follows the volunteer profile; blank it to show
        # that saving the form restores it rather than asking.
        Presenter.objects.filter(pk=presenter.pk).update(discord_username="")
        client.force_login(speaker)
        page = client.get(PROFILE).content.decode()
        assert FIELD not in page
        assert "Change it there and it follows here" in page and "ada_vol" in page
        assert reverse("volunteer:index") in page
        response = client.post(
            PROFILE,
            {"display_name": "Ada", "timezone": "UTC", "discord_username": "other"},
        )
        assertRedirects(response, PROFILE)
        presenter.refresh_from_db()
        assert presenter.discord_username == "ada_vol"

    def test_the_organizer_form_shows_the_volunteers_value_read_only(
        self, client, conference, organizer, speaker, presenter
    ):
        """An organizer cannot set what the next volunteer profile save
        would overwrite; the form says where the value comes from."""
        volunteer(speaker, conference, "ada_vol")
        client.force_login(organizer)
        url = reverse("speakers:presenter_edit", args=[presenter.slug])
        page = client.get(url).content.decode()
        assert FIELD not in page
        assert "from their volunteer profile" in page and "ada_vol" in page
        response = client.post(
            url,
            {
                "display_name": "Ada",
                "email": "ada@example.com",
                "timezone": "UTC",
                "discord_username": "org_set",
            },
        )
        assert response.status_code == 302
        presenter.refresh_from_db()
        assert presenter.discord_username == "ada_vol"

    def test_the_organizer_page_lists_every_handle(self, client, organizer, presenter):
        """Blank ones show as blank, so an organizer can see what is missing."""
        client.force_login(organizer)
        url = reverse("speakers:presenter_detail", args=[presenter.slug])
        page = client.get(url).content.decode()
        for label in (
            "Website",
            "GitHub",
            "Mastodon",
            "LinkedIn",
            "Bluesky",
            "Discord",
        ):
            assert f"<strong>{label}:</strong>" in page
        presenter.discord_username = "ada_l"
        presenter.github_username = "ada"
        presenter.bluesky_username = "ada.bsky.social"
        presenter.save()
        page = client.get(url).content.decode()
        assert "ada_l" in page
        assert 'href="https://github.com/ada"' in page
        assert 'href="https://bsky.app/profile/ada.bsky.social"' in page


@pytest.mark.django_db
class TestFollowsTheVolunteerProfile:
    def test_saving_the_volunteer_profile_updates_the_presenter_rows(
        self, conference, speaker, presenter
    ):
        other = make_presenter(
            conference,
            user=User.objects.create_user("grace", email="grace@example.com"),
            discord_username="grace_h",
        )
        presenter.discord_username = "old"
        presenter.save()
        profile = volunteer(speaker, conference, "ada_vol")
        presenter.refresh_from_db()
        assert presenter.discord_username == "ada_vol"
        profile.discord_username = "ada_newer"
        profile.save()
        presenter.refresh_from_db()
        assert presenter.discord_username == "ada_newer"
        # A blank one is nothing to follow.
        profile.discord_username = ""
        profile.save()
        presenter.refresh_from_db()
        assert presenter.discord_username == "ada_newer"
        other.refresh_from_db()
        assert other.discord_username == "grace_h"

    def test_the_newest_edition_wins(self, conference, speaker, presenter):
        past = Conference.objects.create(
            year=2024, name="PyLadiesCon 2024", slug="2024"
        )
        volunteer(speaker, past, "ada_2024")
        volunteer(speaker, conference, "ada_now")
        assert presenter.volunteer_discord_username == "ada_now"
        assert make_presenter(conference).volunteer_discord_username == ""
        assert volunteer_discord_username(None) == ""

    def test_accepting_an_invitation_takes_the_volunteers_username(
        self, conference, enabled
    ):
        user = User.objects.create_user("sam", email="sam@example.com")
        EmailAddress.objects.create(
            user=user, email="sam@example.com", verified=True, primary=True
        )
        volunteer(user, conference, "sam_vol")
        invited = make_presenter(conference, email="sam@example.com")
        assert link_presenter_user(invited) == user
        invited.refresh_from_db()
        assert invited.discord_username == "sam_vol"

    def test_a_username_the_presenter_gave_is_kept(self, conference, enabled):
        user = User.objects.create_user("sam", email="sam@example.com")
        EmailAddress.objects.create(
            user=user, email="sam@example.com", verified=True, primary=True
        )
        volunteer(user, conference, "sam_vol")
        invited = make_presenter(
            conference, email="sam@example.com", discord_username="sam_own"
        )
        # The volunteer profile was saved before the row existed, so this
        # is the one path where the two can differ.
        link_presenter_user(invited)
        invited.refresh_from_db()
        assert invited.discord_username == "sam_own"


def propose(client, conference, **extra):
    data = {
        "you-display_name": "Sam Newcomer",
        "you-bio_md": "I write tests.",
        "you-timezone": "UTC",
        "session-kind": session_type(conference, "TALK").pk,
        "session-title": "A talk about testing",
        "session-summary_md": "What testing is for.",
        "session-level": "ALL",
        "session-language": "en",
    }
    data.update(extra)
    return client.post(PROPOSE, data, follow=True)


@pytest.mark.django_db
class TestProposing:
    @pytest.fixture
    def stranger(self, db):
        return User.objects.create_user(username="sam", email="sam@example.com")

    def test_a_stranger_is_asked(self, client, conference, enabled, stranger):
        assert client.get(PROPOSE).status_code == 200  # signed out: no user
        client.force_login(stranger)
        assert 'name="you-discord_username"' in client.get(PROPOSE).content.decode()
        propose(client, conference, **{"you-discord_username": "sam_d"})
        assert Presenter.objects.get(user=stranger).discord_username == "sam_d"

    def test_a_volunteer_is_not_asked(self, client, conference, enabled, stranger):
        volunteer(stranger, conference, "sam_vol")
        client.force_login(stranger)
        page = client.get(PROPOSE).content.decode()
        assert 'name="you-discord_username"' not in page
        assert NOTE in page and "sam_vol" in page
        propose(client, conference, **{"you-discord_username": "other"})
        assert Presenter.objects.get(user=stranger).discord_username == "sam_vol"


@pytest.mark.django_db
class TestVolunteerForm:
    def test_prefills_from_the_presenter_row(self, conference, speaker, presenter):
        presenter.discord_username = "ada_spk"
        presenter.save()
        assert (
            VolunteerProfileForm(user=speaker).initial["discord_username"] == "ada_spk"
        )

    def test_a_prior_volunteer_profile_wins(self, conference, speaker, presenter):
        presenter.discord_username = "ada_spk"
        presenter.save()
        past = Conference.objects.create(
            year=2024, name="PyLadiesCon 2024", slug="2024"
        )
        volunteer(speaker, past, "ada_2024")
        assert (
            VolunteerProfileForm(user=speaker).initial["discord_username"] == "ada_2024"
        )

    def test_nothing_to_prefill(self, speaker, presenter):
        assert "discord_username" not in VolunteerProfileForm(user=speaker).initial

    def test_the_accessor_without_the_module(self, monkeypatch, speaker, presenter):
        presenter.discord_username = "ada_spk"
        presenter.save()
        assert presenter_discord_username(None) == ""
        monkeypatch.setattr("speakers.shared.apps.is_installed", lambda label: False)
        assert presenter_discord_username(speaker) == ""
