"""The group admin shows its members from the group's side."""

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth.models import Group, Permission, User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from portal.models import Conference
from volunteer.constants import ApplicationStatus
from volunteer.models import VolunteerProfile

CHANGELIST = reverse("admin:auth_group_changelist")


def account(username, conference=None, *, verified=True, status=None, active=True):
    user = User.objects.create_user(
        username=username, email=f"{username}@x.org", first_name=username.title()
    )
    if not active:
        User.objects.filter(pk=user.pk).update(is_active=False)
    if verified:
        EmailAddress.objects.create(user=user, email=user.email, verified=True)
    if status is not None:
        VolunteerProfile.objects.create(
            user=user, conference=conference, application_status=status
        )
    return user


def change_url(group):
    return reverse("admin:auth_group_change", args=[group.pk])


@pytest.fixture
def group(db):
    return Group.objects.create(name="Infra maintainers")


@pytest.fixture
def ada(conference):
    return account("ada", conference, status=ApplicationStatus.APPROVED)


@pytest.mark.django_db
class TestCandidates:
    def test_this_years_approved_verified_volunteers_and_current_members(
        self, client, admin_user, conference, group, ada
    ):
        account("pen", conference, status=ApplicationStatus.PENDING)
        account("raw", conference, verified=False, status=ApplicationStatus.APPROVED)
        account("gone", conference, status=ApplicationStatus.APPROVED, active=False)
        old = Conference.objects.create(year=2020, name="2020", slug="2020")
        account("past", old, status=ApplicationStatus.APPROVED)
        stale = account("stale", old, status=ApplicationStatus.APPROVED)
        group.user_set.add(stale)
        client.force_login(admin_user)
        response = client.get(change_url(group))
        field = response.context["adminform"].form.fields["users"]
        assert {u.username for u in field.queryset} == {"ada", "stale"}
        assert [field.label_from_instance(u) for u in field.queryset] == [
            "Ada (ada)",
            "Stale (stale), not volunteering this year",
        ]
        assert response.context["adminform"].form.initial["users"] == [stale.pk]
        # The box is the same widget the permissions use: the select is
        # marked for SelectFilter2.js, which builds the two lists.
        content = response.content.decode()
        assert 'name="users"' in content and "SelectFilter2" in content
        assert content.count('class="selectfilter"') == 2

    def test_standing_labels(self, client, admin_user, conference, group):
        raw = account(
            "raw", conference, verified=False, status=ApplicationStatus.APPROVED
        )
        gone = account(
            "gone", conference, status=ApplicationStatus.APPROVED, active=False
        )
        group.user_set.add(raw, gone)
        client.force_login(admin_user)
        field = client.get(change_url(group)).context["adminform"].form.fields["users"]
        labels = {u.username: field.label_from_instance(u) for u in field.queryset}
        assert labels["raw"] == "Raw (raw), email unverified"
        assert labels["gone"] == "Gone (gone), account inactive"

    def test_no_active_edition_offers_only_current_members(
        self, client, admin_user, conference, group, ada
    ):
        stale = account("stale", conference, status=ApplicationStatus.APPROVED)
        group.user_set.add(stale)
        Conference.objects.update(is_active=False)
        client.force_login(admin_user)
        field = client.get(change_url(group)).context["adminform"].form.fields["users"]
        assert {u.username for u in field.queryset} == {"stale"}

    def test_new_group_offers_candidates(self, client, admin_user, ada):
        client.force_login(admin_user)
        response = client.get(reverse("admin:auth_group_add"))
        field = response.context["adminform"].form.fields["users"]
        assert {u.username for u in field.queryset} == {"ada"}


@pytest.mark.django_db
class TestSaving:
    def test_add_and_remove_members(self, client, admin_user, conference, group, ada):
        old = Conference.objects.create(year=2020, name="2020", slug="2020")
        stale = account("stale", old, status=ApplicationStatus.APPROVED)
        group.user_set.add(stale)
        permission = Permission.objects.get(codename="view_maintenance")
        group.permissions.add(permission)
        client.force_login(admin_user)
        response = client.post(
            change_url(group),
            {"name": group.name, "permissions": [permission.pk], "users": [ada.pk]},
        )
        assert response.status_code == 302
        assert list(group.user_set.all()) == [ada]
        assert list(group.permissions.all()) == [permission]

    def test_an_ineligible_id_is_refused(self, client, admin_user, conference, group):
        pending = account("pen", conference, status=ApplicationStatus.PENDING)
        client.force_login(admin_user)
        response = client.post(
            change_url(group), {"name": group.name, "users": [pending.pk]}
        )
        assert response.status_code == 200
        assert "users" in response.context["adminform"].form.errors
        assert not group.user_set.exists()


@pytest.mark.django_db
class TestChangelist:
    def test_counts_members_and_the_stale(
        self, client, admin_user, conference, group, ada
    ):
        old = Conference.objects.create(year=2020, name="2020", slug="2020")
        stale = account("stale", old, status=ApplicationStatus.APPROVED)
        raw = account(
            "raw", conference, verified=False, status=ApplicationStatus.APPROVED
        )
        group.user_set.add(ada, stale, raw)
        Group.objects.create(name="Empty")
        client.force_login(admin_user)
        rows = {
            g.name: (g.member_count, g.stale_member_count)
            for g in client.get(CHANGELIST).context["cl"].result_list
        }
        assert rows == {"Infra maintainers": (3, 2), "Empty": (0, 0)}

    def test_query_count_does_not_grow_with_members(
        self, client, admin_user, conference, group, ada
    ):
        client.force_login(admin_user)
        group.user_set.add(ada)
        with CaptureQueriesContext(connection) as few:
            client.get(change_url(group))
            client.get(CHANGELIST)
        for name in ("bea", "cy", "dee", "eve"):
            group.user_set.add(
                account(name, conference, status=ApplicationStatus.APPROVED)
            )
        Group.objects.create(name="Second").user_set.add(ada)
        with CaptureQueriesContext(connection) as many:
            client.get(change_url(group))
            client.get(CHANGELIST)
        assert len(few) == len(many)
