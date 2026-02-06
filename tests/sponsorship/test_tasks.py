import pytest
from django.contrib.auth.models import User
from django.core import mail

from sponsorship.models import SponsorshipProfile, SponsorshipProgressStatus
from sponsorship.tasks import (
    send_internal_email_task,
    send_internal_sponsor_onboarding_email_task,
    send_internal_sponsor_progress_update_email_task,
)
from volunteer.models import Region, Role, RoleTypes, VolunteerProfile


@pytest.fixture
def admin_user_with_role():
    """Create an admin user with proper role."""
    admin_role = Role.objects.create(
        short_name=RoleTypes.ADMIN, description="Admin role"
    )
    admin_user = User.objects.create_superuser(
        username="testadmin",
        email="test-admin@example.com",
        password="pyladiesadmin123",
    )
    admin_profile = VolunteerProfile(user=admin_user)
    admin_profile.region = Region.NORTH_AMERICA
    admin_profile.save()
    admin_profile.roles.add(admin_role)
    admin_profile.save()
    return admin_user


@pytest.fixture
def sponsorship_profile(admin_user):
    """Create a test sponsorship profile."""
    return SponsorshipProfile.objects.create(
        main_contact_user=admin_user,
        organization_name="Test Org",
        progress_status=SponsorshipProgressStatus.AWAITING_RESPONSE.value,
    )


@pytest.mark.django_db
class TestSponsorshipTasks:
    """Test cases for sponsorship Celery tasks."""

    def test_send_internal_email_task(self, admin_user_with_role):
        """Test internal email task sends to admin users."""
        mail.outbox.clear()

        result = send_internal_email_task(
            subject="Test Subject",
            markdown_template="emails/sponsorship/internal_sponsor_onboarding.md",
            context={"profile": {"organization_name": "Test Org"}},
        )

        assert "Sent" in result
        assert len(mail.outbox) >= 1
        assert mail.outbox[0].subject == "Test Subject"

    def test_send_internal_email_task_no_recipients(self):
        """Test internal email task when no recipients exist."""
        mail.outbox.clear()

        result = send_internal_email_task(
            subject="Test Subject",
            markdown_template="emails/sponsorship/internal_sponsor_onboarding.md",
            context={"profile": {"organization_name": "Test Org"}},
        )

        assert "No recipients found" in result
        assert len(mail.outbox) == 0

    def test_send_internal_sponsor_onboarding_email_task(
        self, admin_user_with_role, sponsorship_profile
    ):
        """Test onboarding email task is sent."""
        mail.outbox.clear()

        result = send_internal_sponsor_onboarding_email_task(sponsorship_profile.id)

        assert "Sent" in result
        assert len(mail.outbox) >= 1

    def test_send_internal_sponsor_onboarding_email_task_profile_not_found(self):
        """Test onboarding email task when profile doesn't exist."""
        result = send_internal_sponsor_onboarding_email_task(99999)
        assert "SponsorshipProfile with id 99999 not found" in result

    def test_send_internal_sponsor_progress_update_email_task(
        self, admin_user_with_role, sponsorship_profile
    ):
        """Test progress update email task is sent."""
        mail.outbox.clear()

        result = send_internal_sponsor_progress_update_email_task(
            sponsorship_profile.id
        )

        assert "Sent" in result
        assert len(mail.outbox) >= 1

    def test_send_internal_sponsor_progress_update_email_task_profile_not_found(self):
        """Test progress update email task when profile doesn't exist."""
        result = send_internal_sponsor_progress_update_email_task(99999)
        assert "SponsorshipProfile with id 99999 not found" in result
