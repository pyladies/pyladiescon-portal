import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from portal.constants import SPONSORSHIP_GOAL
from portal.models import Conference
from sponsorship.models import (
    SponsorshipProfile,
    SponsorshipProgressStatus,
    SponsorshipTier,
)
from sponsorship.views import SponsorshipProfileFilter, SponsorshipProfileTable
from volunteer.constants import ApplicationStatus
from volunteer.languages import LANGUAGES
from volunteer.models import VolunteerProfile


@pytest.mark.django_db
class TestSponsorshipConferenceScoping:
    def _sponsor(self, name, conference):
        return SponsorshipProfile.objects.create(
            organization_name=name,
            conference=conference,
            progress_status=SponsorshipProgressStatus.PAID,
        )

    def test_admin_can_switch_year(self, client, admin_user, conference):
        past = Conference.objects.create(
            year=2024, name="PyLadiesCon 2024", slug="2024"
        )
        self._sponsor("Active Sponsor", conference)
        self._sponsor("Past Sponsor", past)
        client.force_login(admin_user)
        url = reverse("sponsorship:sponsorship_list")

        active_orgs = [
            p.organization_name for p in client.get(url).context["object_list"]
        ]
        assert "Active Sponsor" in active_orgs
        assert "Past Sponsor" not in active_orgs

        past_orgs = [
            p.organization_name
            for p in client.get(f"{url}?conference={past.pk}").context["object_list"]
        ]
        assert "Past Sponsor" in past_orgs
        assert "Active Sponsor" not in past_orgs

    def test_stats_follow_selected_year(self, client, admin_user, conference):
        past = Conference.objects.create(
            year=2024, name="PyLadiesCon 2024", slug="2024", sponsorship_goal=9999
        )
        client.force_login(admin_user)
        url = reverse("sponsorship:sponsorship_list")

        # Default tab → the active conference's goal.
        active_stats = client.get(url).context["stats"]
        assert active_stats[SPONSORSHIP_GOAL] == conference.sponsorship_goal

        # Switching the year tab → that conference's goal.
        past_stats = client.get(f"{url}?conference={past.pk}").context["stats"]
        assert past_stats[SPONSORSHIP_GOAL] == 9999

    def test_stats_none_when_selected_conference_not_viewable(
        self, client, admin_user, conference
    ):
        client.force_login(admin_user)
        url = reverse("sponsorship:sponsorship_list")
        response = client.get(f"{url}?conference=99999")
        assert response.context["stats"] is None

    def test_tier_filter_scoped_to_selected_year(self, client, admin_user, conference):
        past = Conference.objects.create(
            year=2024, name="PyLadiesCon 2024", slug="2024"
        )
        active_tier = SponsorshipTier.objects.create(
            name="Gold", amount=1000, conference=conference
        )
        past_tier = SponsorshipTier.objects.create(
            name="OldGold", amount=500, conference=past
        )
        client.force_login(admin_user)
        url = reverse("sponsorship:sponsorship_list")

        def tier_options(query=""):
            response = client.get(url + query)
            return list(response.context["tiers"])

        # Default (active edition) → only the active edition's tiers.
        assert active_tier in tier_options()
        assert past_tier not in tier_options()

        # Switched to the past edition → only that edition's tiers.
        assert past_tier in tier_options(f"?conference={past.pk}")
        assert active_tier not in tier_options(f"?conference={past.pk}")

    def test_volunteer_sees_only_the_year_they_are_approved_for(
        self, client, portal_user, conference
    ):
        past = Conference.objects.create(
            year=2024, name="PyLadiesCon 2024", slug="2024"
        )
        # approved for the past edition only, not the active one
        VolunteerProfile.objects.create(
            user=portal_user,
            conference=past,
            application_status=ApplicationStatus.APPROVED,
            discord_username="d",
        )
        self._sponsor("Active Sponsor", conference)
        self._sponsor("Past Sponsor", past)
        client.force_login(portal_user)

        response = client.get(reverse("sponsorship:sponsorship_list"))
        assert response.status_code == 200
        orgs = [p.organization_name for p in response.context["object_list"]]
        assert "Past Sponsor" in orgs
        assert "Active Sponsor" not in orgs

    def test_volunteer_cannot_open_other_year_sponsor_detail(
        self, client, portal_user, conference
    ):
        # approved for the active edition only
        VolunteerProfile.objects.create(
            user=portal_user,
            conference=conference,
            application_status=ApplicationStatus.APPROVED,
            discord_username="d",
        )
        past = Conference.objects.create(
            year=2024, name="PyLadiesCon 2024", slug="2024"
        )
        past_sponsor = self._sponsor("Past Sponsor", past)
        client.force_login(portal_user)

        response = client.get(
            reverse(
                "sponsorship:sponsorship_profile_detail",
                kwargs={"pk": past_sponsor.pk},
            )
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestSponsorshipViews:
    def test_sponsors_list_view_forbidden_if_not_approved_volunteer(
        self, client, portal_user, conference
    ):
        client.force_login(portal_user)
        response = client.get(reverse("sponsorship:sponsorship_list"))
        assert response.status_code == 403

        # create the volunteer profile but is not approved
        profile = VolunteerProfile(user=portal_user, conference=conference)
        profile.save()

        response = client.get(reverse("sponsorship:sponsorship_list"))
        assert response.status_code == 403

    def test_sponsors_list_view_is_superuser(self, client, admin_user):

        client.force_login(admin_user)
        url = reverse("sponsorship:sponsorship_list")
        response = client.get(url)
        assert response.status_code == 200

    def test_sponsors_list_view_is_approved_volunteer(
        self, client, portal_user, conference
    ):
        profile = VolunteerProfile(
            user=portal_user,
            application_status=ApplicationStatus.APPROVED,
            conference=conference,
        )
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

    def test_sponsors_table_render_logo(
        self,
        client,
        admin_user,
        conference,
    ):
        tier = SponsorshipTier.objects.create(
            name="Gold",
            amount=5000.00,
            description="Gold tier sponsorship",
            conference=conference,
        )

        profile = SponsorshipProfile.objects.create(
            organization_name="Override Corp",
            sponsorship_tier=tier,
            progress_status=SponsorshipProgressStatus.PAID,
            conference=conference,
        )

        profile.logo = SimpleUploadedFile(
            name="test_image.jpg",
            content=open("./tests/sponsorship/test_img.png", "rb").read(),
            content_type="image/jpeg",
        )

        client.force_login(admin_user)
        url = reverse("sponsorship:sponsorship_list")
        response = client.get(url)

        assert response.status_code == 200
        assert isinstance(response.context["table"], SponsorshipProfileTable)

        sponsors_table = response.context["table"]
        logo_render = sponsors_table.render_logo(profile.logo, profile)
        assert profile.logo.url in logo_render
        assert f'alt="Logo of {profile.organization_name}"' in logo_render

    def test_sponsors_table_render_no_logo(
        self,
        client,
        admin_user,
        conference,
    ):
        tier = SponsorshipTier.objects.create(
            name="Gold",
            amount=5000.00,
            description="Gold tier sponsorship",
            conference=conference,
        )

        profile = SponsorshipProfile.objects.create(
            organization_name="Override Corp",
            sponsorship_tier=tier,
            progress_status=SponsorshipProgressStatus.PAID,
            conference=conference,
        )

        client.force_login(admin_user)
        url = reverse("sponsorship:sponsorship_list")
        response = client.get(url)

        assert response.status_code == 200
        assert isinstance(response.context["table"], SponsorshipProfileTable)

        sponsors_table = response.context["table"]
        logo_render = sponsors_table.render_logo(profile.logo, profile)
        assert logo_render == ""

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
        self, client, portal_user, status, css_class, is_visible, conference
    ):
        """Volunteer can only view Committed sponsors.

        Paid, approved, accepted, invoiced, agreement sent and signed.
        Volunteer cannot see pending/cancelled/rejected sponsors.

        """

        tier = SponsorshipTier.objects.create(
            name="Gold",
            amount=5000.00,
            description="Gold tier sponsorship",
            conference=conference,
        )

        SponsorshipProfile.objects.create(
            organization_name="Override Corp",
            sponsorship_tier=tier,
            progress_status=status,
            conference=conference,
        )

        profile = VolunteerProfile(
            user=portal_user,
            application_status=ApplicationStatus.APPROVED,
            conference=conference,
        )
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

    def test_sponsors_table_render_amount_without_override(
        self, client, admin_user, conference
    ):

        tier = SponsorshipTier.objects.create(
            name="Gold",
            amount=5000.00,
            description="Gold tier sponsorship",
            conference=conference,
        )

        profile = SponsorshipProfile.objects.create(
            organization_name="Override Corp",
            sponsorship_tier=tier,
            conference=conference,
        )
        client.force_login(admin_user)
        url = reverse("sponsorship:sponsorship_list")
        response = client.get(url)

        sponsors_table = response.context["table"]
        amount_render = sponsors_table.render_amount(tier.amount, profile)
        assert amount_render == f"${tier.amount:,.2f}"

    def test_sponsors_table_render_amount_with_override(
        self, client, admin_user, conference
    ):
        tier = SponsorshipTier.objects.create(
            name="Gold",
            amount=5000.00,
            description="Gold tier sponsorship",
            conference=conference,
        )

        profile = SponsorshipProfile.objects.create(
            organization_name="Override Corp",
            sponsorship_tier=tier,
            sponsorship_override_amount=3000.00,
            conference=conference,
        )

        client.force_login(admin_user)
        url = reverse("sponsorship:sponsorship_list")
        response = client.get(url)
        sponsors_table = response.context["table"]
        amount_render = sponsors_table.render_amount(tier.amount, profile)
        assert amount_render == f"${profile.sponsorship_override_amount:,.2f}"

    def test_sponsors_table_render_amount_no_sponsorship_tier(
        self, client, admin_user, conference
    ):

        profile = SponsorshipProfile.objects.create(
            organization_name="Override Corp",
            conference=conference,
        )

        client.force_login(admin_user)
        url = reverse("sponsorship:sponsorship_list")
        response = client.get(url)
        sponsors_table = response.context["table"]
        amount_render = sponsors_table.render_amount("", profile)
        assert amount_render == ""

    def test_sponsors_table_render_actions(self, client, admin_user, conference):

        profile = SponsorshipProfile.objects.create(
            organization_name="Override Corp",
            conference=conference,
        )

        client.force_login(admin_user)
        url = reverse("sponsorship:sponsorship_list")

        response = client.get(url)
        sponsors_table = response.context["table"]
        action_button = sponsors_table.render_actions("", profile)
        assert "btn-primary" in action_button
        assert "fa-pencil" in action_button  # edit icon
        assert "fa-trash" in action_button  # delete icon
        assert (
            reverse("sponsorship:sponsorship_profile_edit", args=[profile.pk])
            in action_button
        )

    def test_sponsors_table_render_github_issue_url(
        self, client, admin_user, conference
    ):

        profile = SponsorshipProfile.objects.create(
            organization_name="Override Corp",
            conference=conference,
        )

        client.force_login(admin_user)
        url = reverse("sponsorship:sponsorship_list")

        response = client.get(url)
        sponsors_table = response.context["table"]
        gh_url_render = sponsors_table.render_github_issue_url("", profile)
        assert gh_url_render == ""

        profile.github_issue_url = "https://github.com/python/cpython/issues/1234"
        profile.save()
        gh_url_render = sponsors_table.render_github_issue_url(
            profile.github_issue_url, profile
        )
        assert profile.github_issue_url in gh_url_render


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
        self, client, admin_user, conference
    ):

        client.force_login(admin_user)

        SponsorshipProfile.objects.create(
            main_contact_user=admin_user,
            organization_name="Test Org 1",
            conference=conference,
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

    def test_filter_sponsorship_table(self, client, admin_user, conference):
        tier_1 = SponsorshipTier.objects.create(
            name="Silver",
            amount=3000.00,
            description="Silver tier",
            conference=conference,
        )
        tier_2 = SponsorshipTier.objects.create(
            name="Gold",
            amount=5000.00,
            description="Gold tier",
            conference=conference,
        )
        SponsorshipProfile.objects.create(
            organization_name="Alpha Corp",
            sponsorship_tier=tier_1,
            progress_status=SponsorshipProgressStatus.NOT_CONTACTED,
            conference=conference,
        )
        SponsorshipProfile.objects.create(
            organization_name="Beta LLC",
            sponsorship_tier=tier_2,
            progress_status=SponsorshipProgressStatus.PAID,
            conference=conference,
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

        # Status filtering is driven by the quick-filter chips (?progress_status=).
        not_contacted = client.get(
            url + f"?progress_status={SponsorshipProgressStatus.NOT_CONTACTED.value}"
        )
        assert len(not_contacted.context["table"].rows) == 1  # only Alpha Corp

        invoiced = client.get(
            url + f"?progress_status={SponsorshipProgressStatus.INVOICED.value}"
        )
        assert len(invoiced.context["table"].rows) == 0  # none invoiced

    def test_sponsorship_profile_detail_view_for_approved_volunteer(
        self, client, portal_user, conference
    ):
        """Test that approved volunteers can view sponsorship details."""
        tier = SponsorshipTier.objects.create(
            name="Gold",
            amount=5000.00,
            description="Gold tier sponsorship",
            conference=conference,
        )

        profile = SponsorshipProfile.objects.create(
            organization_name="Test Corp",
            sponsorship_tier=tier,
            progress_status=SponsorshipProgressStatus.APPROVED,
            conference=conference,
        )

        # Create approved volunteer profile
        volunteer_profile = VolunteerProfile(
            user=portal_user,
            application_status=ApplicationStatus.APPROVED,
            conference=conference,
        )
        volunteer_profile.languages_spoken = [LANGUAGES[0]]
        volunteer_profile.save()

        client.force_login(portal_user)
        url = reverse(
            "sponsorship:sponsorship_profile_detail", kwargs={"pk": profile.pk}
        )
        response = client.get(url)

        assert response.status_code == 200
        assert response.context["profile"] == profile
        # Approved volunteers should not see send invoice button
        assert not response.context["can_send_invoice"]

    def test_sponsorship_profile_detail_view_for_admin_shows_send_invoice_button(
        self, client, admin_user, conference
    ):
        """Test that admins can see the send invoice button for approved sponsors."""
        tier = SponsorshipTier.objects.create(
            name="Gold",
            amount=5000.00,
            description="Gold tier sponsorship",
            conference=conference,
        )

        profile = SponsorshipProfile.objects.create(
            organization_name="Test Corp",
            sponsorship_tier=tier,
            progress_status=SponsorshipProgressStatus.APPROVED,
            conference=conference,
        )

        client.force_login(admin_user)
        url = reverse(
            "sponsorship:sponsorship_profile_detail", kwargs={"pk": profile.pk}
        )
        response = client.get(url)

        assert response.status_code == 200
        assert response.context["profile"] == profile
        # Admins should see send invoice button for approved sponsors
        assert response.context["can_send_invoice"]

    def test_sponsorship_profile_detail_view_admin_no_button_for_non_approved(
        self, client, admin_user, conference
    ):
        """Test that send invoice button is not shown for non-approved sponsors."""
        tier = SponsorshipTier.objects.create(
            name="Gold",
            amount=5000.00,
            description="Gold tier sponsorship",
            conference=conference,
        )

        profile = SponsorshipProfile.objects.create(
            organization_name="Test Corp",
            sponsorship_tier=tier,
            progress_status=SponsorshipProgressStatus.PAID,  # Not approved
            conference=conference,
        )

        client.force_login(admin_user)
        url = reverse(
            "sponsorship:sponsorship_profile_detail", kwargs={"pk": profile.pk}
        )
        response = client.get(url)

        assert response.status_code == 200
        # Should not show send invoice button for non-approved sponsors
        assert not response.context["can_send_invoice"]

    def test_send_invoice_view_updates_status_and_sends_email(
        self, client, admin_user, conference
    ):
        """Test that send invoice view updates status and sends email."""
        from django.core import mail

        tier = SponsorshipTier.objects.create(
            name="Gold",
            amount=5000.00,
            description="Gold tier sponsorship",
            conference=conference,
        )

        profile = SponsorshipProfile.objects.create(
            organization_name="Test Corp",
            sponsorship_tier=tier,
            progress_status=SponsorshipProgressStatus.APPROVED,
            conference=conference,
        )

        # Clear the mail outbox
        mail.outbox = []

        client.force_login(admin_user)
        url = reverse("sponsorship:sponsorship_send_invoice", kwargs={"pk": profile.pk})
        response = client.post(url)

        # Should redirect back to detail view
        assert response.status_code == 302
        expected_url = reverse(
            "sponsorship:sponsorship_profile_detail", kwargs={"pk": profile.pk}
        )
        assert response.url == expected_url

        # Check that status remains APPROVED (no status change)
        profile.refresh_from_db()
        assert profile.progress_status == SponsorshipProgressStatus.APPROVED

        # Check that emails were sent
        assert len(mail.outbox) >= 1
        # Find the PSF invoice email
        psf_email = None
        for email in mail.outbox:
            if "PyLadiesCon Sponsorship Contract Request: Test Corp" in email.subject:
                psf_email = email
                break
        assert psf_email is not None

        # Check success message
        messages = list(response.wsgi_request._messages)
        assert len(messages) == 1
        assert "Invoice request sent to PSF accounting team for Test Corp" in str(
            messages[0].message
        )


@pytest.mark.django_db
class TestSponsorshipCRUD:
    def _sponsor(self, conference, **kwargs):
        return SponsorshipProfile.objects.create(
            organization_name=kwargs.pop("organization_name", "Acme"),
            conference=conference,
            progress_status=SponsorshipProgressStatus.AWAITING_RESPONSE,
            **kwargs,
        )

    def test_admin_can_edit_sponsor(self, client, admin_user, portal_user, conference):
        profile = self._sponsor(conference, user=portal_user)
        client.force_login(admin_user)
        response = client.post(
            reverse("sponsorship:sponsorship_profile_edit", kwargs={"pk": profile.pk}),
            {
                "organization_name": "Acme Updated",
                "conference": conference.pk,
                "main_contact_user": admin_user.pk,
                "progress_status": SponsorshipProgressStatus.AWAITING_RESPONSE.value,
            },
            follow=True,
        )
        assert response.status_code == 200
        profile.refresh_from_db()
        assert profile.organization_name == "Acme Updated"
        assert profile.user == portal_user  # owner is not reassigned on edit

    def test_admin_can_delete_sponsor(self, client, admin_user, conference):
        profile = self._sponsor(conference)
        client.force_login(admin_user)
        response = client.post(
            reverse(
                "sponsorship:sponsorship_profile_delete", kwargs={"pk": profile.pk}
            ),
            follow=True,
        )
        assert response.status_code == 200
        assert not SponsorshipProfile.objects.filter(pk=profile.pk).exists()

    def test_edit_delete_require_admin(self, client, portal_user, conference):
        profile = self._sponsor(conference)
        client.force_login(portal_user)  # not staff/superuser
        for name in [
            "sponsorship:sponsorship_profile_edit",
            "sponsorship:sponsorship_profile_delete",
        ]:
            url = reverse(name, kwargs={"pk": profile.pk})
            assert client.get(url).status_code in (302, 403)

    def test_edit_page_links_back_to_list(self, client, admin_user, conference):
        profile = self._sponsor(conference)
        client.force_login(admin_user)
        response = client.get(
            reverse("sponsorship:sponsorship_profile_edit", kwargs={"pk": profile.pk})
        )
        assert response.status_code == 200
        assert reverse("sponsorship:sponsorship_list") in response.content.decode()


@pytest.mark.django_db
class TestSponsorshipTierCRUD:
    def _tier(self, conference, **kwargs):
        return SponsorshipTier.objects.create(
            name=kwargs.pop("name", "Gold"),
            amount=kwargs.pop("amount", 1000),
            description=kwargs.pop("description", "g"),
            conference=conference,
        )

    def test_list(self, client, admin_user, conference):
        tier = self._tier(conference)
        client.force_login(admin_user)
        response = client.get(reverse("sponsorship:tier_list"))
        assert response.status_code == 200
        assert tier in response.context["tiers"]

    def test_create(self, client, admin_user, conference):
        client.force_login(admin_user)
        response = client.post(
            reverse("sponsorship:tier_new"),
            {
                "conference": conference.pk,
                "name": "Gold",
                "amount": "1000",
                "description": "Gold tier",
                "sponsor_limit": "3",
            },
            follow=True,
        )
        assert response.status_code == 200
        tier = SponsorshipTier.objects.get(name="Gold", conference=conference)
        assert tier.sponsor_limit == 3

    def test_update(self, client, admin_user, conference):
        tier = self._tier(conference)
        client.force_login(admin_user)
        response = client.post(
            reverse("sponsorship:tier_edit", kwargs={"pk": tier.pk}),
            {
                "conference": conference.pk,
                "name": "Platinum",
                "amount": "2000",
                "description": "g",
            },
            follow=True,
        )
        assert response.status_code == 200
        tier.refresh_from_db()
        assert tier.name == "Platinum"
        assert tier.amount == 2000

    def test_delete(self, client, admin_user, conference):
        tier = self._tier(conference)
        client.force_login(admin_user)
        response = client.post(
            reverse("sponsorship:tier_delete", kwargs={"pk": tier.pk}), follow=True
        )
        assert response.status_code == 200
        assert not SponsorshipTier.objects.filter(pk=tier.pk).exists()

    def test_requires_admin(self, client, portal_user, conference):
        tier = self._tier(conference)
        client.force_login(portal_user)  # not staff/superuser
        assert client.get(reverse("sponsorship:tier_list")).status_code in (302, 403)
        assert client.get(reverse("sponsorship:tier_new")).status_code in (302, 403)
        for name in ["sponsorship:tier_edit", "sponsorship:tier_delete"]:
            url = reverse(name, kwargs={"pk": tier.pk})
            assert client.get(url).status_code in (302, 403)

    def test_list_scoped_to_selected_year(self, client, admin_user, conference):
        past = Conference.objects.create(
            year=2024, name="PyLadiesCon 2024", slug="2024"
        )
        active_tier = self._tier(conference, name="Active")
        past_tier = SponsorshipTier.objects.create(
            name="Past", amount=1, description="d", conference=past
        )
        client.force_login(admin_user)
        url = reverse("sponsorship:tier_list")

        default_tiers = list(client.get(url).context["tiers"])
        assert active_tier in default_tiers
        assert past_tier not in default_tiers

        switched = list(client.get(f"{url}?conference={past.pk}").context["tiers"])
        assert past_tier in switched
        assert active_tier not in switched

        # Invalid year falls back to the active edition.
        invalid = list(client.get(f"{url}?conference=99999").context["tiers"])
        assert active_tier in invalid


@pytest.mark.django_db
class TestSponsorActionsColumn:
    """The actions (edit/delete) column is hidden from read-only viewers."""

    def _profile(self, conference):
        tier = SponsorshipTier.objects.create(
            name="Gold", amount=5000, description="g", conference=conference
        )
        return SponsorshipProfile.objects.create(
            organization_name="Corp",
            sponsorship_tier=tier,
            progress_status=SponsorshipProgressStatus.APPROVED,
            conference=conference,
        )

    def test_actions_hidden_for_read_only_viewer(self, client, portal_user, conference):
        profile = self._profile(conference)
        VolunteerProfile.objects.create(
            user=portal_user,
            application_status=ApplicationStatus.APPROVED,
            conference=conference,
        )
        client.force_login(portal_user)
        response = client.get(reverse("sponsorship:sponsorship_list"))
        assert response.status_code == 200
        columns = [column.name for column in response.context["table"].columns]
        assert "actions" not in columns
        edit_url = reverse(
            "sponsorship:sponsorship_profile_edit", kwargs={"pk": profile.pk}
        )
        assert edit_url not in response.content.decode()

    def test_actions_shown_for_organizer(self, client, admin_user, conference):
        profile = self._profile(conference)
        client.force_login(admin_user)
        response = client.get(reverse("sponsorship:sponsorship_list"))
        assert response.status_code == 200
        columns = [column.name for column in response.context["table"].columns]
        assert "actions" in columns
        edit_url = reverse(
            "sponsorship:sponsorship_profile_edit", kwargs={"pk": profile.pk}
        )
        assert edit_url in response.content.decode()


@pytest.mark.django_db
class TestSponsorshipIndexRedirect:
    def test_root_redirects_to_list(self, client):
        response = client.get(reverse("sponsorship:index"))
        assert response.status_code == 302
        assert response.url == reverse("sponsorship:sponsorship_list")


@pytest.mark.django_db
class TestSponsorshipNeedsAttention:
    def _profile(self, conference, status):
        tier = SponsorshipTier.objects.create(
            name="T", amount=1, description="d", conference=conference
        )
        return SponsorshipProfile.objects.create(
            organization_name="Org",
            sponsorship_tier=tier,
            progress_status=status,
            conference=conference,
        )

    def test_attention_counts_for_manager(self, client, admin_user, conference):
        self._profile(conference, SponsorshipProgressStatus.AGREEMENT_SENT)
        self._profile(conference, SponsorshipProgressStatus.AGREEMENT_SIGNED)
        self._profile(conference, SponsorshipProgressStatus.INVOICED)
        self._profile(conference, SponsorshipProgressStatus.PAID)  # not flagged
        client.force_login(admin_user)
        response = client.get(reverse("sponsorship:sponsorship_list"))
        assert response.context["attention_unsigned"] == 1
        assert response.context["attention_awaiting_invoice"] == 1
        assert response.context["attention_unpaid"] == 1
        content = response.content.decode()
        assert "Needs attention" in content
        # Status links preserve scroll so the page doesn't jump on filter.
        assert "js-preserve-scroll" in content

    def test_no_attention_panel_for_read_only_viewer(
        self, client, portal_user, conference
    ):
        VolunteerProfile.objects.create(
            user=portal_user,
            application_status=ApplicationStatus.APPROVED,
            conference=conference,
        )
        client.force_login(portal_user)
        response = client.get(reverse("sponsorship:sponsorship_list"))
        assert "attention_unsigned" not in response.context
        assert "Needs attention" not in response.content.decode()

    def test_tier_filter_chip_narrows_list(self, client, admin_user, conference):
        tier_a = SponsorshipTier.objects.create(
            name="A", amount=1, description="d", conference=conference
        )
        tier_b = SponsorshipTier.objects.create(
            name="B", amount=2, description="d", conference=conference
        )
        SponsorshipProfile.objects.create(
            organization_name="OrgA",
            sponsorship_tier=tier_a,
            progress_status=SponsorshipProgressStatus.PAID,
            conference=conference,
        )
        SponsorshipProfile.objects.create(
            organization_name="OrgB",
            sponsorship_tier=tier_b,
            progress_status=SponsorshipProgressStatus.PAID,
            conference=conference,
        )
        client.force_login(admin_user)
        url = reverse("sponsorship:sponsorship_list") + f"?sponsorship_tier={tier_a.pk}"
        response = client.get(url)
        assert len(response.context["table"].rows) == 1
        assert response.context["selected_tier"] == str(tier_a.pk)

    def test_status_filter_chip_narrows_list(self, client, admin_user, conference):
        self._profile(conference, SponsorshipProgressStatus.INVOICED)
        self._profile(conference, SponsorshipProgressStatus.PAID)
        client.force_login(admin_user)
        url = (
            reverse("sponsorship:sponsorship_list")
            + f"?progress_status={SponsorshipProgressStatus.INVOICED.value}"
        )
        response = client.get(url)
        assert len(response.context["table"].rows) == 1
        assert response.context["selected_status"] == str(
            SponsorshipProgressStatus.INVOICED.value
        )
