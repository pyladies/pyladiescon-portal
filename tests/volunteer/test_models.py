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

    def test_send_volunteer_email(self, portal_user):
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]

        profile.application_status = "Approved"
        profile.save()

        profile.send_volunteer_email()

        assert (
            str(mail.outbox[0].subject)
            == "[PyLadiesCon Dev]  Volunteer Application Status"
        )
