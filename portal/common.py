from django.core.cache import cache
from django.db.models import Count, Sum

from attendee.models import AttendeeProfile, PretixOrder
from portal.constants import (
    CACHE_KEY_ATTENDEE_BREAKDOWN,
    CACHE_KEY_ATTENDEE_COUNT,
    CACHE_KEY_DONATION_BREAKDOWN,
    CACHE_KEY_DONATION_TOWARDS_GOAL_PERCENT,
    CACHE_KEY_DONATIONS_TOTAL_AMOUNT,
    CACHE_KEY_DONORS_COUNT,
    CACHE_KEY_SPONSORSHIP_BREAKDOWN,
    CACHE_KEY_SPONSORSHIP_COMMITTED,
    CACHE_KEY_SPONSORSHIP_COMMITTED_COUNT,
    CACHE_KEY_SPONSORSHIP_PAID,
    CACHE_KEY_SPONSORSHIP_PAID_COUNT,
    CACHE_KEY_SPONSORSHIP_PAID_PERCENT,
    CACHE_KEY_SPONSORSHIP_PENDING,
    CACHE_KEY_SPONSORSHIP_PENDING_COUNT,
    CACHE_KEY_SPONSORSHIP_TOWARDS_GOAL_PERCENT,
    CACHE_KEY_TEAMS_COUNT,
    CACHE_KEY_TOTAL_FUNDS_RAISED,
    CACHE_KEY_TOTAL_SPONSORSHIPS,
    CACHE_KEY_VOLUNTEER_BREAKDOWN,
    CACHE_KEY_VOLUNTEER_LANGUAGES,
    CACHE_KEY_VOLUNTEER_ONBOARDED_COUNT,
    CACHE_KEY_VOLUNTEER_PYLADIES_CHAPTERS,
    CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT,
    DONATION_GOAL_AMOUNT,
    DONATIONS_GOAL,
    SPONSORSHIP_GOAL,
    SPONSORSHIP_GOAL_AMOUNT,
    STATS_CACHE_TIMEOUT,
)
from sponsorship.models import (
    IndividualDonation,
    SponsorshipProfile,
    SponsorshipProgressStatus,
)
from volunteer.constants import ApplicationStatus
from volunteer.models import Team, VolunteerProfile


def get_stats_cached_values():
    """Collect some stats and return them in a dictionary."""
    stats_dict = {}

    stats_dict.update(get_volunteer_stats_dict())

    stats_dict.update(get_sponsorships_stats_dict())
    stats_dict.update(get_donations_stats_dict())
    stats_dict.update(get_attendee_stats_dict())
    return stats_dict


def get_volunteer_stats_dict():
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
    stats_dict[CACHE_KEY_VOLUNTEER_BREAKDOWN] = get_volunteer_breakdown()
    return stats_dict


