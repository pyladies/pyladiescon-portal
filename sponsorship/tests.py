from django.test import TestCase

# Create your tests here.

from django.test import TestCase
from django.contrib.auth.models import User
from sponsorship.models import SponsorshipProfile, SponsorshipTier
from volunteer.models import VolunteerProfile  # if it's in a separate app
from django.core.files.uploadedfile import SimpleUploadedFile

class SponsorshipProfileTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.tier = SponsorshipTier.objects.create(
            name="Gold",
            amount=5000.00,
            description="Gold Tier Benefits"
        )

    def test_application_status_is_pending_on_creation(self):
        logo = SimpleUploadedFile("logo.png", b"file_content", content_type="image/png")
        profile = SponsorshipProfile.objects.create(
            user=self.user,
            main_contact=self.user,
            sponsor_organization_name="Test Org",
            sponsorship_type=SponsorshipProfile.ORGANIZATION,
            sponsorship_tier=self.tier,
            logo=logo,
            company_description="We support PyLadiesCon!"
        )
        self.assertEqual(profile.application_status, SponsorshipProfile.APPLICATION_PENDING)

    def test_user_can_have_both_volunteer_and_sponsor_profiles(self):
        # Create a VolunteerProfile for the user
        VolunteerProfile.objects.create(
            user=self.user,
            timezone="UTC",  # required field
            languages_spoken="{English}"
        )

        # Create a SponsorshipProfile for the same user
        profile = SponsorshipProfile.objects.create(
            user=self.user,
            main_contact=self.user,
            sponsor_organization_name="Both Roles Org",
            sponsorship_type=SponsorshipProfile.INDIVIDUAL,
            sponsorship_tier=self.tier,
            logo="test_logo.png",
            company_description="Has both roles",
        )

        self.assertEqual(profile.user, self.user)
        self.assertTrue(VolunteerProfile.objects.filter(user=self.user).exists())

