import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from portal.models import Conference
from portal_account.models import PortalProfile
from sponsorship.models import (
    SponsorshipProfile,
    SponsorshipProgressStatus,
    SponsorshipTier,
)
from volunteer.constants import ApplicationStatus
from volunteer.models import PyladiesChapter, Team, VolunteerProfile


@pytest.mark.django_db
class TestPortalIndex:

    def test_index_unauthenticated(self, client):

        response = client.get(reverse("index"))
        assert response.status_code == 200
        assert "Sign up" in response.content.decode()
        assert "Login" in response.content.decode()

    def test_navbar_shows_active_conference_year(self, client, conference):
        response = client.get(reverse("index"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Active conference edition" in content  # the navbar badge
        assert str(conference.year) in content

    def test_index_authenticated_no_profile_created(self, client, portal_user):

        client.force_login(portal_user)
        response = client.get(reverse("index"), follow=True)

        assert "Sign out" not in response.content.decode()
        assert "Login" not in response.content.decode()
        assertRedirects(response, reverse("portal_account:portal_profile_new"))

    def test_index_authenticated_profile_already_created(self, client, portal_user):

        portal_profile = PortalProfile(user=portal_user)
        portal_profile.save()

        client.force_login(portal_user)
        response = client.get(reverse("index"))
        assert response.status_code == 200
        assert "Sign out" not in response.content.decode()
        assert "Login" not in response.content.decode()

    def test_organizer_redirected_to_dashboard(self, client, admin_user, conference):
        PortalProfile.objects.create(user=admin_user)
        client.force_login(admin_user)
        response = client.get(reverse("index"))
        assertRedirects(response, reverse("organizer_dashboard"))

    def test_non_organizer_sees_landing(self, client, portal_user, conference):
        PortalProfile.objects.create(user=portal_user)
        client.force_login(portal_user)
        response = client.get(reverse("index"))
        assert response.status_code == 200


@pytest.mark.django_db
class TestPortalStats:

    def test_stats_doesnt_require_login(self, client):
        response = client.get(reverse("portal_stats"))
        assert response.status_code == 200
        assert "PyLadiesCon Stats" in response.content.decode()

    def test_stats_defaults_to_active_conference(self, client, conference):
        response = client.get(reverse("portal_stats"))
        assert response.status_code == 200
        assert response.context["selected_conference"] == conference

    def test_stats_year_switcher_selects_requested_year(self, client, conference):
        past = Conference.objects.create(
            year=2024, name="PyLadiesCon 2024", slug="2024"
        )
        response = client.get(reverse("portal_stats") + "?year=2024")
        assert response.status_code == 200
        assert response.context["selected_conference"] == past

    def test_stats_invalid_year_falls_back_to_active(self, client, conference):
        response = client.get(reverse("portal_stats") + "?year=9999")
        assert response.status_code == 200
        assert response.context["selected_conference"] == conference

    def test_stats_historical_year_renders_snapshot(self, client, conference):
        Conference.objects.create(
            year=2024,
            name="PyLadiesCon 2024",
            slug="2024",
            proposals_count=164,
            historical_snapshot={
                "registrations": 600,
                "sponsors": 8,
                "sponsorship_amount": 10500,
                "donors": 58,
                "donation_amount": 650,
            },
        )
        response = client.get(reverse("portal_stats") + "?year=2024")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Final numbers" in content
        assert "600" in content  # snapshot registrations
        assert "164" in content  # proposals_count

    def test_stats_comparison_page_is_public(self, client, conference):
        response = client.get(reverse("portal_stats_comparison"))
        assert response.status_code == 200
        assert "Year-over-Year Comparison" in response.content.decode()


@pytest.mark.django_db
class TestPyladiesChapters:

    def test_view_pyladies_chapters_is_public(self, client):
        response = client.get(reverse("chapters"))
        assert response.status_code == 200
        assert "PyLadies Chapters" in response.content.decode()

    def test_view_pyladies_chapters_displays_chapters(self, client):
        chapter_1 = PyladiesChapter.objects.create(
            chapter_name="vancouver",
            chapter_description="Vancouver, Canada",
            chapter_website="https://vancouver.pyladies.com/",
        )
        chapter_2 = PyladiesChapter.objects.create(
            chapter_name="berlin", chapter_description="Berlin, Germany"
        )

        response = client.get(reverse("chapters"))
        assert response.status_code == 200
        assert chapter_1.chapter_name in response.content.decode()
        assert chapter_2.chapter_name in response.content.decode()
        assert chapter_1.chapter_description in response.content.decode()
        assert chapter_2.chapter_description in response.content.decode()
        assert chapter_1.chapter_website in response.content.decode()


@pytest.mark.django_db
class TestStatsJSON:

    def test_stats_json_endpoint(self, client):
        """Test that the stats JSON endpoint returns the expected data.

        Actual stats values are tested in test_common.py.
        This is just testing that the endpoint is reachable and returns a JSON response.
        """
        response = client.get(reverse("portal_stats_json"))
        assert response.status_code == 200
        data = response.json()
        assert "stats" in data

    def test_stats_json_accepts_year(self, client, conference):
        Conference.objects.create(year=2024, name="PyLadiesCon 2024", slug="2024")
        response = client.get(reverse("portal_stats_json") + "?year=2024")
        assert response.status_code == 200
        assert "stats" in response.json()


@pytest.mark.django_db
class TestDashboardGallery:

    def test_dashboard_gallery_is_public(self, client):
        response = client.get(reverse("dashboard_gallery"))
        assert response.status_code == 200
        assert "Gallery of Dashboard Visualization" in response.content.decode()


@pytest.mark.django_db
class TestStartNewYear:
    def test_requires_admin(self, client, portal_user):
        client.force_login(portal_user)  # not staff/superuser
        response = client.get(reverse("start_new_year"))
        assert response.status_code in (302, 403)

    def test_staff_non_superuser_denied(self, client, django_user_model, conference):
        # The wizard is superuser-only, so plain staff cannot reach it.
        staff = django_user_model.objects.create_user("staffy", is_staff=True)
        client.force_login(staff)
        response = client.get(reverse("start_new_year"))
        assert response.status_code in (302, 403)

    def test_get_renders_form_with_source(self, client, admin_user, conference):
        client.force_login(admin_user)
        response = client.get(reverse("start_new_year"))
        assert response.status_code == 200
        assert response.context["source"] == conference  # most recent edition

    def test_creates_carries_over_and_activates(self, client, admin_user, conference):
        conference.sponsorship_goal = 15000
        conference.donation_goal = 2500
        conference.save()
        Team.objects.create(conference=conference, short_name="Comms", description="c")
        SponsorshipTier.objects.create(
            conference=conference, name="Gold", amount=1000, description="g"
        )
        vol = User.objects.create(username="returner")
        VolunteerProfile.objects.create(
            user=vol,
            conference=conference,
            application_status=ApplicationStatus.APPROVED,
        )
        client.force_login(admin_user)

        response = client.post(
            reverse("start_new_year"),
            {
                "year": 2026,
                "name": "PyLadiesCon 2026",
                "slug": "2026",
                "clone_teams": "on",
                "copy_tiers": "on",
                "copy_goals": "on",
                "bring_volunteers": "on",
                "activate": "on",
            },
            follow=True,
        )

        assert response.status_code == 200
        new = Conference.objects.get(year=2026)
        assert new.is_active is True
        assert new.sponsorship_goal == 15000
        assert new.donation_goal == 2500
        assert new.teams.count() == 1
        assert new.sponsorship_tiers.count() == 1
        assert new.volunteer_profiles.filter(user=vol).exists()
        # single-active enforcer demoted the previous edition
        conference.refresh_from_db()
        assert conference.is_active is False

    def test_creates_without_previous_edition(self, client, admin_user, conference):
        # No prior edition to carry from.
        Conference.objects.all().delete()
        client.force_login(admin_user)

        response = client.post(
            reverse("start_new_year"),
            {
                "year": 2027,
                "name": "PyLadiesCon 2027",
                "slug": "2027",
                "clone_teams": "on",
                "copy_tiers": "on",
                "copy_goals": "on",
            },
            follow=True,
        )

        assert response.status_code == 200
        new = Conference.objects.get(year=2027)
        assert new.is_active is False
        assert new.teams.count() == 0
        assert new.sponsorship_tiers.count() == 0

    def test_duplicate_year_rejected(self, client, admin_user, conference):
        client.force_login(admin_user)
        response = client.post(
            reverse("start_new_year"),
            {"year": conference.year, "name": "Dup", "slug": "dup"},
        )
        assert response.status_code == 200  # re-renders with errors
        assert not Conference.objects.filter(slug="dup").exists()

    def test_duplicate_slug_rejected(self, client, admin_user, conference):
        client.force_login(admin_user)
        response = client.post(
            reverse("start_new_year"),
            {"year": 2099, "name": "Dup", "slug": conference.slug},
        )
        assert response.status_code == 200  # re-renders with errors
        assert not Conference.objects.filter(year=2099).exists()


@pytest.mark.django_db
class TestStartNextYearGate:
    def test_wizard_blocked_when_date_not_passed(self, client, admin_user, conference):
        conference.conference_date = None
        conference.save()
        client.force_login(admin_user)
        response = client.get(reverse("start_new_year"))
        assert response.status_code == 302
        assert response.url == reverse("index")

    def test_card_shown_when_date_passed(self, client, admin_user, conference):
        # autouse conference_date is in the past -> can start next year
        client.force_login(admin_user)
        response = client.get(reverse("organizer_dashboard"))
        assert "Start next year" in response.content.decode()

    def test_card_hidden_when_date_not_passed(self, client, admin_user, conference):
        conference.conference_date = None
        conference.save()
        client.force_login(admin_user)
        response = client.get(reverse("organizer_dashboard"))
        assert "Start next year" not in response.content.decode()


@pytest.mark.django_db
class TestConferenceCRUD:
    def test_list_shows_conferences(self, client, admin_user, conference):
        client.force_login(admin_user)
        response = client.get(reverse("conference_list"))
        assert response.status_code == 200
        assert conference in response.context["conferences"]

    def test_update_conference(self, client, admin_user, conference):
        client.force_login(admin_user)
        response = client.post(
            reverse("conference_edit", kwargs={"pk": conference.pk}),
            {
                "year": conference.year,
                "name": "Renamed Edition",
                "slug": conference.slug,
                "sponsorship_goal": "15000",
                "donation_goal": "2500",
                "proposals_count": "0",
                "conference_date": "2025-11-15",
            },
            follow=True,
        )
        assert response.status_code == 200
        conference.refresh_from_db()
        assert conference.name == "Renamed Edition"
        assert str(conference.conference_date) == "2025-11-15"

    def test_delete_empty_conference(self, client, admin_user, conference):
        extra = Conference.objects.create(year=2099, name="Empty", slug="empty")
        client.force_login(admin_user)
        response = client.post(
            reverse("conference_delete", kwargs={"pk": extra.pk}), follow=True
        )
        assert response.status_code == 200
        assert not Conference.objects.filter(pk=extra.pk).exists()

    def test_delete_blocked_when_has_data(self, client, admin_user, conference):
        extra = Conference.objects.create(year=2099, name="HasData", slug="hasdata")
        Team.objects.create(conference=extra, short_name="T", description="d")
        client.force_login(admin_user)
        response = client.post(
            reverse("conference_delete", kwargs={"pk": extra.pk}), follow=True
        )
        assert response.status_code == 200
        assert Conference.objects.filter(pk=extra.pk).exists()  # protected, not deleted
        assert "Cannot delete" in response.content.decode()

    def test_requires_superuser(self, client, django_user_model, conference):
        staff = django_user_model.objects.create_user("staffy2", is_staff=True)
        client.force_login(staff)
        urls = [
            reverse("conference_list"),
            reverse("conference_edit", kwargs={"pk": conference.pk}),
            reverse("conference_delete", kwargs={"pk": conference.pk}),
        ]
        for url in urls:
            assert client.get(url).status_code in (302, 403)


@pytest.mark.django_db
class TestOrganizerDashboard:
    def test_requires_admin(self, client, portal_user):
        client.force_login(portal_user)
        response = client.get(reverse("organizer_dashboard"))
        assert response.status_code in (302, 403)

    def test_renders_for_admin(self, client, admin_user, conference):
        client.force_login(admin_user)
        response = client.get(reverse("organizer_dashboard"))
        assert response.status_code == 200
        assert "Organizer dashboard" in response.content.decode()
        assert response.context["conference"] == conference

    def test_needs_attention_counts(
        self, client, admin_user, conference, django_user_model
    ):
        # An unled team with a pending member.
        team = Team.objects.create(
            short_name="Comms", description="d", conference=conference
        )
        member = VolunteerProfile.objects.create(
            user=django_user_model.objects.create_user("m1"),
            conference=conference,
            application_status=ApplicationStatus.PENDING,
        )
        member.teams.add(team)
        # A committed-but-uninvoiced sponsor.
        tier = SponsorshipTier.objects.create(
            name="Gold", amount=1000, description="g", conference=conference
        )
        SponsorshipProfile.objects.create(
            organization_name="Corp",
            sponsorship_tier=tier,
            progress_status=SponsorshipProgressStatus.APPROVED,
            conference=conference,
        )
        client.force_login(admin_user)
        response = client.get(reverse("organizer_dashboard"))
        assert response.context["pending_reviews"] == 1
        assert response.context["unled_teams"] == 1
        assert response.context["awaiting_invoice"] == 1

    def test_no_active_conference_renders_zeros(self, client, admin_user, conference):
        conference.is_active = False
        conference.save()
        client.force_login(admin_user)
        response = client.get(reverse("organizer_dashboard"))
        assert response.status_code == 200
        assert response.context["conference"] is None
        assert response.context["pending_reviews"] == 0
        assert response.context["unled_teams"] == 0
        assert response.context["awaiting_invoice"] == 0
