import pytest
from django.contrib.auth import get_user_model

from portal.common import get_stats_cached_values, get_volunteer_signup_stat_cache
from portal.constants import CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT
from volunteer.models import VolunteerProfile

# from django.core.cache import cache


@pytest.mark.django_db
class TestGetStatsCachedValues:

    def test_get_volunteer_signup_stat_cache(self):
        """Test that the volunteer signup count is cached and returned correctly."""

        # cache_key = CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT
        # cache.delete(cache_key)

        result = get_volunteer_signup_stat_cache()
        assert result == 0

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

        # cache_key = CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT
        # cache.delete(cache_key)

        stats = get_stats_cached_values()
        assert stats[CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT] == 0

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
