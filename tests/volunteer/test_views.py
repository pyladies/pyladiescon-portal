import pytest
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from volunteer.languages import LANGUAGES
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
        }
        response = client.post(reverse("volunteer:volunteer_profile_new"), data=data)
        assert response.status_code == 302

        profile = VolunteerProfile.objects.get(user=portal_user)
        assert profile.languages_spoken == [LANGUAGES[0][0], LANGUAGES[1][0]]
        assert profile.timezone == "UTC"
        assert profile.pyladies_chapter == data["pyladies_chapter"]
        assert profile.discord_username == data["discord_username"]
        assert profile.github_username == data["github_username"]
        assert profile.bluesky_username == data["bluesky_username"]
        assert profile.mastodon_url == data["mastodon_url"]
        assert profile.x_username == data["x_username"]
        assert profile.linkedin_url == data["linkedin_url"]
        assert profile.instagram_username == data["instagram_username"]

    def test_edit_volunteer_profile_form_submit(self, client, portal_user):
        client.force_login(portal_user)
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.timezone = "UTC+1"
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
        }
        response = client.post(
            reverse("volunteer:volunteer_profile_edit", kwargs={"pk": profile.id}),
            data=data,
        )
        assert response.status_code == 302

        profile = VolunteerProfile.objects.get(user=portal_user)
        assert profile.languages_spoken == [LANGUAGES[0][0], LANGUAGES[1][0]]
        assert profile.timezone == "UTC"
        assert profile.pyladies_chapter == data["pyladies_chapter"]
        assert profile.discord_username == data["discord_username"]
        assert profile.github_username == data["github_username"]
        assert profile.bluesky_username == data["bluesky_username"]
        assert profile.mastodon_url == data["mastodon_url"]
        assert profile.x_username == data["x_username"]
        assert profile.linkedin_url == data["linkedin_url"]
        assert profile.instagram_username == data["instagram_username"]
