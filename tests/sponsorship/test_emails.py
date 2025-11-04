import pytest
from django.contrib.auth.models import User
from django.core import mail

from sponsorship.constants import PSF_ACCOUNTING_EMAIL, SPONSORSHIP_COMMITTEE_EMAIL
from sponsorship.emails import (
    send_psf_invoice_request_email,
    send_sponsorship_status_emails,
)
from sponsorship.models import (
    SponsorshipProfile,
    SponsorshipProgressStatus,
    SponsorshipTier,
)


@pytest.mark.django_db
class TestSponsorshipEmails:
    def test_send_sponsorship_status_emails(self):
        """Test that sponsorship status emails are sent correctly."""
        user = User.objects.create_user(
            username="sponsor", email="sponsor@example.com", password="testpass"
        )

        tier = SponsorshipTier.objects.create(
            name="Gold", amount=5000.00, description="Gold tier sponsorship"
        )

        profile = SponsorshipProfile.objects.create(
            user=user,
            organization_name="Test Corp",
            sponsorship_tier=tier,
            progress_status=SponsorshipProgressStatus.APPROVED,
        )

        # Clear the mail outbox
        mail.outbox = []

        # Send the emails
        send_sponsorship_status_emails(profile)

        # Check that two emails were sent (one to sponsor, one to team)
        assert len(mail.outbox) == 2

        # Check sponsor email
        sponsor_email = mail.outbox[0]
        assert "Your Sponsorship Profile Has Been Approved" in sponsor_email.subject
        assert sponsor_email.to == ["sponsor@example.com"]

        # Check team email
        team_email = mail.outbox[1]
        assert "New Sponsorship Approved: Test Corp" in team_email.subject
        assert team_email.to == ["team@example.com"]

    def test_send_psf_invoice_request_email(self):
        """Test that PSF invoice request email is sent correctly."""
        tier = SponsorshipTier.objects.create(
            name="Gold", amount=5000.00, description="Gold tier sponsorship"
        )

        profile = SponsorshipProfile.objects.create(
            organization_name="Test Corp",
            sponsorship_tier=tier,
            progress_status=SponsorshipProgressStatus.APPROVED,
            sponsors_contact_email="contact@testcorp.com",
        )

        # Clear the mail outbox
        mail.outbox = []

        # Send the email
        send_psf_invoice_request_email(profile)

        # Check that one email was sent
        assert len(mail.outbox) == 1

        email = mail.outbox[0]

        # Check email subject
        assert "PyLadiesCon Sponsorship Contract Request: Test Corp" in email.subject

        # Check recipients
        assert PSF_ACCOUNTING_EMAIL in email.to
        # Ensure the project recipients include our sponsors contact
        assert SPONSORSHIP_COMMITTEE_EMAIL in email.to

        # Check email body contains expected content
        assert "Test Corp" in email.body
        assert "Gold" in email.body
        assert "$5000" in email.body  # Amount formatting may vary
