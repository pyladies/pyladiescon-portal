from django.core.cache import cache
from django.db.models import Sum

from portal.constants import (
    CACHE_KEY_SPONSORSHIP_COMMITTED,
    CACHE_KEY_SPONSORSHIP_COMMITTED_COUNT,
    CACHE_KEY_SPONSORSHIP_PAID,
    CACHE_KEY_SPONSORSHIP_PAID_COUNT,
    CACHE_KEY_SPONSORSHIP_PENDING,
    CACHE_KEY_SPONSORSHIP_PENDING_COUNT,
    CACHE_KEY_TOTAL_SPONSORSHIPS,
    CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT,
    STATS_CACHE_TIMEOUT,
)
from sponsorship.models import SponsorshipProfile, SponsorshipProgressStatus
from volunteer.models import VolunteerProfile


def get_stats_cached_values():
    """Collect some stats and return them in a dictionary."""
    stats_dict = {}

    stats_dict[CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT] = get_volunteer_signup_stat_cache()
    stats_dict.update(get_sponsorships_stats_dict())
    return stats_dict


def get_sponsorships_stats_dict():
    stats_dict = {}
    stats_dict[CACHE_KEY_TOTAL_SPONSORSHIPS] = get_sponsorship_total_count_stats_cache()
    stats_dict[CACHE_KEY_SPONSORSHIP_PAID] = get_sponsorship_paid_amount_stats_cache()
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
        total_paid = f"${total_paid:,.0f}"
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
        total_pending = f"${total_pending:,.0f}"

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
        total_committed = f"${total_committed:,.0f}"
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
