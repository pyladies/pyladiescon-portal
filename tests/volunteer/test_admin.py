import pytest
from django.conf import settings
from django.core import mail
from django.urls import reverse

from volunteer.languages import LANGUAGES
from volunteer.models import ApplicationStatus, VolunteerProfile


@pytest.mark.django_db
class TestAdminActions:

    def test_bulk_waitlist_action(self, client, portal_user):
        portal_user.is_superuser = True
        portal_user.is_staff = True
        portal_user.save()

        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.save()

        assert profile.application_status == ApplicationStatus.PENDING
        client.force_login(portal_user)
        data = {
            "action": "bulk_waitlist_volunteers",
            "select_across": ["0"],
            "index": ["0"],
            "_selected_action": [str(profile.id)],
        }

        mail.outbox.clear()

        response = client.post(
            reverse("admin:volunteer_volunteerprofile_changelist"), data, follow=True
        )

        assert response.status_code == 200
        assert len(mail.outbox) == 1
        # one message was sent to notify user about waitlisted status
        assert (
            str(mail.outbox[0].subject)
            == f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Volunteer Application Updated"
        )
        assert "We are placing you on a waitlist" in str(mail.outbox[0].body)
        profile.refresh_from_db()
        assert profile.application_status == ApplicationStatus.WAITLISTED
