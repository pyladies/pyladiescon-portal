import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from pytest_django.asserts import assertRedirects

from speakers.checklists import instantiate_presenter_checklist
from speakers.constants import AutoRule, ItemOwner, ItemStatus
from speakers.forms import ChecklistTemplateItemForm
from speakers.models import (
    ActivityLog,
    ChecklistItem,
    ChecklistTemplateItem,
    Handbook,
    HandbookReadReceipt,
)
from speakers.program_types import presenter_role, seed_program_types, session_type
from speakers.seeds import seed_checklists

from .factories import add_presenter, make_presenter, make_session, make_settings

GUIDE = reverse("speakers:my_guide")
READ = reverse("speakers:my_guide_read")
LIST = reverse("speakers:handbook_list")


def editor(key="speaker"):
    return reverse("speakers:handbook_editor", args=[key])


@pytest.fixture
def enabled(conference):
    return make_settings(conference)


@pytest.fixture
def speaker(db):
    return User.objects.create_user(username="ada", email="ada@example.com")


@pytest.fixture
def presenter(conference, enabled, speaker):
    return make_presenter(conference, email="ada@example.com", user=speaker)


@pytest.fixture
def organizer(db):
    return User.objects.create_user(username="organizer", is_staff=True)


def publish(
    conference,
    version,
    body="Be **kind**.",
    key="speaker",
    title=None,
    url="https://conference.pyladies.com/docs/",
):
    handbook = Handbook.objects.create(
        conference=conference,
        key=key,
        version=version,
        body_md=body,
        url=url,
        title=title or f"{key.title()} guide",
    )
    handbook.publish()
    return handbook


def ack(key="speaker"):
    return {"acknowledge": "on", "key": key}


def guide_item(conference, presenter, key=""):
    return ChecklistItem.objects.create(
        conference=conference,
        owner=ItemOwner.SPEAKER,
        title=f"Read the {key or 'speaker'} guide",
        presenter=presenter,
        auto_complete_rule=AutoRule.HANDBOOK_READ,
        requires_handbook=key,
    )


