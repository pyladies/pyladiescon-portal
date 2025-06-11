import pytest
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from volunteer.constants import Region
from volunteer.languages import LANGUAGES
from volunteer.models import ApplicationStatus, Role, Team, VolunteerProfile
from volunteer.views import (
    VolunteerProfileFilter,
    VolunteerProfileTable,
)


@pytest.mark.django_db
class TestVolunteer:

    def test_volunteer_view_requires_login(self, client):
        response = client.get(reverse("volunteer:index"))
        assertRedirects(response, reverse("account_login") + "?next=/volunteer/")

    def test_volunteer_profile_view_no_profile(self, client, portal_user):
        client.force_login(portal_user)
        response = client.get(reverse("volunteer:index"))
        assert response.status_code == 200
        assert response.context["profile_id"] is None

    def test_volunteer_profile_view_with_profile(self, client, portal_user):
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.save()

        client.force_login(portal_user)
        response = client.get(reverse("volunteer:index"))

        assert response.context["profile_id"] == profile.id
        assert response.status_code == 200

    def test_volunteer_profile_update_own_profile(self, client, portal_user):
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.save()
        client.force_login(portal_user)
        response = client.get(
            reverse("volunteer:volunteer_profile_edit", kwargs={"pk": profile.id})
        )
        assert response.status_code == 200

    def test_volunteer_profile_cannot_edit_other_profile(
        self, client, portal_user, django_user_model
    ):
        another_user = django_user_model.objects.create_user(
            username="other",
        )
        another_profile = VolunteerProfile(user=another_user)
        another_profile.languages_spoken = [LANGUAGES[0]]
        another_profile.save()

        client.force_login(portal_user)
        response = client.get(
            reverse(
                "volunteer:volunteer_profile_edit", kwargs={"pk": another_profile.id}
            )
        )
        assertRedirects(response, reverse("volunteer:index"))

    def test_volunteer_profile_create(self, client, portal_user):
        client.force_login(portal_user)
        response = client.get(reverse("volunteer:volunteer_profile_new"))
        assert response.status_code == 200

    def test_volunteer_profile_cannot_create_if_exists(self, client, portal_user):
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.region = Region.NORTH_AMERICA
        profile.save()

        client.force_login(portal_user)
        response = client.get(reverse("volunteer:volunteer_profile_new"))
        assertRedirects(response, reverse("volunteer:index"))

    def test_volunteer_profile_cannot_view_other_profile(
        self, client, portal_user, django_user_model
    ):
        another_user = django_user_model.objects.create_user(
            username="other",
        )
        another_profile = VolunteerProfile(user=another_user)
        another_profile.languages_spoken = [LANGUAGES[0]]
        another_profile.region = Region.NORTH_AMERICA
        another_profile.save()

        client.force_login(portal_user)
        response = client.get(
            reverse(
                "volunteer:volunteer_profile_detail", kwargs={"pk": another_profile.id}
            )
        )
        assertRedirects(response, reverse("volunteer:index"))

    def test_volunteer_profile_view_own_profile(self, client, portal_user):
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.region = Region.NORTH_AMERICA
        profile.save()
        client.force_login(portal_user)
        response = client.get(
            reverse("volunteer:volunteer_profile_detail", kwargs={"pk": profile.id})
        )
        assert response.status_code == 200
        profile_result = response.context["volunteerprofile"]
        assert profile_result == profile

    def test_new_volunteer_profile_form_submit(self, client, portal_user):
        client.force_login(portal_user)

        assert VolunteerProfile.objects.filter(user=portal_user).count() == 0

        data = {
            "languages_spoken": [LANGUAGES[0][0], LANGUAGES[1][0]],
            "timezone": "UTC",
            "github_username": "test-github",
            "discord_username": "testdiscord1234",
            "instagram_username": "test_instagram",
            "bluesky_username": "test.bsky.social",
            "mastodon_url": "https://mastodon.social/@test",
            "x_username": "test_x",
            "linkedin_url": "https://www.linkedin.com/in/test",
            "pyladies_chapter": "Test Chapter",
            "additional_comments": "Blablabla",
            "availability_hours_per_week": 10,
            "region": Region.NORTH_AMERICA,
        }
        response = client.post(reverse("volunteer:volunteer_profile_new"), data=data)
        assert response.status_code == 302

        profile = VolunteerProfile.objects.get(user=portal_user)
        assert profile.languages_spoken == [LANGUAGES[0][0], LANGUAGES[1][0]]
        assert profile.region == Region.NORTH_AMERICA
        assert profile.pyladies_chapter == data["pyladies_chapter"]
        assert profile.discord_username == data["discord_username"]
        assert profile.github_username == data["github_username"]
        assert profile.bluesky_username == data["bluesky_username"]
        assert profile.mastodon_url == data["mastodon_url"]
        assert profile.x_username == data["x_username"]
        assert profile.linkedin_url == data["linkedin_url"]
        assert profile.instagram_username == data["instagram_username"]
        assert profile.additional_comments == data["additional_comments"]
        assert (
            profile.availability_hours_per_week == data["availability_hours_per_week"]
        )

    def test_edit_volunteer_profile_form_submit(self, client, portal_user):
        client.force_login(portal_user)
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.region = Region.NORTH_AMERICA
        profile.discord_username = "blabla"
        profile.availability_hours_per_week = 20
        profile.save()

        data = {
            "languages_spoken": [LANGUAGES[0][0], LANGUAGES[1][0]],
            "timezone": "UTC",
            "github_username": "test-github",
            "discord_username": "testdiscord1234",
            "instagram_username": "test_instagram",
            "bluesky_username": "test.bsky.social",
            "mastodon_url": "https://mastodon.social/@test",
            "x_username": "test_x",
            "linkedin_url": "https://www.linkedin.com/in/test",
            "pyladies_chapter": "Test Chapter",
            "additional_comments": "Blablabla",
            "availability_hours_per_week": 40,
            "region": Region.ASIA,
        }
        response = client.post(
            reverse("volunteer:volunteer_profile_edit", kwargs={"pk": profile.id}),
            data=data,
        )
        assert response.status_code == 302

        profile = VolunteerProfile.objects.get(user=portal_user)
        assert profile.languages_spoken == [LANGUAGES[0][0], LANGUAGES[1][0]]
        assert profile.region == Region.ASIA
        assert profile.pyladies_chapter == data["pyladies_chapter"]
        assert profile.discord_username == data["discord_username"]
        assert profile.github_username == data["github_username"]
        assert profile.bluesky_username == data["bluesky_username"]
        assert profile.mastodon_url == data["mastodon_url"]
        assert profile.x_username == data["x_username"]
        assert profile.linkedin_url == data["linkedin_url"]
        assert profile.instagram_username == data["instagram_username"]
        assert profile.additional_comments == data["additional_comments"]
        assert (
            profile.availability_hours_per_week == data["availability_hours_per_week"]
        )

    def test_redirect_when_teams_exist(self, client, portal_user):
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.save()
        portal_user.is_superuser = True
        portal_user.save()

        team = Team(short_name="Test Team", description="Test Description")
        team.save()
        team.team_leads.add(profile)

        client.force_login(portal_user)
        response = client.get(reverse("team_detail", kwargs={"pk": team.id}))

        response_data = response.context["team"]

        assert response.status_code == 200
        assert response_data.short_name == team.short_name

    def test_redirect_when_teams_does_not_exist(self, client, portal_user):
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.save()
        portal_user.is_superuser = True
        portal_user.save()

        client.force_login(portal_user)
        response = client.get(reverse("team_detail", kwargs={"pk": 123}))

        assertRedirects(response, reverse("teams"))


