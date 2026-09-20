import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from portal.models import Conference
from speakers.checklists import instantiate_presenter_checklist
from speakers.constants import (
    AutoRule,
    ChecklistScope,
    DueAnchor,
    ItemOwner,
    ItemStatus,
)
from speakers.models import ChecklistItem, ChecklistTemplate, ChecklistTemplateItem
from speakers.program_types import presenter_role, seed_program_types, session_type
from speakers.seeds import DEFAULT_TEMPLATES, seed_checklists

from .factories import add_presenter, make_presenter, make_session, make_settings

LIST = reverse("speakers:template_list")


@pytest.fixture
def enabled(conference):
    return make_settings(conference)


@pytest.fixture
def organizer(db):
    return User.objects.create_user(username="organizer", is_staff=True)


@pytest.fixture
def template(conference, enabled):
    template = ChecklistTemplate.objects.create(
        conference=conference,
        scope=ChecklistScope.PRESENTER,
        name="Workshop presenter",
        kind=session_type(conference, "WORKSHOP"),
        role=presenter_role(conference, "PRESENTER"),
    )
    for order, title in enumerate(["Bio", "Guide", "Register"]):
        ChecklistTemplateItem.objects.create(
            template=template, order=order, owner=ItemOwner.SPEAKER, title=title
        )
    return template


def action(template, item, name):
    return reverse("speakers:template_item_action", args=[template.pk, item.pk, name])


@pytest.mark.django_db
class TestAccess:
    def test_organizer_only(self, client, portal_user, enabled, conference, template):
        liaison = User.objects.create_user(username="lena")
        make_presenter(conference, liaison=liaison)
        client.force_login(liaison)
        assert client.get(LIST).status_code == 403
        assert (
            client.get(
                reverse("speakers:template_detail", args=[template.pk])
            ).status_code
            == 403
        )
        client.force_login(portal_user)
        assert client.get(LIST).status_code == 403

    def test_rail_link(self, client, organizer, enabled):
        client.force_login(organizer)
        assert LIST in client.get(reverse("organizer_dashboard")).content.decode()


@pytest.mark.django_db
class TestListAndSeed:
    def test_list_groups_by_scope(self, client, organizer, enabled, conference):
        seed_checklists(conference)
        client.force_login(organizer)
        response = client.get(LIST)
        assert (
            len(response.context["presenter_templates"]) == len(DEFAULT_TEMPLATES) - 1
        )
        assert len(response.context["session_templates"]) == 1
        content = response.content.decode()
        assert "PyJam post-production" in content and "Workshop presenter" in content

    def test_empty_then_load_defaults(self, client, organizer, enabled, conference):
        client.force_login(organizer)
        assert "None yet" in client.get(LIST).content.decode()
        assert client.post(LIST).status_code == 405
        response = client.post(reverse("speakers:template_seed"), follow=True)
        assert (
            f"Loaded {len(DEFAULT_TEMPLATES)} template(s)" in response.content.decode()
        )
        assert conference.checklist_templates.count() == len(DEFAULT_TEMPLATES)