@pytest.mark.django_db
class TestSpeakerGuide:
    def test_coming_soon_without_published_version(
        self, client, speaker, presenter, conference
    ):
        Handbook.objects.create(conference=conference, version=1, body_md="draft")
        guide_item(conference, presenter)
        client.force_login(speaker)
        content = client.get(GUIDE).content.decode()
        assert "Nothing to read just yet" in content
        assert client.post(READ, ack()).status_code == 400

    def test_only_the_guides_the_checklist_asks_for(
        self, client, speaker, presenter, conference
    ):
        publish(conference, 1)
        publish(conference, 1, key="workshop")
        guide_item(conference, presenter)
        client.force_login(speaker)
        content = client.get(GUIDE).content.decode()
        assert (
            'data-guide="speaker"' in content and 'data-guide="workshop"' not in content
        )
        assert 'href="https://conference.pyladies.com/docs/"' in content
        assert "I have read the Speaker guide (version 1)" in content

    def test_acknowledge_records_receipt_per_version(
        self, client, speaker, presenter, conference
    ):
        first = publish(conference, 1)
        guide_item(conference, presenter)
        client.force_login(speaker)
        response = client.post(READ, ack())
        assertRedirects(response, GUIDE)
        receipt = HandbookReadReceipt.objects.get(presenter=presenter, handbook=first)
        assert receipt.conference == conference
        content = client.get(GUIDE).content.decode()
        assert "You confirmed on" in content and 'name="acknowledge"' not in content
        assert ActivityLog.objects.get(action="handbook.read").data == {
            "key": "speaker",
            "version": 1,
        }
        client.post(READ, ack())  # confirming again is a no-op
        assert HandbookReadReceipt.objects.count() == 1
        second = publish(conference, 2, body="New rules")
        assert 'name="acknowledge"' in client.get(GUIDE).content.decode()
        client.post(READ, ack())
        assert HandbookReadReceipt.objects.filter(presenter=presenter).count() == 2
        assert HandbookReadReceipt.objects.filter(handbook=second).exists()

    def test_unticked_box_records_nothing(self, client, speaker, presenter, conference):
        publish(conference, 1)
        guide_item(conference, presenter)
        client.force_login(speaker)
        response = client.post(READ, {"key": "speaker"}, follow=True)
        assert "Tick the box" in response.content.decode()
        assert HandbookReadReceipt.objects.count() == 0

    def test_nothing_asked_for_nothing_to_confirm(
        self, client, speaker, presenter, conference
    ):
        """A presenter whose checklist does not exist yet is asked to read
        nothing, rather than acknowledging a guide it may never name."""
        publish(conference, 1)
        client.force_login(speaker)
        content = client.get(GUIDE).content.decode()
        assert "Nothing to read just yet" in content
        assert 'name="acknowledge"' not in content
        assert client.post(READ, ack()).status_code == 400
        assert HandbookReadReceipt.objects.count() == 0

    def test_cannot_acknowledge_a_guide_not_required(
        self, client, speaker, presenter, conference
    ):
        publish(conference, 1, key="performer")
        client.force_login(speaker)
        assert client.post(READ, ack("performer")).status_code == 400

    def test_note_only_guide_without_link(self, client, speaker, presenter, conference):
        publish(conference, 1, url="")
        guide_item(conference, presenter)
        client.force_login(speaker)
        content = client.get(GUIDE).content.decode()
        assert "Open the" not in content and "<strong>kind</strong>" in content

    def test_keynote_and_workshop_presenter_reads_two_guides(
        self, client, speaker, presenter, conference
    ):
        """A presenter on a keynote and a workshop gets one item per guide,
        each completing on its own acknowledgement, and republishing one
        guide re-opens only that item."""
        seed_checklists(conference)
        keynote = make_session(conference, kind="KEYNOTE")
        workshop = make_session(conference, kind="WORKSHOP")
        instantiate_presenter_checklist(
            add_presenter(keynote, presenter, confirmed=True)
        )
        instantiate_presenter_checklist(
            add_presenter(workshop, presenter, confirmed=True)
        )
        keynote_item = presenter.checklist_items.get(title="Read the keynote guide")
        workshop_item = presenter.checklist_items.get(title="Read the workshop guide")
        assert keynote_item.requires_handbook == "keynote"
        assert workshop_item.guide_key == "workshop"
        publish(conference, 1, key="keynote")
        publish(conference, 1, key="workshop")
        publish(conference, 1)  # the general guide is not required by these items
        client.force_login(speaker)
        content = client.get(GUIDE).content.decode()
        assert 'data-guide="keynote"' in content and 'data-guide="workshop"' in content
        assert 'data-guide="speaker"' not in content
        client.post(READ, ack("workshop"))
        keynote_item.refresh_from_db()
        workshop_item.refresh_from_db()
        assert workshop_item.status == ItemStatus.DONE
        assert keynote_item.status == ItemStatus.TODO
        client.post(READ, ack("keynote"))
        keynote_item.refresh_from_db()
        assert keynote_item.status == ItemStatus.DONE
        publish(conference, 2, key="workshop")
        keynote_item.refresh_from_db()
        workshop_item.refresh_from_db()
        assert workshop_item.status == ItemStatus.TODO
        assert keynote_item.status == ItemStatus.DONE

    def test_two_workshops_need_one_acknowledgement(
        self, client, speaker, presenter, conference
    ):
        first = guide_item(conference, presenter, "workshop")
        second = guide_item(conference, presenter, "workshop")
        publish(conference, 1, key="workshop")
        client.force_login(speaker)
        assert client.get(GUIDE).content.decode().count('data-guide="workshop"') == 1
        client.post(READ, ack("workshop"))
        assert (
            ChecklistItem.objects.filter(
                pk__in=[first.pk, second.pk], status=ItemStatus.DONE
            ).count()
            == 2
        )

    def test_rail_has_guide(self, client, speaker, presenter):
        client.force_login(speaker)
        assert GUIDE in client.get(reverse("speakers:my_dashboard")).content.decode()

    def test_requires_presenter(self, client, portal_user, enabled):
        client.force_login(portal_user)
        assert client.get(GUIDE).status_code == 403


