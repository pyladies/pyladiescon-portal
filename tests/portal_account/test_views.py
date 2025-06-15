import pytest
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from portal_account.models import PortalProfile


@pytest.mark.django_db
class TestPortalProfile:

    def test_portal_profile_view_requires_login(self, client):

        response = client.get(reverse("portal_account:index"))
        assertRedirects(response, reverse("account_login") + "?next=/portal_account/")

    def test_portal_profile_view_no_profile(self, client, portal_user):
        client.force_login(portal_user)
        response = client.get(reverse("portal_account:index"))
        assert response.status_code == 200
        assert response.context["profile_id"] is None

    def test_portal_profile_view_with_profile(self, client, portal_user):
        profile = PortalProfile(user=portal_user)
        profile.save()

        client.force_login(portal_user)
        response = client.get(reverse("portal_account:index"))

        assert response.context["profile_id"] == profile.id
        assert response.status_code == 200

    def test_portal_profile_update_own_profile(self, client, portal_user):
        profile = PortalProfile(user=portal_user)
        profile.save()
        client.force_login(portal_user)
        response = client.get(
            reverse("portal_account:portal_profile_edit", kwargs={"pk": profile.id})
        )
        assert response.status_code == 200

    def test_portal_profile_cannot_edit_other_profile(
        self, client, portal_user, django_user_model
    ):
        another_user = django_user_model.objects.create_user(
            username="other",
        )
        another_profile = PortalProfile(user=another_user)
        another_profile.save()

        client.force_login(portal_user)
        response = client.get(
            reverse(
                "portal_account:portal_profile_edit", kwargs={"pk": another_profile.id}
            )
        )
        assertRedirects(response, reverse("portal_account:index"))

    def test_portal_profile_cannot_view_other_profile(
        self, client, portal_user, django_user_model
    ):
        another_user = django_user_model.objects.create_user(
            username="other",
        )
        another_profile = PortalProfile(user=another_user)
        another_profile.save()

        client.force_login(portal_user)
        response = client.get(
            reverse(
                "portal_account:portal_profile_detail",
                kwargs={"pk": another_profile.id},
            )
        )
        assertRedirects(response, reverse("portal_account:index"))

    def test_portal_profile_view_own_profile(self, client, portal_user):
        profile = PortalProfile(user=portal_user)
        profile.save()
        client.force_login(portal_user)
        response = client.get(
            reverse("portal_account:portal_profile_detail", kwargs={"pk": profile.id})
        )
        assert response.status_code == 200

    def test_portal_profile_cannot_create_another(self, client, portal_user):
        profile = PortalProfile(user=portal_user)
        profile.save()
        client.force_login(portal_user)
        response = client.get(reverse("portal_account:portal_profile_new"))

        assertRedirects(response, reverse("portal_account:index"))

    def test_portal_profile_create_if_doesnt_exist(self, client, portal_user):
        client.force_login(portal_user)
        response = client.get(reverse("portal_account:portal_profile_new"))

        assert response.status_code == 200
