from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth.models import User
from sponsorship.models import SponsorshipProfile, ApplicationStatus, SponsorshipTier

class EmailLogicTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='lucille', email='lucille@example.com', password='testpass123')
        self.tier = SponsorshipTier.objects.create(name='Gold', amount=1000, description='Gold Tier')
        self.profile = SponsorshipProfile.objects.create(
            user=self.user,
            main_contact=self.user,
            sponsor_organization_name="Lucille Inc.",
            sponsorship_type=SponsorshipProfile.INDIVIDUAL,
            sponsorship_tier=self.tier,
            logo="logo.png",
            company_description="We sponsor women in tech.",
            application_status=ApplicationStatus.PENDING
        )

    @patch("sponsorship.emails.send_mail")
    def test_send_sponsorship_profile_email(self, mock_send_mail):
        from sponsorship.emails import send_sponsorship_profile_email
        send_sponsorship_profile_email(self.user, self.profile)
        mock_send_mail.assert_called_once()
        args, kwargs = mock_send_mail.call_args
        self.assertIn("Submission Received", args[0])
        self.assertEqual(args[3], [self.user.email])


    @patch("sponsorship.emails.send_mail")
    def test_send_sponsorship_status_emails(self, mock_send_mail):
        from sponsorship.emails import send_sponsorship_status_emails
        send_sponsorship_status_emails(self.profile)
        self.assertEqual(mock_send_mail.call_count, 2)

    @patch("sponsorship.signals._send_email")
    def test_signal_on_create_triggers_email(self, mock_send_email):
        self.profile.delete()
        SponsorshipProfile.objects.create(
            user=self.user,
            main_contact=self.user,
            sponsor_organization_name="Lucille Inc.",
            sponsorship_type=SponsorshipProfile.INDIVIDUAL,
            sponsorship_tier=self.tier,
            logo="logo.png",
            company_description="We sponsor women in tech.",
            application_status=ApplicationStatus.PENDING
        )
        self.assertTrue(mock_send_email.called)

    @patch("sponsorship.signals._send_email")
    def test_signal_on_approval_sends_2_emails(self, mock_send_email):
        self.profile.application_status = ApplicationStatus.APPROVED
        self.profile.save()
        self.assertEqual(mock_send_email.call_count, 2)
