CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT = "volunteer_signups_count"
CACHE_KEY_VOLUNTEER_ONBOARDED_COUNT = "volunteer_onboarded_count"
CACHE_KEY_TEAMS_COUNT = "volunteer_teams_count"
CACHE_KEY_VOLUNTEER_LANGUAGES = "volunteer_languages_count"
CACHE_KEY_VOLUNTEER_PYLADIES_CHAPTERS = "volunteer_pyladies_chapters_count"

STATS_CACHE_TIMEOUT = 5 * 60  # 5 minutes

CACHE_KEY_TOTAL_SPONSORSHIPS = "sponsorship_total_count"
CACHE_KEY_SPONSORSHIP_PAID = "sponsorship_paid_amount"
CACHE_KEY_SPONSORSHIP_PENDING = "sponsorship_pending_amount"
CACHE_KEY_SPONSORSHIP_COMMITTED = "sponsorship_committed_amount"
CACHE_KEY_SPONSORSHIP_PAID_COUNT = "sponsorship_paid_count"
CACHE_KEY_SPONSORSHIP_PENDING_COUNT = "sponsorship_pending_count"
CACHE_KEY_SPONSORSHIP_COMMITTED_COUNT = "sponsorship_committed_count"
CACHE_KEY_SPONSORSHIP_PAID_PERCENT = "sponsorship_paid_percent"
CACHE_KEY_SPONSORSHIP_TOWARDS_GOAL_PERCENT = "sponsorship_towards_goal_percent"
CACHE_KEY_SPONSORSHIP_BREAKDOWN = "sponsorship_breakdown"
SPONSORSHIP_GOAL_AMOUNT = 15000

CACHE_KEY_VOLUNTEER_BREAKDOWN = "volunteer_breakdown"

DONATION_GOAL_AMOUNT = 2500
CACHE_KEY_DONATION_BREAKDOWN = "donation_breakdown"
CACHE_KEY_DONATIONS_TOTAL_AMOUNT = "donations_total_amount"
CACHE_KEY_DONORS_COUNT = "donors_count"
CACHE_KEY_DONATION_TOWARDS_GOAL_PERCENT = "donation_towards_goal_percent"

CACHE_KEY_TOTAL_FUNDS_RAISED = "total_funds_raised"


DONATIONS_GOAL = "donations_goal"
SPONSORSHIP_GOAL = "sponsorship_goal"

CACHE_KEY_ATTENDEE_COUNT = "attendee_count"
CACHE_KEY_ATTENDEE_FIRST_TIME_COUNT = "attendee_first_time_count"
CACHE_KEY_ATTENDEE_FIRST_TIME_PERCENT = "attendee_first_time_percent"

CACHE_KEY_ATTENDEE_BREAKDOWN = "attendee_breakdown"
CACHE_KEY_ATTENDEE_BY_ROLE = "attendee_by_role"
CACHE_KEY_ATTENDEE_BY_COUNTRY = "attendee_by_country"
CACHE_KEY_ATTENDEE_BY_EXPERIENCE = "attendee_by_experience"
CACHE_KEY_ATTENDEE_BY_INDUSTRY = "attendee_by_industry"
CACHE_KEY_ATTENDEE_BY_REGION = "attendee_by_region"

# Historical data for comparison charts
CACHE_KEY_HISTORICAL_COMPARISON = "historical_comparison"

# Historical data from past PyLadiesCon events
# Data source: https://conference.pyladies.com/2024-pyladiescon-ends/
HISTORICAL_STATS = {
    "2023": {
        "registrations": 600,
        "proposals": 164,
        "sponsors": 8,
        "sponsorship_amount": 10500,
        "donors": 58,
        "donation_amount": 650,
    },
    "2024": {
        "registrations": 732,
        "proposals": 192,
        "sponsors": 11,
        "sponsorship_amount": 10000,
        "donors": 105,
        "donation_amount": 1520,
    },
}

# Current year proposals count (not stored in database)
PROPOSALS_2025_COUNT = 194

BASE_PRETIX_URL = "https://pretix.eu/api/v1/"