def get_sponsorships_stats_dict():
    stats_dict = {}
    stats_dict[SPONSORSHIP_GOAL] = SPONSORSHIP_GOAL_AMOUNT
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
    stats_dict[CACHE_KEY_SPONSORSHIP_BREAKDOWN] = get_sponsorship_breakdown()
    stats_dict[CACHE_KEY_TOTAL_FUNDS_RAISED] = (
        get_total_donations_amount_cache()
        + get_sponsorship_committed_amount_stats_cache()
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
            CACHE_KEY_VOLUNTEER_ONBOARDED_COUNT,
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
        volunteer_languages_qs = (
            VolunteerProfile.objects.filter(language__isnull=False)
            .distinct()
            .select_related("language")
        )
        volunteer_languages_count = volunteer_languages_qs.values_list(
            "language__id"
        ).count()
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
            chapter__isnull=False
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
        sponsorship_count = SponsorshipProfile.objects.filter(
            progress_status__gt=SponsorshipProgressStatus.NOT_CONTACTED
        ).count()
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


def get_sponsorship_breakdown():
    sponsorship_breakdown = cache.get(CACHE_KEY_SPONSORSHIP_BREAKDOWN)
    if not sponsorship_breakdown:
        sponsorship_breakdown = []

        # Breakdown by Status
        sponsors = SponsorshipProfile.objects.filter(
            progress_status__gt=SponsorshipProgressStatus.NOT_CONTACTED
        ).select_related("sponsorship_tier")
        sponsors_by_status = sponsors.values("progress_status").annotate(
            count=Count("id")
        )
        result = [
            [SponsorshipProgressStatus(data["progress_status"]).label, data["count"]]
            for data in sponsors_by_status
        ]
        sponsorship_breakdown.append(
            {
                "title": "Sponsors By Status",
                "columns": [["string", "Progress"], ["number", "Count"]],
                "data": result,
                "chart_id": "sponsorship_by_status",
            }
        )

        # breakdown by Tier
        sponsors_by_tier = (
            sponsors.filter(sponsorship_tier__isnull=False)
            .values("sponsorship_tier__name")
            .annotate(count=Count("id"))
        )
        result = [
            [data["sponsorship_tier__name"], data["count"]] for data in sponsors_by_tier
        ]
        sponsorship_breakdown.append(
            {
                "title": "Sponsors By Tier",
                "columns": [["string", "Sponsorship Tier"], ["number", "Count"]],
                "data": result,
                "chart_id": "sponsorship_by_tier",
            }
        )

        cache.set(
            CACHE_KEY_SPONSORSHIP_BREAKDOWN,
            sponsorship_breakdown,
            STATS_CACHE_TIMEOUT,
        )
    return sponsorship_breakdown


def get_volunteer_breakdown():
    """Returns the volunteer breakdown stats"""
    volunteer_breakdown = cache.get(CACHE_KEY_VOLUNTEER_BREAKDOWN)

    if not volunteer_breakdown:
        volunteer_breakdown = []

        # Breakdown by chapter
        volunteers = VolunteerProfile.objects.all().select_related(
            "chapter", "region", "language"
        )
        volunteers_by_chapter = (
            volunteers.filter(chapter__isnull=False)
            .values("chapter__chapter_description")
            .annotate(count=Count("id"))
        )
        result = [
            [data["chapter__chapter_description"], data["count"]]
            for data in volunteers_by_chapter
        ]
        volunteer_breakdown.append(
            {
                "title": "Volunteers By Chapter",
                "columns": ["Chapter", "Volunteers"],
                "data": result,
                "chart_id": "volunteer_by_chapter",
            }
        )

        # Breakdown by region
        volunteers_by_region = (
            volunteers.filter(region__isnull=False)
            .values("region")
            .annotate(count=Count("id"))
        )
        result = [[data["region"], data["count"]] for data in volunteers_by_region]
        volunteer_breakdown.append(
            {
                "title": "Volunteers By Region",
                "columns": ["Region", "Volunteers"],
                "data": result,
                "chart_id": "volunteers_by_region",
            }
        )

        # Breakdown by languages
        volunteers_by_languages = (
            volunteers.filter(language__isnull=False)
            .values("language__name")
            .annotate(count=Count("id"))
        )
        result = [
            [data["language__name"], data["count"]] for data in volunteers_by_languages
        ]
        volunteer_breakdown.append(
            {
                "title": "Volunteers By Languages",
                "columns": ["Language", "Volunteers"],
                "data": result,
                "chart_id": "volunteers_by_languages",
            }
        )

        cache.set(
            CACHE_KEY_VOLUNTEER_BREAKDOWN,
            volunteer_breakdown,
            STATS_CACHE_TIMEOUT,
        )
    return volunteer_breakdown


def get_total_donations_amount_cache():
    """Returns the donations amount"""
    total_donations = cache.get(CACHE_KEY_DONATIONS_TOTAL_AMOUNT)
    if not total_donations:

        individual_donations = (
            IndividualDonation.objects.aggregate(Sum("donation_amount"))[
                "donation_amount__sum"
            ]
            or 0
        )
        donations_from_pretix = (
            PretixOrder.objects.filter(status="p").aggregate(Sum("total"))["total__sum"]
            or 0
        )
        total_donations = individual_donations + donations_from_pretix
        cache.set(
            CACHE_KEY_DONATIONS_TOTAL_AMOUNT,
            total_donations,
            STATS_CACHE_TIMEOUT,
        )
    return total_donations


def get_donors_count_cache():
    """Returns the number of unique donors"""
    donors_count = cache.get(CACHE_KEY_DONORS_COUNT)
    if not donors_count:

        individual_donors_count = (
            IndividualDonation.objects.values("donor_email").distinct().count()
        )
        pretix_donors_count = PretixOrder.objects.filter(
            status="p", total__gt=0
        ).count()
        donors_count = individual_donors_count + pretix_donors_count
        cache.set(
            CACHE_KEY_DONORS_COUNT,
            donors_count,
            STATS_CACHE_TIMEOUT,
        )
    return donors_count


def get_donation_to_goal_percent_cache():
    """Returns donation towards goal percent"""
    donation_towards_goal_percent = cache.get(CACHE_KEY_DONATION_TOWARDS_GOAL_PERCENT)
    if not donation_towards_goal_percent:
        total_donations = get_total_donations_amount_cache()
        donation_towards_goal_percent = (
            (total_donations / DONATION_GOAL_AMOUNT) * 100
            if DONATION_GOAL_AMOUNT > 0
            else 0
        )
        cache.set(
            CACHE_KEY_DONATION_TOWARDS_GOAL_PERCENT,
            donation_towards_goal_percent,
            STATS_CACHE_TIMEOUT,
        )
    return donation_towards_goal_percent


def get_donations_stats_dict():
    stats_dict = {}
    stats_dict[DONATIONS_GOAL] = DONATION_GOAL_AMOUNT
    stats_dict[CACHE_KEY_DONATION_BREAKDOWN] = {
        "total_donations_amount": get_total_donations_amount_cache(),
        "donors_count": get_donors_count_cache(),
        "donation_towards_goal_percent": get_donation_to_goal_percent_cache(),
    }
    return stats_dict


def get_attendee_count_cache():
    """Returns the attendee count"""
    attendee_count = cache.get(CACHE_KEY_ATTENDEE_COUNT)
    if not attendee_count:
        attendee_count = PretixOrder.objects.filter(status="p").count()
        cache.set(
            CACHE_KEY_ATTENDEE_COUNT,
            attendee_count,
            STATS_CACHE_TIMEOUT,
        )
    return attendee_count


def get_attendee_stats_dict():
    stats_dict = {}
    stats_dict[CACHE_KEY_ATTENDEE_COUNT] = get_attendee_count_cache()
    stats_dict[CACHE_KEY_ATTENDEE_BREAKDOWN] = get_attendee_breakdown()
    return stats_dict


def get_attendee_breakdown():
    """Returns the attendee demographic breakdown stats."""
    attendee_breakdown = cache.get(CACHE_KEY_ATTENDEE_BREAKDOWN)

    if not attendee_breakdown:
        attendee_breakdown = []

        # Get all paid attendee profiles
        profiles = AttendeeProfile.objects.filter(order__status="p").select_related(
            "order"
        )

        # Breakdown by role
        profiles_by_role = (
            profiles.filter(job_role__isnull=False)
            .values("job_role")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        if profiles_by_role.exists():
            result = [[data["job_role"], data["count"]] for data in profiles_by_role]
            attendee_breakdown.append(
                {
                    "title": "Attendees By Role",
                    "columns": [["string", "Role"], ["number", "Count"]],
                    "data": result,
                    "chart_id": "attendee_by_role",
                }
            )

        # Breakdown by country
        profiles_by_country = (
            profiles.filter(country__isnull=False)
            .values("country")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        if profiles_by_country.exists():
            result = [[data["country"], data["count"]] for data in profiles_by_country]
            attendee_breakdown.append(
                {
                    "title": "Attendees By Country",
                    "columns": [["string", "Country"], ["number", "Count"]],
                    "data": result,
                    "chart_id": "attendee_by_country",
                }
            )

        # Breakdown by region
        profiles_by_region = (
            profiles.filter(region__isnull=False)
            .values("region")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        if profiles_by_region.exists():
            result = [[data["region"], data["count"]] for data in profiles_by_region]
            attendee_breakdown.append(
                {
                    "title": "Attendees By Region",
                    "columns": [["string", "Region"], ["number", "Count"]],
                    "data": result,
                    "chart_id": "attendee_by_region",
                }
            )

        # Breakdown by experience level
        profiles_by_experience = (
            profiles.filter(experience_level__isnull=False)
            .values("experience_level")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        if profiles_by_experience.exists():
            result = [
                [data["experience_level"], data["count"]]
                for data in profiles_by_experience
            ]
            attendee_breakdown.append(
                {
                    "title": "Attendees By Experience Level",
                    "columns": [["string", "Experience Level"], ["number", "Count"]],
                    "data": result,
                    "chart_id": "attendee_by_experience",
                }
            )

        # Breakdown by industry
        profiles_by_industry = (
            profiles.filter(industry__isnull=False)
            .values("industry")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        if profiles_by_industry.exists():
            result = [
                [data["industry"], data["count"]] for data in profiles_by_industry
            ]
            attendee_breakdown.append(
                {
                    "title": "Attendees By Industry",
                    "columns": [["string", "Industry"], ["number", "Count"]],
                    "data": result,
                    "chart_id": "attendee_by_industry",
                }
            )

        # Breakdown by company size
        profiles_by_company_size = (
            profiles.filter(company_size__isnull=False)
            .values("company_size")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        if profiles_by_company_size.exists():
            result = [
                [data["company_size"], data["count"]]
                for data in profiles_by_company_size
            ]
            attendee_breakdown.append(
                {
                    "title": "Attendees By Company Size",
                    "columns": [["string", "Company Size"], ["number", "Count"]],
                    "data": result,
                    "chart_id": "attendee_by_company_size",
                }
            )

        cache.set(
            CACHE_KEY_ATTENDEE_BREAKDOWN,
            attendee_breakdown,
            STATS_CACHE_TIMEOUT,
        )

    return attendee_breakdown
