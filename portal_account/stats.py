"""Account signup figures for the Maintenance section.

Everything here is derived from ``auth.User`` and allauth's ``EmailAddress``
at request time; nothing is cached or stored, so the page is always current.
"""

from datetime import timedelta

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Exists, OuterRef
from django.utils import timezone

from portal_account.cleanup import unverified_accounts

DAILY_RANGES = (30, 90)
DEFAULT_DAILY_RANGE = 30


def _with_verified_flag(queryset):
    verified = EmailAddress.objects.filter(user_id=OuterRef("pk"), verified=True)
    return queryset.annotate(has_verified_email=Exists(verified))


def _window(users, since):
    """Signups since ``since`` with their verified share, for the summary row."""
    rows = list(
        _with_verified_flag(users.filter(date_joined__gte=since)).values_list(
            "has_verified_email", flat=True
        )
    )
    signups = len(rows)
    verified = sum(1 for flag in rows if flag)
    return {
        "signups": signups,
        "verified": verified,
        "verified_percent": round(100 * verified / signups) if signups else 0,
    }


def daily_signups(days):
    """One row per calendar day for the last ``days`` days, oldest first.

    Each row carries the signups that day and how many of them later
    verified.
    """
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    users = get_user_model().objects.filter(
        date_joined__date__gte=start,
    )
    per_day = {start + timedelta(days=i): [0, 0] for i in range(days)}
    for joined, verified in _with_verified_flag(users).values_list(
        "date_joined", "has_verified_email"
    ):
        day = timezone.localtime(joined).date()
        per_day[day][0] += 1
        if verified:
            per_day[day][1] += 1
    return [
        {
            "date": day,
            "signups": signups,
            "verified": verified,
            "unverified": signups - verified,
        }
        for day, (signups, verified) in per_day.items()
    ]


def account_signup_stats(days=DEFAULT_DAILY_RANGE):
    """Totals, recent windows and the daily series for the Accounts page."""
    users = get_user_model().objects.all()
    now = timezone.now()
    today_start = timezone.make_aware(
        timezone.datetime.combine(timezone.localdate(), timezone.datetime.min.time())
    )
    verified_users = _with_verified_flag(users).filter(has_verified_email=True)
    retention_days = settings.UNVERIFIED_ACCOUNT_RETENTION_DAYS
    total = users.count()
    verified = verified_users.count()
    daily = daily_signups(days)
    return {
        "totals": {
            "accounts": total,
            "verified": verified,
            "unverified": total - verified,
            "never_logged_in": users.filter(last_login__isnull=True).count(),
            "pending_deletion": unverified_accounts(retention_days).count(),
        },
        "retention_days": retention_days,
        "windows": [
            {"label": "Today", **_window(users, today_start)},
            {"label": "Last 7 days", **_window(users, now - timedelta(days=7))},
            {"label": "Last 30 days", **_window(users, now - timedelta(days=30))},
        ],
        "days": days,
        "daily": daily,
        # [date, verified, unverified] per day, for the Google Charts column
        # chart on the Accounts page (same library as the public Stats page).
        "chart_rows": [
            [row["date"].isoformat(), row["verified"], row["unverified"]]
            for row in daily
        ],
    }
