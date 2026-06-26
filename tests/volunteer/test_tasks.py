import pytest
from django.contrib.auth.models import User
from django.core import mail

from volunteer.constants import ApplicationStatus, Region
from volunteer.models import Role, Team, VolunteerProfile
from volunteer.tasks import (
    send_internal_volunteer_onboarding_email_task,
    send_volunteer_cancelled_emails_task,
    send_volunteer_onboarding_email_task,
    send_volunteer_profile_emails_task,
)


@pytest.fixture
def staff_recipient(conference):
    """A staff user who receives internal team notifications."""
    return User.objects.create_user(
        username="staffteam", email="staff@example.com", is_staff=True
    )


@pytest.fixture
def volunteer_profile(portal_user, conference):
    return VolunteerProfile.objects.create(
        user=portal_user,
        conference=conference,
        discord_username="d",
        region=Region.NORTH_AMERICA,
        application_status=ApplicationStatus.APPROVED,
    )


@pytest.mark.django_db
class TestVolunteerEmailTasks:
    def test_profile_emails_created(self, volunteer_profile, staff_recipient):
        mail.outbox.clear()
        result = send_volunteer_profile_emails_task(volunteer_profile.id, True)
        assert "Sent volunteer profile emails" in result
        # applicant notification + internal (staff) notification
        assert len(mail.outbox) >= 2

    def test_profile_emails_updated(self, volunteer_profile):
        mail.outbox.clear()
        result = send_volunteer_profile_emails_task(volunteer_profile.id, False)
        assert "Sent volunteer profile emails" in result
        assert len(mail.outbox) == 1

    def test_profile_emails_not_found(self):
        assert "not found" in send_volunteer_profile_emails_task(99999, True)

    def test_onboarding_email(self, volunteer_profile):
        mail.outbox.clear()
        result = send_volunteer_onboarding_email_task(volunteer_profile.id)
        assert "Sent volunteer onboarding email" in result
        assert len(mail.outbox) == 1

    def test_onboarding_email_not_found(self):
        assert "not found" in send_volunteer_onboarding_email_task(99999)

    def test_internal_onboarding_email(self, volunteer_profile, staff_recipient):
        mail.outbox.clear()
        result = send_internal_volunteer_onboarding_email_task(volunteer_profile.id)
        assert "Sent internal volunteer onboarding email" in result
        assert len(mail.outbox) >= 1

    def test_internal_onboarding_email_not_found(self):
        assert "not found" in send_internal_volunteer_onboarding_email_task(99999)

    def test_cancelled_emails(self, volunteer_profile, conference):
        team = Team.objects.create(
            short_name="Dev", description="d", conference=conference
        )
        lead_user = User.objects.create_user(username="lead", email="lead@example.com")
        lead_profile = VolunteerProfile.objects.create(
            user=lead_user, conference=conference, discord_username="l"
        )
        team.team_leads.add(lead_profile)
        role = Role.objects.create(short_name="Dev", description="d")

        mail.outbox.clear()
        result = send_volunteer_cancelled_emails_task(
            volunteer_profile.id, [team.id], [role.id]
        )
        assert "Sent volunteer cancellation emails" in result
        # confirmation to the volunteer + notification to the team lead
        assert len(mail.outbox) >= 2

    def test_cancelled_emails_not_found(self):
        assert "not found" in send_volunteer_cancelled_emails_task(99999, [], [])
