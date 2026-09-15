from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from speakers.checklists import (
    ChecklistError,
    add_adhoc_item,
    assign_item,
    backfill_template_item,
    block_item,
    complete_item,
    instantiate_presenter_checklist,
    instantiate_session_checklist,
    reopen_item,
    skip_item,
)
from speakers.constants import (
    AutoRule,
    Delivery,
    DueAnchor,
    ItemOwner,
    ItemStatus,
    MediaKind,
    PresenterRole,
    SessionKind,
    SessionStatus,
)
from speakers.models import (
    ActivityLog,
    ChecklistItem,
    ChecklistTemplate,
    ChecklistTemplateItem,
    TransitionError,
)
from speakers.seeds import seed_checklists
from speakers.services import accept_invitation, send_invitation

from .factories import (
    add_presenter,
    make_invitation,
    make_presenter,
    make_session,
    make_settings,
    make_slot,
)


@pytest.fixture
def seeded(conference):
    conference.start_date = date(2026, 12, 5)
    conference.save()
    make_settings(conference, translation_languages=["pt-br", "es"])
    seed_checklists(conference)
    return conference


@pytest.fixture
def liaison(db):
    return User.objects.create_user(username="lena", email="lena@example.com")


def workshop_template(conference):
    return ChecklistTemplate.objects.get(
        conference=conference, kind=SessionKind.WORKSHOP, role=PresenterRole.PRESENTER
    )


@pytest.mark.django_db
class TestInstantiateOnAccept:
    def test_accept_creates_exactly_the_template_items(self, seeded, liaison):
        session = make_session(seeded, kind=SessionKind.WORKSHOP)
        presenter = make_presenter(seeded, liaison=liaison)
        add_presenter(session, presenter)
        invitation = make_invitation(presenter, session)
        send_invitation(invitation)
        accept_invitation(invitation)

        template = workshop_template(seeded)
        items = list(presenter.checklist_items.order_by("order", "id"))
        assert [i.title for i in items] == list(
            template.items.values_list("title", flat=True)
        )
        assert all(i.session == session and i.conference == seeded for i in items)
        assert ChecklistItem.objects.count() == template.items.count()

        bio = presenter.checklist_items.get(title="Update your bio and headshot")
        assert bio.owner == ItemOwner.SPEAKER
        assert bio.due_date == invitation.accepted_at.date() + timedelta(days=7)
        assert bio.auto_complete_rule == AutoRule.BIO_AND_HEADSHOT
        assert bio.is_automatic is True
        register = presenter.checklist_items.get(title="Register for the conference")
        assert register.due_date == date(2026, 11, 21)
        slot_item = presenter.checklist_items.get(title="Confirm your scheduled slot")
        assert slot_item.due_date is None  # no slot yet
        onboarding = presenter.checklist_items.get(title="Onboarding email sent")
        assert onboarding.owner == ItemOwner.ORGANIZER
        assert onboarding.assignee == liaison
        promo = presenter.checklist_items.get(title="Promo materials prepared")
        assert promo.assignee is None

    def test_required_item_gates_confirmation(self, seeded):
        session = make_session(seeded, kind=SessionKind.WORKSHOP)
        presenter = make_presenter(seeded)
        add_presenter(session, presenter)
        invitation = make_invitation(presenter, session)
        send_invitation(invitation)
        accept_invitation(invitation)
        session.refresh_from_db()
        assert session.status == SessionStatus.INVITED
        with pytest.raises(TransitionError, match="Required checklist items"):
            session.confirm()
        item = presenter.checklist_items.get(
            title="Confirm your session title and summary"
        )
        assert item.is_required is True
        complete_item(item, actor=presenter.user)
        session.refresh_from_db()
        assert session.status == SessionStatus.CONFIRMED

    def test_accepting_again_does_not_duplicate(self, seeded):
        session = make_session(seeded, kind=SessionKind.WORKSHOP)
        presenter = make_presenter(seeded)
        link = add_presenter(session, presenter)
        instantiate_presenter_checklist(link)
        count = presenter.checklist_items.count()
        assert instantiate_presenter_checklist(link) == []
        assert presenter.checklist_items.count() == count

    def test_no_template_no_items(self, conference):
        session = make_session(conference)
        link = add_presenter(session, make_presenter(conference))
        assert instantiate_presenter_checklist(link) == []

    def test_slot_anchors_session_items(self, seeded):
        session = make_session(seeded, kind=SessionKind.WORKSHOP)
        make_slot(session)
        link = add_presenter(session, make_presenter(seeded), confirmed=True)
        instantiate_presenter_checklist(link)
        item = link.presenter.checklist_items.get(title="Confirm your scheduled slot")
        assert item.due_date == date(2026, 11, 21)


