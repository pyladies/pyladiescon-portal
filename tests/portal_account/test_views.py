import pytest
from allauth.account.models import EmailAddress
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from portal_account.models import PortalProfile


@pytest.mark.django_db
class TestAccountRedirects:
    """Finishing an account task returns to the account page, not the landing page."""

    def test_profile_update_redirects_to_account(self, client, portal_user):
        profile = PortalProfile.objects.create(user=portal_user)
        client.force_login(portal_user)
        response = client.post(
            reverse("portal_account:portal_profile_edit", kwargs={"pk": profile.id}),
            {"first_name": "Jane", "last_name": "Doe", "pronouns": "she/her"},
        )
        assertRedirects(response, reverse("portal_account:index"))

    def test_password_change_redirects_to_account(self, client, portal_user):
        portal_user.set_password("oldpass12345")
        portal_user.save()
        client.force_login(portal_user)
        response = client.post(
            reverse("account_change_password"),
            {
                "oldpassword": "oldpass12345",
                "password1": "newpass67890",
                "password2": "newpass67890",
            },
        )
        assertRedirects(response, reverse("portal_account:index"))

    def test_email_management_redirects_to_account(self, client, portal_user):
        EmailAddress.objects.create(
            user=portal_user, email="a@example.com", verified=True, primary=True
        )
        EmailAddress.objects.create(
            user=portal_user, email="b@example.com", verified=True, primary=False
        )
        client.force_login(portal_user)
        response = client.post(
            reverse("account_email"),
            {"action_primary": "", "email": "b@example.com"},
        )
        assertRedirects(response, reverse("portal_account:index"))


@pytest.mark.django_db
class TestAccountRail:
    """Stage E: the settings rail on the deep account pages."""

    def test_detail_page_rail_highlights_view(self, client, portal_user):
        profile = PortalProfile.objects.create(user=portal_user)
        client.force_login(portal_user)
        response = client.get(
            reverse("portal_account:portal_profile_detail", kwargs={"pk": profile.id})
        )
        assert response.status_code == 200
        assert response.context["account_active"] == "profile_view"
        content = response.content.decode()
        assert 'id="appSidebar"' in content  # rail present
        assert reverse("account_email") in content  # Account-and-security group
        assert reverse("account_change_password") in content
        assert "nav-link d-flex align-items-center active" in content  # View active

    def test_edit_page_rail_highlights_edit(self, client, portal_user):
        profile = PortalProfile.objects.create(user=portal_user)
        client.force_login(portal_user)
        response = client.get(
            reverse("portal_account:portal_profile_edit", kwargs={"pk": profile.id})
        )
        assert response.status_code == 200
        assert response.context["account_active"] == "profile_edit"
        content = response.content.decode()
        assert 'id="appSidebar"' in content
        assert (
            reverse("portal_account:portal_profile_detail", kwargs={"pk": profile.id})
            in content
        )

    def test_create_page_rail_offers_create(self, client, portal_user):
        # No profile yet -> the rail's Profile group offers "Create my profile".
        client.force_login(portal_user)
        response = client.get(reverse("portal_account:portal_profile_new"))
        assert response.status_code == 200
        assert response.context["account_active"] == "profile_new"
        content = response.content.decode()
        assert 'id="appSidebar"' in content
        assert "Create my profile" in content


# -----------------------------------------------------------------------------------
# Portal Profile Tests
# -----------------------------------------------------------------------------------


@pytest.mark.django_db
class TestPortalProfile:

    def test_portal_profile_view_requires_login(self, client):
        response = client.get(reverse("portal_account:index"))
        assertRedirects(response, reverse("account_login") + "?next=/portal_account/")

    def test_portal_profile_view_no_profile(self, client, portal_user):
        client.force_login(portal_user)
        response = client.get(reverse("portal_account:index"))
        assert response.status_code == 200
        assert response.context["profile"] is None

    def test_portal_profile_view_with_profile(self, client, portal_user):
        profile = PortalProfile(user=portal_user)
        profile.save()
        client.force_login(portal_user)
        response = client.get(reverse("portal_account:index"))
        assert response.context["profile"] == profile
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
        another_user = django_user_model.objects.create_user(username="other")
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
        another_user = django_user_model.objects.create_user(username="other")
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
