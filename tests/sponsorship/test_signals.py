"""
Tests for sponsorship/signals.py - Complete coverage for all missing lines
"""

from unittest.mock import Mock, patch

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from sponsorship.models import SponsorshipProfile, SponsorshipTier
from sponsorship.signals import _send_email


class TestSponsorshipSignals(TestCase):
    """Test sponsorship signal handlers"""

    def setUp(self):
        """Set up test data"""
        # Create users for the sponsorship
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            first_name="Test",
            last_name="User",
        )

        self.main_contact = User.objects.create_user(
            username="maincontact",
            email="contact@example.com",
            first_name="Main",
            last_name="Contact",
        )

        # Create sponsorship tier
        self.tier = SponsorshipTier.objects.create(
            name="Gold", amount=5000.00, description="Gold tier sponsorship"
        )

    @patch("sponsorship.signals.render_to_string")
    @patch("sponsorship.signals.EmailMultiAlternatives")
    @patch("sponsorship.signals.Site.objects.get_current")
    def test_send_email_function_direct(
        self, mock_get_current, mock_email_class, mock_render
    ):
        """Test the _send_email function directly - covers lines 9-23"""
        # Setup mocks
        mock_site = Mock()
        mock_site.name = "Test Site"
        mock_get_current.return_value = mock_site

        mock_render.side_effect = ["Text content", "HTML content"]
        mock_msg = Mock()
        mock_email_class.return_value = mock_msg

        # Test the function
        _send_email(
            subject="Test Subject",
            recipient_list=["test@example.com"],
            html_template="test.html",
            text_template="test.txt",
            context={"test": "value"},
        )

        # Verify site was added to context
        mock_get_current.assert_called_once()

        # Verify templates were rendered with correct context
        expected_context = {"test": "value", "current_site": mock_site}
        mock_render.assert_any_call("test.txt", expected_context)
        mock_render.assert_any_call("test.html", expected_context)

        # Verify email was created correctly
        mock_email_class.assert_called_once_with(
            "Test Subject",
            "Text content",
            settings.DEFAULT_FROM_EMAIL,
            ["test@example.com"],
        )

        # Verify HTML alternative was attached and email sent
        mock_msg.attach_alternative.assert_called_once_with("HTML content", "text/html")
        mock_msg.send.assert_called_once()

    @patch("sponsorship.signals._send_email")
    @override_settings(ACCOUNT_EMAIL_SUBJECT_PREFIX="[Test] ")
    def test_sponsorship_created_signal(self, mock_send_email):
        """Test signal when SponsorshipProfile is created - covers lines 26-36"""
        # Create a new sponsorship profile (this triggers the signal with created=True)
        sponsorship = SponsorshipProfile.objects.create(
            user=self.user,
            main_contact_user=self.main_contact,
            organization_name="Test Company",
            sponsorship_tier=self.tier,
            company_description="Test description",
            application_status="pending",
        )

        # Verify _send_email was called for sponsor confirmation
        mock_send_email.assert_called_once_with(
            "[Test]  Sponsorship Application Received",
            [self.user.email],
            html_template="sponsorship/email/sponsor_status_update.html",
            text_template="sponsorship/email/sponsor_status_update.txt",
            context={"profile": sponsorship},
        )

    @patch("sponsorship.signals._send_email")
    @override_settings(ACCOUNT_EMAIL_SUBJECT_PREFIX="[Test] ")
    def test_sponsorship_approved_signal(self, mock_send_email):
        """Test signal when SponsorshipProfile is approved - covers lines 37-57"""
        # First create a sponsorship
        sponsorship = SponsorshipProfile.objects.create(
            user=self.user,
            main_contact_user=self.main_contact,
            organization_name="Approved Company",
            sponsorship_tier=self.tier,
            company_description="Test description",
            application_status="pending",
        )

        # Clear any calls from creation
        mock_send_email.reset_mock()

        # Now update to approved status (this triggers the signal with created=False)
        sponsorship.application_status = "approved"
        sponsorship.save()

        # Verify both approval emails were sent
        self.assertEqual(mock_send_email.call_count, 2)

        # Check first call - sponsor approval email
        first_call = mock_send_email.call_args_list[0]
        self.assertEqual(
            first_call[0][0], "[Test]  Sponsorship Profile Approved"
        )  # subject
        self.assertEqual(first_call[0][1], [self.user.email])  # recipient_list
        self.assertEqual(
            first_call[1]["html_template"], "sponsorship/email/sponsor_approved.html"
        )
        self.assertEqual(
            first_call[1]["text_template"], "sponsorship/email/sponsor_approved.txt"
        )
        self.assertEqual(first_call[1]["context"], {"profile": sponsorship})

        # Check second call - internal team notification
        second_call = mock_send_email.call_args_list[1]
        self.assertEqual(
            second_call[0][0], "[Test]  New Sponsorship Approved: Approved Company"
        )
        self.assertEqual(second_call[0][1], ["team@example.com"])
        self.assertEqual(
            second_call[1]["html_template"],
            "sponsorship/email/team_status_notification.html",
        )
        self.assertEqual(
            second_call[1]["text_template"],
            "sponsorship/email/team_status_notification.txt",
        )
        self.assertEqual(second_call[1]["context"], {"profile": sponsorship})

    @patch("sponsorship.signals._send_email")
    def test_sponsorship_update_not_approved(self, mock_send_email):
        """Test that signal doesn't send approval email for non-approved updates"""
        # Create a sponsorship
        sponsorship = SponsorshipProfile.objects.create(
            user=self.user,
            main_contact_user=self.main_contact,
            organization_name="Test Company",
            sponsorship_tier=self.tier,
            company_description="Test description",
            application_status="pending",
        )

        # Clear creation calls
        mock_send_email.reset_mock()

        # Update to rejected status
        sponsorship.application_status = "rejected"
        sponsorship.save()

        # Should not send approval email
        mock_send_email.assert_not_called()

        # Test other non-approval updates
        sponsorship.company_description = "Updated description"
        sponsorship.save()

        # Still should not send emails
        mock_send_email.assert_not_called()

    @patch("sponsorship.signals._send_email")
    def test_sponsorship_update_cancelled_status(self, mock_send_email):
        """Test that signal doesn't send approval email for cancelled status"""
        # Create a sponsorship
        sponsorship = SponsorshipProfile.objects.create(
            user=self.user,
            main_contact_user=self.main_contact,
            organization_name="Test Company",
            sponsorship_tier=self.tier,
            company_description="Test description",
            application_status="pending",
        )

        # Clear creation calls
        mock_send_email.reset_mock()

        # Update to cancelled status
        sponsorship.application_status = "cancelled"
        sponsorship.save()

        # Should not send approval email
        mock_send_email.assert_not_called()

    @patch("sponsorship.signals.render_to_string")
    @patch("sponsorship.signals.EmailMultiAlternatives")
    @patch("sponsorship.signals.Site.objects.get_current")
    def test_send_email_with_empty_context(
        self, mock_get_current, mock_email_class, mock_render
    ):
        """Test _send_email with empty/None context - covers context = context or {} line"""
        mock_site = Mock()
        mock_get_current.return_value = mock_site
        mock_render.side_effect = ["Text", "HTML"]
        mock_msg = Mock()
        mock_email_class.return_value = mock_msg

        # Call with None context
        _send_email(
            subject="Test",
            recipient_list=["test@example.com"],
            html_template="test.html",
            text_template="test.txt",
            context=None,
        )

        # Verify empty dict was used and site was added
        expected_context = {"current_site": mock_site}
        mock_render.assert_any_call("test.txt", expected_context)
        mock_render.assert_any_call("test.html", expected_context)

    @patch("sponsorship.signals._send_email")
    @override_settings(ACCOUNT_EMAIL_SUBJECT_PREFIX="")
    def test_empty_subject_prefix(self, mock_send_email):
        """Test signal with empty subject prefix"""
        # Create sponsorship with empty prefix
        sponsorship = SponsorshipProfile.objects.create(
            user=self.user,
            main_contact_user=self.main_contact,
            organization_name="No Prefix Company",
            sponsorship_tier=self.tier,
            company_description="Test description",
            application_status="pending",
        )

        # Verify subject without prefix
        mock_send_email.assert_called_once_with(
            " Sponsorship Application Received",  # Note the space before
            [self.user.email],
            html_template="sponsorship/email/sponsor_status_update.html",
            text_template="sponsorship/email/sponsor_status_update.txt",
            context={"profile": sponsorship},
        )
