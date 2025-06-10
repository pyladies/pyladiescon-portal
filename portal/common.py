# from django.core.cache import cache
#
from portal.constants import CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT  # , STATS_CACHE_TIMEOUT
from volunteer.models import VolunteerProfile


def get_stats_cached_values():
    """Collect some stats and return them in a dictionary."""
    stats_dict = {}

    stats_dict[CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT] = get_volunteer_signup_stat_cache()

    return stats_dict


def get_volunteer_signup_stat_cache():
    """Returns the cached count of volunteer signups.
    Not using cache
    """
    # volunteer_signups_count = cache.get(CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT)
    # if not volunteer_signups_count:
    volunteer_signups_count = VolunteerProfile.objects.count()
    # cache.set(
    #     CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT,
    #     volunteer_signups_count,
    #     STATS_CACHE_TIMEOUT,
    # )
    return volunteer_signups_count
