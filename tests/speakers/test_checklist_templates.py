from datetime import date, datetime, timezone
from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.urls import reverse

from portal.models import Conference
from speakers.constants import (
    AutoRule,
    ChecklistScope,
    Delivery,
    DueAnchor,
    ItemOwner,
    MediaKind,
)
from speakers.models import (
    ChecklistTemplate,
    ChecklistTemplateItem,
    PresenterRole,
    SessionType,
)
from speakers.program_types import (
    DEFAULT_ROLES,
    DEFAULT_SESSION_TYPES,
    presenter_role,
    seed_program_types,
    session_type,
)
from speakers.seeds import DEFAULT_TEMPLATES, clone_checklists, seed_checklists

from .factories import make_session, make_settings


@pytest.fixture
def other_conference(db):
    return Conference.objects.create(
        year=2024, name="PyLadiesCon 2024", slug="pyladiescon-2024"
    )


def make_template(conference, **kwargs):
    """``kind`` and ``role`` may be codes; they resolve to the edition's rows."""
    kwargs.setdefault("scope", ChecklistScope.PRESENTER)
    kwargs.setdefault("name", "Workshop presenter")
    kwargs.setdefault("kind", "WORKSHOP")
    if kwargs["scope"] == ChecklistScope.PRESENTER:
        kwargs.setdefault("role", "PRESENTER")
    else:
        kwargs.setdefault("delivery", Delivery.PRE_RECORDED)
    if isinstance(kwargs["kind"], str):
        kwargs["kind"] = session_type(conference, kwargs["kind"])
    role = kwargs.get("role")
    if isinstance(role, str):
        kwargs["role"] = presenter_role(conference, role) if role else None
    return ChecklistTemplate.objects.create(conference=conference, **kwargs)


def make_item(template, **kwargs):
    kwargs.setdefault("owner", ItemOwner.SPEAKER)
    kwargs.setdefault("title", "Do the thing")
    return ChecklistTemplateItem.objects.create(template=template, **kwargs)


