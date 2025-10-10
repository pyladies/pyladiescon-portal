import pytest
from django.contrib.messages import get_messages
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
        assert response.context["profile"] is None

    def test_volunteer_profile_view_with_profile(self, client, portal_user):
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.save()

        client.force_login(portal_user)
        response = client.get(reverse("volunteer:index"))

        assert response.context["profile"] == profile
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

    def test_volunteer_profile_edit_nonexistent_profile(self, client, portal_user):
        client.force_login(portal_user)
        response = client.get(
            reverse("volunteer:volunteer_profile_edit", kwargs={"pk": 99999})
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

    def test_volunteer_profile_view_nonexistent_profile(self, client, portal_user):
        client.force_login(portal_user)
        response = client.get(
            reverse("volunteer:volunteer_profile_detail", kwargs={"pk": 99999})
        )
        assertRedirects(response, reverse("volunteer:index"))

    def test_volunteer_profile_view_staff_can_view_other_profile(
        self, client, portal_user, django_user_model
    ):
        another_user = django_user_model.objects.create_user(
            username="other",
        )
        another_profile = VolunteerProfile(user=another_user)
        another_profile.languages_spoken = [LANGUAGES[0]]
        another_profile.region = Region.NORTH_AMERICA
        another_profile.save()

        # Make portal_user staff
        portal_user.is_staff = True
        portal_user.save()

        client.force_login(portal_user)
        response = client.get(
            reverse(
                "volunteer:volunteer_profile_detail", kwargs={"pk": another_profile.id}
            )
        )
        assert response.status_code == 200
        profile_result = response.context["volunteerprofile"]
        assert profile_result == another_profile

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
        expected_team_url = reverse("team_detail", kwargs={"pk": team.pk})
        expected_team_render = f'<a href="{expected_team_url}" class="badge bg-secondary">{team.short_name}</a> '
        assert team_render == expected_team_render

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

        another_profile.application_status = ApplicationStatus.PENDING
        another_profile.save()
        action_button = volunteer_table.render_actions("", another_profile)
        assert "btn-primary" in action_button
        assert "Review" in action_button

        another_profile.application_status = ApplicationStatus.APPROVED
        another_profile.save()
        action_button = volunteer_table.render_actions("", another_profile)
        assert "btn-info" in action_button
        assert "Manage" in action_button

    def test_render_teams_with_multiple_teams(
        self, client, portal_user, django_user_model
    ):
        """Test that multiple teams are rendered correctly with links."""
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.save()

        another_user = django_user_model.objects.create_user(
            username="other",
        )
        another_profile = VolunteerProfile(user=another_user)
        another_profile.languages_spoken = [LANGUAGES[0]]
        another_profile.save()

        # Create multiple teams
        team1 = Team(short_name="Team 1", description="First Team")
        team1.save()
        team2 = Team(short_name="Team 2", description="Second Team")
        team2.save()

        # Add both teams to profile
        another_profile.teams.add(team1, team2)
        another_profile.save()

        portal_user.is_superuser = True
        portal_user.save()

        client.force_login(portal_user)
        url = reverse("volunteer:volunteer_profile_list")
        response = client.get(url)

        volunteer_table = response.context["table"]
        team_render = volunteer_table.render_teams(None, another_profile)

        # Check that both teams are rendered with links
        team1_url = reverse("team_detail", kwargs={"pk": team1.pk})
        team2_url = reverse("team_detail", kwargs={"pk": team2.pk})

        assert (
            f'<a href="{team1_url}" class="badge bg-secondary">Team 1</a>'
            in team_render
        )
        assert (
            f'<a href="{team2_url}" class="badge bg-secondary">Team 2</a>'
            in team_render
        )

    def test_render_teams_with_no_teams(self, client, portal_user):
        """Test that profiles with no teams render empty string."""
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.save()

        portal_user.is_superuser = True
        portal_user.save()

        client.force_login(portal_user)
        url = reverse("volunteer:volunteer_profile_list")
        response = client.get(url)

        volunteer_table = response.context["table"]
        team_render = volunteer_table.render_teams(None, profile)

        # Should return empty string when no teams
        assert team_render == ""

    def test_team_badge_links_are_clickable(self, client, portal_user):
        """Test that team badges contain proper href attributes."""
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.save()

        team = Team(short_name="Test Team", description="Test Description")
        team.save()
        profile.teams.add(team)
        profile.save()

        portal_user.is_superuser = True
        portal_user.save()

        client.force_login(portal_user)
        url = reverse("volunteer:volunteer_profile_list")
        response = client.get(url)

        volunteer_table = response.context["table"]
        team_render = volunteer_table.render_teams(None, profile)

        # Check that the rendered HTML contains href attribute
        assert reverse("teams") in team_render
        assert reverse("team_detail", kwargs={"pk": team.pk}) in team_render
        assert "badge bg-secondary" in team_render

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

        # Test search with actual search term
        search_with_term = filter.search_fulltext(
            filter_queryset, "", portal_user.username
        )
        assert search_with_term.count() == 1

        qs = filter.filter_languages_spoken(filter_queryset, "", LANGUAGES[1])
        assert qs.count() == 0  # no matching languages

        qs = filter.filter_languages_spoken(filter_queryset, "", LANGUAGES[0])
        assert qs.count() == 2  # both profiles match the language


@pytest.mark.django_db
class TestManageVolunteerApplications:

    def test_review_volunteers_view_forbidden_if_not_superuser(
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
                "volunteer:volunteer_profile_manage", kwargs={"pk": another_profile.id}
            )
        )
        assert response.status_code == 403

    def test_review_volunteers_view_is_superuser(
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
        response = client.get(
            reverse(
                "volunteer:volunteer_profile_manage", kwargs={"pk": another_profile.id}
            )
        )
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
        response = client.get(
            reverse(
                "volunteer:volunteer_profile_manage", kwargs={"pk": another_profile.id}
            )
        )
        assert response.status_code == 200

    def test_approve_volunteer_profile_valid_data(
        self, client, portal_user, django_user_model
    ):
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

        team = Team(short_name="Test Team", description="Test Description")
        team.save()
        team.team_leads.add(profile)

        role = Role(short_name="Test Role", description="Test Role Description")
        role.save()
        another_profile.roles.add(role)

        client.force_login(portal_user)
        response = client.post(
            reverse(
                "volunteer:volunteer_profile_manage", kwargs={"pk": another_profile.id}
            ),
            data={"teams": [team.id], "roles": [role.id]},
        )

        assert response.status_code == 302
        another_profile.refresh_from_db()
        assert another_profile.application_status == ApplicationStatus.APPROVED

        assert another_profile.teams.count() == 1
        assert another_profile.teams.first().short_name == team.short_name

        assert another_profile.roles.count() == 1
        assert another_profile.roles.first().short_name == role.short_name

    def test_approve_volunteer_profile_data_not_valid(
        self, client, portal_user, django_user_model
    ):
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

        # no such team or role
        response = client.post(
            reverse(
                "volunteer:volunteer_profile_manage", kwargs={"pk": another_profile.id}
            ),
            data={"teams": [111]},
        )

        # stays in the same page because of errors
        assert response.status_code == 200
        another_profile.refresh_from_db()

        # application status remains pending and no teams or roles are assigned
        assert another_profile.application_status == ApplicationStatus.PENDING
        assert another_profile.teams.count() == 0
        assert another_profile.roles.count() == 0

    def test_resend_onboarding_email_if_approved(
        self, client, portal_user, django_user_model
    ):
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.save()

        another_user = django_user_model.objects.create_user(
            username="other",
        )
        another_profile = VolunteerProfile(user=another_user)
        another_profile.languages_spoken = [LANGUAGES[0]]
        another_profile.application_status = ApplicationStatus.APPROVED
        another_profile.save()

        portal_user.is_superuser = True
        portal_user.save()

        client.force_login(portal_user)
        response = client.post(
            reverse(
                "volunteer:resend_onboarding_email", kwargs={"pk": another_profile.id}
            ),
        )

        # redirected to the manage volunteer page because it was successful
        messages = list(get_messages(response.wsgi_request))
        assert len(messages) == 1
        assert "Onboarding email was sent successfully." in messages[0].message

    @pytest.mark.parametrize(
        "application_status",
        [
            ApplicationStatus.CANCELLED,
            ApplicationStatus.REJECTED,
            ApplicationStatus.PENDING,
        ],
    )
    def test_resend_onboarding_email_not_sent_if_not_approved(
        self, client, portal_user, django_user_model, application_status
    ):
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.save()

        another_user = django_user_model.objects.create_user(
            username="other",
        )
        another_profile = VolunteerProfile(user=another_user)
        another_profile.languages_spoken = [LANGUAGES[0]]
        another_profile.application_status = application_status
        another_profile.save()

        portal_user.is_superuser = True
        portal_user.save()

        client.force_login(portal_user)
        response = client.post(
            reverse(
                "volunteer:resend_onboarding_email", kwargs={"pk": another_profile.id}
            ),
        )
        messages = list(get_messages(response.wsgi_request))
        assert len(messages) == 1
        assert (
            "Onboarding email can only be sent to approved volunteers."
            in messages[0].message
        )

    def test_resend_onboarding_email_not_sent_if_no_such_object(
        self, client, portal_user
    ):

        portal_user.is_superuser = True
        portal_user.save()

        client.force_login(portal_user)

        response = client.post(
            reverse("volunteer:resend_onboarding_email", kwargs={"pk": 123456}),
        )
        messages = list(get_messages(response.wsgi_request))
        assert len(messages) == 1
        assert "Volunteer profile not found." in messages[0].message


@pytest.mark.django_db
class TestCancelVolunteering:

    def test_cancel_volunteering_by_volunteer_themselves(
        self, client, portal_user, django_user_model
    ):
        """Test that volunteers can cancel their own application."""
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.application_status = ApplicationStatus.APPROVED
        profile.save()

        # Create a team and add volunteer to it
        team = Team(short_name="Test Team", description="Test Description")
        team.save()
        profile.teams.add(team)

        client.force_login(portal_user)
        response = client.post(
            reverse("volunteer:cancel_volunteering", kwargs={"pk": profile.id})
        )

        # Check redirect
        assertRedirects(response, reverse("volunteer:index"))

        # Check profile was updated
        profile.refresh_from_db()
        assert profile.application_status == ApplicationStatus.CANCELLED
        assert profile.teams.count() == 0

        # Check success message
        messages = list(get_messages(response.wsgi_request))
        assert len(messages) == 1
        assert (
            "Your volunteer application has been cancelled successfully."
            in messages[0].message
        )

    def test_cancel_volunteering_by_staff(self, client, portal_user, django_user_model):
        """Test that staff can cancel volunteer applications."""
        volunteer_user = django_user_model.objects.create_user(username="volunteer")
        profile = VolunteerProfile(user=volunteer_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.application_status = ApplicationStatus.APPROVED
        profile.save()

        # Create a team and add volunteer to it
        team = Team(short_name="Test Team", description="Test Description")
        team.save()
        profile.teams.add(team)

        # Make portal_user staff
        portal_user.is_staff = True
        portal_user.save()

        client.force_login(portal_user)
        response = client.post(
            reverse("volunteer:cancel_volunteering", kwargs={"pk": profile.id})
        )

        # Check redirect
        assertRedirects(response, reverse("volunteer:volunteer_profile_list"))

        # Check profile was updated
        profile.refresh_from_db()
        assert profile.application_status == ApplicationStatus.CANCELLED
        assert profile.teams.count() == 0

    def test_cancel_volunteering_permission_denied(
        self, client, portal_user, django_user_model
    ):
        """Test that users cannot cancel other users' applications without permission."""
        volunteer_user = django_user_model.objects.create_user(username="volunteer")
        profile = VolunteerProfile(user=volunteer_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.application_status = ApplicationStatus.APPROVED
        profile.save()

        client.force_login(portal_user)
        response = client.post(
            reverse("volunteer:cancel_volunteering", kwargs={"pk": profile.id})
        )

        # Check redirect to index with error
        assertRedirects(response, reverse("volunteer:index"))

        # Check profile was NOT updated
        profile.refresh_from_db()
        assert profile.application_status == ApplicationStatus.APPROVED

        # Check error message
        messages = list(get_messages(response.wsgi_request))
        assert len(messages) == 1
        assert (
            "You don't have permission to cancel this volunteer application."
            in messages[0].message
        )

    def test_cancel_already_cancelled_application(self, client, portal_user):
        """Test that cancelling an already cancelled application shows warning."""
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.application_status = ApplicationStatus.CANCELLED
        profile.save()

        client.force_login(portal_user)
        response = client.post(
            reverse("volunteer:cancel_volunteering", kwargs={"pk": profile.id})
        )

        # Check redirect
        assertRedirects(
            response,
            reverse("volunteer:volunteer_profile_detail", kwargs={"pk": profile.id}),
        )

        # Check warning message
        messages = list(get_messages(response.wsgi_request))
        assert len(messages) == 1
        assert "This volunteer application is already cancelled." in messages[0].message

    def test_cancel_volunteering_nonexistent_profile(self, client, portal_user):
        """Test cancelling a non-existent profile returns error."""
        client.force_login(portal_user)
        response = client.post(
            reverse("volunteer:cancel_volunteering", kwargs={"pk": 99999})
        )

        # Check redirect to index with error
        assertRedirects(response, reverse("volunteer:index"))

        # Check error message
        messages = list(get_messages(response.wsgi_request))
        assert len(messages) == 1
        assert "Volunteer profile not found." in messages[0].message

    def test_cancel_volunteering_with_team_leads(
        self, client, portal_user, django_user_model
    ):
        """Test that cancelling volunteering sends notifications to team leads."""
        # Create volunteer
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.application_status = ApplicationStatus.APPROVED
        profile.save()

        # Create team lead
        team_lead_user = django_user_model.objects.create_user(
            username="teamlead", email="teamlead@example.com"
        )
        team_lead_profile = VolunteerProfile(user=team_lead_user)
        team_lead_profile.languages_spoken = [LANGUAGES[0]]
        team_lead_profile.save()

        # Create team with lead
        team = Team(short_name="Test Team", description="Test Description")
        team.save()
        team.team_leads.add(team_lead_profile)
        profile.teams.add(team)

        client.force_login(portal_user)
        client.post(reverse("volunteer:cancel_volunteering", kwargs={"pk": profile.id}))

        # Check that the cancellation was successful
        profile.refresh_from_db()
        assert profile.application_status == ApplicationStatus.CANCELLED
        assert profile.teams.count() == 0

    def test_volunteer_list_excludes_cancelled(
        self, client, portal_user, django_user_model
    ):
        """Test that cancelled applications are excluded from the volunteer list."""
        # Create profiles with different statuses
        approved_user = django_user_model.objects.create_user(username="approved")
        approved_profile = VolunteerProfile(user=approved_user)
        approved_profile.languages_spoken = [LANGUAGES[0]]
        approved_profile.application_status = ApplicationStatus.APPROVED
        approved_profile.save()

        cancelled_user = django_user_model.objects.create_user(username="cancelled")
        cancelled_profile = VolunteerProfile(user=cancelled_user)
        cancelled_profile.languages_spoken = [LANGUAGES[0]]
        cancelled_profile.application_status = ApplicationStatus.CANCELLED
        cancelled_profile.save()

        pending_user = django_user_model.objects.create_user(username="pending")
        pending_profile = VolunteerProfile(user=pending_user)
        pending_profile.languages_spoken = [LANGUAGES[0]]
        pending_profile.application_status = ApplicationStatus.PENDING
        pending_profile.save()

        # Make portal_user staff to access the list
        portal_user.is_staff = True
        portal_user.save()

        client.force_login(portal_user)
        response = client.get(reverse("volunteer:volunteer_profile_list"))

        assert response.status_code == 200

        # Get the queryset from the table
        table = response.context["table"]
        profiles_in_table = [item for item in table.data]

        # Check that cancelled profile is not in the list
        profile_ids = [profile.id for profile in profiles_in_table]
        assert approved_profile.id in profile_ids
        assert pending_profile.id in profile_ids
        assert cancelled_profile.id not in profile_ids

    def test_cancel_volunteering_generic_exception(
        self, client, portal_user, monkeypatch
    ):
        """Test the generic exception handler in cancel volunteering."""
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.application_status = ApplicationStatus.APPROVED
        profile.save()

        # Mock the save method to raise an exception
        def mock_save(*args, **kwargs):
            raise Exception("Database error")

        monkeypatch.setattr(VolunteerProfile, "save", mock_save)

        client.force_login(portal_user)
        response = client.post(
            reverse("volunteer:cancel_volunteering", kwargs={"pk": profile.id})
        )

        # Should redirect to profile detail page on exception
        assertRedirects(
            response,
            reverse("volunteer:volunteer_profile_detail", kwargs={"pk": profile.id}),
        )

        # Check error message
        messages = list(get_messages(response.wsgi_request))
        assert len(messages) == 1
        assert "An error occurred while cancelling:" in messages[0].message

    def test_volunteer_table_render_actions_approved_branch(
        self, portal_user, django_user_model
    ):
        """Test the render_actions method specifically for APPROVED status to ensure branch coverage."""
        import uuid

        from volunteer.views import VolunteerProfileTable

        # Create a profile with APPROVED status
        another_user = django_user_model.objects.create_user(
            username=f"testuser_{uuid.uuid4().hex[:8]}"
        )
        profile = VolunteerProfile(user=another_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.application_status = ApplicationStatus.APPROVED
        profile.save()

        # Ensure we're testing the right status
        assert profile.application_status == ApplicationStatus.APPROVED

        # Create table instance and call render_actions directly
        table = VolunteerProfileTable([])
        result = table.render_actions("", profile)

        # Verify the APPROVED branch was executed and we get expected result
        assert result is not None
        assert "btn-info" in result
        assert "Manage" in result
        assert "volunteer_profile_manage" in result

    def test_volunteer_table_render_actions_edge_cases(
        self, portal_user, django_user_model
    ):
        """Test render_actions with different application statuses to ensure full branch coverage."""
        import uuid

        from volunteer.views import VolunteerProfileTable

        table = VolunteerProfileTable([])

        # Test with REJECTED status (should return empty string)
        user1 = django_user_model.objects.create_user(
            username=f"user_rejected_{uuid.uuid4().hex[:8]}"
        )
        profile1 = VolunteerProfile(user=user1)
        profile1.languages_spoken = [LANGUAGES[0]]
        profile1.application_status = ApplicationStatus.REJECTED
        profile1.save()

        result1 = table.render_actions("", profile1)
        assert result1 == ""

        # Test with CANCELLED status (should return empty string)
        user2 = django_user_model.objects.create_user(
            username=f"user_cancelled_{uuid.uuid4().hex[:8]}"
        )
        profile2 = VolunteerProfile(user=user2)
        profile2.languages_spoken = [LANGUAGES[0]]
        profile2.application_status = ApplicationStatus.CANCELLED
        profile2.save()

        result2 = table.render_actions("", profile2)
        assert result2 == ""
