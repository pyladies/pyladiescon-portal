import pytest
from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from tablib import Dataset

from portal.models import Conference
from volunteer.admin import PyladiesChapterAdmin, VolunteerProfileResource
from volunteer.constants import ApplicationStatus
from volunteer.models import PyladiesChapter, VolunteerProfile


@pytest.mark.django_db
class TestAdminActions:

    def test_bulk_waitlist_action(self, client, portal_user, language, conference):
        portal_user.is_superuser = True
        portal_user.is_staff = True
        portal_user.save()

        profile = VolunteerProfile(user=portal_user, conference=conference)
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

    def test_export_includes_conference_year(self, conference):
        user = User.objects.create_user("exp_vol", email="exp@example.com")
        VolunteerProfile.objects.create(
            user=user, conference=conference, discord_username="d"
        )
        dataset = VolunteerProfileResource().export()
        assert "conference" in dataset.headers
        idx = dataset.headers.index("conference")
        assert str(dataset[0][idx]) == str(conference.year)


@pytest.mark.django_db
class TestActiveConferenceFilter:
    """The conference list filter defaults the changelist to the active edition."""

    def _changelist_queryset(self, client, admin_user, query=""):
        client.force_login(admin_user)
        url = reverse("admin:volunteer_volunteerprofile_changelist")
        response = client.get(url + query)
        assert response.status_code == 200
        return list(response.context["cl"].queryset)

    def _two_editions(self, conference):
        """One profile in the active edition, one in a past edition."""
        active_user = User.objects.create_user("active_vol", email="a@example.com")
        past = Conference.objects.create(
            year=2024, name="PyLadiesCon 2024", slug="2024"
        )
        past_user = User.objects.create_user("past_vol", email="p@example.com")
        active_profile = VolunteerProfile.objects.create(
            user=active_user, conference=conference, discord_username="a"
        )
        past_profile = VolunteerProfile.objects.create(
            user=past_user, conference=past, discord_username="p"
        )
        return active_profile, past_profile, past

    def test_defaults_to_active_conference(self, client, admin_user, conference):
        active_profile, past_profile, _ = self._two_editions(conference)
        qs = self._changelist_queryset(client, admin_user)
        assert active_profile in qs
        assert past_profile not in qs

    def test_all_shows_every_conference(self, client, admin_user, conference):
        active_profile, past_profile, _ = self._two_editions(conference)
        qs = self._changelist_queryset(client, admin_user, "?conference=all")
        assert active_profile in qs
        assert past_profile in qs

    def test_filter_by_specific_conference(self, client, admin_user, conference):
        active_profile, past_profile, past = self._two_editions(conference)
        qs = self._changelist_queryset(client, admin_user, f"?conference={past.pk}")
        assert past_profile in qs
        assert active_profile not in qs

    def test_no_active_conference_shows_all(self, client, admin_user, conference):
        active_profile, past_profile, _ = self._two_editions(conference)
        conference.is_active = False
        conference.save()
        qs = self._changelist_queryset(client, admin_user)
        assert active_profile in qs
        assert past_profile in qs