@pytest.mark.django_db
class TestSeed:
    def test_seed_twice_produces_no_duplicates(self, conference):
        result = seed_checklists(conference)
        assert result.templates == len(DEFAULT_TEMPLATES)
        assert result.items == sum(len(spec[5]) for spec in DEFAULT_TEMPLATES)
        assert result.skipped == []
        again = seed_checklists(conference)
        assert (again.templates, again.items) == (0, 0)
        assert conference.checklist_templates.count() == len(DEFAULT_TEMPLATES)
        assert (
            ChecklistTemplateItem.objects.filter(
                template__conference=conference
            ).count()
            == result.items
        )

    def test_seed_skips_templates_for_types_the_edition_lacks(self, conference, client):
        """An edition without a keynote (retired, or seeded from an older
        list) keeps not having one: the two keynote templates are skipped
        and reported, the type is not conjured up, and a custom type
        (OPEN_SPACE) survives."""
        # Settings first: creating the row seeds the default types, which
        # would otherwise bring KEYNOTE back after we delete it below.
        make_settings(conference)
        seed_program_types(conference)
        SessionType.objects.get(conference=conference, code="KEYNOTE").delete()
        SessionType.objects.create(
            conference=conference, code="OPEN_SPACE", name="Open space"
        )
        # A missing role skips too: the panel moderator template, whose PANEL
        # type still exists.
        PresenterRole.objects.get(conference=conference, code="MODERATOR").delete()
        keynote = sorted(t[1] for t in DEFAULT_TEMPLATES if t[2] == "KEYNOTE")
        moderator = sorted(t[1] for t in DEFAULT_TEMPLATES if t[3] == "MODERATOR")
        assert keynote and moderator
        result = seed_checklists(conference)
        assert result.templates == len(DEFAULT_TEMPLATES) - len(keynote) - len(
            moderator
        )
        assert sorted(name for name, _ in result.skipped) == sorted(keynote + moderator)
        reasons = dict(result.skipped)
        assert all("no KEYNOTE session type" in reasons[n] for n in keynote)
        assert all("no MODERATOR presenter role" in reasons[n] for n in moderator)
        codes = set(
            SessionType.objects.filter(conference=conference).values_list(
                "code", flat=True
            )
        )
        assert "KEYNOTE" not in codes and "OPEN_SPACE" in codes
        assert not ChecklistTemplate.objects.filter(kind__code="KEYNOTE").exists()
        # The command and the button both say what was left out.
        out = StringIO()
        call_command("seed_checklists", conference=str(conference.year), stdout=out)
        assert "Skipped Keynote host: no KEYNOTE session type" in out.getvalue()
        organizer = User.objects.create_user(username="seed-org", is_staff=True)
        client.force_login(organizer)
        page = client.post(
            reverse("speakers:template_seed"), follow=True
        ).content.decode()
        assert f"Skipped {len(keynote) + len(moderator)}" in page
        assert "Keynote presenter" in page and "MODERATOR presenter role" in page

    def test_every_speaker_line_has_a_description(self):
        """A speaker's to-do says what to do and where it shows up, not just
        a title."""
        missing = [
            spec["title"]
            for _, _, _, _, _, items in DEFAULT_TEMPLATES
            for spec in items
            if spec["owner"] == ItemOwner.SPEAKER and not spec.get("description_md")
        ]
        assert missing == []

    def test_default_templates_name_only_default_codes(self):
        """A template naming a type or role that the defaults do not seed
        would raise DoesNotExist on every fresh edition; catch it here."""
        types = {row[0] for row in DEFAULT_SESSION_TYPES}
        roles = {row[0] for row in DEFAULT_ROLES}
        # The every-presenter template names neither a type nor a role.
        assert {spec[2] for spec in DEFAULT_TEMPLATES if spec[2]} <= types
        assert {spec[3] for spec in DEFAULT_TEMPLATES if spec[3]} <= roles

    def test_seed_fills_empty_descriptions_but_keeps_written_ones(
        self, conference, client
    ):
        """An edition seeded before the defaults carried descriptions gets
        them on "Load defaults"; an organizer's own text is never touched."""
        seed_checklists(conference)
        ChecklistTemplateItem.objects.update(description_md="")
        keep = ChecklistTemplateItem.objects.filter(title="Do a tech check").first()
        keep.description_md = "Our own wording."
        keep.save()
        result = seed_checklists(conference)
        assert (result.templates, result.items) == (0, 0)
        assert result.described > 0
        assert not ChecklistTemplateItem.objects.filter(
            owner=ItemOwner.SPEAKER, description_md=""
        ).exists()
        keep.refresh_from_db()
        assert keep.description_md == "Our own wording."
        assert seed_checklists(conference).described == 0
        # The command and the button both say so (the title sits on several
        # templates, so the count is however many lines share it).
        guide = ChecklistTemplateItem.objects.filter(title="Read the speaker guide")
        n = guide.count()
        assert n > 0
        guide.update(description_md="")
        out = StringIO()
        call_command("seed_checklists", conference=str(conference.year), stdout=out)
        assert f"Filled in {n} missing description(s)." in out.getvalue()
        guide.update(description_md="")
        make_settings(conference)
        organizer = User.objects.create_user(username="seed-org2", is_staff=True)
        client.force_login(organizer)
        page = client.post(
            reverse("speakers:template_seed"), follow=True
        ).content.decode()
        assert f"Filled in {n} missing description(s)." in page

    def test_seed_adds_missing_items_but_keeps_edits(self, conference):
        seed_checklists(conference)
        template = ChecklistTemplate.for_presenter(
            make_session(conference, kind="WORKSHOP"),
            presenter_role(conference, "PRESENTER"),
        )
        template.name = "Workshop presenter (edited)"
        template.save()
        template.items.filter(title="Do a tech check").delete()
        again = seed_checklists(conference)
        assert (again.templates, again.items) == (0, 1)
        template.refresh_from_db()
        assert template.name == "Workshop presenter (edited)"
        assert template.items.filter(title="Do a tech check").exists()

    def test_seed_content_matches_design(self, conference):
        seed_checklists(conference)
        workshop = ChecklistTemplate.objects.get(
            conference=conference,
            kind__code="WORKSHOP",
            role__code="PRESENTER",
        )
        speaker_titles = list(
            workshop.items.filter(owner=ItemOwner.SPEAKER).values_list(
                "title", flat=True
            )
        )
        assert speaker_titles[0] == "Check your session title and summary"
        assert "Share a link to your workshop materials" in speaker_titles
        assert "Update your bio and headshot" not in speaker_titles  # general now
        general = ChecklistTemplate.for_general(conference)
        general_titles = list(general.items.values_list("title", flat=True))
        assert general_titles[0] == "Update your bio and headshot"
        assert "Join the PyLadiesCon Discord" in general_titles
        assert "Presenter in portal" in general_titles
        assert workshop.items.get(title="Read the workshop guide").once_per_presenter
        organizer_titles = list(
            workshop.items.filter(owner=ItemOwner.ORGANIZER).values_list(
                "title", flat=True
            )
        )
        assert organizer_titles[0] == "Invitation sent"
        assert organizer_titles[-1] == "Day-of reminder sent"
        panelist = ChecklistTemplate.objects.get(
            conference=conference, kind__code="PANEL", role__code="PANELIST"
        )
        assert not panelist.items.filter(
            owner=ItemOwner.SPEAKER, title__icontains="materials"
        ).exists()
        post = ChecklistTemplate.objects.get(
            conference=conference, scope=ChecklistScope.SESSION
        )
        assert post.kind.code == "PYJAM" and post.delivery == Delivery.PRE_RECORDED
        translate = post.items.get(title="Translate")
        assert translate.per_translation_language is True
        assert translate.auto_complete_rule == AutoRule.ASSET_EXISTS
        assert translate.requires_asset_kind == MediaKind.TRANSLATION
        transcribe = post.items.get(title="Transcribe")
        assert transcribe.requires_asset_language == "session"
        host = ChecklistTemplate.objects.get(
            conference=conference, kind__code="OPENING", role__code="HOST"
        )
        assert host.items.filter(owner=ItemOwner.SPEAKER).count() == 1

    def test_seed_is_per_edition(self, conference, other_conference):
        seed_checklists(conference)
        assert other_conference.checklist_templates.count() == 0

    def test_command_defaults_to_active(self, conference):
        out = StringIO()
        call_command("seed_checklists", stdout=out)
        assert f"into {conference}" in out.getvalue()
        assert conference.checklist_templates.exists()

    def test_command_by_year_and_slug(self, conference, other_conference):
        out = StringIO()
        call_command("seed_checklists", conference="2024", stdout=out)
        assert other_conference.checklist_templates.exists()
        call_command("seed_checklists", conference=other_conference.slug, stdout=out)
        assert conference.checklist_templates.count() == 0

    def test_command_errors(self, conference):
        with pytest.raises(CommandError, match="No conference matches"):
            call_command("seed_checklists", conference="nope")
        conference.is_active = False
        conference.save()
        with pytest.raises(CommandError, match="No active conference"):
            call_command("seed_checklists")


