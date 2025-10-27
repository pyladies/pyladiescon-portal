from django.core.cache import cache
from django.db.models import Sum

from portal.constants import (
    CACHE_KEY_SPONSORSHIP_COMMITTED,
    CACHE_KEY_SPONSORSHIP_COMMITTED_COUNT,
    CACHE_KEY_SPONSORSHIP_PAID,
    CACHE_KEY_SPONSORSHIP_PAID_COUNT,
    CACHE_KEY_SPONSORSHIP_PAID_PERCENT,
    CACHE_KEY_SPONSORSHIP_PENDING,
    CACHE_KEY_SPONSORSHIP_PENDING_COUNT,
    CACHE_KEY_SPONSORSHIP_TOWARDS_GOAL_PERCENT,
    CACHE_KEY_TEAMS_COUNT,
    CACHE_KEY_TOTAL_SPONSORSHIPS,
    CACHE_KEY_VOLUNTEER_LANGUAGES,
    CACHE_KEY_VOLUNTEER_ONBOARDED_COUNT,
    CACHE_KEY_VOLUNTEER_PYLADIES_CHAPTERS,
    CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT,
    SPONSORSHIP_GOAL_AMOUNT,
    STATS_CACHE_TIMEOUT,
)
from sponsorship.models import SponsorshipProfile, SponsorshipProgressStatus
from volunteer.constants import ApplicationStatus
from volunteer.models import Team, VolunteerProfile


def get_stats_cached_values():
    """Collect some stats and return them in a dictionary."""
    stats_dict = {}

    stats_dict[CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT] = get_volunteer_signup_stat_cache()
    stats_dict[CACHE_KEY_VOLUNTEER_ONBOARDED_COUNT] = (
        get_volunteer_onboarded_stat_cache()
    )
    stats_dict[CACHE_KEY_TEAMS_COUNT] = get_volunteer_teams_stat_cache()
    stats_dict[CACHE_KEY_VOLUNTEER_LANGUAGES] = get_volunteer_languages_stat_cache()
    stats_dict[CACHE_KEY_VOLUNTEER_PYLADIES_CHAPTERS] = (
        get_volunteer_pyladies_chapters_stat_cache()
    )

    stats_dict.update(get_sponsorships_stats_dict())
    return stats_dict


def get_sponsorships_stats_dict():
    stats_dict = {}
    stats_dict[CACHE_KEY_TOTAL_SPONSORSHIPS] = get_sponsorship_total_count_stats_cache()
    stats_dict[CACHE_KEY_SPONSORSHIP_PAID] = get_sponsorship_paid_amount_stats_cache()
    stats_dict[CACHE_KEY_SPONSORSHIP_PAID_PERCENT] = (
        get_sponsorship_paid_percent_cache()
    )
    stats_dict[CACHE_KEY_SPONSORSHIP_TOWARDS_GOAL_PERCENT] = (
        get_sponsorship_to_goal_percent_cache()
    )

    stats_dict[CACHE_KEY_SPONSORSHIP_PENDING] = (
        get_sponsorship_pending_amount_stats_cache()
    )
    stats_dict[CACHE_KEY_SPONSORSHIP_COMMITTED] = (
        get_sponsorship_committed_amount_stats_cache()
    )
    stats_dict[CACHE_KEY_SPONSORSHIP_PAID_COUNT] = (
        get_sponsorship_paid_count_stats_cache()
    )
    stats_dict[CACHE_KEY_SPONSORSHIP_PENDING_COUNT] = (
        get_sponsorship_pending_count_stats_cache()
    )
    stats_dict[CACHE_KEY_SPONSORSHIP_COMMITTED_COUNT] = (
        get_sponsorship_committed_count_stats_cache()
    )

    return stats_dict


