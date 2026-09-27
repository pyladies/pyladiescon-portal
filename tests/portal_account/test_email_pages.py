"""The two readers of the sent-email record: Maintenance > Emails, and a
person's own "Emails we sent you" (design §13.1, task 2.23)."""

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from common.models import SentEmail, SentEmailStatus
from common.send_emails import send_email
from portal.models import Conference
from portal.navigation import ORGANIZE, SECTION_BY_NAME
from portal_account.models import PortalProfile
from tests.speakers.factories import make_presenter, make_session, make_settings

TRAIL = reverse("maintenance_emails")
MINE = reverse("portal_account:my_emails")


def send(subject, to, template="emails/base_email.md", **kwargs):
    return send_email(subject, to, markdown_template=template, **kwargs)


@pytest.fixture
def ada(db):
    user = User.objects.create_user(username="ada", email="ada@example.com")
    PortalProfile.objects.create(user=user)
    return user


@pytest.fixture
def presenter(conference, ada):
    make_settings(conference)
    return make_presenter(conference, email="ada@example.com", user=ada)


@pytest.mark.django_db
class TestMaintenanceEmails:
    def test_newest_first_with_the_body_and_the_rules(self, client, maintainer):
        first = send("First one", ["a@x.org"])
        second = send("Second one", ["b@x.org"])
        client.force_login(maintainer)
        content = client.get(TRAIL).content.decode()
        assert content.index("Second one") < content.index("First one")
        assert "Hello from" in content
        assert "<strong>" in content and "**" not in content
        assert f"email-{first.pk}" in content and f"email-{second.pk}" in content
        # UTC on the server, the reader's clock added by the page.
        assert "<time datetime=" in content and "UTC</time>" in content
        assert "time[data-utc]" in content
        assert "pruned nightly" in content and "withheld from the body" in content
        # The rail and the user menu offer it.
        assert content.count(TRAIL) >= 2

    def test_filters(self, client, maintainer, conference, presenter):
        other_edition = Conference.objects.create(year=2020, name="2020", slug="2020")
        session = make_session(conference)
        to_ada = send("To Ada", [presenter.email], context={"presenter": presenter})
        about_ada = send(
            "About Ada",
            ["org@x.org"],
            template="emails/base_email.md",
            context={"presenter": presenter, "session": session},
        )
        elsewhere = send("Old edition", ["z@x.org"], conference=other_edition)
        failed = SentEmail.objects.create(
            to="f@x.org",
            subject="Broken",
            template="emails/volunteer/x.md",
            status=SentEmailStatus.FAILED,
            error="RuntimeError: smtp down",
        )
        client.force_login(maintainer)

        def subjects(query):
            response = client.get(TRAIL, query)
            return [email.subject for email in response.context["object_list"]]

        assert subjects({"presenter": presenter.pk}) == ["About Ada", "To Ada"]
        assert subjects({"conference": other_edition.pk}) == ["Old edition"]
        assert subjects({"template": "emails/volunteer/x.md"}) == ["Broken"]
        assert subjects({"status": SentEmailStatus.FAILED}) == ["Broken"]
        assert subjects({"search": "z@x"}) == ["Old edition"]
        assert subjects({"search": "ada"}) == ["About Ada", "To Ada"]
        content = client.get(TRAIL, {"search": "x"}).content.decode()
        assert "Reset" in content and "smtp down" in content
        assert elsewhere.pk and failed.pk and to_ada.pk and about_ada.pk

    def test_query_count_does_not_grow_with_rows(self, client, maintainer, presenter):
        client.force_login(maintainer)
        for i in range(2):
            send(f"Mail {i}", [presenter.email], context={"presenter": presenter})
        with CaptureQueriesContext(connection) as few:
            client.get(TRAIL)
        for i in range(6):
            send(f"More {i}", [presenter.email], context={"presenter": presenter})
        with CaptureQueriesContext(connection) as many:
            client.get(TRAIL)
        assert len(few) == len(many)

    def test_pages(self, client, maintainer):
        for i in range(51):
            send(f"Mail {i}", ["a@x.org"])
        client.force_login(maintainer)
        content = client.get(TRAIL).content.decode()
        assert "Page 1 of 2" in content and "Older" in content
        content = client.get(TRAIL, {"page": 2, "search": "Mail"}).content.decode()
        assert (
            "Page 2 of 2" in content and "Newer" in content and "search=Mail" in content
        )

    def test_organizer_who_is_not_a_maintainer_is_refused(self, client, conference):
        organizer = User.objects.create_user(
            username="org", email="org@x.org", is_staff=True
        )
        client.force_login(organizer)
        assert client.get(TRAIL).status_code == 403

    def test_anonymous_is_sent_to_login(self, client):
        assertRedirects(client.get(TRAIL), reverse("account_login") + "?next=" + TRAIL)

    def test_organize_rail_offers_it_to_maintainers(self, client, maintainer):
        maintainer.is_staff = True
        maintainer.save()
        client.force_login(maintainer)
        content = client.get(reverse("organizer_dashboard")).content.decode()
        assert TRAIL in content

    def test_navigation_section(self):
        assert SECTION_BY_NAME["maintenance_emails"] == ORGANIZE


@pytest.mark.django_db
class TestMyEmails:
    def test_exactly_what_is_theirs(self, client, ada, presenter):
        by_account = send("Yours by account", [ada.email], context={"user": ada})
        # Before the account existed: the presenter row is hers now.
        by_presenter = send(
            "Yours by presenter", [presenter.email], context={"presenter": presenter}
        )
        SentEmail.objects.filter(pk=by_presenter.pk).update(user=None)
        send("Same address, nobody's", [ada.email])
        grace = User.objects.create_user(username="grace", email="g@x.org")
        send("Grace's", [grace.email], context={"user": grace})
        client.force_login(ada)
        response = client.get(MINE)
        subjects = [email.subject for email in response.context["object_list"]]
        assert subjects == ["Yours by presenter", "Yours by account"]
        content = response.content.decode()
        assert "We keep these for the edition plus" in content
        assert f"mine-{by_account.pk}" in content
        # One kind only: nothing to filter by.
        assert 'name="kind"' not in content

    def test_kind_filter(self, client, ada):
        send("Base", [ada.email], context={"user": ada})
        send(
            "Other",
            [ada.email],
            template="emails/base_email.md",
            context={"user": ada},
        )
        SentEmail.objects.filter(subject="Other").update(template="emails/x/other.md")
        client.force_login(ada)
        content = client.get(MINE).content.decode()
        assert 'name="kind"' in content and "x/other" in content
        response = client.get(MINE, {"kind": "emails/x/other.md"})
        assert [e.subject for e in response.context["object_list"]] == ["Other"]
        assert response.context["kind"] == "emails/x/other.md"

    def test_account_page_and_rail_link_to_it(self, client, ada):
        client.force_login(ada)
        assert MINE in client.get(reverse("portal_account:index")).content.decode()
        content = client.get(MINE).content.decode()
        assert "Emails we sent you" in content
        assert (
            reverse("portal_account:portal_profile_edit", args=[ada.portalprofile.pk])
            in content
        )

    def test_requires_login(self, client):
        assertRedirects(client.get(MINE), reverse("account_login") + "?next=" + MINE)
