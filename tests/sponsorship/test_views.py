import pytest
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from sponsorship.models import (
    SponsorshipProfile,
    SponsorshipProgressStatus,
    SponsorshipTier,
)
from sponsorship.views import SponsorshipProfileFilter, SponsorshipProfileTable
from volunteer.constants import ApplicationStatus
from volunteer.models import LANGUAGES, VolunteerProfile


@pytest.mark.django_db
class TestSponsorshipViews:
    def test_sponsors_list_view_forbidden_if_not_approved_volunteer(
        self, client, portal_user
    ):
        client.force_login(portal_user)
        response = client.get(reverse("sponsorship:sponsorship_list"))
        assert response.status_code == 403

        # create the volunteer profile but is not approved
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.save()

        response = client.get(reverse("sponsorship:sponsorship_list"))
        assert response.status_code == 403

    def test_sponsors_list_view_is_superuser(self, client, admin_user):

        client.force_login(admin_user)
        url = reverse("sponsorship:sponsorship_list")
        response = client.get(url)
        assert response.status_code == 200

    def test_sponsors_list_view_is_approved_volunteer(self, client, portal_user):
        profile = VolunteerProfile(
            user=portal_user, application_status=ApplicationStatus.APPROVED
        )
        profile.languages_spoken = [LANGUAGES[0]]
        profile.save()

        client.force_login(portal_user)
        url = reverse("sponsorship:sponsorship_list")
        response = client.get(url)
        assert response.status_code == 200

    @pytest.mark.parametrize(
        "status,css_class",
        [
            (SponsorshipProgressStatus.NOT_CONTACTED.label, "bg-dark"),
            (SponsorshipProgressStatus.CANCELLED.label, "bg-dark"),
            (SponsorshipProgressStatus.REJECTED.label, "bg-danger"),
            (SponsorshipProgressStatus.ACCEPTED.label, "bg-info"),
            (SponsorshipProgressStatus.INVOICED.label, "bg-info"),
            (SponsorshipProgressStatus.APPROVED.label, "bg-success"),
            (SponsorshipProgressStatus.PAID.label, "bg-success"),
            (SponsorshipProgressStatus.AGREEMENT_SENT.label, "bg-primary"),
            (SponsorshipProgressStatus.AGREEMENT_SIGNED.label, "bg-primary"),
            (SponsorshipProgressStatus.AWAITING_RESPONSE.label, "bg-warning"),
        ],
    )
    def test_sponsors_table_render_progress_status(
        self, client, admin_user, status, css_class
    ):

        client.force_login(admin_user)
        url = reverse("sponsorship:sponsorship_list")
        response = client.get(url)

        assert response.status_code == 200
        assert isinstance(response.context["table"], SponsorshipProfileTable)

        sponsors_table = response.context["table"]
        progress_status_render = sponsors_table.render_progress_status(status)
        assert css_class in progress_status_render

    @pytest.mark.parametrize(
        "status,css_class,is_visible",
        [
            (SponsorshipProgressStatus.NOT_CONTACTED, "bg-dark", False),
            (SponsorshipProgressStatus.CANCELLED, "bg-dark", False),
            (SponsorshipProgressStatus.REJECTED, "bg-danger", False),
            (SponsorshipProgressStatus.ACCEPTED, "bg-info", True),
            (SponsorshipProgressStatus.INVOICED, "bg-info", True),
            (SponsorshipProgressStatus.APPROVED, "bg-success", True),
            (SponsorshipProgressStatus.PAID, "bg-success", True),
            (SponsorshipProgressStatus.AGREEMENT_SENT, "bg-primary", True),
            (SponsorshipProgressStatus.AGREEMENT_SIGNED, "bg-primary", True),
            (SponsorshipProgressStatus.AWAITING_RESPONSE, "bg-warning", False),
        ],
    )
    def test_sponsors_table_render_progress_status_for_approved_volunteer(
        self, client, portal_user, status, css_class, is_visible
    ):
        """Volunteer can only view Committed sponsors.

        Paid, approved, accepted, invoiced, agreement sent and signed.
        Volunteer cannot see pending/cancelled/rejected sponsors.

        """

        tier = SponsorshipTier.objects.create(
            name="Gold", amount=5000.00, description="Gold tier sponsorship"
        )

        SponsorshipProfile.objects.create(
            organization_name="Override Corp",
            sponsorship_tier=tier,
            progress_status=status,
        )

        profile = VolunteerProfile(
            user=portal_user, application_status=ApplicationStatus.APPROVED
        )
        profile.languages_spoken = [LANGUAGES[0]]
        profile.save()

        client.force_login(portal_user)
        url = reverse("sponsorship:sponsorship_list")
        response = client.get(url)
        assert response.status_code == 200
        assert isinstance(response.context["table"], SponsorshipProfileTable)

        sponsors_table = response.context["table"]
        if is_visible:
            # There is one row because the status is in one of the approved status
            assert len(sponsors_table.rows) == 1
        else:
            # No rows in the table because the status is not approved
            assert len(sponsors_table.rows) == 0

    def test_sponsors_table_render_amount_without_override(self, client, admin_user):

        tier = SponsorshipTier.objects.create(
            name="Gold", amount=5000.00, description="Gold tier sponsorship"
        )

        profile = SponsorshipProfile.objects.create(
            organization_name="Override Corp",
            sponsorship_tier=tier,
        )
        client.force_login(admin_user)
        url = reverse("sponsorship:sponsorship_list")
        response = client.get(url)

        sponsors_table = response.context["table"]
        amount_render = sponsors_table.render_amount(tier.amount, profile)
        assert amount_render == f"${tier.amount:,.2f}"

    def test_sponsors_table_render_amount_with_override(self, client, admin_user):
        tier = SponsorshipTier.objects.create(
            name="Gold", amount=5000.00, description="Gold tier sponsorship"
        )

        profile = SponsorshipProfile.objects.create(
            organization_name="Override Corp",
            sponsorship_tier=tier,
            sponsorship_override_amount=3000.00,
        )

        client.force_login(admin_user)
        url = reverse("sponsorship:sponsorship_list")
        response = client.get(url)
        sponsors_table = response.context["table"]
        amount_render = sponsors_table.render_amount(tier.amount, profile)
        assert amount_render == f"${profile.sponsorship_override_amount:,.2f}"

    def test_sponsors_table_render_amount_no_sponsorship_tier(self, client, admin_user):

        profile = SponsorshipProfile.objects.create(
            organization_name="Override Corp",
        )

        client.force_login(admin_user)
        url = reverse("sponsorship:sponsorship_list")
        response = client.get(url)
        sponsors_table = response.context["table"]
        amount_render = sponsors_table.render_amount("", profile)
        assert amount_render == ""

    def test_sponsors_table_render_actions(self, client, admin_user):

        profile = SponsorshipProfile.objects.create(
            organization_name="Override Corp",
        )

        client.force_login(admin_user)
        url = reverse("sponsorship:sponsorship_list")

        response = client.get(url)
        sponsors_table = response.context["table"]
        action_button = sponsors_table.render_actions("", profile)
        assert "btn-primary" in action_button
        assert "Update" in action_button


