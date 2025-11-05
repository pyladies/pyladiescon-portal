import pytest

from sponsorship.forms import SponsorshipProfileForm
from sponsorship.models import (
    SponsorshipProgressStatus,
    SponsorshipTier,
)


@pytest.mark.django_db
class TestSponsorshipProfileForm:
    BASE_VALID_DATA = {
        "organization_name": "Awesome Company",
        "progress_status": SponsorshipProgressStatus.AWAITING_RESPONSE.value,
    }

    @pytest.fixture
    def form_data(self, admin_user):
        return {
            "organization_name": "Awesome Company",
            "progress_status": SponsorshipProgressStatus.AWAITING_RESPONSE.value,
            "main_contact_user": admin_user,
        }

    def test_form_saves_correctly(self, form_data):

        form = SponsorshipProfileForm(data=form_data)
        assert form.is_valid()

        profile = form.save()
        assert profile.organization_name == form_data["organization_name"]
        assert profile.progress_status == form_data["progress_status"]
        assert profile.main_contact_user == form_data["main_contact_user"]

    def test_required_fields(self, form_data, admin_user, portal_user):
        """Test validation of required fields."""
        form = SponsorshipProfileForm(data={})
        assert not form.is_valid()
        assert "organization_name" in form.errors
        assert "progress_status" in form.errors
        assert "main_contact_user" in form.errors

        form = SponsorshipProfileForm(data={"organization_name": "Test Org"})
        assert not form.is_valid()
        assert "progress_status" in form.errors
        assert "main_contact_user" in form.errors
        assert "organization_name" not in form.errors

        form = SponsorshipProfileForm(
            data={"progress_status": SponsorshipProgressStatus.AWAITING_RESPONSE.value}
        )
        assert not form.is_valid()
        assert "progress_status" not in form.errors
        assert "main_contact_user" in form.errors
        assert "organization_name" in form.errors

        form = SponsorshipProfileForm(data={"main_contact_user": admin_user})
        assert not form.is_valid()
        assert "progress_status" in form.errors
        assert "main_contact_user" not in form.errors
        assert "organization_name" in form.errors

        form = SponsorshipProfileForm(
            data={
                "main_contact_user": portal_user,
                "organization_name": "Test Org",
                "progress_status": SponsorshipProgressStatus.AWAITING_RESPONSE.value,
            }
        )
        assert not form.is_valid()
        assert "progress_status" not in form.errors
        assert "main_contact_user" in form.errors  # Portal user is not admin
        assert "organization_name" not in form.errors

    def test_form_with_user(self, form_data, portal_user):
        """Test that the user is associated to the profile if exists."""
        form = SponsorshipProfileForm(data=form_data, user=portal_user)
        assert form.is_valid()
        form.save()
        assert form.instance.user == portal_user

    def test_form_without_user(self, form_data):
        """Test that the profile can be created without a user."""
        form = SponsorshipProfileForm(data=form_data)
        assert form.is_valid()
        profile = form.save()
        assert profile.user is None

    def test_fields_are_saved(self, form_data, admin_user):
        """Test that all fields are saved correctly."""

        tier = SponsorshipTier.objects.create(name="Gold", amount=5000)
        form_data.update(
            {
                "sponsor_contact_name": "John Doe",
                "sponsors_contact_email": "test2@example.com",
                "sponsorship_tier": tier.id,
                "sponsorship_override_amount": 4500,
                "po_number": "PO-12345",
                "organization_address": "123 Test St, Test City",
                "company_description": "We are a test company.",
                "progress_status": SponsorshipProgressStatus.ACCEPTED.value,
            }
        )

        form = SponsorshipProfileForm(data=form_data)
        assert form.is_valid()
        profile = form.save()

        assert profile.organization_name == form_data["organization_name"]
        assert profile.sponsor_contact_name == form_data["sponsor_contact_name"]
        assert profile.sponsors_contact_email == form_data["sponsors_contact_email"]
        assert profile.sponsorship_tier == tier
        assert (
            profile.sponsorship_override_amount
            == form_data["sponsorship_override_amount"]
        )
        assert profile.po_number == form_data["po_number"]
        assert profile.organization_address == form_data["organization_address"]
        assert profile.company_description == form_data["company_description"]
        assert profile.progress_status == form_data["progress_status"]
        assert profile.po_number == form_data["po_number"]
