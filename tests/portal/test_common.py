import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

from attendee.models import AttendeeProfile, PretixOrder, PretixOrderstatus
from portal.common import (
    get_sponsorship_committed_amount_stats_cache,
    get_sponsorship_committed_count_stats_cache,
    get_sponsorship_paid_amount_stats_cache,
    get_sponsorship_paid_percent_cache,
    get_sponsorship_pending_amount_stats_cache,
    get_sponsorship_pending_count_stats_cache,
    get_sponsorship_to_goal_percent_cache,
    get_sponsorship_total_count_stats_cache,
    get_stats_cached_values,
    get_volunteer_signup_stat_cache,
)
from portal.constants import (
    CACHE_KEY_SPONSORSHIP_COMMITTED,
    CACHE_KEY_SPONSORSHIP_COMMITTED_COUNT,
    CACHE_KEY_SPONSORSHIP_PAID,
    CACHE_KEY_SPONSORSHIP_PAID_PERCENT,
    CACHE_KEY_SPONSORSHIP_PENDING,
    CACHE_KEY_SPONSORSHIP_PENDING_COUNT,
    CACHE_KEY_SPONSORSHIP_TOWARDS_GOAL_PERCENT,
    CACHE_KEY_TOTAL_SPONSORSHIPS,
    CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT,
)
from sponsorship.models import (
    SponsorshipProfile,
    SponsorshipProgressStatus,
    SponsorshipTier,
)
from volunteer.models import VolunteerProfile