@pytest.mark.django_db
class TestTemplateForms:
    def test_create_and_edit(self, client, organizer, enabled, conference):
        client.force_login(organizer)
        assert client.get(reverse("speakers:template_create")).status_code == 200
        response = client.post(
            reverse("speakers:template_create"),
            {
                "scope": ChecklistScope.PRESENTER,
                "name": "Talk presenter",
                "kind": session_type(conference, "TALK").pk,
                "role": presenter_role(conference, "PRESENTER").pk,
                "is_active": "on",
            },
        )
        template = ChecklistTemplate.objects.get(name="Talk presenter")
        assertRedirects(
            response, reverse("speakers:template_detail", args=[template.pk])
        )
        assert template.conference == conference
        edit = reverse("speakers:template_edit", args=[template.pk])
        assert "Edit" in client.get(edit).content.decode()
        client.post(
            edit,
            {
                "scope": ChecklistScope.PRESENTER,
                "name": "Talk speaker",
                "kind": session_type(conference, "TALK").pk,
                "role": presenter_role(conference, "PRESENTER").pk,
            },
        )
        template.refresh_from_db()
        assert template.name == "Talk speaker" and template.is_active is False

    def test_validation_errors_shown(self, client, organizer, template, conference):
        client.force_login(organizer)
        response = client.post(
            reverse("speakers:template_create"),
            {
                "scope": ChecklistScope.PRESENTER,
                "kind": session_type(conference, "WORKSHOP").pk,
            },
        )
        assert "name" in response.context["form"].errors
        response = client.post(
            reverse("speakers:template_create"),
            {
                "scope": ChecklistScope.PRESENTER,
                "name": "x",
                "kind": session_type(conference, "WORKSHOP").pk,
            },
        )
        assert response.context["form"].errors["role"] == [
            "Presenter templates need a role."
        ]
        response = client.post(
            reverse("speakers:template_create"),
            {
                "scope": ChecklistScope.PRESENTER,
                "name": "dup",
                "kind": session_type(conference, "WORKSHOP").pk,
                "role": presenter_role(conference, "PRESENTER").pk,
            },
        )
        assert "exists" in response.context["form"].errors["kind"][0]

    def test_other_edition_template_404(self, client, organizer, enabled):
        other = Conference.objects.create(year=2024, name="Old", slug="2024")
        seed_program_types(other)
        foreign = ChecklistTemplate.objects.create(
            conference=other,
            scope=ChecklistScope.SESSION,
            name="x",
            kind=session_type(other, "PYJAM"),
            delivery="PRE_RECORDED",
        )
        client.force_login(organizer)
        assert (
            client.get(
                reverse("speakers:template_detail", args=[foreign.pk])
            ).status_code
            == 404
        )
        assert (
            client.get(reverse("speakers:template_edit", args=[foreign.pk])).status_code
            == 404
        )