@pytest.mark.django_db
class TestSponsorshipCreateViews:
    def test_sponsors_list_view_forbidden_if_not_superuser(self, client, portal_user):
        client.force_login(portal_user)
        response = client.get(reverse("sponsorship:sponsorship_profile_new"))
        assert response.status_code == 403

    def test_sponsors_list_view_is_superuser(
        self,
        client,
        admin_user,
    ):

        client.force_login(admin_user)
        url = reverse("sponsorship:sponsorship_profile_new")
        response = client.get(url)
        assert response.status_code == 200

    def test_sponsorship_profile_create_successful(self, client, admin_user):
        client.force_login(admin_user)
        url = reverse("sponsorship:sponsorship_profile_new")
        data = {
            "main_contact_user": admin_user.id,
            "organization_name": "Test Org",
            "progress_status": SponsorshipProgressStatus.AGREEMENT_SENT,
        }
        response = client.post(url, data=data)
        assert response.status_code == 302
        assertRedirects(
            response,
            reverse("sponsorship:sponsorship_list"),
        )
        assert SponsorshipProfile.objects.count() == 1
        profile = SponsorshipProfile.objects.first()
        assert profile.main_contact_user == admin_user
        assert profile.organization_name == "Test Org"
        assert profile.progress_status == SponsorshipProgressStatus.AGREEMENT_SENT

    def test_sponsorship_profile_create_user_can_create_multiple_profiles(
        self, client, admin_user
    ):

        client.force_login(admin_user)

        SponsorshipProfile.objects.create(
            main_contact_user=admin_user, organization_name="Test Org 1"
        )
        response = client.get(reverse("sponsorship:sponsorship_profile_new"))
        # Form page loads successfully even though the user already created a sponsorship profile before
        assert response.status_code == 200

        data = {
            "main_contact_user": admin_user.id,
            "organization_name": "Test Org 2",
            "progress_status": SponsorshipProgressStatus.NOT_CONTACTED,
        }
        response = client.post(
            reverse("sponsorship:sponsorship_profile_new"), data=data
        )
        assert response.status_code == 302
        assert (
            SponsorshipProfile.objects.filter(main_contact_user=admin_user).count() == 2
        )
        profile = SponsorshipProfile.objects.filter(main_contact_user=admin_user).last()
        assert profile.organization_name == "Test Org 2"
        assert profile.progress_status == SponsorshipProgressStatus.NOT_CONTACTED

    def test_filter_sponsorship_table(self, client, admin_user):
        tier_1 = SponsorshipTier.objects.create(
            name="Silver", amount=3000.00, description="Silver tier"
        )
        tier_2 = SponsorshipTier.objects.create(
            name="Gold", amount=5000.00, description="Gold tier"
        )
        SponsorshipProfile.objects.create(
            organization_name="Alpha Corp",
            sponsorship_tier=tier_1,
            progress_status=SponsorshipProgressStatus.NOT_CONTACTED,
        )
        SponsorshipProfile.objects.create(
            organization_name="Beta LLC",
            sponsorship_tier=tier_2,
            progress_status=SponsorshipProgressStatus.PAID,
        )

        client.force_login(admin_user)
        url = reverse("sponsorship:sponsorship_list")
        response = client.get(url)
        assert response.status_code == 200
        assert isinstance(response.context["filter"], SponsorshipProfileFilter)

        filter = response.context["filter"]
        filter_queryset = filter.qs
        search_by_name = filter.search_fulltext(filter_queryset, "", "")
        assert search_by_name.count() == 2

        qs = filter.search_fulltext(filter_queryset, "", "Alpha")
        assert qs.count() == 1  # Only Alpha Corp matches

        qs = filter.filter_progress_status(
            filter_queryset, "", SponsorshipProgressStatus.NOT_CONTACTED
        )
        assert qs.count() == 1  # Only Alpha Corp has NOT_CONTACTED status

        qs = filter.filter_progress_status(
            filter_queryset, "", SponsorshipProgressStatus.INVOICED
        )
        assert qs.count() == 0  # No sponsors with INVOICED status
