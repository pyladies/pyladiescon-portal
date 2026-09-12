import importlib
from datetime import timedelta

import pytest
from allauth.account.models import EmailAddress
from django.apps import apps
from django.contrib.auth.models import Group, User
from django.urls import reverse
from django.utils import timezone
from pytest_django.asserts import assertContains, assertNotContains

from portal.context_processors import user_capabilities
from portal_account.permissions import MAINTAINERS_GROUP, is_maintainer
from portal_account.stats import account_signup_stats, daily_signups
from tests.portal.test_context_processors import _request

migration = importlib.import_module("portal_account.migrations.0004_maintenance_setup")


@pytest.fixture
def maintainers_group(db):
    """The group the data migration creates; tests run without migrations."""
    migration.create_maintainers_group(apps, None)
    return Group.objects.get(name=MAINTAINERS_GROUP)


@pytest.fixture
def maintainer(maintainers_group):
    """A non-staff user whose only capability is the maintainers group."""
    user = User.objects.create_user(username="maintainer", email="m@example.com")
    user.groups.add(maintainers_group)
    return user


def signup(username, *, days_ago, verified=False):
    """A user who joined ``days_ago`` days ago, optionally verified."""
    user = User.objects.create_user(username=username, email=f"{username}@x.org")
    User.objects.filter(pk=user.pk).update(
        date_joined=timezone.now() - timedelta(days=days_ago)
    )
    EmailAddress.objects.create(
        user=user, email=user.email, primary=True, verified=verified
    )
    return user


@pytest.mark.django_db
class TestMaintainersGroup:
    def test_migration_creates_group_with_permission(self, maintainers_group):
        codenames = maintainers_group.permissions.values_list("codename", flat=True)
        assert list(codenames) == ["view_maintenance"]

    def test_migration_is_idempotent(self, maintainers_group):
        migration.create_maintainers_group(apps, None)
        assert Group.objects.filter(name=MAINTAINERS_GROUP).count() == 1

    def test_reverse_removes_group(self, maintainers_group):
        migration.delete_maintainers_group(apps, None)
        assert not Group.objects.filter(name=MAINTAINERS_GROUP).exists()

    def test_membership_grants_maintainer(self, portal_user, maintainer):
        assert is_maintainer(portal_user) is False
        assert is_maintainer(maintainer) is True

    def test_superuser_is_maintainer_without_group(self, admin_user):
        assert is_maintainer(admin_user) is True

    def test_staff_alone_is_not_maintainer(self, portal_user):
        # Organizer (staff) and maintainer are independent capabilities.
        portal_user.is_staff = True
        portal_user.save()
        assert is_maintainer(portal_user) is False

    def test_capability_flag(self, portal_user, maintainer, conference):
        assert user_capabilities(_request(portal_user))["is_maintainer"] is False
        assert user_capabilities(_request(maintainer))["is_maintainer"] is True
        assert user_capabilities(_request())["is_maintainer"] is False


@pytest.mark.django_db
class TestMaintenanceAccountsView:
    url = reverse("maintenance_accounts")

    def test_anonymous_redirected_to_login(self, client):
        response = client.get(self.url)
        assert response.status_code == 302
        assert reverse("account_login") in response["Location"]

    def test_regular_user_forbidden(self, client, portal_user):
        client.force_login(portal_user)
        assert client.get(self.url).status_code == 403

    def test_organizer_without_group_forbidden(self, client, portal_user):
        portal_user.is_staff = True
        portal_user.save()
        client.force_login(portal_user)
        assert client.get(self.url).status_code == 403

    def test_maintainer_renders(self, client, maintainer):
        client.force_login(maintainer)
        response = client.get(self.url)
        assertContains(response, "Pending deletion")
        assertContains(response, "Signups per day, last 30 days")
        assertContains(response, "gstatic.com/charts/loader.js")
        assertContains(response, 'id="signup-chart-rows"')
        assertContains(response, "showTextEvery: 7")
        assertContains(response, "Show as table")

    def test_superuser_renders(self, client, admin_user):
        client.force_login(admin_user)
        assert client.get(self.url).status_code == 200

    def test_user_menu_link_only_for_maintainers(self, client, portal_user, maintainer):
        # ``index`` sends logged-in users on to their hub; follow it.
        client.force_login(portal_user)
        response = client.get(reverse("index"), follow=True)
        assertNotContains(response, 'href="/maintenance/"')
        client.force_login(maintainer)
        response = client.get(reverse("index"), follow=True)
        assertContains(response, 'href="/maintenance/"')

    def test_organize_rail_section_only_for_maintainers(
        self, client, portal_user, admin_user, conference
    ):
        # An organizer who is not a maintainer gets no Maintenance section.
        portal_user.is_staff = True
        portal_user.save()
        client.force_login(portal_user)
        response = client.get(reverse("organizer_dashboard"))
        assertNotContains(response, 'href="/maintenance/"')
        # A superuser is both, so the Organize rail shows the section.
        client.force_login(admin_user)
        response = client.get(reverse("organizer_dashboard"))
        assertContains(response, 'href="/maintenance/"')

    @pytest.mark.parametrize(
        "query, expected",
        [("", 30), ("?days=90", 90), ("?days=7", 30), ("?days=x", 30)],
    )
    def test_days_range(self, client, admin_user, query, expected):
        client.force_login(admin_user)
        response = client.get(self.url + query)
        assert response.context["days"] == expected
        assert len(response.context["daily"]) == expected
        assert response.context["label_every"] == (7 if expected == 30 else 15)


@pytest.mark.django_db
class TestAccountSignupStats:
    def test_totals_and_windows(self, settings):
        settings.UNVERIFIED_ACCOUNT_RETENTION_DAYS = 7
        signup("today_ok", days_ago=0, verified=True)
        signup("today_no", days_ago=0)
        signup("week_no", days_ago=3)
        signup("old_no", days_ago=20)  # unverified past the window
        signup("old_ok", days_ago=40, verified=True)

        stats = account_signup_stats()

        assert stats["totals"] == {
            "accounts": 5,
            "verified": 2,
            "unverified": 3,
            "never_logged_in": 5,
            "pending_deletion": 1,
        }
        assert stats["retention_days"] == 7
        today, week, month = stats["windows"]
        assert (today["signups"], today["verified"], today["verified_percent"]) == (
            2,
            1,
            50,
        )
        assert (week["signups"], week["verified"]) == (3, 1)
        assert (month["signups"], month["verified_percent"]) == (4, 25)

    def test_daily_series_is_oldest_first_and_scaled_to_busiest_day(self):
        signup("a", days_ago=0, verified=True)
        signup("b", days_ago=0)
        signup("c", days_ago=1)

        daily = daily_signups(3)

        assert [row["signups"] for row in daily] == [0, 1, 2]
        assert daily[-1] == {
            "date": timezone.localdate(),
            "signups": 2,
            "verified": 1,
            "unverified": 1,
        }

    def test_chart_rows_are_json_friendly(self):
        signup("a", days_ago=0, verified=True)
        signup("b", days_ago=0)

        rows = account_signup_stats(days=2)["chart_rows"]

        assert rows[-1] == [timezone.localdate().isoformat(), 1, 1]
        assert rows[0][1:] == [0, 0]

    def test_empty_database(self):
        stats = account_signup_stats()
        assert stats["totals"]["accounts"] == 0
        assert stats["windows"][0]["verified_percent"] == 0
        assert all(row["signups"] == 0 for row in stats["daily"])
        assert all(row[1:] == [0, 0] for row in stats["chart_rows"])
