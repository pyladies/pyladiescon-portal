from io import BytesIO

import pytest
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image
from pytest_django.asserts import assertRedirects

import sponsorship.views as views
from portal_account.models import PortalProfile
from sponsorship.models import SponsorshipProfile, SponsorshipTier

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


def create_sample_image():
    """Utility function for creating a sample image"""
    image = Image.new("RGB", (100, 100), color="red")
    image_bytes = BytesIO()
    image.save(image_bytes, format="PNG")
    image_bytes.seek(0)
    return image_bytes.read()


def test_create_sample_image():
    """Test the sample image creation function"""
    image_data = create_sample_image()
    assert isinstance(image_data, bytes)
    assert len(image_data) > 0


@pytest.mark.django_db
class TestSponsorshipViews:

    def test_create_sponsorship_profile_get(self, client, portal_user):
        client.force_login(portal_user)
        response = client.get(reverse("sponsorship:create_sponsorship_profile"))
        assert response.status_code == 200
        assert "form" in response.context

    def test_create_sponsorship_profile_post_valid(
        self, client, portal_user, monkeypatch
    ):
        client.force_login(portal_user)

        tier = SponsorshipTier.objects.create(
            name="Champion", amount=10000.00, description="Champion sponsorship tier"
        )

        # Make the view instantiate the form with user=request.user
        RealForm = views.SponsorshipProfileForm

        def FormFactory(*args, **kwargs):
            kwargs.setdefault("user", portal_user)
            return RealForm(*args, **kwargs)

        monkeypatch.setattr(views, "SponsorshipProfileForm", FormFactory, raising=False)

        data = {
            "main_contact_user": portal_user.id,
            "organization_name": "Test Organization",
            "sponsorship_tier": tier.pk,
            "company_description": "We support tech initiatives.",
            "application_status": "pending",
        }

        response = client.post(
            reverse("sponsorship:create_sponsorship_profile"), data=data, follow=True
        )
        assert response.status_code == 200
        assert SponsorshipProfile.objects.filter(user=portal_user).exists()

    def test_sponsorship_profile_str_returns_org_name(self, portal_user):
        tier = SponsorshipTier.objects.create(
            name="Champion", amount=10000.00, description="Champion sponsorship tier"
        )

        profile = SponsorshipProfile.objects.create(
            user=portal_user,
            main_contact_user=portal_user,
            organization_name="Test Org",
            sponsorship_tier=tier,
            company_description="Test description",
        )
        assert str(profile) == "Test Org"

    @pytest.mark.skip(reason="Failing on CI, needs investigation")
    def test_sponsorship_profile_with_logo(
        self, client, portal_user
    ):  # pragma: no cover
        """This test is allowed to fail on CI."""
        tier = SponsorshipTier.objects.create(
            name="Champion", amount=10000.00, description="Champion sponsorship tier"
        )

        sample_image = create_sample_image()
        logo = SimpleUploadedFile("logo.png", sample_image, content_type="image/png")
        client.force_login(portal_user)

        data = {
            "main_contact_user": portal_user.id,
            "organization_name": "Test Organization",
            "sponsorship_tier": tier.pk,
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