@pytest.mark.django_db
class TestGetStatsCachedValues:

    def test_get_volunteer_signup_stat_cache(self):
        """Test that the volunteer signup count is cached and returned correctly."""

        cache_key = CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT
        cache.delete(cache_key)

        result = get_volunteer_signup_stat_cache()
        assert result == 0
        cache.delete(cache_key)

        VolunteerProfile.objects.create(
            user=get_user_model().objects.create(username="testuser1"),
        )
        VolunteerProfile.objects.create(
            user=get_user_model().objects.create(username="testuser2"),
        )

        result = get_volunteer_signup_stat_cache()
        assert result == 2

    def test_get_stats_cached_values(self):
        """Test that the stats dictionary contains the volunteer signup count."""

        cache_key = CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT
        cache.delete(cache_key)

        stats = get_stats_cached_values()
        assert stats[CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT] == 0
        cache.delete(cache_key)

        VolunteerProfile.objects.create(
            user=get_user_model().objects.create(username="testuser1"),
        )
        VolunteerProfile.objects.create(
            user=get_user_model().objects.create(username="testuser2"),
        )

        result = get_stats_cached_values()
        assert result.get(CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT) == 2

    def test_get_sponsorship_total_counts_stats_does_not_count_not_contacted(self):
        cache_key = CACHE_KEY_TOTAL_SPONSORSHIPS
        cache.delete(cache_key)

        stats = get_stats_cached_values()
        assert stats[CACHE_KEY_TOTAL_SPONSORSHIPS] == 0
        cache.delete(cache_key)

        SponsorshipProfile.objects.create(
            organization_name="testorg1"
        )  # status is not contacted, is not counted
        SponsorshipProfile.objects.create(
            organization_name="testorg2",
            progress_status=SponsorshipProgressStatus.PAID.value,
        )
        SponsorshipProfile.objects.create(
            organization_name="testorg3",
            progress_status=SponsorshipProgressStatus.INVOICED.value,
        )

        result = get_sponsorship_total_count_stats_cache()
        assert result == 2

    def test_get_sponsorship_paid_amount_stats_cache(self):
        cache_key = CACHE_KEY_SPONSORSHIP_PAID
        cache.delete(cache_key)

        stats = get_stats_cached_values()
        assert stats[CACHE_KEY_SPONSORSHIP_PAID] == 0
        cache.delete(cache_key)
        tier_1 = SponsorshipTier.objects.create(name="Tier 1", amount=1000)

        SponsorshipProfile.objects.create(
            organization_name="testorg1",
            sponsorship_tier=tier_1,
            progress_status=SponsorshipProgressStatus.PAID.value,
        )
        SponsorshipProfile.objects.create(
            organization_name="testorg2",
            sponsorship_tier=tier_1,
            progress_status=SponsorshipProgressStatus.PAID.value,
            sponsorship_override_amount=900,
        )

        result = get_sponsorship_paid_amount_stats_cache()
        assert result == 1900

    def test_get_sponsorship_pending_amount_stats_cache(self):
        cache_key = CACHE_KEY_SPONSORSHIP_PENDING
        cache.delete(cache_key)

        stats = get_stats_cached_values()
        assert stats[CACHE_KEY_SPONSORSHIP_PENDING] == 0
        cache.delete(cache_key)
        tier_1 = SponsorshipTier.objects.create(name="Tier 1", amount=1000)

        SponsorshipProfile.objects.create(
            organization_name="testorg1",
            sponsorship_tier=tier_1,
            progress_status=SponsorshipProgressStatus.INVOICED.value,
        )
        SponsorshipProfile.objects.create(
            organization_name="testorg2",
            sponsorship_tier=tier_1,
            progress_status=SponsorshipProgressStatus.INVOICED.value,
            sponsorship_override_amount=900,
        )

        result = get_sponsorship_pending_amount_stats_cache()
        assert result == 1900

    def test_get_sponsorship_committed_amount_stats_cache(self):
        cache_key = CACHE_KEY_SPONSORSHIP_COMMITTED
        cache.delete(cache_key)

        stats = get_stats_cached_values()
        assert stats[CACHE_KEY_SPONSORSHIP_COMMITTED] == 0
        cache.delete(cache_key)
        tier_1 = SponsorshipTier.objects.create(name="Tier 1", amount=1000)

        SponsorshipProfile.objects.create(
            organization_name="testorg1",
            sponsorship_tier=tier_1,
            progress_status=SponsorshipProgressStatus.INVOICED.value,
        )
        SponsorshipProfile.objects.create(
            organization_name="testorg2",
            sponsorship_tier=tier_1,
            progress_status=SponsorshipProgressStatus.PAID.value,
            sponsorship_override_amount=900,
        )

        result = get_sponsorship_committed_amount_stats_cache()
        assert result == 1900

    def test_get_sponsorship_pending_count_stats_cache(self):
        cache_key = CACHE_KEY_SPONSORSHIP_PENDING_COUNT
        cache.delete(cache_key)

        stats = get_stats_cached_values()
        assert stats[CACHE_KEY_SPONSORSHIP_PENDING_COUNT] == 0
        cache.delete(cache_key)
        tier_1 = SponsorshipTier.objects.create(name="Tier 1", amount=1000)

        SponsorshipProfile.objects.create(
            organization_name="testorg1",
            sponsorship_tier=tier_1,
            progress_status=SponsorshipProgressStatus.INVOICED.value,
        )
        SponsorshipProfile.objects.create(
            organization_name="testorg2",
            sponsorship_tier=tier_1,
            progress_status=SponsorshipProgressStatus.INVOICED.value,
            sponsorship_override_amount=900,
        )

        result = get_sponsorship_pending_count_stats_cache()
        assert result == 2

    def test_get_sponsorship_committed_count_stats_cache(self):
        cache_key = CACHE_KEY_SPONSORSHIP_COMMITTED_COUNT
        cache.delete(cache_key)

        stats = get_stats_cached_values()
        assert stats[CACHE_KEY_SPONSORSHIP_COMMITTED_COUNT] == 0
        cache.delete(cache_key)
        tier_1 = SponsorshipTier.objects.create(name="Tier 1", amount=1000)

        SponsorshipProfile.objects.create(
            organization_name="testorg1",
            sponsorship_tier=tier_1,
            progress_status=SponsorshipProgressStatus.INVOICED.value,
        )
        SponsorshipProfile.objects.create(
            organization_name="testorg2",
            sponsorship_tier=tier_1,
            progress_status=SponsorshipProgressStatus.PAID.value,
            sponsorship_override_amount=900,
        )

        result = get_sponsorship_committed_count_stats_cache()
        assert result == 2

    def test_get_sponsorship_paid_percent_cache(self):
        cache_key = CACHE_KEY_SPONSORSHIP_PAID_PERCENT
        cache.delete(cache_key)

        stats = get_sponsorship_paid_percent_cache()
        assert stats == 0
        cache.delete(cache_key)

        tier_1 = SponsorshipTier.objects.create(name="Tier 1", amount=1000)
        SponsorshipProfile.objects.create(
            organization_name="testorg1",
            sponsorship_tier=tier_1,
            progress_status=SponsorshipProgressStatus.PAID,
        )
        SponsorshipProfile.objects.create(
            organization_name="testorg2",
            sponsorship_tier=tier_1,
            progress_status=SponsorshipProgressStatus.INVOICED,
        )

        result = get_sponsorship_paid_percent_cache()
        assert result == 50

    def test_get_sponsorship_to_goal_percent_cache(self):
        cache_key = CACHE_KEY_SPONSORSHIP_TOWARDS_GOAL_PERCENT
        cache.delete(cache_key)

        stats = get_sponsorship_to_goal_percent_cache()
        assert stats == 0
        cache.delete(cache_key)

        tier_1 = SponsorshipTier.objects.create(name="Tier 1", amount=1000)
        SponsorshipProfile.objects.create(
            organization_name="testorg1",
            sponsorship_tier=tier_1,
            progress_status=SponsorshipProgressStatus.PAID,
        )
        SponsorshipProfile.objects.create(
            organization_name="testorg2",
            sponsorship_tier=tier_1,
            progress_status=SponsorshipProgressStatus.PAID,
        )
        SponsorshipProfile.objects.create(
            organization_name="testorg3",
            sponsorship_tier=tier_1,
            progress_status=SponsorshipProgressStatus.PAID,
        )

        result = get_sponsorship_to_goal_percent_cache()
        assert result == 20


