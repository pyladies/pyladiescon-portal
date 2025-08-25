import pytest
from django.urls import reverse

from portal_account.models import PortalProfile
from sponsorship.models import SponsorshipProfile


@pytest.mark.django_db
class TestPortalProfileModel:

    def test_profile_url(self, portal_user):
        profile = PortalProfile(user=portal_user)
        profile.save()

        assert profile.get_absolute_url() == reverse(
            "portal_account:portal_profile_edit", kwargs={"pk": profile.pk}
        )

    def test_profile_str_representation(self, portal_user):
        profile = PortalProfile(user=portal_user)

        assert str(profile) == portal_user.username


@pytest.mark.django_db
class TestSponsorshipProfileModel:

    def test_sponsorship_profile_str_representation(self, portal_user):
        """Test the string representation of SponsorshipProfile"""
        profile = SponsorshipProfile.objects.create(
            user=portal_user,
            main_contact_user=portal_user,
            organization_name="Test Organization",
            sponsorship_type="Champion",
            company_description="Test description",
        )

        assert str(profile) == "Test Organization"

    def test_get_sponsorship_prices_classmethod(self):
        """Test the get_sponsorship_prices classmethod"""
        prices = SponsorshipProfile.get_sponsorship_prices()

        expected_prices = {
            "Champion": 10000.00,
            "Supporter": 5000.00,
            "Connector": 2500.00,
            "Booster": 1000.00,
            "Partner": 500.00,
            "Individual": 100.00,
        }

        assert prices == expected_prices
        assert isinstance(prices, dict)

    def test_get_default_amount(self, portal_user):
        """Test get_default_amount method for different sponsorship types"""
        # Test Champion type
        profile = SponsorshipProfile.objects.create(
            user=portal_user,
            main_contact_user=portal_user,
            organization_name="Test Org",
            sponsorship_type="Champion",
            company_description="Test description",
        )

        assert profile.get_default_amount() == 10000.00

    def test_get_default_amount_unknown_type(self, portal_user):
        """Test get_default_amount with unknown sponsorship type"""
        profile = SponsorshipProfile.objects.create(
            user=portal_user,
            main_contact_user=portal_user,
            organization_name="Test Org",
            sponsorship_type="Champion",  # Create with valid type first
            company_description="Test description",
        )

        # Manually change to invalid type to test fallback
        profile.sponsorship_type = "InvalidType"
        assert profile.get_default_amount() == 0.00

    def test_save_auto_sets_amount_when_none(self, portal_user):
        """Test that save method auto-sets amount when None"""
        profile = SponsorshipProfile(
            user=portal_user,
            main_contact_user=portal_user,
            organization_name="Test Org",
            sponsorship_type="Supporter",
            company_description="Test description",
            amount_to_pay=None,
        )
        profile.save()

        assert profile.amount_to_pay == 5000.00  # Supporter default

    def test_save_auto_sets_amount_when_zero(self, portal_user):
        """Test that save method auto-sets amount when 0"""
        profile = SponsorshipProfile(
            user=portal_user,
            main_contact_user=portal_user,
            organization_name="Test Org",
            sponsorship_type="Booster",
            company_description="Test description",
            amount_to_pay=0,
        )
        profile.save()

        assert profile.amount_to_pay == 1000.00  # Booster default

    def test_save_preserves_custom_amount(self, portal_user):
        """Test that save method preserves custom amount when provided"""
        custom_amount = 7500.00
        profile = SponsorshipProfile(
            user=portal_user,
            main_contact_user=portal_user,
            organization_name="Test Org",
            sponsorship_type="Champion",
            company_description="Test description",
            amount_to_pay=custom_amount,
        )
        profile.save()

        assert profile.amount_to_pay == custom_amount
        assert profile.amount_to_pay != 10000.00  # Should not be the default

    def test_sponsorship_type_display_with_price(self, portal_user):
        """Test the sponsorship_type_display_with_price property"""
        profile = SponsorshipProfile.objects.create(
            user=portal_user,
            main_contact_user=portal_user,
            organization_name="Test Org",
            sponsorship_type="Champion",
            company_description="Test description",
        )

        display_text = profile.sponsorship_type_display_with_price
        expected = "Champion ($10,000.00)"
        assert display_text == expected

    def test_sponsorship_type_display_with_price_different_types(
        self, portal_user, django_user_model
    ):
        """Test the display property with different sponsorship types"""
        test_cases = [
            ("Supporter", "Supporter ($5,000.00)"),
            ("Individual", "Individual ($100.00)"),
            ("Partner", "Partner ($500.00)"),
        ]

        for i, (sponsor_type, expected_display) in enumerate(test_cases):
            # Create a unique user for each test case to avoid OneToOneField constraint
            unique_user = django_user_model.objects.create_user(
                username=f"test_user_{sponsor_type.lower()}_{i}"
            )
            contact_user = django_user_model.objects.create_user(
                username=f"contact_user_{sponsor_type.lower()}_{i}"
            )

            profile = SponsorshipProfile.objects.create(
                user=unique_user,
                main_contact_user=contact_user,
                organization_name=f"Test {sponsor_type} Org",
                sponsorship_type=sponsor_type,
                company_description="Test description",
            )

            assert profile.sponsorship_type_display_with_price == expected_display

    def test_sponsorship_type_display_with_price_unknown_type(self, portal_user):
        """Test the display property with unknown sponsorship type"""
        profile = SponsorshipProfile.objects.create(
            user=portal_user,
            main_contact_user=portal_user,
            organization_name="Test Org",
            sponsorship_type="Champion",  # Create with valid type
            company_description="Test description",
        )

        # Manually change to unknown type to test fallback
        profile.sponsorship_type = "UnknownType"
        profile.save()

        display_text = profile.sponsorship_type_display_with_price
        # Should show the display name and $0.00 for unknown type
        expected = "UnknownType ($0.00)"
        assert display_text == expected

    def test_default_field_values(self, portal_user):
        """Test that default field values are set correctly"""
        profile = SponsorshipProfile.objects.create(
            user=portal_user,
            main_contact_user=portal_user,
            organization_name="Test Org",
            sponsorship_type="Champion",
            company_description="Test description",
        )

        assert profile.application_status == "pending"
        assert profile.payment_status == "not_paid"

    def test_model_choices_constants(self):
        """Test that model choice constants are defined correctly"""
        assert hasattr(SponsorshipProfile, "SPONSORSHIP_TYPES")
        assert hasattr(SponsorshipProfile, "APPLICATION_STATUS_CHOICES")
        assert hasattr(SponsorshipProfile, "PAYMENT_STATUS_CHOICES")
        assert hasattr(SponsorshipProfile, "SPONSORSHIP_PRICES")

        # Verify some expected values
        sponsorship_types = dict(SponsorshipProfile.SPONSORSHIP_TYPES)
        assert sponsorship_types["Champion"] == "Champion"
        assert sponsorship_types["Individual"] == "Individual"

        app_status = dict(SponsorshipProfile.APPLICATION_STATUS_CHOICES)
        assert app_status["pending"] == "Pending"
        assert app_status["approved"] == "Approved"