@pytest.mark.django_db
class TestClone:
    def test_clone_copies_templates_and_items(self, conference, other_conference):
        seed_checklists(other_conference)
        # A per-session template: the general one names no kind or role, and
        # the assertions below match those by code.
        template = other_conference.checklist_templates.exclude(kind=None).first()
        template.is_active = False
        template.save()
        item = template.items.first()
        item.description_md = "Custom note"
        item.due_offset_days = 42
        item.save()
        templates, items = clone_checklists(conference, other_conference)
        assert templates == len(DEFAULT_TEMPLATES)
        assert (
            items
            == ChecklistTemplateItem.objects.filter(
                template__conference=other_conference
            ).count()
        )
        # Types and roles are matched by code, not by row.
        copy = ChecklistTemplate.objects.get(
            conference=conference,
            scope=template.scope,
            kind__code=template.kind.code,
            role__code=template.role.code,
            delivery=template.delivery,
        )
        assert copy.kind.conference == conference and copy.role.conference == conference
        assert copy.is_active is False
        copied_item = copy.items.get(title=item.title)
        assert copied_item.description_md == "Custom note"
        assert copied_item.due_offset_days == 42
        assert copied_item.pk != item.pk
        assert clone_checklists(conference, other_conference) == (0, 0)

    def test_clone_command(self, conference, other_conference):
        seed_checklists(other_conference)
        out = StringIO()
        call_command("clone_checklists", source="2024", target="2025", stdout=out)
        assert f"from {other_conference} into {conference}" in out.getvalue()
        assert conference.checklist_templates.count() == len(DEFAULT_TEMPLATES)


