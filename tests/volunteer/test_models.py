import pytest
from django.conf.global_settings import LANGUAGES
from django.core import mail
from django.urls import reverse

from volunteer.models import Role, Team, VolunteerProfile


@pytest.mark.django_db
class TestVolunteerModel:

    def test_volunteer_profile(self, portal_user):
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.timezone = "UTC"
        profile.save()

        assert profile.get_absolute_url() == reverse(
            "volunteer:volunteer_profile_edit", kwargs={"pk": profile.pk}
        )

    def test_profile_str_representation(self, portal_user):
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.timezone = "UTC"
        assert str(profile) == portal_user.username

    def test_team_str_representation(self, portal_user):
        team = Team(short_name="Test Team")
        team.save()
        assert str(team) == "Test Team"

    def test_role_str_representation(self, portal_user):
        role = Role(short_name="Test Role")
        role.save()
        assert str(role) == "Test Role"

    def test_email_is_sent_after_saved(self, portal_user):
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.timezone = "UTC"
        profile.save()
        assert (
            str(mail.outbox[0].subject)
            == "[PyLadiesCon Dev]  Volunteer Application Received"
        )

    def test_email_is_sent_after_updated(self, portal_user):
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.timezone = "UTC"
        profile.save()
        mail.outbox.clear()

        profile.timezone = "UTC+1"
        profile.save()

        assert (
            str(mail.outbox[0].subject)
            == "[PyLadiesCon Dev]  Volunteer Application Updated"
        )

    def test_volunteer_notification_email_contains_info(self, portal_user):
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0], LANGUAGES[1]]
        profile.timezone = "UTC"
        profile.bluesky_username = "mybsky"
        profile.discord_username = "mydiscord"
        profile.github_username = "mygithub"
        profile.instagram_username = "myinstagram"
        profile.mastodon_url = "mymastodon"
        profile.x_username = "myxusername"
        profile.linkedin_url = "mylinkedin"
        profile.pyladies_chapter = "mychapter"

        profile.save()

        body = str(mail.outbox[0].body)
        assert profile.bluesky_username in body
        assert profile.discord_username in body
        assert profile.github_username in body
        assert profile.instagram_username in body
        assert profile.mastodon_url in body
        assert profile.x_username in body
        assert profile.linkedin_url in body
        assert profile.timezone in body
        assert profile.languages_spoken[0][0] in body
        assert profile.user.first_name in body
        assert profile.pyladies_chapter in body

        assert reverse("volunteer:index") in body
