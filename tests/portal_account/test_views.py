import pytest
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from portal_account.models import PortalProfile
from sponsorship.models import SponsorshipProfile

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


# -----------------------------------------------------------------------------------
# Sponsorship Profile View Tests
# -----------------------------------------------------------------------------------


@pytest.mark.django_db
class TestSponsorshipViews:

    def test_create_sponsorship_profile_get(self, client, portal_user):
        client.force_login(portal_user)
        response = client.get(reverse("sponsorship:create_sponsorship_profile"))
        assert response.status_code == 200
        assert "form" in response.context

    def test_create_sponsorship_profile_post_valid(self, client, portal_user):
        logo = SimpleUploadedFile("logo.png", b"dummydata", content_type="image/png")
        client.force_login(portal_user)
        data = {
            "main_contact_user": portal_user.id,
            "organization_name": "Test Organization",
            "sponsorship_type": "Champion",
            "company_description": "We support tech initiatives.",
        }
        file_data = {"logo": logo}

        response = client.post(
            reverse("sponsorship:create_sponsorship_profile"),
            data={**data, **file_data},
            follow=True,
        )

        assert response.status_code == 200
        assert SponsorshipProfile.objects.filter(user=portal_user).exists()
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        assert "Sponsorship profile submitted successfully!" in messages

    def test_sponsorship_profile_str_returns_org_name(self, portal_user):
        logo = SimpleUploadedFile("logo.png", b"dummydata", content_type="image/png")
        profile = SponsorshipProfile.objects.create(
            user=portal_user,
            main_contact_user=portal_user,
            organization_name="Test Org",
            sponsorship_type="Champion",
            logo=logo,
            company_description="Test description",
        )
        assert str(profile) == "Test Org"
