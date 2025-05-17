import pytest
from django.test import RequestFactory
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from portal_account.models import PortalProfile
from portal_account.views import index


@pytest.mark.django_db
class TestPortalProfile:
    def test_portal_profile_view_requires_login(self, client):
        response = client.get(reverse("portal_account:index"))
        assertRedirects(response, reverse("account_login") + "?next=/portal_account/")

    def test_index_view_with_profile(self, client, portal_user):
        """Test index view when user has a profile"""
        profile = PortalProfile.objects.create(user=portal_user, tos_agreement=True)
        client.force_login(portal_user)

        response = client.get(reverse("portal_account:index"))

        assert response.status_code == 200
        assert response.context["profile_id"] == profile.id

    def test_index_view_no_profile_direct(self, portal_user):
        """Test index view directly (bypassing middleware) when user has no profile"""
        request = RequestFactory().get(reverse("portal_account:index"))
        request.user = portal_user

        PortalProfile.objects.filter(user=portal_user).delete()

        response = index(request)

        assert response.status_code == 200
        assert b"profile_id" not in response.content

    def test_index_view_no_profile_with_middleware(self, client, portal_user):
        """Test index view with middleware when user has no profile"""
        client.force_login(portal_user)
        PortalProfile.objects.filter(user=portal_user).delete()

        response = client.get(reverse("portal_account:index"), follow=True)

        assertRedirects(response, reverse("portal_account:portal_profile_new"))
        assert len(response.redirect_chain) == 1
        assert response.redirect_chain[0][0].endswith(
            reverse("portal_account:portal_profile_new")
        )

    def test_portal_profile_create_if_doesnt_exist(self, client, portal_user):
        client.force_login(portal_user)
        response = client.get(reverse("portal_account:portal_profile_new"))
        assert response.status_code == 200

    def test_portal_profile_cannot_create_another(self, client, portal_user):
        PortalProfile.objects.create(user=portal_user, tos_agreement=True)
        client.force_login(portal_user)
        response = client.get(reverse("portal_account:portal_profile_new"))
        assertRedirects(response, reverse("portal_account:index"))

    def test_portal_profile_view_own_profile(self, client, portal_user):
        profile = PortalProfile.objects.create(user=portal_user, tos_agreement=True)
        client.force_login(portal_user)
        response = client.get(
            reverse("portal_account:portal_profile_detail", kwargs={"pk": profile.id})
        )
        assert response.status_code == 200

    def test_portal_profile_cannot_view_other_profile(
        self, client, portal_user, django_user_model
    ):
        other_user = django_user_model.objects.create_user(username="other")
        other_profile = PortalProfile.objects.create(
            user=other_user, tos_agreement=True
        )
        PortalProfile.objects.create(user=portal_user, tos_agreement=True)

        client.force_login(portal_user)
        response = client.get(
            reverse(
                "portal_account:portal_profile_detail", kwargs={"pk": other_profile.id}
            )
        )
        assertRedirects(response, reverse("portal_account:index"))

    def test_portal_profile_update_own_profile(self, client, portal_user):
        profile = PortalProfile.objects.create(user=portal_user, tos_agreement=True)
        client.force_login(portal_user)
        response = client.get(
            reverse("portal_account:portal_profile_edit", kwargs={"pk": profile.id})
        )
        assert response.status_code == 200

    def test_portal_profile_update_redirects_for_other_user(
        self, client, portal_user, django_user_model
    ):
        other_user = django_user_model.objects.create_user(username="intruder")
        other_profile = PortalProfile.objects.create(
            user=other_user, tos_agreement=True
        )
        PortalProfile.objects.create(user=portal_user, tos_agreement=True)

        client.force_login(portal_user)
        response = client.get(
            reverse(
                "portal_account:portal_profile_edit", kwargs={"pk": other_profile.id}
            )
        )
        assertRedirects(response, reverse("portal_account:index"))

    def test_get_form_kwargs_create(self, client, portal_user):
        """Test that form kwargs include user in create view"""
        client.force_login(portal_user)
        response = client.get(reverse("portal_account:portal_profile_new"))
        view = response.context_data["view"]
        form_kwargs = view.get_form_kwargs()
        assert "user" in form_kwargs
        assert form_kwargs["user"] == portal_user

    def test_get_form_kwargs_update(self, client, portal_user):
        """Test that form kwargs include user in update view"""
        profile = PortalProfile.objects.create(user=portal_user, tos_agreement=True)
        client.force_login(portal_user)
        response = client.get(
            reverse("portal_account:portal_profile_edit", kwargs={"pk": profile.id})
        )
        view = response.context_data["view"]
        form_kwargs = view.get_form_kwargs()
        assert "user" in form_kwargs
        assert form_kwargs["user"] == portal_user

    def test_tos_redirect_middleware(self, client, portal_user):
        profile = PortalProfile.objects.create(user=portal_user, tos_agreement=False)
        client.force_login(portal_user)
        response = client.get(reverse("portal_account:index"), follow=True)
        assertRedirects(
            response,
            reverse("portal_account:portal_profile_edit", kwargs={"pk": profile.id}),
        )

    def test_tos_middleware_excluded_paths(self, client, portal_user):
        """Test that middleware doesn't redirect for excluded paths"""
        profile = PortalProfile.objects.create(user=portal_user, tos_agreement=False)
        client.force_login(portal_user)

        excluded_paths = [
            "/accounts/login/",
            "/portal_account/profile/new",
            f"/portal_account/profile/edit/{profile.id}/",
            f"/portal_account/profile/view/{profile.id}/",
        ]

        for path in excluded_paths:
            response = client.get(path)
            assert not (
                response.status_code == 302
                and "/portal_account/profile/edit/" in response.url
            )

        admin_response = client.get("/admin/")
        assert admin_response.status_code == 302
        assert "/admin/login/" in admin_response.url

    def test_tos_middleware_with_agreement(self, client, portal_user):
        """Test middleware doesn't redirect when TOS is agreed"""
        PortalProfile.objects.create(user=portal_user, tos_agreement=True)
        client.force_login(portal_user)
        response = client.get("/some-path/")
        assert response.status_code == 404

    def test_tos_middleware_unauthenticated_user(self, client):
        """Test middleware skips check for unauthenticated users"""
        response = client.get("/any-path/")
        assert response.status_code == 404

    def test_tos_middleware_no_profile(self, client, portal_user):
        """Test middleware redirects to profile creation when no profile exists"""
        client.force_login(portal_user)
        response = client.get("/any-path/", follow=True)
        assertRedirects(response, reverse("portal_account:portal_profile_new"))
