import pytest
from django.conf.global_settings import LANGUAGES
from django.urls import reverse, reverse_lazy
from pytest_django.asserts import assertRedirects

from volunteer.models import VolunteerProfile


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
        profile.timezone = "UTC"
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
        another_profile.timezone = "UTC"
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
        profile.timezone = "UTC"
        profile.save()
        client.force_login(portal_user)
        response = client.get(
            reverse("volunteer:volunteer_profile_detail", kwargs={"pk": profile.id})
        )
        assert response.status_code == 200
