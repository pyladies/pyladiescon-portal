"""Session types and presenter roles as rows: seeding, the role mapping,
and the validation that keeps a presenter off a panel."""

from io import StringIO

import pytest
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command

from portal.models import Conference
from speakers.constants import Delivery
from speakers.models import PresenterRole, Session, SessionPresenter, SessionType
from speakers.program_types import (
    DEFAULT_ROLES,
    DEFAULT_SESSION_TYPES,
    presenter_role,
    seed_program_types,
    session_type,
)

from .factories import add_presenter, make_presenter, make_session, make_settings


@pytest.mark.django_db
class TestSeeding:
    def test_defaults_once(self, conference):
        assert seed_program_types(conference) == (
            len(DEFAULT_SESSION_TYPES),
            len(DEFAULT_ROLES),
        )
        assert seed_program_types(conference) == (0, 0)
        panel = SessionType.objects.get(conference=conference, code="PANEL")
        assert set(panel.roles.values_list("code", flat=True)) == {
            "PANELIST",
            "MODERATOR",
        }
        assert panel.default_role.code == "PANELIST"
        assert panel.is_content and panel.default_duration_minutes == 60
        pyjam = SessionType.objects.get(conference=conference, code="PYJAM")
        assert pyjam.default_delivery == Delivery.PRE_RECORDED
        coffee = SessionType.objects.get(conference=conference, code="BREAK")
        assert not coffee.is_content and coffee.spans_all_channels
        assert not coffee.has_presenters and coffee.default_role is None
        assert [t.code for t in SessionType.objects.filter(conference=conference)][
            :3
        ] == ["WORKSHOP", "TALK", "LIGHTNING"]

    def test_organizer_edits_survive_reseeding(self, conference):
        seed_program_types(conference)
        talk = SessionType.objects.get(conference=conference, code="TALK")
        talk.name = "Lecture"
        talk.default_duration_minutes = 25
        talk.save()
        host = PresenterRole.objects.get(conference=conference, code="HOST")
        talk.roles.add(host)
        seed_program_types(conference)
        talk.refresh_from_db()
        assert talk.name == "Lecture" and talk.default_duration_minutes == 25
        assert talk.roles.filter(code="HOST").exists()

    def test_settings_row_seeds_the_edition(self, conference):
        assert not SessionType.objects.filter(conference=conference).exists()
        make_settings(conference)
        assert SessionType.objects.filter(conference=conference).count() == len(
            DEFAULT_SESSION_TYPES
        )

    def test_helpers_seed_on_demand(self, conference):
        assert session_type(conference, "WORKSHOP").name == "Workshop"
        other = Conference.objects.create(year=2024, name="Old", slug="old")
        assert presenter_role(other, "HOST").conference == other
        assert presenter_role(other, "HOST").email_word == "host"
        # Editions are independent.
        assert SessionType.objects.filter(conference=other).count() == len(
            DEFAULT_SESSION_TYPES
        )

    def test_codes_are_upper_case(self, conference):
        role = PresenterRole.objects.create(
            conference=conference, code=" mc ", name="MC"
        )
        kind = SessionType.objects.create(
            conference=conference, code="sprint", name="Sprint"
        )
        assert role.code == "MC" and kind.code == "SPRINT"
        assert str(role) == "MC" and str(kind) == "Sprint"

    def test_management_command(self, conference):
        out = StringIO()
        call_command("seed_program_types", stdout=out)
        assert "12 session types and 5 roles created" in out.getvalue()
        Conference.objects.create(year=2024, name="Old", slug="old")
        out = StringIO()
        call_command("seed_program_types", conference="2024", stdout=out)
        assert "Old" in out.getvalue() or "2024" in out.getvalue()
        out = StringIO()
        call_command("seed_program_types", conference="old", stdout=out)
        assert "0 session types" in out.getvalue()
        with pytest.raises(CommandError, match="No conference"):
            call_command("seed_program_types", conference="nope")


