from datetime import timedelta
from io import StringIO

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.core.management import call_command
from django.utils import timezone

from portal_account.cleanup import delete_unverified_accounts, unverified_accounts
from portal_account.tasks import delete_unverified_accounts_task


def make_user(username, *, days_old, verified=False, logged_in=False, staff=False):
    """A user joined ``days_old`` days ago with one email address."""
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", is_staff=staff
    )
    joined = timezone.now() - timedelta(days=days_old)
    User.objects.filter(pk=user.pk).update(
        date_joined=joined, last_login=joined if logged_in else None
    )
    EmailAddress.objects.create(
        user=user, email=user.email, primary=True, verified=verified
    )
    return user


@pytest.mark.django_db
class TestUnverifiedAccounts:
    def test_only_old_unverified_never_logged_in_non_staff(self):
        stale = make_user("stale", days_old=10)
        make_user("verified", days_old=10, verified=True)
        make_user("recent", days_old=2)
        make_user("logged_in", days_old=10, logged_in=True)
        make_user("staff", days_old=10, staff=True)
        User.objects.create_user(username="no_address")

        assert list(unverified_accounts(7)) == [stale]

    def test_delete_returns_count_and_dry_run_keeps_rows(self):
        make_user("stale", days_old=10)

        assert delete_unverified_accounts(7, dry_run=True) == 1
        assert User.objects.filter(username="stale").exists()
        assert delete_unverified_accounts(7) == 1
        assert not User.objects.filter(username="stale").exists()


@pytest.mark.django_db
class TestDeleteUnverifiedAccountsCommand:
    def test_deletes_and_reports(self, settings):
        settings.UNVERIFIED_ACCOUNT_RETENTION_DAYS = 7
        make_user("stale", days_old=10)
        keep = make_user("verified", days_old=10, verified=True)

        out = StringIO()
        call_command("delete_unverified_accounts", stdout=out)

        assert "Deleted 1 unverified account(s) older than 7 day(s)" in out.getvalue()
        assert list(User.objects.all()) == [keep]

    def test_dry_run_deletes_nothing(self, settings):
        settings.UNVERIFIED_ACCOUNT_RETENTION_DAYS = 7
        make_user("stale", days_old=10)

        out = StringIO()
        call_command("delete_unverified_accounts", "--dry-run", stdout=out)

        assert "Would delete 1 unverified account(s)" in out.getvalue()
        assert User.objects.filter(username="stale").exists()

    def test_days_override(self, settings):
        settings.UNVERIFIED_ACCOUNT_RETENTION_DAYS = 7
        make_user("three_days", days_old=3)

        out = StringIO()
        call_command("delete_unverified_accounts", "--days", "1", stdout=out)

        assert "older than 1 day(s)" in out.getvalue()
        assert not User.objects.filter(username="three_days").exists()


@pytest.mark.django_db
class TestDeleteUnverifiedAccountsTask:
    def test_task_runs_command(self, settings):
        settings.UNVERIFIED_ACCOUNT_RETENTION_DAYS = 7
        make_user("stale", days_old=10)

        result = delete_unverified_accounts_task.delay()

        assert result.get() == "Deleted 1 unverified account(s) older than 7 day(s)"
        assert not User.objects.filter(username="stale").exists()
