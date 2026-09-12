"""Scheduled maintenance for portal accounts."""

from celery import shared_task
from django.conf import settings

from portal_account.cleanup import delete_unverified_accounts


@shared_task
def delete_unverified_accounts_task():
    """Delete stale unverified accounts.

    Scheduled through django-celery-beat (the "Delete unverified accounts"
    periodic task seeded by migration 0004); the return value is what the
    task result and the worker log record.
    """
    days = settings.UNVERIFIED_ACCOUNT_RETENTION_DAYS
    count = delete_unverified_accounts(days)
    return f"Deleted {count} unverified account(s) older than {days} day(s)"