def get_volunteer_signup_stat_cache():
    """Returns the cached count of volunteer signups."""
    volunteer_signups_count = cache.get(CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT)
    if not volunteer_signups_count:
        volunteer_signups_count = VolunteerProfile.objects.count()
        cache.set(
            CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT,
            volunteer_signups_count,
            STATS_CACHE_TIMEOUT,
        )
    return volunteer_signups_count


def get_volunteer_onboarded_stat_cache():
    """Returns the cached count of volunteers onboarded."""
    volunteer_onboarded_count = cache.get(CACHE_KEY_VOLUNTEER_ONBOARDED_COUNT)
    if not volunteer_onboarded_count:
        volunteer_onboarded_count = VolunteerProfile.objects.filter(
            application_status=ApplicationStatus.APPROVED.value
        ).count()
        cache.set(
            CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT,
            volunteer_onboarded_count,
            STATS_CACHE_TIMEOUT,
        )
    return volunteer_onboarded_count


def get_volunteer_teams_stat_cache():
    """Returns the cached count of volunteer teams."""
    volunteer_teams_count = cache.get(CACHE_KEY_TEAMS_COUNT)
    if not volunteer_teams_count:
        volunteer_teams_count = Team.objects.count()
        cache.set(
            CACHE_KEY_TEAMS_COUNT,
            volunteer_teams_count,
            STATS_CACHE_TIMEOUT,
        )
    return volunteer_teams_count


def get_volunteer_languages_stat_cache():
    """Returns the cached count of volunteer languages."""
    volunteer_languages_count = cache.get(CACHE_KEY_VOLUNTEER_LANGUAGES)
    if not volunteer_languages_count:
        volunteer_languages_qs = VolunteerProfile.objects.annotate(
            num_languages=Sum("languages_spoken")
        ).values_list("languages_spoken", flat=True)
        volunteer_languages_count = volunteer_languages_qs.count()
        cache.set(
            CACHE_KEY_VOLUNTEER_LANGUAGES,
            volunteer_languages_count,
            STATS_CACHE_TIMEOUT,
        )
    return volunteer_languages_count


def get_volunteer_pyladies_chapters_stat_cache():
    volunteer_pyladies_chapters_count = cache.get(CACHE_KEY_VOLUNTEER_PYLADIES_CHAPTERS)
    if not volunteer_pyladies_chapters_count:
        volunteer_pyladies_chapters_count = VolunteerProfile.objects.filter(
            pyladies_chapter__isnull=False
        ).count()
        cache.set(
            CACHE_KEY_VOLUNTEER_PYLADIES_CHAPTERS,
            volunteer_pyladies_chapters_count,
            STATS_CACHE_TIMEOUT,
        )
    return volunteer_pyladies_chapters_count


SPONSOR_COMMITTED_STATUS = [
    SponsorshipProgressStatus.ACCEPTED,
    SponsorshipProgressStatus.APPROVED,
    SponsorshipProgressStatus.AGREEMENT_SENT,
    SponsorshipProgressStatus.AGREEMENT_SIGNED,
    SponsorshipProgressStatus.INVOICED,
    SponsorshipProgressStatus.PAID,
]
SPONSOR_PENDING_STATUS = [
    SponsorshipProgressStatus.ACCEPTED,
    SponsorshipProgressStatus.APPROVED,
    SponsorshipProgressStatus.AGREEMENT_SENT,
    SponsorshipProgressStatus.AGREEMENT_SIGNED,
    SponsorshipProgressStatus.INVOICED,
]


def get_sponsorship_total_count_stats_cache():
    """Returns total sponsorship count"""
    sponsorship_count = cache.get(CACHE_KEY_TOTAL_SPONSORSHIPS)
    if not sponsorship_count:
        sponsorship_count = SponsorshipProfile.objects.count()
        cache.set(CACHE_KEY_TOTAL_SPONSORSHIPS, sponsorship_count, STATS_CACHE_TIMEOUT)
    return sponsorship_count


