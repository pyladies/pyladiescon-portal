import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from portal.context_processors import user_capabilities
from volunteer.models import ApplicationStatus, Team, VolunteerProfile


def _request(user=None):
    request = RequestFactory().get("/")
    if user is not None:
        request.user = user
    return request


@pytest.mark.django_db
class TestUserCapabilities:
    def test_request_without_user(self):
        # A request that never went through auth middleware has no ``user``.
        caps = user_capabilities(_request())
        assert caps["is_organizer"] is False
        assert caps["can_manage_sponsorship"] is False
        assert caps["can_view_sponsorship"] is False
        assert caps["active_volunteer_profile"] is None
        assert caps["leads_any_team"] is False

    def test_anonymous_user(self):
        caps = user_capabilities(_request(AnonymousUser()))
        assert caps["is_organizer"] is False
        assert caps["can_view_sponsorship"] is False

    def test_organizer(self, admin_user, conference):
        caps = user_capabilities(_request(admin_user))
        assert caps["is_organizer"] is True
        assert caps["can_manage_sponsorship"] is True
        assert caps["can_view_sponsorship"] is True

    def test_approved_volunteer_is_read_only_viewer(self, portal_user, conference):
        VolunteerProfile.objects.create(
            user=portal_user,
            conference=conference,
            application_status=ApplicationStatus.APPROVED,
        )
        caps = user_capabilities(_request(portal_user))
        assert caps["is_organizer"] is False
        assert caps["can_manage_sponsorship"] is False
        assert caps["can_view_sponsorship"] is True
        assert caps["active_volunteer_profile"] is not None

    def test_unapproved_volunteer_cannot_view(self, portal_user, conference):
        VolunteerProfile.objects.create(
            user=portal_user,
            conference=conference,
            application_status=ApplicationStatus.PENDING,
        )
        caps = user_capabilities(_request(portal_user))
        assert caps["can_view_sponsorship"] is False

    def test_leads_any_team(self, portal_user, conference):
        profile = VolunteerProfile.objects.create(
            user=portal_user,
            conference=conference,
            application_status=ApplicationStatus.APPROVED,
        )
        team = Team.objects.create(
            short_name="Comms", description="d", conference=conference
        )
        team.team_leads.add(profile)
        caps = user_capabilities(_request(portal_user))
        assert caps["leads_any_team"] is True