@pytest.mark.django_db
class TestManageVolunteers:

    def test_manage_volunteers_view_forbidden_if_not_superuser(
        self, client, portal_user
    ):

        client.force_login(portal_user)
        response = client.get(reverse("volunteer:volunteer_profile_list"))
        assert response.status_code == 403

    def test_manage_volunteers_view_is_superuser(
        self, client, portal_user, django_user_model
    ):
        another_user = django_user_model.objects.create_user(
            username="other",
        )
        another_profile = VolunteerProfile(user=another_user)
        another_profile.languages_spoken = [LANGUAGES[0]]
        another_profile.save()

        portal_user.is_superuser = True
        portal_user.save()

        client.force_login(portal_user)
        url = reverse("volunteer:volunteer_profile_list")
        response = client.get(url)
        assert response.status_code == 200

    def test_manage_volunteers_view_is_staff(
        self, client, portal_user, django_user_model
    ):
        another_user = django_user_model.objects.create_user(
            username="other",
        )
        another_profile = VolunteerProfile(user=another_user)
        another_profile.languages_spoken = [LANGUAGES[0]]
        another_profile.save()

        portal_user.is_staff = True
        portal_user.save()

        client.force_login(portal_user)
        url = reverse("volunteer:volunteer_profile_list")
        response = client.get(url)
        assert response.status_code == 200

    def test_manage_volunteers_table(self, client, portal_user, django_user_model):
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.save()

        another_user = django_user_model.objects.create_user(
            username="other",
        )
        another_profile = VolunteerProfile(user=another_user)
        another_profile.languages_spoken = [LANGUAGES[0]]
        another_profile.save()

        team = Team(short_name="Test Team", description="Test Team Description")
        team.save()
        team.team_leads.add(another_profile)

        another_profile.teams.add(team)
        another_profile.save()

        role = Role(short_name="Test Role", description="Test Role Description")
        role.save()
        another_profile.roles.add(role)

        portal_user.is_superuser = True
        portal_user.save()

        client.force_login(portal_user)
        url = reverse("volunteer:volunteer_profile_list")
        response = client.get(url)

        assert response.status_code == 200
        assert isinstance(response.context["table"], VolunteerProfileTable)

        volunteer_table = response.context["table"]
        team_render = volunteer_table.render_teams(team, another_profile)
        assert (
            team_render == f'<span class="badge bg-secondary">{team.short_name}</span> '
        )

        role_render = volunteer_table.render_roles(role, another_profile)
        assert (
            role_render == f'<span class="badge bg-secondary">{role.short_name}</span> '
        )

        render_username_for_superuser = volunteer_table.render_username(
            portal_user, profile
        )
        assert "fa-user-secret" in render_username_for_superuser

        render_username_not_superuser = volunteer_table.render_username(
            another_user, another_profile
        )
        assert "fa-user-secret" not in render_username_not_superuser

        render_application_status = volunteer_table.render_application_status(
            ApplicationStatus.APPROVED
        )
        assert ApplicationStatus.APPROVED in render_application_status
        assert "bg-success" in render_application_status

        render_application_status = volunteer_table.render_application_status(
            ApplicationStatus.REJECTED
        )
        assert ApplicationStatus.REJECTED in render_application_status
        assert "bg-danger" in render_application_status

        render_application_status = volunteer_table.render_application_status(
            ApplicationStatus.CANCELLED
        )
        assert ApplicationStatus.CANCELLED in render_application_status
        assert "bg-secondary" in render_application_status

        render_application_status = volunteer_table.render_application_status(
            ApplicationStatus.PENDING
        )
        assert ApplicationStatus.PENDING in render_application_status
        assert "bg-warning" in render_application_status

    def test_filter_volunteers_table(self, client, portal_user, django_user_model):
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.save()

        another_user = django_user_model.objects.create_user(
            username="other",
        )
        another_profile = VolunteerProfile(user=another_user)
        another_profile.languages_spoken = [LANGUAGES[0]]
        another_profile.save()

        portal_user.is_superuser = True
        portal_user.save()

        client.force_login(portal_user)
        url = reverse("volunteer:volunteer_profile_list")
        response = client.get(url)

        assert response.status_code == 200
        assert isinstance(response.context["filter"], VolunteerProfileFilter)

        filter = response.context["filter"]
        filter_queryset = filter.qs
        search_by_name = filter.search_fulltext(filter_queryset, "", "")
        assert search_by_name.count() == 2