def get_sponsorship_paid_amount_stats_cache():
    """Returns total sponsorship paid amount"""
    cache.delete(CACHE_KEY_SPONSORSHIP_PAID)
    total_paid = cache.get(CACHE_KEY_SPONSORSHIP_PAID)
    if not total_paid:
        paid_sponsors = SponsorshipProfile.objects.filter(
            progress_status=SponsorshipProgressStatus.PAID
        )
        paid_sponsors_no_override_qs = paid_sponsors.filter(
            sponsorship_override_amount__isnull=True, sponsorship_tier__isnull=False
        )
        if paid_sponsors_no_override_qs:
            paid_sponsors_no_override = paid_sponsors_no_override_qs.aggregate(
                Sum("sponsorship_tier__amount")
            )["sponsorship_tier__amount__sum"]
        else:
            paid_sponsors_no_override = 0

        paid_sponsors_with_override_qs = paid_sponsors.filter(
            sponsorship_override_amount__isnull=False
        )
        if paid_sponsors_with_override_qs:

            paid_sponsors_with_override = paid_sponsors_with_override_qs.aggregate(
                Sum("sponsorship_override_amount")
            )["sponsorship_override_amount__sum"]
        else:
            paid_sponsors_with_override = 0

        total_paid = paid_sponsors_no_override + paid_sponsors_with_override
        total_paid = total_paid
        cache.set(CACHE_KEY_SPONSORSHIP_PAID, total_paid, STATS_CACHE_TIMEOUT)
    return total_paid


def get_sponsorship_pending_amount_stats_cache():
    """Returns total sponsorship pending amount"""
    total_pending = cache.get(CACHE_KEY_SPONSORSHIP_PENDING)
    if not total_pending:
        pending_sponsors = SponsorshipProfile.objects.filter(
            progress_status__in=SPONSOR_PENDING_STATUS
        )
        pending_sponsors_no_override_qs = pending_sponsors.filter(
            sponsorship_override_amount__isnull=True, sponsorship_tier__isnull=False
        )
        if pending_sponsors_no_override_qs:
            pending_sponsors_no_override = pending_sponsors_no_override_qs.aggregate(
                Sum("sponsorship_tier__amount")
            )["sponsorship_tier__amount__sum"]
        else:
            pending_sponsors_no_override = 0

        pending_sponsors_with_override_qs = pending_sponsors.filter(
            sponsorship_override_amount__isnull=False
        )
        if pending_sponsors_with_override_qs:
            pending_sponsors_with_override = (
                pending_sponsors_with_override_qs.aggregate(
                    Sum("sponsorship_override_amount")
                )["sponsorship_override_amount__sum"]
            )
        else:
            pending_sponsors_with_override = 0

        total_pending = pending_sponsors_no_override + pending_sponsors_with_override
        total_pending = total_pending

    cache.set(CACHE_KEY_SPONSORSHIP_PENDING, total_pending, STATS_CACHE_TIMEOUT)
    return total_pending


def get_sponsorship_committed_amount_stats_cache():
    """Returns total sponsorship committed amount"""
    total_committed = cache.get(CACHE_KEY_SPONSORSHIP_COMMITTED)
    if not total_committed:
        committed_sponsors = SponsorshipProfile.objects.filter(
            progress_status__in=SPONSOR_COMMITTED_STATUS
        )
        committed_sponsors_no_override_qs = committed_sponsors.filter(
            sponsorship_override_amount__isnull=True, sponsorship_tier__isnull=False
        )
        if committed_sponsors_no_override_qs:
            committed_sponsors_no_override = (
                committed_sponsors_no_override_qs.aggregate(
                    Sum("sponsorship_tier__amount")
                )["sponsorship_tier__amount__sum"]
            )
        else:
            committed_sponsors_no_override = 0
        committed_sponsors_with_override_qs = committed_sponsors.filter(
            sponsorship_override_amount__isnull=False
        )
        if committed_sponsors_with_override_qs:
            committed_sponsors_with_override = (
                committed_sponsors_with_override_qs.aggregate(
                    Sum("sponsorship_override_amount")
                )["sponsorship_override_amount__sum"]
            )
        else:
            committed_sponsors_with_override = 0

        total_committed = (
            committed_sponsors_no_override + committed_sponsors_with_override
        )
        total_committed = total_committed
        cache.set(CACHE_KEY_SPONSORSHIP_COMMITTED, total_committed, STATS_CACHE_TIMEOUT)
    return total_committed