@pytest.mark.django_db
class TestAttendeeStats:
    """Test attendee statistics functions."""

    def test_attendee_breakdown_with_profiles(self):
        """Test attendee breakdown with various demographic data."""
        from portal.common import get_attendee_breakdown

        # Create paid orders with profiles
        order1 = PretixOrder.objects.create(
            order_code="ORDER1",
            status=PretixOrderstatus.PAID,
            email="test1@example.com",
        )
        AttendeeProfile.objects.create(
            order=order1,
            city="Vancouver",
            country="Canada",
            may_share_email_with_sponsor=True,
            experience_level="Intermediate",
            expectation_from_event=["Networking", "Learning"],
            heard_about=["Social Media"],
            participated_in_previous_event=["PyLadiesCon 2023"],
            pyladies_chapter="San Francisco",
            age_range="19-25",
            organization_name="Umbrella Corp",
            current_position=["Intern"],
        )

        order2 = PretixOrder.objects.create(
            order_code="ORDER2",
            status=PretixOrderstatus.PAID,
            email="test2@example.com",
        )
        AttendeeProfile.objects.create(
            order=order2,
            city="New New York",
            country="Canada",
            may_share_email_with_sponsor=False,
            experience_level="Junior",
            expectation_from_event=["Networking", "Speaking"],
            heard_about=["Meetup"],
            participated_in_previous_event=["PyLadiesCon 2024"],
            pyladies_chapter="San Francisco",
            age_range="19-25",
            organization_name="Umbrella Corp",
            current_position=["Director"],
        )

        order3 = PretixOrder.objects.create(
            order_code="ORDER3",
            status=PretixOrderstatus.PAID,
            email="test3@example.com",
        )
        AttendeeProfile.objects.create(
            order=order3,
            city="Raccoon City",
            country="United States",
            may_share_email_with_sponsor=True,
            experience_level="Expert",
            expectation_from_event=["Teaching"],
            heard_about=["Conference"],
            participated_in_previous_event=["PyLadiesCon 2023"],
            pyladies_chapter="San Francisco",
            age_range="19-25",
            organization_name="Umbrella Corp",
            current_position=["Manager"],
        )

        breakdown = get_attendee_breakdown()

        assert breakdown["attendee_current_position_breakdown"] == [
            ["Director", 1],
            ["Intern", 1],
            ["Manager", 1],
        ]
        assert breakdown["attendee_experience_breakdown"] == [
            ["Expert", 1],
            ["Intermediate", 1],
            ["Junior", 1],
        ]

    def test_attendee_breakdown_with_no_profiles(self):
        """Test attendee breakdown returns empty when no profiles exist."""
        from portal.common import get_attendee_breakdown

        cache.clear()
        breakdown = get_attendee_breakdown()
        assert breakdown["attendee_current_position_breakdown"] == []
        assert breakdown["attendee_experience_breakdown"] == []
