import pytest
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from portal_account.models import PortalProfile


@pytest.mark.django_db
class TestPortalIndex:

    def test_index_unauthenticated(self, client):

        response = client.get(reverse("index"))
        assert response.status_code == 200
        assert "Sign up" in response.content.decode()
        assert "Login" in response.content.decode()

    def test_index_authenticated_no_profile_created(self, client, portal_user):

        client.force_login(portal_user)
        response = client.get(reverse("index"), follow=True)

        assert "Sign out" not in response.content.decode()
        assert "Login" not in response.content.decode()
        assertRedirects(response, reverse("portal_account:portal_profile_new"))

    def test_index_authenticated_profile_already_created(self, client, portal_user):

        portal_profile = PortalProfile(user=portal_user)
        portal_profile.save()

        client.force_login(portal_user)
        response = client.get(reverse("index"))
        assert response.status_code == 200
        assert "Sign out" not in response.content.decode()
        assert "Login" not in response.content.decode()

    def test_index_authenticated_with_volunteer_profile_and_teams(
        self, client, portal_user, django_assert_num_queries
    ):
        from django.contrib.auth import get_user_model

        from volunteer.models import Team, VolunteerProfile

        # Create volunteer profile and team
        portal_profile = PortalProfile(user=portal_user)
        portal_profile.save()
        volunteer_profile = VolunteerProfile.objects.create(
            user=portal_user, languages_spoken=["en"]
        )
        team = Team.objects.create(short_name="Test Team")
        volunteer_profile.teams.add(team)

        client.force_login(portal_user)
        response = client.get(reverse("index"))
        assert response.status_code == 200
        assert "Test Team" in response.content.decode()

    def test_index_authenticated_with_volunteer_profile_no_teams(
        self, client, portal_user
    ):
        from volunteer.models import VolunteerProfile

        portal_profile = PortalProfile(user=portal_user)
        portal_profile.save()
        volunteer_profile = VolunteerProfile.objects.create(
            user=portal_user, languages_spoken=["en"]
        )
        # No teams added
        client.force_login(portal_user)
        response = client.get(reverse("index"))
        assert response.status_code == 200
        assert "Test Team" not in response.content.decode()
