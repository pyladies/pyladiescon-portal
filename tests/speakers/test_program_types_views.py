"""The "Session types and roles" settings page (organizers only)."""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from speakers.forms import SessionTypeForm
from speakers.models import PresenterRole, SessionType
from speakers.program_types import presenter_role, session_type

from .factories import add_presenter, make_presenter, make_session, make_settings

PAGE = reverse("speakers:program_types")


@pytest.fixture
def enabled(conference):
    return make_settings(conference)


@pytest.fixture
def organizer(db):
    return User.objects.create_user(
        username="org", email="org@example.com", is_staff=True
    )


@pytest.mark.django_db
class TestAccess:
    def test_organizer_only(self, client, portal_user, organizer, enabled):
        client.force_login(portal_user)
        assert client.get(PAGE).status_code == 403
        client.force_login(organizer)
        assert client.get(PAGE).status_code == 200

    def test_rail_entry_for_organizers(self, client, organizer, enabled):
        client.force_login(organizer)
        content = client.get(reverse("speakers:session_list")).content.decode()
        assert PAGE in content and "Types and roles" in content


@pytest.mark.django_db
class TestListing:
    def test_shows_types_and_roles(self, client, organizer, enabled, conference):
        client.force_login(organizer)
        content = client.get(PAGE).content.decode()
        assert "Session types" in content and "Presenter roles" in content
        assert "PyJam performance" in content and "Pre-recorded" in content
        assert "No, confirmed as created" in content  # a break
        assert "nobody" in content  # the break allows no roles
        assert "Performer" in content and "thank you for being a performer" in content
        assert reverse("speakers:session_type_create") in content
        assert reverse("speakers:presenter_role_create") in content


@pytest.mark.django_db
class TestSessionTypeForms:
    def test_add_a_type_with_roles(self, client, organizer, enabled, conference):
        client.force_login(organizer)
        host = presenter_role(conference, "HOST")
        presenter = presenter_role(conference, "PRESENTER")
        response = client.post(
            reverse("speakers:session_type_create"),
            {
                "name": "Sprint",
                "code": "sprint",
                "is_content": "on",
                "default_duration_minutes": 120,
                "default_delivery": "LIVE",
                "roles": [presenter.pk, host.pk],
                "default_role": presenter.pk,
                "sort_order": 55,
                "is_active": "on",
            },
        )
        assertRedirects(response, PAGE)
        sprint = SessionType.objects.get(conference=conference, code="SPRINT")
        assert set(sprint.roles.values_list("code", flat=True)) == {"PRESENTER", "HOST"}
        assert sprint.default_role == presenter
        # It is usable straight away.
        session = make_session(conference, kind=sprint)
        assert (
            add_presenter(session, make_presenter(conference), role=host).role == host
        )

    def test_default_role_must_be_allowed(self, conference):
        host = presenter_role(conference, "HOST")
        form = SessionTypeForm(
            conference=conference,
            data={
                "name": "Sprint",
                "code": "SPRINT",
                "default_duration_minutes": 60,
                "default_delivery": "LIVE",
                "roles": [presenter_role(conference, "PRESENTER").pk],
                "default_role": host.pk,
                "sort_order": 1,
                "is_active": "on",
            },
        )
        assert form.errors == {
            "default_role": ["The default role must be one of the allowed roles."]
        }

    def test_case_variant_code_is_a_form_error_not_a_crash(
        self, client, organizer, enabled, conference
    ):
        client.force_login(organizer)
        response = client.post(
            reverse("speakers:presenter_role_create"),
            {
                "name": "Panelist again",
                "code": "panelist",
                "email_word": "p",
                "sort_order": 1,
                "is_active": "on",
            },
        )
        assert response.status_code == 200
        assert "already exists" in response.content.decode()
        response = client.post(
            reverse("speakers:session_type_create"),
            {
                "name": "Panel again",
                "code": " panel ",
                "default_duration_minutes": 1,
                "default_delivery": "LIVE",
                "sort_order": 1,
                "is_active": "on",
            },
        )
        assert response.status_code == 200
        assert "already exists" in response.content.decode()

    def test_retired_role_stays_on_the_type_form(
        self, client, organizer, enabled, conference
    ):
        panel = session_type(conference, "PANEL")
        moderator = presenter_role(conference, "MODERATOR")
        moderator.is_active = False
        moderator.save()
        client.force_login(organizer)
        url = reverse("speakers:session_type_edit", args=[panel.pk])
        assert moderator in client.get(url).context["form"].fields["roles"].queryset
        # A new type is not offered the retired role.
        form = client.get(reverse("speakers:session_type_create")).context["form"]
        assert moderator not in form.fields["roles"].queryset

    def test_edit_keeps_code_once_in_use(self, client, organizer, enabled, conference):
        talk = session_type(conference, "TALK")
        client.force_login(organizer)
        url = reverse("speakers:session_type_edit", args=[talk.pk])
        form = client.get(url).context["form"]
        assert form.fields["code"].disabled is False
        make_session(conference, kind=talk)
        form = client.get(url).context["form"]
        assert form.fields["code"].disabled is True
        response = client.post(
            url,
            {
                "name": "Lecture",
                "code": "IGNORED",
                "is_content": "on",
                "default_duration_minutes": 25,
                "default_delivery": "LIVE",
                "roles": [presenter_role(conference, "PRESENTER").pk],
                "default_role": presenter_role(conference, "PRESENTER").pk,
                "sort_order": 20,
                "is_active": "on",
            },
        )
        assertRedirects(response, PAGE)
        talk.refresh_from_db()
        assert talk.name == "Lecture" and talk.code == "TALK"
        assert talk.default_duration_minutes == 25

    def test_other_editions_rows_are_404(self, client, organizer, enabled, conference):
        from portal.models import Conference

        other = Conference.objects.create(year=2024, name="Old", slug="old")
        theirs = session_type(other, "TALK")
        client.force_login(organizer)
        assert (
            client.get(
                reverse("speakers:session_type_edit", args=[theirs.pk])
            ).status_code
            == 404
        )
        # Only this edition's roles are offered.
        form = client.get(reverse("speakers:session_type_create")).context["form"]
        assert all(r.conference == conference for r in form.fields["roles"].queryset)


@pytest.mark.django_db
class TestPresenterRoleForms:
    def test_add_and_edit_a_role(self, client, organizer, enabled, conference):
        client.force_login(organizer)
        response = client.post(
            reverse("speakers:presenter_role_create"),
            {
                "name": "Interpreter",
                "code": "interpreter",
                "email_word": "interpreter",
                "sort_order": 60,
                "is_active": "on",
            },
        )
        assertRedirects(response, PAGE)
        role = PresenterRole.objects.get(conference=conference, code="INTERPRETER")
        assert role.email_word == "interpreter"
        url = reverse("speakers:presenter_role_edit", args=[role.pk])
        assert client.get(url).context["form"].fields["code"].disabled is False
        talk = session_type(conference, "TALK")
        talk.roles.add(role)
        add_presenter(
            make_session(conference, kind=talk), make_presenter(conference), role=role
        )
        assert client.get(url).context["form"].fields["code"].disabled is True
        response = client.post(
            url,
            {
                "name": "Live interpreter",
                "code": "X",
                "email_word": "interpreter",
                "sort_order": 60,
                "is_active": "on",
            },
        )
        assertRedirects(response, PAGE)
        role.refresh_from_db()
        assert role.name == "Live interpreter" and role.code == "INTERPRETER"
        assert "Live interpreter" in client.get(PAGE).content.decode()