@pytest.mark.django_db
class TestSessionScope:
    def test_confirm_creates_post_production_items(self, seeded):
        jam = make_session(
            seeded,
            kind=SessionKind.PYJAM,
            delivery=Delivery.PRE_RECORDED,
            language="en",
        )
        add_presenter(
            jam, make_presenter(seeded), role=PresenterRole.PERFORMER, confirmed=True
        )
        jam.confirm()
        titles = list(jam.checklist_items.values_list("title", flat=True))
        assert "Translate (pt-br)" in titles and "Translate (es)" in titles
        assert titles.count("Translate") == 0
        transcribe = jam.checklist_items.get(title="Transcribe")
        assert transcribe.requires_asset_language == "en"
        assert transcribe.requires_asset_kind == MediaKind.TRANSCRIPT
        assert transcribe.presenter is None
        assert jam.checklist_items.filter(owner=ItemOwner.ORGANIZER).count() == len(
            titles
        )
        # Confirming again (e.g. cancel then re-confirm) does not duplicate.
        assert instantiate_session_checklist(jam) == []

    def test_live_session_has_no_post_production(self, seeded):
        jam = make_session(seeded, kind=SessionKind.PYJAM)
        add_presenter(jam, make_presenter(seeded), confirmed=True)
        jam.confirm()
        assert jam.checklist_items.count() == 0

    def test_without_settings_row_no_translation_items(self, conference):
        seed_checklists(conference)
        jam = make_session(
            conference, kind=SessionKind.PYJAM, delivery=Delivery.PRE_RECORDED
        )
        created = instantiate_session_checklist(jam)
        assert not any(i.title.startswith("Translate") for i in created)


@pytest.mark.django_db
class TestBackfill:
    def test_presenter_scope_backfill(self, seeded):
        template = workshop_template(seeded)
        session = make_session(seeded, kind=SessionKind.WORKSHOP)
        confirmed = add_presenter(session, make_presenter(seeded), confirmed=True)
        pending = add_presenter(session, make_presenter(seeded))
        instantiate_presenter_checklist(confirmed)
        new_item = ChecklistTemplateItem.objects.create(
            template=template,
            owner=ItemOwner.SPEAKER,
            title="Send us a fun fact",
            order=99,
            due_anchor=DueAnchor.CONFERENCE_START,
            due_offset_days=10,
        )
        assert backfill_template_item(new_item) == 1
        item = confirmed.presenter.checklist_items.get(title="Send us a fun fact")
        assert item.due_date == date(2026, 11, 25)
        assert not pending.presenter.checklist_items.exists()
        assert backfill_template_item(new_item) == 0

    def test_session_scope_backfill_only_instantiated_sessions(self, seeded):
        jam = make_session(
            seeded, kind=SessionKind.PYJAM, delivery=Delivery.PRE_RECORDED
        )
        untouched = make_session(
            seeded, kind=SessionKind.PYJAM, delivery=Delivery.PRE_RECORDED
        )
        instantiate_session_checklist(jam)
        template = ChecklistTemplate.for_session(jam)
        new_item = ChecklistTemplateItem.objects.create(
            template=template,
            owner=ItemOwner.ORGANIZER,
            title="Archive the master",
            order=99,
        )
        assert backfill_template_item(new_item) == 1
        assert jam.checklist_items.filter(title="Archive the master").exists()
        assert not untouched.checklist_items.exists()
        translate = template.items.get(title="Translate")
        assert backfill_template_item(translate) == 0