@pytest.mark.django_db
class TestHandbookList:
    def test_organizer_only(self, client, portal_user, enabled, organizer):
        client.force_login(portal_user)
        assert client.get(LIST).status_code == 403
        client.force_login(organizer)
        assert client.get(LIST).status_code == 200
        assert LIST in client.get(reverse("organizer_dashboard")).content.decode()

    def test_lists_guides_with_default_placeholder(
        self, client, organizer, enabled, conference, presenter
    ):
        client.force_login(organizer)
        rows = client.get(LIST).context["rows"]
        assert [r["key"] for r in rows] == ["speaker"] and rows[0]["missing"]
        current = publish(conference, 1, key="workshop")
        current.record_read(presenter)
        Handbook.objects.create(conference=conference, key="workshop", version=2)
        rows = client.get(LIST).context["rows"]
        assert [r["key"] for r in rows] == ["workshop"]
        assert rows[0]["readers"] == 1 and rows[0]["draft"].version == 2

    def test_lists_keys_the_checklists_ask_for_and_nobody_wrote(
        self, client, organizer, enabled, conference
    ):
        """A seeded edition asks for workshop, keynote and performer guides;
        until someone writes them the items have nothing to read, so the
        organizer side says so (review of #424)."""
        seed_program_types(conference)
        seed_checklists(conference)
        publish(conference, 1, key="workshop")
        client.force_login(organizer)
        response = client.get(LIST)
        rows = response.context["rows"]
        missing = [r["key"] for r in rows if r.get("missing")]
        assert missing == ["keynote", "performer", "speaker"]
        assert [r["key"] for r in rows if not r.get("missing")] == ["workshop"]
        assert response.context["missing_count"] == 3
        content = response.content.decode()
        assert "Not created yet" in content and "?key=keynote#add-guide" in content
        # The button lands on the add form with the key and a title filled in.
        form = client.get(LIST, {"key": "keynote"}).context["new_form"]
        assert form.initial == {"key": "keynote", "title": "Keynote guide"}

    def test_add_guide(self, client, organizer, enabled, conference):
        client.force_login(organizer)
        response = client.post(LIST, {"key": "Performer", "title": "Performer guide"})
        assertRedirects(response, editor("performer"))
        draft = Handbook.draft(conference, "performer")
        assert draft.title == "Performer guide" and draft.url.startswith("https://")
        response = client.post(LIST, {"key": "performer", "title": "Again"})
        assert "already exists" in response.context["new_form"].errors["key"][0]