def get_sponsorship_paid_count_stats_cache():
    """Returns sponsorship paid count"""
    sponsorship_paid_count = cache.get(CACHE_KEY_SPONSORSHIP_PAID_COUNT)
    if not sponsorship_paid_count:
        sponsorship_paid_count = SponsorshipProfile.objects.filter(
            progress_status=SponsorshipProgressStatus.PAID
        ).count()
        cache.set(
            CACHE_KEY_SPONSORSHIP_PAID_COUNT,
            sponsorship_paid_count,
            STATS_CACHE_TIMEOUT,
        )
    return sponsorship_paid_count


def get_sponsorship_pending_count_stats_cache():
    """Returns sponsorship pending count"""
    sponsorship_pending_count = cache.get(CACHE_KEY_SPONSORSHIP_PENDING_COUNT)
    if not sponsorship_pending_count:
        sponsorship_pending_count = SponsorshipProfile.objects.filter(
            progress_status__in=SPONSOR_PENDING_STATUS
        ).count()
        cache.set(
            CACHE_KEY_SPONSORSHIP_PENDING_COUNT,
            sponsorship_pending_count,
            STATS_CACHE_TIMEOUT,
        )
    return sponsorship_pending_count


def get_sponsorship_committed_count_stats_cache():
    """Returns sponsorship committed count"""
    sponsorship_committed_count = cache.get(CACHE_KEY_SPONSORSHIP_COMMITTED_COUNT)
    if not sponsorship_committed_count:
        sponsorship_committed_count = SponsorshipProfile.objects.filter(
            progress_status__in=SPONSOR_COMMITTED_STATUS
        ).count()
        cache.set(
            CACHE_KEY_SPONSORSHIP_COMMITTED_COUNT,
            sponsorship_committed_count,
            STATS_CACHE_TIMEOUT,
        )
    return sponsorship_committed_count


def get_sponsorship_to_goal_percent_cache():
    """Returns sponsorship towards goal percent"""
    sponsorship_towards_goal_percent = cache.get(
        CACHE_KEY_SPONSORSHIP_TOWARDS_GOAL_PERCENT
    )
    if not sponsorship_towards_goal_percent:
        total_paid = get_sponsorship_paid_amount_stats_cache()
        sponsorship_towards_goal_percent = (
            (total_paid / SPONSORSHIP_GOAL_AMOUNT) * 100
            if SPONSORSHIP_GOAL_AMOUNT > 0
            else 0
        )
        cache.set(
            CACHE_KEY_SPONSORSHIP_TOWARDS_GOAL_PERCENT,
            sponsorship_towards_goal_percent,
            STATS_CACHE_TIMEOUT,
        )
    return sponsorship_towards_goal_percent


def get_sponsorship_paid_percent_cache():
    """Returns sponsorship paid percent"""
    sponsorship_paid_percent = cache.get(CACHE_KEY_SPONSORSHIP_PAID_PERCENT)
    if not sponsorship_paid_percent:
        total_sponsorships = get_sponsorship_committed_amount_stats_cache()
        total_paid_sponsorships = get_sponsorship_paid_amount_stats_cache()
        sponsorship_paid_percent = (
            (total_paid_sponsorships / total_sponsorships) * 100
            if total_sponsorships > 0
            else 0
        )
        cache.set(
            CACHE_KEY_SPONSORSHIP_PAID_PERCENT,
            sponsorship_paid_percent,
            STATS_CACHE_TIMEOUT,
        )
    return sponsorship_paid_percent