@pytest.mark.django_db
class TestDueDates:
    def test_after_invitation_accepted(self, conference):
        item = make_item(
            make_template(conference),
            due_anchor=DueAnchor.INVITATION_ACCEPTED,
            due_offset_days=7,
        )
        accepted = datetime(2026, 10, 1, 15, 30, tzinfo=timezone.utc)
        assert item.due_date(invitation_accepted=accepted) == date(2026, 10, 8)

    def test_before_conference_start(self, conference):
        item = make_item(
            make_template(conference),
            due_anchor=DueAnchor.CONFERENCE_START,
            due_offset_days=14,
        )
        assert item.due_date(conference_start=date(2026, 12, 5)) == date(2026, 11, 21)

    def test_before_session_start(self, conference):
        item = make_item(
            make_template(conference),
            due_anchor=DueAnchor.SESSION_START,
            due_offset_days=3,
        )
        start = datetime(2026, 12, 6, 9, 0, tzinfo=timezone.utc)
        assert item.due_date(session_start=start) == date(2026, 12, 3)

    def test_unknown_anchor_or_missing_base(self, conference):
        template = make_template(conference)
        assert make_item(template).due_date(conference_start=date(2026, 12, 5)) is None
        item = make_item(template, title="x", due_anchor=DueAnchor.SESSION_START)
        assert item.due_date(conference_start=date(2026, 12, 5)) is None


@pytest.mark.django_db
class TestValidation:
    def test_unknown_rule_rejected_at_save(self, conference):
        with pytest.raises(ValidationError, match="Unknown rule"):
            make_item(make_template(conference), auto_complete_rule="teleport")

    def test_asset_kind_needs_a_rule(self, conference):
        template = make_template(conference)
        with pytest.raises(ValidationError, match="needs a rule"):
            make_item(template, requires_asset_kind=MediaKind.RAW_VIDEO)
        item = make_item(
            template,
            requires_asset_kind=MediaKind.RAW_VIDEO,
            auto_complete_rule=AutoRule.ASSET_EXISTS,
        )
        assert item.is_automatic is True
        assert str(item) == "Do the thing"

    def test_template_key_rules(self, conference):
        with pytest.raises(ValidationError, match="need a role"):
            make_template(conference, role="")
        with pytest.raises(ValidationError, match="need a delivery"):
            make_template(conference, scope=ChecklistScope.SESSION, delivery="")
        with pytest.raises(ValidationError, match="Only session templates"):
            make_template(conference, delivery=Delivery.LIVE)
        with pytest.raises(ValidationError, match="Only presenter templates"):
            make_template(conference, scope=ChecklistScope.SESSION, role="HOST")

    def test_type_and_role_must_belong_to_the_edition(
        self, conference, other_conference
    ):
        with pytest.raises(ValidationError, match="session type of this edition"):
            make_template(conference, kind=session_type(other_conference, "TALK"))
        with pytest.raises(ValidationError, match="role of this edition"):
            make_template(conference, role=presenter_role(other_conference, "HOST"))

    def test_lookup_helpers(self, conference, other_conference):
        template = make_template(conference)
        session = make_session(conference, kind="WORKSHOP")
        assert (
            ChecklistTemplate.for_presenter(
                session, presenter_role(conference, "PRESENTER")
            )
            == template
        )
        assert (
            ChecklistTemplate.for_presenter(session, presenter_role(conference, "HOST"))
            is None
        )
        template.is_active = False
        template.save()
        assert (
            ChecklistTemplate.for_presenter(
                session, presenter_role(conference, "PRESENTER")
            )
            is None
        )
        jam = make_session(conference, kind="PYJAM", delivery=Delivery.PRE_RECORDED)
        post = make_template(
            conference,
            scope=ChecklistScope.SESSION,
            kind="PYJAM",
            name="Post",
        )
        assert ChecklistTemplate.for_session(jam) == post
        assert str(post) == "Post"
        other_jam = make_session(
            other_conference, kind="PYJAM", delivery=Delivery.PRE_RECORDED
        )
        assert ChecklistTemplate.for_session(other_jam) is None


@pytest.mark.django_db
class TestAdmin:
    def test_changelist_and_change_form(self, client, admin_user, conference):
        seed_checklists(conference)
        client.force_login(admin_user)
        assert (
            client.get(
                reverse("admin:speakers_checklisttemplate_changelist")
            ).status_code
            == 200
        )
        template = conference.checklist_templates.get(
            kind__code="WORKSHOP", role__code="PRESENTER"
        )
        response = client.get(
            reverse("admin:speakers_checklisttemplate_change", args=[template.pk])
        )
        assert response.status_code == 200
        assert "Share a link to your workshop materials" in response.content.decode()
