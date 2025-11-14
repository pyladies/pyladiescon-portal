import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail

from sponsorship.models import (
    SponsorshipProfile,
    SponsorshipProgressStatus,
    SponsorshipTier,
)
from volunteer.constants import Region, RoleTypes
from volunteer.models import (
    Role,
    VolunteerProfile,
)


@pytest.mark.django_db
class TestSponsorshipModel:

    def test_profile_str_representation(self, admin_user):
        """Test string representation of SponsorshipProfile."""
        profile = SponsorshipProfile()
        profile.organization_name = "Very Cool Company"
        profile.main_contact_user = admin_user
        profile.progress_status = SponsorshipProgressStatus.AWAITING_RESPONSE.value
        profile.save()
        assert str(profile) == profile.organization_name

    def test_tier_str_representation(self):
        """Test string representation of SponsorshipTier."""
        tier = SponsorshipTier(
            name="Gold", amount=3000.00, description="Test Description"
        )
        tier.save()
        assert str(tier) == f"{tier.name} (${tier.amount:.2f})"

    def test_donation_str_representation(self):
        """Test string representation of IndividualDonation."""
        from sponsorship.models import IndividualDonation

        donation = IndividualDonation(transaction_id="TX12345", donation_amount=150.00)
        donation.save()
        assert (
            str(donation)
            == f"{donation.transaction_id}: ${donation.donation_amount:.2f}"
        )

    def test_tier_relationships(self, admin_user):
        """Test tier relationships with sponsorship."""
        tier = SponsorshipTier.objects.create(
            name="Gold", amount=3000.00, description="Test Description"
        )
        profile = SponsorshipProfile()
        profile.organization_name = "Very Cool Company"
        profile.main_contact_user = admin_user
        profile.progress_status = SponsorshipProgressStatus.AWAITING_RESPONSE.value
        profile.sponsorship_tier = tier
        profile.save()

        assert profile.sponsorship_tier == tier

    def test_email_is_sent_after_saved(self, admin_user):
        # set up an admin account to receive internal notification email
        admin_role = Role.objects.create(
            short_name=RoleTypes.ADMIN, description="Admin role"
        )
        admin_user_to_notify = User.objects.create_superuser(
            username="testadmin",
            email="test-admin@example.com",
            password="pyladiesadmin123",
        )
        admin_profile = VolunteerProfile(user=admin_user_to_notify)
        admin_profile.region = Region.NORTH_AMERICA
        admin_profile.save()

        User.objects.create_superuser(
            username="testsuperuser",
            email="superusertest@example.com",
            password="supersuper123",
        )

        admin_profile.roles.add(admin_role)
        admin_profile.save()

        mail.outbox.clear()

        # the actual process to test
        profile = SponsorshipProfile(
            main_contact_user=admin_user,
            organization_name="Test Org",
            progress_status=SponsorshipProgressStatus.AWAITING_RESPONSE.value,
        )

        profile.save()

        # 3 emails were sent:
        assert len(mail.outbox) == 3  # emails sent to 3 different admins
        for email in mail.outbox:
            assert (  # user creation, to internal staff
                str(email.subject)
                == f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} New Sponsorship Tracking: {profile.organization_name}"
            )

    def test_no_email_if_no_admin_user(self, portal_user):

        mail.outbox.clear()

        # the actual process to test
        profile = SponsorshipProfile(
            main_contact_user=portal_user,
            organization_name="Test Org",
            progress_status=SponsorshipProgressStatus.AWAITING_RESPONSE.value,
        )

        profile.save()

        # 3 emails were sent:
        assert len(mail.outbox) == 0  # emails sent to 3 different admins

    def test_email_is_sent_after_updated(self, admin_user):
        profile = SponsorshipProfile(
            main_contact_user=admin_user,
            organization_name="Test Org",
            progress_status=SponsorshipProgressStatus.AWAITING_RESPONSE.value,
        )
        profile.save()
        mail.outbox.clear()

        profile.progress_status = SponsorshipProgressStatus.INVOICED.value
        profile.save()
        assert (
            str(mail.outbox[0].subject)
            == f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Update in Sponsorship Tracking for {profile.organization_name}"
        )

    def test_sponsorship_notification_email_contains_info(self, admin_user):
        admin_user_to_notify = User.objects.create_superuser(
            username="testadmin",
            email="test-admin@example.com",
            password="pyladiesadmin123",
        )
        admin_profile = VolunteerProfile(user=admin_user_to_notify)
        admin_profile.region = Region.NORTH_AMERICA
        admin_profile.save()

        tier = SponsorshipTier.objects.create(
            name="Gold", amount=5000.00, description="Gold Tier"
        )

        profile = SponsorshipProfile(user=admin_user)
        profile.progress_status = SponsorshipProgressStatus.INVOICED
        profile.sponsorship_tier = tier
        profile.organization_name = "Test Org"
        profile.sponsor_contact_name = "John Doe"
        profile.sponsors_contact_email = "test@example.com"
        profile.company_description = "We are a test company."
        profile.organization_address = "123 Test St, Test City"
        profile.sponsorship_override_amount = 4500
        mail.outbox.clear()

        profile.save()

        body = str(mail.outbox[0].body)
        assert profile.progress_status.label in body
        assert profile.sponsorship_tier.name in body
        assert profile.organization_name in body
        assert profile.sponsor_contact_name in body
        assert profile.sponsors_contact_email in body
        assert profile.company_description in body
        assert profile.organization_address in body
        assert str(profile.sponsorship_override_amount) in body

    def test_po_number_field_is_saved(self, admin_user):
        """Test that the PO Number field is saved correctly."""
        tier = SponsorshipTier.objects.create(
            name="Gold", amount=3000.00, description="Test Description"
        )
        profile = SponsorshipProfile(
            main_contact_user=admin_user,
            organization_name="Test Company",
            progress_status=SponsorshipProgressStatus.AWAITING_RESPONSE.value,
            sponsorship_tier=tier,
            po_number="PO-2024-12345",
        )
        profile.save()

        # Retrieve the profile from the database to verify it was saved
        saved_profile = SponsorshipProfile.objects.get(id=profile.id)
        assert saved_profile.po_number == "PO-2024-12345"

    def test_po_number_field_can_be_empty(self, admin_user):
        """Test that the PO Number field can be left empty (optional)."""
        tier = SponsorshipTier.objects.create(
            name="Silver", amount=2000.00, description="Test Description"
        )
        profile = SponsorshipProfile(
            main_contact_user=admin_user,
            organization_name="Test Company Without PO",
            progress_status=SponsorshipProgressStatus.AWAITING_RESPONSE.value,
            sponsorship_tier=tier,
            po_number=None,
        )
        profile.save()

        # Retrieve the profile from the database to verify it was saved
        saved_profile = SponsorshipProfile.objects.get(id=profile.id)
        assert saved_profile.po_number is None
