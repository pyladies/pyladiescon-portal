import pytest
from allauth.account.models import EmailAddress
from django.contrib.admin.sites import AdminSite
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from portal_account.admin import PortalProfileAdmin, PortalProfileResource
from portal_account.models import PortalProfile


@pytest.mark.django_db
class TestPortalProfileAdmin:

    def test_changelist_shows_creation_date(self, client, admin_user, portal_user):
        """The changelist exposes when each profile was created."""
        profile = PortalProfile.objects.create(user=portal_user)

        client.force_login(admin_user)
        response = client.get(reverse("admin:portal_account_portalprofile_changelist"))

        assert response.status_code == 200
        changelist = response.context["cl"]
        assert "creation_date" in changelist.list_display
        assert changelist.date_hierarchy == "creation_date"
        assert list(changelist.result_list) == [profile]

    def test_ordered_newest_first(
        self, client, admin_user, portal_user, django_user_model
    ):
        """Newest profiles sort to the top, so a sign-up burst is visible."""
        older = PortalProfile.objects.create(user=portal_user)
        newer = PortalProfile.objects.create(
            user=django_user_model.objects.create_user("later", email="l@example.com")
        )

        assert older.creation_date < newer.creation_date

        admin_instance = PortalProfileAdmin(PortalProfile, AdminSite())
        assert admin_instance.ordering == ("-creation_date",)

        client.force_login(admin_user)
        response = client.get(reverse("admin:portal_account_portalprofile_changelist"))

        assert list(response.context["cl"].result_list) == [newer, older]

    def test_email_verified_column(self, client, admin_user, portal_user):
        """The column reports whether the account confirmed an address."""
        PortalProfile.objects.create(user=portal_user)
        admin_instance = PortalProfileAdmin(PortalProfile, AdminSite())

        client.force_login(admin_user)
        url = reverse("admin:portal_account_portalprofile_changelist")
        request = client.get(url).wsgi_request

        unverified = admin_instance.get_queryset(request).get(user=portal_user)
        assert admin_instance.email_verified(unverified) is False

        EmailAddress.objects.create(
            user=portal_user, email=portal_user.email, verified=True, primary=True
        )
        verified = admin_instance.get_queryset(request).get(user=portal_user)
        assert admin_instance.email_verified(verified) is True

    def test_changelist_query_count_does_not_grow(
        self, client, admin_user, portal_user, django_user_model
    ):
        """Query count is flat whether the changelist holds one row or many."""
        PortalProfile.objects.create(user=portal_user)
        client.force_login(admin_user)
        url = reverse("admin:portal_account_portalprofile_changelist")

        with CaptureQueriesContext(connection) as one_row:
            client.get(url)

        for index in range(5):
            PortalProfile.objects.create(
                user=django_user_model.objects.create_user(
                    f"extra{index}", email=f"extra{index}@example.com"
                )
            )

        with CaptureQueriesContext(connection) as six_rows:
            client.get(url)

        assert len(six_rows.captured_queries) == len(one_row.captured_queries)


@pytest.mark.django_db
class TestPortalProfileResource:

    def test_export_includes_account_context(self, portal_user):
        """The export carries the columns needed to audit a sign-up."""
        PortalProfile.objects.create(user=portal_user)
        EmailAddress.objects.create(
            user=portal_user, email=portal_user.email, verified=True, primary=True
        )

        dataset = PortalProfileResource().export()

        assert dataset.headers[:4] == [
            "id",
            "user",
            "user__username",
            "user__email",
        ]
        assert "creation_date" in dataset.headers
        assert "email_verified" in dataset.headers

        row = dict(zip(dataset.headers, dataset[0]))
        assert row["user__username"] == portal_user.username
        assert row["user__email"] == portal_user.email
        assert row["email_verified"] == "1"
        assert row["creation_date"]

    def test_export_marks_unconfirmed_accounts(self, portal_user):
        """A profile whose user never confirmed an address exports as False."""
        PortalProfile.objects.create(user=portal_user)

        dataset = PortalProfileResource().export()

        row = dict(zip(dataset.headers, dataset[0]))
        assert row["email_verified"] == "0"