@pytest.mark.django_db
class TestItems:
    def test_detail_lists_items_in_order(self, client, organizer, template):
        client.force_login(organizer)
        response = client.get(reverse("speakers:template_detail", args=[template.pk]))
        assert [i.title for i in response.context["items"]] == [
            "Bio",
            "Guide",
            "Register",
        ]
        assert "Back-fill" in response.content.decode()

    def test_add_item_with_rule_does_not_touch_instances(
        self, client, organizer, template, conference
    ):
        session = make_session(conference, kind="WORKSHOP")
        link = add_presenter(session, make_presenter(conference), confirmed=True)
        instantiate_presenter_checklist(link)
        assert link.presenter.checklist_items.count() == 3
        client.force_login(organizer)
        url = reverse("speakers:template_item_add", args=[template.pk])
        assert client.get(url).status_code == 200
        response = client.post(
            url,
            {
                "title": "Tech check",
                "owner": ItemOwner.SPEAKER,
                "due_anchor": DueAnchor.SESSION_START,
                "due_offset_days": 3,
                "auto_complete_rule": "",
                "requires_asset_kind": "",
                "requires_asset_language": "",
                "assignee_default": "UNASSIGNED",
                "is_required": "on",
            },
        )
        assertRedirects(
            response, reverse("speakers:template_detail", args=[template.pk])
        )
        item = template.items.get(title="Tech check")
        assert item.order == 3 and item.is_required is True
        assert link.presenter.checklist_items.count() == 3  # unchanged

    def test_rule_dropdown_rejects_unknown(self, client, organizer, template):
        client.force_login(organizer)
        response = client.post(
            reverse("speakers:template_item_add", args=[template.pk]),
            {
                "title": "x",
                "owner": ItemOwner.SPEAKER,
                "auto_complete_rule": "teleport",
                "assignee_default": "UNASSIGNED",
            },
        )
        assert "auto_complete_rule" in response.context["form"].errors
        content = client.get(
            reverse("speakers:template_item_add", args=[template.pk])
        ).content.decode()
        assert AutoRule.HANDBOOK_READ in content

    def test_edit_item(self, client, organizer, template, conference):
        item = template.items.get(title="Bio")
        session = make_session(conference, kind="WORKSHOP")
        link = add_presenter(session, make_presenter(conference), confirmed=True)
        instantiate_presenter_checklist(link)
        client.force_login(organizer)
        url = reverse("speakers:template_item_edit", args=[template.pk, item.pk])
        assert "Edit" in client.get(url).content.decode()
        client.post(
            url,
            {
                "title": "Bio and headshot",
                "owner": ItemOwner.SPEAKER,
                "auto_complete_rule": AutoRule.BIO_AND_HEADSHOT,
                "assignee_default": "UNASSIGNED",
                "due_offset_days": 0,
            },
        )
        item.refresh_from_db()
        assert item.title == "Bio and headshot"
        assert link.presenter.checklist_items.get(template_item=item).title == "Bio"

    def test_edit_item_of_other_template_404(
        self, client, organizer, template, conference
    ):
        other = ChecklistTemplate.objects.create(
            conference=conference,
            scope=ChecklistScope.PRESENTER,
            name="Panelist",
            kind=session_type(conference, "PANEL"),
            role=presenter_role(conference, "PANELIST"),
        )
        item = template.items.first()
        client.force_login(organizer)
        assert (
            client.get(
                reverse("speakers:template_item_edit", args=[other.pk, item.pk])
            ).status_code
            == 404
        )
        assert client.post(action(other, item, "delete")).status_code == 404

    def test_move_up_down_and_bounds(self, client, organizer, template):
        bio, guide, register = list(template.items.order_by("order"))
        client.force_login(organizer)
        client.post(action(template, register, "up"))
        assert [i.title for i in template.items.order_by("order", "id")] == [
            "Bio",
            "Register",
            "Guide",
        ]
        client.post(action(template, bio, "down"))
        assert [i.title for i in template.items.order_by("order", "id")] == [
            "Register",
            "Bio",
            "Guide",
        ]
        client.post(action(template, register, "up"))  # already first: no change
        assert [i.title for i in template.items.order_by("order", "id")] == [
            "Register",
            "Bio",
            "Guide",
        ]
        assert [i.order for i in template.items.order_by("order", "id")] == [0, 1, 2]

    def test_delete(self, client, organizer, template):
        item = template.items.get(title="Guide")
        client.force_login(organizer)
        response = client.post(action(template, item, "delete"), follow=True)
        assert "Removed “Guide”" in response.content.decode()
        assert template.items.count() == 2

    def test_unknown_action(self, client, organizer, template):
        client.force_login(organizer)
        assert (
            client.post(action(template, template.items.first(), "explode")).status_code
            == 400
        )

    def test_backfill_adds_once_and_evaluates(
        self, client, organizer, template, conference
    ):
        session = make_session(conference, kind="WORKSHOP")
        presenter = make_presenter(
            conference, bio_md="hi", headshot="speakers/headshots/x.png"
        )
        link = add_presenter(session, presenter, confirmed=True)
        instantiate_presenter_checklist(link)
        new_item = ChecklistTemplateItem.objects.create(
            template=template,
            order=3,
            owner=ItemOwner.SPEAKER,
            title="Headshot check",
            auto_complete_rule=AutoRule.BIO_AND_HEADSHOT,
        )
        client.force_login(organizer)
        response = client.post(action(template, new_item, "backfill"), follow=True)
        assert "to 1 existing checklist(s)" in response.content.decode()
        instance = ChecklistItem.objects.get(template_item=new_item)
        assert instance.presenter == presenter
        assert instance.status == ItemStatus.DONE  # the rule ran on the new instance
        response = client.post(action(template, new_item, "backfill"), follow=True)
        assert "to 0 existing checklist(s)" in response.content.decode()
        assert ChecklistItem.objects.filter(template_item=new_item).count() == 1