@pytest.mark.django_db
class TestLifecycle:
    @pytest.fixture
    def item(self, seeded, liaison):
        presenter = make_presenter(seeded, liaison=liaison)
        session = make_session(seeded, kind=SessionKind.PANEL)
        return add_adhoc_item(
            seeded,
            "Bring cookies",
            ItemOwner.SPEAKER,
            presenter=presenter,
            session=session,
            due_date=date(2026, 1, 1),
            actor=liaison,
        )

    def test_adhoc_item_logged(self, item, liaison):
        assert item.template_item is None
        assert str(item) == "Bring cookies"
        entry = ActivityLog.for_target(item.presenter).get()
        assert entry.action == "checklist.item_added"
        assert entry.actor == liaison
        assert entry.data["item_id"] == item.pk
        assert item.is_overdue is True

    def test_complete_reopen_skip_block(self, item, liaison):
        complete_item(item, actor=liaison, note="done at the bake sale")
        item.refresh_from_db()
        assert item.status == ItemStatus.DONE
        assert item.completed_by == liaison
        assert item.completed_at is not None
        assert item.note == "done at the bake sale"
        assert item.is_done and not item.is_open and not item.is_overdue
        reopen_item(item, actor=liaison)
        assert item.completed_by is None and item.completed_at is None
        skip_item(item, actor=liaison)
        assert item.status == ItemStatus.SKIPPED
        block_item(item, "video is 4 minutes over")
        assert item.status == ItemStatus.BLOCKED and item.is_open
        actions = [e.action for e in ActivityLog.for_target(item.presenter)]
        assert actions == [
            "checklist.blocked",
            "checklist.skipped",
            "checklist.todo",
            "checklist.done",
            "checklist.item_added",
        ]
        assert ActivityLog.objects.get(action="checklist.done").actor == liaison

    def test_same_status_not_logged_twice(self, item, liaison):
        complete_item(item, actor=liaison)
        complete_item(item, actor=liaison)
        assert ActivityLog.objects.filter(action="checklist.done").count() == 1

    def test_automatic_items_cannot_be_ticked_by_hand(self, item, liaison):
        item.auto_complete_rule = AutoRule.HANDBOOK_READ
        item.save()
        with pytest.raises(ChecklistError, match="completes itself"):
            complete_item(item, actor=liaison)
        with pytest.raises(ChecklistError):
            reopen_item(item, actor=liaison)
        complete_item(item, manual=False)
        assert item.status == ItemStatus.DONE
        skip_item(item, actor=liaison)  # organizers may still skip one
        assert item.status == ItemStatus.SKIPPED

    def test_assign(self, item, liaison, portal_user):
        assign_item(item, portal_user, actor=liaison)
        assert item.assignee == portal_user
        assign_item(item, portal_user, actor=liaison)
        assign_item(item, None, actor=liaison)
        entries = ActivityLog.objects.filter(action="checklist.assigned")
        assert entries.count() == 2
        assert "→ nobody" in entries.first().message

    def test_required_skip_confirms_session(self, seeded):
        session = make_session(seeded, kind=SessionKind.WORKSHOP)
        presenter = make_presenter(seeded)
        link = add_presenter(session, presenter, confirmed=True)
        session.mark_invited()
        instantiate_presenter_checklist(link)
        required = presenter.checklist_items.get(is_required=True)
        skip_item(required)
        session.refresh_from_db()
        assert session.status == SessionStatus.CONFIRMED

    def test_required_item_without_session(self, seeded):
        presenter = make_presenter(seeded)
        item = add_adhoc_item(
            seeded, "Sign the form", ItemOwner.SPEAKER, presenter=presenter
        )
        item.is_required = True
        item.save()
        complete_item(item)  # nothing to confirm, must not fail
        assert item.status == ItemStatus.DONE

    def test_confirm_blocked_message_lists_titles(self, seeded):
        session = make_session(seeded, kind=SessionKind.WORKSHOP)
        add_presenter(session, make_presenter(seeded), confirmed=True)
        add_adhoc_item(seeded, "Sign the form", ItemOwner.SPEAKER, session=session)
        ChecklistItem.objects.update(is_required=True)
        with pytest.raises(TransitionError, match="Sign the form"):
            session.confirm()
        session.refresh_from_db()
        assert session.status == SessionStatus.DRAFT

    def test_unsaved_session_skips_gate(self, seeded):
        session = make_session(seeded, kind=SessionKind.BREAK)
        session.confirm(save=False)
        assert session.status == SessionStatus.CONFIRMED
        assert not session.checklist_items.exists()

    def test_overdue_needs_due_date(self, seeded):
        item = add_adhoc_item(
            seeded, "x", ItemOwner.SPEAKER, presenter=make_presenter(seeded)
        )
        assert item.is_overdue is False
        item.due_date = timezone.now().date()
        assert item.is_overdue is False


@pytest.mark.django_db
class TestAdmin:
    def test_changelist(self, client, admin_user, seeded):
        add_adhoc_item(
            seeded, "Bring cookies", ItemOwner.SPEAKER, presenter=make_presenter(seeded)
        )
        client.force_login(admin_user)
        response = client.get(reverse("admin:speakers_checklistitem_changelist"))
        assert response.status_code == 200
        assert "Bring cookies" in response.content.decode()
        response = client.get(
            reverse("admin:speakers_checklisttemplateitem_changelist")
        )
        assert response.status_code == 200
