"""Deletion of accounts that never verified their email address.

The verification email promises recipients that an unverified account is
deleted after ``UNVERIFIED_ACCOUNT_RETENTION_DAYS``; the functions here keep
that promise, whether run by the scheduled task or by hand through the
``delete_unverified_accounts`` management command. Why unverified accounts
are ephemeral is documented in ``docs/architecture/signup-abuse-protection.md``.
"""

from datetime import timedelta

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.db.models import Exists, OuterRef
from django.utils import timezone


def unverified_accounts(older_than_days):
    """Users past the retention window with no verified address and no login.

    Staff and superusers are never candidates, whatever their state.
    """
    cutoff = timezone.now() - timedelta(days=older_than_days)
    verified = EmailAddress.objects.filter(user_id=OuterRef("pk"), verified=True)
    return (
        get_user_model()
        .objects.filter(
            date_joined__lt=cutoff,
            last_login__isnull=True,
            is_staff=False,
            is_superuser=False,
        )
        .annotate(has_verified_email=Exists(verified))
        .filter(has_verified_email=False)
    )


def delete_unverified_accounts(older_than_days, dry_run=False):
    """Delete the accounts ``unverified_accounts`` selects; return how many.

    With ``dry_run`` nothing is deleted and the count is what a real run
    would remove.
    """
    users = unverified_accounts(older_than_days)
    count = users.count()
    if not dry_run:
        users.delete()
    return count