@pytest.mark.django_db
class TestHandbookEditor:
    def test_unknown_key_404(self, client, organizer, enabled):
        client.force_login(organizer)
        assert client.get(editor("nope")).status_code == 404
        assert (
            client.get(editor()).status_code == 200
        )  # the default guide always exists

    def test_save_draft_then_publish(
        self, client, organizer, enabled, conference, presenter
    ):
        client.force_login(organizer)
        assert (
            client.get(editor()).context["form"].initial["url"]
            == "https://conference.pyladies.com/docs/"
        )
        response = client.post(
            editor(),
            {
                "title": "Guide",
                "url": "https://example.org/guide",
                "body_md": "Hello",
                "action": "save",
            },
        )
        assertRedirects(response, editor())
        draft = Handbook.draft(conference)
        assert draft.version == 1 and not draft.is_published and draft.key == "speaker"
        assert Handbook.current(conference) is None
        content = client.get(editor()).content.decode()
        assert "Editing draft version 1" in content
        client.post(
            editor(),
            {
                "title": "Guide",
                "url": "https://example.org/guide",
                "body_md": "Hello *there*",
                "action": "publish",
            },
        )
        current = Handbook.current(conference)
        assert current.pk == draft.pk and current.url == "https://example.org/guide"
        assert Handbook.draft(conference) is None
        assert ActivityLog.objects.get(action="handbook.published").data == {
            "key": "speaker",
            "version": 1,
        }
        assert "Version 1 is live" in client.get(editor()).content.decode()

    def test_versions_are_per_key(self, client, organizer, enabled, conference):
        client.force_login(organizer)
        client.post(
            editor(),
            {
                "title": "Guide",
                "url": "https://e.org/1",
                "body_md": "",
                "action": "publish",
            },
        )
        client.post(
            editor(),
            {
                "title": "Guide",
                "url": "https://e.org/2",
                "body_md": "",
                "action": "publish",
            },
        )
        client.post(LIST, {"key": "workshop", "title": "Workshop guide"})
        client.post(
            editor("workshop"),
            {
                "title": "Workshop guide",
                "url": "https://e.org/w",
                "body_md": "",
                "action": "publish",
            },
        )
        assert Handbook.current(conference).version == 2
        assert Handbook.current(conference, "workshop").version == 1
        assert Handbook.next_version(conference, "workshop") == 2
        assert Handbook.keys(conference) == [
            ("speaker", "Guide"),
            ("workshop", "Workshop guide"),
        ]

    def test_publish_empty_refused(self, client, organizer, enabled, conference):
        client.force_login(organizer)
        response = client.post(
            editor(),
            {"title": "Guide", "url": "", "body_md": "  ", "action": "publish"},
        )
        assert response.status_code == 200
        assert "before publishing" in response.context["form"].errors["url"][0]
        assert Handbook.objects.count() == 0

    def test_invalid_form_rerenders(self, client, organizer, enabled):
        client.force_login(organizer)
        response = client.post(
            editor(), {"title": "", "body_md": "x", "action": "save"}
        )
        assert (
            response.status_code == 200 and "title" in response.context["form"].errors
        )

    def test_reader_counts(self, client, organizer, enabled, conference, presenter):
        handbook = publish(conference, 1)
        handbook.record_read(presenter)
        assert str(handbook) == "Speaker guide v1"
        assert handbook.published_at <= timezone.now()
        client.force_login(organizer)
        assert client.get(editor()).context["versions"][0].reader_count == 1


@pytest.mark.django_db
class TestTemplateItemGuideChoice:
    def test_choices_come_from_the_editions_guides(self, conference, enabled):
        publish(conference, 1, key="workshop")
        form = ChecklistTemplateItemForm(conference=conference)
        choices = form.fields["requires_handbook"].choices
        assert choices[0] == ("", "speaker (default)")
        assert ("workshop", "Workshop guide (workshop)") in choices
        assert not any(key == "speaker" for key, _ in choices[1:])

    def test_seeds_name_the_guides(self, conference):
        seed_program_types(conference)
        seed_checklists(conference)
        keys = dict(
            ChecklistTemplateItem.objects.filter(
                template__conference=conference,
                auto_complete_rule=AutoRule.HANDBOOK_READ,
            ).values_list("title", "requires_handbook")
        )
        assert keys["Read the workshop guide"] == "workshop"
        assert keys["Read the keynote guide"] == "keynote"
        assert keys["Read the performer guide"] == "performer"
        assert keys["Read the speaker guide"] == ""
        keynote = conference.checklist_templates.get(
            kind=session_type(conference, "KEYNOTE"),
            role=presenter_role(conference, "PRESENTER"),
        )
        assert keynote.items.filter(title="Read the keynote guide").exists()
        assert not keynote.items.filter(title="Read the speaker guide").exists()
