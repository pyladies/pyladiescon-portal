import pytest
from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from tablib import Dataset

from volunteer.admin import PyladiesChapterAdmin, VolunteerProfileResource
from volunteer.constants import ApplicationStatus
from volunteer.models import PyladiesChapter, VolunteerProfile


@pytest.mark.django_db
class TestAdminActions:

    def test_bulk_waitlist_action(self, client, portal_user, language):
        portal_user.is_superuser = True
        portal_user.is_staff = True
        portal_user.save()

        profile = VolunteerProfile(user=portal_user)
        profile.save()
        profile.language.add(language)

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


@pytest.mark.django_db
class TestPyLadiesChapterAdmin:

    def test_pyladies_chapter_admin_view(self):
        pyladies_chapter_admin = PyladiesChapterAdmin(
            model=PyladiesChapter, admin_site=AdminSite
        )

        chapter = PyladiesChapter.objects.create(
            chapter_name="vancouver",
            chapter_description="Vancouver, Canada",
            chapter_website="https://vancouver.pyladies.com/",
        )

        has_logo_field = pyladies_chapter_admin.has_logo(chapter)
        assert has_logo_field is False

        chapter.logo = SimpleUploadedFile(
            name="test_image.jpg",
            content=open("./tests/sponsorship/test_img.png", "rb").read(),
            content_type="image/jpeg",
        )
        has_logo_field = pyladies_chapter_admin.has_logo(chapter)

        assert has_logo_field is True


class TestVolunteerImportExport:
    def test_export_volunteer_does_not_trigger_email(self, portal_user):
        dataset = Dataset()
        dataset.headers = [
            "id",
            "user__first_name",
            "user__last_name",
            "user__email",
            "application_status",
            "github_username",
            "discord_username",
            "instagram_username",
            "bluesky_username",
            "mastodon_url",
            "x_username",
            "linkedin_url",
            "region",
            "chapter__chapter_name",
        ]
        dataset.append(
            [
                portal_user.id,
                portal_user.first_name,
                portal_user.last_name,
                portal_user.email,
                ApplicationStatus.APPROVED.value,
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "North America",
                "",
            ]
        )

        dataset.append(
            [
                portal_user.id,
                portal_user.first_name,
                portal_user.last_name,
                portal_user.email,
                ApplicationStatus.CANCELLED.value,
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "USA",
                "",
            ]
        )

        resource = VolunteerProfileResource()
        mail.outbox.clear()
        resource.import_data(dataset, dry_run=False)
        assert len(mail.outbox) == 0  # no email
        resource.import_data(dataset, dry_run=True)
        assert len(mail.outbox) == 0  # no email