@pytest.mark.django_db
class TestSessionDefaults:
    def test_duration_and_delivery_follow_the_type(self, conference):
        assert make_session(conference, kind="PYJAM").delivery == Delivery.PRE_RECORDED
        assert make_session(conference, kind="TALK").delivery == Delivery.LIVE
        live_jam = make_session(conference, kind="PYJAM", delivery=Delivery.LIVE)
        assert live_jam.delivery == Delivery.LIVE  # an explicit choice wins
        assert make_session(conference, kind="KEYNOTE").duration_minutes == 45

    def test_type_of_another_edition_is_refused(self, conference):
        other = Conference.objects.create(year=2024, name="Old", slug="old")
        session = Session(
            conference=conference, title="x", kind=session_type(other, "TALK")
        )
        with pytest.raises(ValidationError, match="of this edition"):
            session.full_clean()

    def test_changing_the_type_keeps_everyone_in_an_allowed_role(self, conference):
        panel = make_session(conference, kind="PANEL", title="Careers")
        mod = add_presenter(
            panel, make_presenter(conference, display_name="Grace"), role="MODERATOR"
        )
        panel.kind = session_type(conference, "TALK")
        with pytest.raises(ValidationError) as excinfo:
            panel.full_clean()
        assert "A Talk cannot have: Grace (Moderator)" in str(excinfo.value)
        # Once the role fits, the change goes through.
        SessionPresenter.objects.filter(pk=mod.pk).update(
            role=presenter_role(conference, "PRESENTER")
        )
        panel.full_clean()
        panel.save()
        assert panel.kind.code == "TALK"


@pytest.mark.django_db
class TestRoleMapping:
    def test_presenter_cannot_join_a_panel(self, conference):
        panel = make_session(conference, kind="PANEL")
        with pytest.raises(ValidationError, match="A Panel cannot have a presenter"):
            add_presenter(panel, make_presenter(conference), role="PRESENTER")
        add_presenter(panel, make_presenter(conference), role="PANELIST")
        add_presenter(panel, make_presenter(conference), role="MODERATOR")
        assert panel.session_presenters.count() == 2

    def test_performer_only_on_pyjam(self, conference):
        with pytest.raises(ValidationError, match="Workshop cannot have a performer"):
            add_presenter(
                make_session(conference), make_presenter(conference), role="PERFORMER"
            )
        jam = make_session(conference, kind="PYJAM")
        link = add_presenter(jam, make_presenter(conference))  # the type's default
        assert link.role.code == "PERFORMER"

    def test_a_break_takes_nobody(self, conference):
        coffee = make_session(conference, kind="BREAK")
        with pytest.raises(ValidationError, match="A Break cannot have a host"):
            add_presenter(coffee, make_presenter(conference), role="HOST")

    def test_role_of_another_edition_is_refused(self, conference):
        other = Conference.objects.create(year=2024, name="Old", slug="old")
        session = make_session(conference)
        with pytest.raises(ValidationError, match="role of this edition"):
            add_presenter(
                session,
                make_presenter(conference),
                role=presenter_role(other, "PRESENTER"),
            )

    def test_organizers_can_add_a_role_and_allow_it(self, conference):
        talk = session_type(conference, "TALK")
        interpreter = PresenterRole.objects.create(
            conference=conference,
            code="INTERPRETER",
            name="Interpreter",
            email_word="interpreter",
        )
        talk.roles.add(interpreter)
        session = make_session(conference, kind=talk)
        link = add_presenter(session, make_presenter(conference), role=interpreter)
        assert link.role.email_word == "interpreter"
        assert str(link).endswith("(Interpreter) on " + session.title)

    def test_default_role_must_be_allowed_and_of_the_edition(self, conference):
        talk = session_type(conference, "TALK")
        talk.default_role = presenter_role(conference, "HOST")
        with pytest.raises(ValidationError, match="one of the allowed roles"):
            talk.full_clean()
        other = Conference.objects.create(year=2024, name="Old", slug="old")
        talk.default_role = presenter_role(other, "PRESENTER")
        with pytest.raises(ValidationError, match="role of this edition"):
            talk.full_clean()
        talk.default_role = presenter_role(conference, "PRESENTER")
        talk.full_clean()
