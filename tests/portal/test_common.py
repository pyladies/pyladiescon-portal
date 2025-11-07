import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

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

    def test_individual_donations_stats(self):
        """Test individual donations count and amount calculation"""
        from portal.common import (
            get_corporate_sponsors_amount_cache,
            get_corporate_sponsors_count_cache,
            get_individual_donations_amount_cache,
            get_individual_donations_count_cache,
            get_total_funds_raised_cache,
        )
        from portal.constants import (
            CACHE_KEY_CORPORATE_SPONSORS_AMOUNT,
            CACHE_KEY_CORPORATE_SPONSORS_COUNT,
            CACHE_KEY_INDIVIDUAL_DONATIONS_AMOUNT,
            CACHE_KEY_INDIVIDUAL_DONATIONS_COUNT,
            CACHE_KEY_TOTAL_FUNDS_RAISED,
        )

        # Clear caches
        cache.delete(CACHE_KEY_INDIVIDUAL_DONATIONS_COUNT)
        cache.delete(CACHE_KEY_INDIVIDUAL_DONATIONS_AMOUNT)
        cache.delete(CACHE_KEY_CORPORATE_SPONSORS_COUNT)
        cache.delete(CACHE_KEY_CORPORATE_SPONSORS_AMOUNT)
        cache.delete(CACHE_KEY_TOTAL_FUNDS_RAISED)

        # Create tier
        tier = SponsorshipTier.objects.create(
            name="Individual Tier", amount=100, description="For individuals"
        )

        # Create individual donations (paid)
        SponsorshipProfile.objects.create(
            organization_name="John Doe",
            sponsorship_tier=tier,
            progress_status=SponsorshipProgressStatus.PAID,
            is_individual_donation=True,
        )
        SponsorshipProfile.objects.create(
            organization_name="Jane Smith",
            sponsorship_override_amount=50,
            progress_status=SponsorshipProgressStatus.PAID,
            is_individual_donation=True,
        )

        # Create corporate sponsor (paid)
        corporate_tier = SponsorshipTier.objects.create(
            name="Gold", amount=5000, description="Gold sponsor"
        )
        SponsorshipProfile.objects.create(
            organization_name="Corp Inc",
            sponsorship_tier=corporate_tier,
            progress_status=SponsorshipProgressStatus.PAID,
            is_individual_donation=False,
        )

        # Test individual donations
        individual_count = get_individual_donations_count_cache()
        assert individual_count == 2

        individual_amount = get_individual_donations_amount_cache()
        assert individual_amount == 150  # 100 + 50

        # Test corporate sponsors
        corporate_count = get_corporate_sponsors_count_cache()
        assert corporate_count == 1

        corporate_amount = get_corporate_sponsors_amount_cache()
        assert corporate_amount == 5000

        # Test total funds
        total_funds = get_total_funds_raised_cache()
        assert total_funds == 5150  # 150 + 5000
