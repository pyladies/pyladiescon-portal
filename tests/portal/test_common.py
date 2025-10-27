import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

from portal.common import (
    get_sponsorship_committed_amount_stats_cache,
    get_sponsorship_committed_count_stats_cache,
    get_sponsorship_paid_amount_stats_cache,
    get_sponsorship_pending_amount_stats_cache,
    get_sponsorship_pending_count_stats_cache,
    get_sponsorship_total_count_stats_cache,
    get_stats_cached_values,
    get_volunteer_signup_stat_cache,
)
from portal.constants import (
    CACHE_KEY_SPONSORSHIP_COMMITTED,
    CACHE_KEY_SPONSORSHIP_COMMITTED_COUNT,
    CACHE_KEY_SPONSORSHIP_PAID,
    CACHE_KEY_SPONSORSHIP_PENDING,
    CACHE_KEY_SPONSORSHIP_PENDING_COUNT,
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
            languages_spoken=["en"],
        )
        VolunteerProfile.objects.create(
            user=get_user_model().objects.create(username="testuser2"),
            languages_spoken=["en"],
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
            languages_spoken=["en"],
        )
        VolunteerProfile.objects.create(
            user=get_user_model().objects.create(username="testuser2"),
            languages_spoken=["en"],
        )

        result = get_stats_cached_values()
        assert result.get(CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT) == 2

    def test_get_sponsorship_total_counts_stats(self):
        cache_key = CACHE_KEY_TOTAL_SPONSORSHIPS
        cache.delete(cache_key)

        stats = get_stats_cached_values()
        assert stats[CACHE_KEY_TOTAL_SPONSORSHIPS] == 0
        cache.delete(cache_key)

        SponsorshipProfile.objects.create(organization_name="testorg1")
        SponsorshipProfile.objects.create(organization_name="testorg2")

        result = get_sponsorship_total_count_stats_cache()
        assert result == 2

    def test_get_sponsorship_paid_amount_stats_cache(self):
        cache_key = CACHE_KEY_SPONSORSHIP_PAID
        cache.delete(cache_key)

        stats = get_stats_cached_values()
        assert stats[CACHE_KEY_SPONSORSHIP_PAID] == "$0"
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
        assert result == f"${1900:,.0f}"

    def test_get_sponsorship_pending_amount_stats_cache(self):
        cache_key = CACHE_KEY_SPONSORSHIP_PENDING
        cache.delete(cache_key)

        stats = get_stats_cached_values()
        assert stats[CACHE_KEY_SPONSORSHIP_PENDING] == "$0"
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
        assert result == f"${1900:,.0f}"

    def test_get_sponsorship_committed_amount_stats_cache(self):
        cache_key = CACHE_KEY_SPONSORSHIP_COMMITTED
        cache.delete(cache_key)

        stats = get_stats_cached_values()
        assert stats[CACHE_KEY_SPONSORSHIP_COMMITTED] == "$0"
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
        assert result == f"${1900:,.0f}"

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
