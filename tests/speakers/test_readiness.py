"""Items nobody can start yet (design §9.3a).

The three wait sources, the organizer override on top of them, what the
two sides show, and what the counts and the digests do with a waiting
item.
"""

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.urls import reverse

from speakers.checklists import (
    ChecklistError,
    add_adhoc_item,
    assign_item,
    complete_item,
    instantiate_general_checklist,
    instantiate_presenter_checklist,
    reopen_item,
    skip_item,
)
from speakers.constants import ItemOwner, ItemStatus, ReadyOverride, ReadyRule
from speakers.models import ChecklistTemplateItem, Handbook, ReadinessGate
from speakers.readiness import (
    apply_readiness,
    evaluate_readiness,
    refresh_for_conference,
)
from speakers.reminders import send_checklist_digests
from speakers.seeds import clone_checklists, seed_checklists, seed_readiness_gates
from volunteer.constants import ApplicationStatus
from volunteer.models import VolunteerProfile

from .factories import (
    add_presenter,
    make_presenter,
    make_session,
    make_settings,
    make_slot,
)

GATES = reverse("speakers:readiness_gates")
TODAY = date.today()


@pytest.fixture
def enabled(conference):
    return make_settings(conference)


@pytest.fixture
def organizer(db):
    return User.objects.create_user(
        username="organizer", email="org@example.com", is_staff=True
    )


@pytest.fixture
def speaker_user(db):
    return User.objects.create_user(username="ada", email="ada@example.com")


@pytest.fixture
def world(conference, enabled, speaker_user):
    """Ada on a workshop, with the seeded lines, including the ones that
    wait: the slot, the guides, registration and the tech check."""
    seed_checklists(conference)
    session = make_session(conference, title="Django 101")
    ada = make_presenter(
        conference, display_name="Ada", email="ada@example.com", user=speaker_user
    )
    link = add_presenter(session, ada, confirmed=True)
    # The lines a presenter gets on accepting: the per-session ones and the
    # every-presenter ones.
    instantiate_presenter_checklist(link)
    instantiate_general_checklist(ada)
    return {"session": session, "ada": ada, "link": link}


def item(presenter, title):
    return presenter.checklist_items.get(title=title)


@pytest.mark.django_db
class TestWaitSources:
    def test_a_rule_holds_the_slot_item_until_the_session_is_scheduled(self, world):
        slot_item = item(world["ada"], "Confirm your scheduled slot")
        assert slot_item.is_waiting
        assert slot_item.waiting_reason == "your slot is not scheduled yet"
        with pytest.raises(ChecklistError, match="not ready yet"):
            complete_item(slot_item, actor=world["ada"].user)
        make_slot(world["session"])
        assert refresh_for_conference(world["session"].conference) == 1
        slot_item.refresh_from_db()
        assert not slot_item.is_waiting and slot_item.waiting_reason == ""
        complete_item(slot_item, actor=world["ada"].user)
        assert item(world["ada"], "Confirm your scheduled slot").is_done

    def test_a_rule_holds_the_guide_until_it_is_published(self, world, conference):
        guide_item = item(world["ada"], "Read the workshop guide")
        assert guide_item.is_waiting
        assert guide_item.waiting_reason == "we are still writing it"
        handbook = Handbook.objects.create(
            conference=conference,
            key="workshop",
            title="Workshop guide",
            url="https://x",
        )
        # A draft is not a guide anyone can read.
        refresh_for_conference(conference)
        assert item(world["ada"], "Read the workshop guide").is_waiting
        handbook.publish()
        refresh_for_conference(conference)
        assert not item(world["ada"], "Read the workshop guide").is_waiting

    def test_registration_waits_until_pretix_is_set_up(self, world, conference):
        register = item(world["ada"], "Register for the conference")
        assert register.is_waiting
        assert register.waiting_reason == "registration is not open yet"
        settings_row = conference.speaker_settings
        settings_row.pretix_base_url = "https://pretix.example"
        settings_row.pretix_organizer = "pyladies"
        settings_row.pretix_event = "con2026"
        settings_row.pretix_api_token = "token"
        settings_row.save()
        refresh_for_conference(conference)
        assert not item(world["ada"], "Register for the conference").is_waiting

    def test_a_gate_holds_the_tech_check_until_an_organizer_opens_it(
        self, world, conference, organizer
    ):
        tech = item(world["ada"], "Do a tech check")
        assert tech.is_waiting
        assert tech.waiting_reason == "booking opens closer to the conference"
        gate = ReadinessGate.objects.get(conference=conference, code="tech-check-open")
        assert gate.set_open(True, actor=organizer) is True
        # Flipping it again is not a move, so nothing is re-evaluated twice.
        assert gate.set_open(True, actor=organizer) is False
        refresh_for_conference(conference)
        assert not item(world["ada"], "Do a tech check").is_waiting

    def test_a_per_session_line_waits_for_a_general_one(self, world, conference):
        """The blocking item may be general while the waiting one is on a
        session, which is the common shape: the organizer's onboarding line
        is about the person, the speaker's line is about the talk."""
        blocking = item(world["ada"], "Onboarding email sent")
        waiting_line = item(world["ada"], "Check your session title and summary")
        assert waiting_line.session_id is not None
        waiting_line.waits_for_line = blocking.template_item
        waiting_line.save()
        refresh_for_conference(conference)
        waiting_line.refresh_from_db()
        assert waiting_line.is_waiting and waiting_line.waits_for == blocking
        assert waiting_line.waiting_reason == "we are still on “Onboarding email sent”"

    def test_a_line_waits_for_another_line(self, world, conference):
        """The speaker line opens when the organizer line it names is done,
        and closes again if that item is reopened."""
        blocking = item(world["ada"], "Onboarding email sent")
        waiting_line = item(world["ada"], "Update your bio and headshot")
        waiting_line.waits_for_line = blocking.template_item
        waiting_line.template_waiting_note = "we are getting your onboarding ready"
        waiting_line.save()
        refresh_for_conference(conference)
        waiting_line.refresh_from_db()
        assert waiting_line.is_waiting and waiting_line.waits_for == blocking
        complete_item(blocking, manual=False)
        waiting_line.refresh_from_db()
        assert not waiting_line.is_waiting
        reopen_item(blocking, manual=False)
        waiting_line.refresh_from_db()
        assert waiting_line.is_waiting

    def test_a_skipped_blocker_counts_as_settled(self, world, conference, organizer):
        blocking = item(world["ada"], "Onboarding email sent")
        waiting_line = item(world["ada"], "Update your bio and headshot")
        waiting_line.waits_for = blocking
        waiting_line.save()
        refresh_for_conference(conference)
        assert item(world["ada"], "Update your bio and headshot").is_waiting
        skip_item(blocking, actor=organizer, note="not needed")
        assert not item(world["ada"], "Update your bio and headshot").is_waiting

    def test_a_gate_code_with_no_gate_row_holds_the_item(self, world, conference):
        """A line naming a gate the edition does not have waits: the code
        names work nobody has recorded."""
        line = item(world["ada"], "Do a tech check").template_item
        line.ready_gate_code = "does-not-exist"
        line.save()
        ReadinessGate.objects.filter(conference=conference).delete()
        fresh = add_adhoc_item(
            conference, "Ad hoc", ItemOwner.SPEAKER, presenter=world["ada"]
        )
        assert not fresh.is_waiting  # ad hoc items name no source

    def test_an_item_with_no_source_is_never_waiting(self, world):
        line = item(world["ada"], "Join the PyLadiesCon Discord")
        assert not line.is_waiting
        assert evaluate_readiness(line) == (False, "")


@pytest.mark.django_db
class TestOverride:
    def test_an_organizer_opens_a_waiting_item(self, client, world, organizer):
        slot_item = item(world["ada"], "Confirm your scheduled slot")
        client.force_login(organizer)
        response = client.post(
            reverse("speakers:item_ready", args=[slot_item.pk]),
            {"override": "OPEN", "next": world["ada"].get_absolute_url()},
        )
        assert response.status_code == 302
        slot_item.refresh_from_db()
        assert slot_item.ready_override == ReadyOverride.OPEN
        assert not slot_item.is_waiting
        complete_item(slot_item, actor=organizer)
        # And back to its own conditions.
        client.post(
            reverse("speakers:item_ready", args=[slot_item.pk]), {"override": ""}
        )
        slot_item.refresh_from_db()
        assert slot_item.ready_override == ""

    def test_an_organizer_holds_an_item_shut(self, client, world, organizer):
        discord = item(world["ada"], "Join the PyLadiesCon Discord")
        client.force_login(organizer)
        client.post(
            reverse("speakers:item_ready", args=[discord.pk]), {"override": "HOLD"}
        )
        discord.refresh_from_db()
        assert discord.is_waiting
        assert discord.waiting_reason == "the organizers are holding this"
        with pytest.raises(ChecklistError, match="not ready yet"):
            complete_item(discord, actor=world["ada"].user)

    def test_an_unknown_answer_is_refused(self, client, world, organizer):
        discord = item(world["ada"], "Join the PyLadiesCon Discord")
        client.force_login(organizer)
        response = client.post(
            reverse("speakers:item_ready", args=[discord.pk]), {"override": "MAYBE"}
        )
        assert response.status_code == 400

    def test_a_volunteer_who_carries_the_item_still_cannot_decide(
        self, client, world, conference, organizer
    ):
        """Reaching the queue is not the same as deciding what is ready: a
        volunteer the item was handed to passes the page gate and is still
        refused here."""
        vic = User.objects.create_user(username="vic", email="vic@example.com")
        VolunteerProfile.objects.create(
            user=vic,
            conference=conference,
            application_status=ApplicationStatus.APPROVED,
        )
        carried = item(world["ada"], "Promo materials prepared")
        assign_item(carried, assignee=vic, actor=organizer)
        client.force_login(vic)
        assert client.get(reverse("speakers:checklist_queue")).status_code == 200
        assert (
            client.post(
                reverse("speakers:item_ready", args=[carried.pk]), {"override": "HOLD"}
            ).status_code
            == 403
        )

    def test_only_organizers(self, client, world, speaker_user):
        discord = item(world["ada"], "Join the PyLadiesCon Discord")
        client.force_login(speaker_user)
        assert (
            client.post(
                reverse("speakers:item_ready", args=[discord.pk]), {"override": "HOLD"}
            ).status_code
            == 403
        )


@pytest.mark.django_db
class TestGatesPage:
    def test_a_gate_reads_as_its_name(self, world):
        assert str(ReadinessGate.objects.get(code="tech-check-open")) == (
            "Tech check booking open"
        )

    def test_organizer_sees_gates_and_flips_one(self, client, world, organizer):
        client.force_login(organizer)
        content = client.get(GATES).content.decode()
        assert "Tech check booking open" in content
        assert "tech-check-open" in content
        gate = ReadinessGate.objects.get(code="tech-check-open")
        response = client.post(
            reverse("speakers:readiness_gate_toggle", args=[gate.pk]),
            {"open": "1"},
            follow=True,
        )
        content = response.content.decode()
        assert "is open" in content
        assert not item(world["ada"], "Do a tech check").is_waiting
        # Shutting it again holds the item once more.
        client.post(
            reverse("speakers:readiness_gate_toggle", args=[gate.pk]), {"open": "0"}
        )
        assert item(world["ada"], "Do a tech check").is_waiting

    def test_flipping_to_the_state_it_is_in_changes_nothing(
        self, client, world, organizer
    ):
        gate = ReadinessGate.objects.get(code="tech-check-open")
        client.force_login(organizer)
        response = client.post(
            reverse("speakers:readiness_gate_toggle", args=[gate.pk]),
            {"open": "0"},
            follow=True,
        )
        assert "item(s) changed" not in response.content.decode()

    def test_adding_a_gate_opens_the_items_that_named_it(
        self, client, world, conference, organizer
    ):
        line = item(world["ada"], "Join the PyLadiesCon Discord").template_item
        line.ready_gate_code = "discord-ready"
        line.save()
        discord = item(world["ada"], "Join the PyLadiesCon Discord")
        discord.ready_gate = None
        discord.waits_for_line = None
        discord.save()
        client.force_login(organizer)
        client.post(
            reverse("speakers:readiness_gate_add"),
            {
                "code": "discord-ready",
                "name": "Discord ready",
                "waiting_note": "the server is not open yet",
            },
        )
        assert ReadinessGate.objects.filter(code="discord-ready").exists()

    def test_a_bad_gate_says_why(self, client, world, organizer):
        client.force_login(organizer)
        response = client.post(
            reverse("speakers:readiness_gate_add"),
            {"code": "", "name": ""},
            follow=True,
        )
        assert "That gate was not added" in response.content.decode()

    def test_the_rail_offers_it_and_volunteers_do_not_reach_it(
        self, client, world, organizer, speaker_user
    ):
        client.force_login(organizer)
        assert GATES in client.get(GATES).content.decode()
        client.force_login(speaker_user)
        assert client.get(GATES).status_code == 403


@pytest.mark.django_db
class TestWhatPeopleSee:
    def test_the_speaker_list_says_what_it_waits_for(self, client, world, speaker_user):
        client.force_login(speaker_user)
        content = client.get(reverse("speakers:my_checklist")).content.decode()
        assert "waiting: your slot is not scheduled yet" in content
        assert "checklist-box-waiting" in content

    def test_the_speaker_item_page_offers_no_tick(self, client, world, speaker_user):
        slot_item = item(world["ada"], "Confirm your scheduled slot")
        client.force_login(speaker_user)
        content = client.get(
            reverse("speakers:my_item_detail", args=[slot_item.pk])
        ).content.decode()
        assert "Nothing to do here yet" in content
        assert "Mark as done" not in content

    def test_the_dashboard_counts_waiting_without_chasing(
        self, client, world, speaker_user
    ):
        client.force_login(speaker_user)
        response = client.get(reverse("speakers:my_dashboard"))
        content = response.content.decode()
        assert "waiting" in content
        assert response.context["waiting_count"] >= 1
        # A waiting item with a past due date is not overdue.
        before = response.context["overdue_count"]
        slot_item = item(world["ada"], "Confirm your scheduled slot")
        slot_item.due_date = TODAY - timedelta(days=5)
        slot_item.save()
        assert not slot_item.is_overdue
        after = client.get(reverse("speakers:my_dashboard")).context["overdue_count"]
        assert after == before

    def test_the_organizer_row_and_item_page_show_it(self, client, world, organizer):
        slot_item = item(world["ada"], "Confirm your scheduled slot")
        client.force_login(organizer)
        content = client.get(world["ada"].get_absolute_url()).content.decode()
        assert "waiting: your slot is not scheduled yet" in content
        content = client.get(
            reverse("speakers:item_detail", args=[slot_item.pk])
        ).content.decode()
        assert "Nobody can start this yet" in content
        assert "Open it anyway" in content

    def test_a_waiting_item_is_left_out_of_the_digest(self, world, conference):
        slot_item = item(world["ada"], "Confirm your scheduled slot")
        slot_item.due_date = TODAY + timedelta(days=7)
        slot_item.save()
        mail.outbox.clear()
        send_checklist_digests(conference)
        assert all("Confirm your scheduled slot" not in m.body for m in mail.outbox)


@pytest.mark.django_db
class TestSeedsAndCloning:
    def test_seeding_gates_is_idempotent(self, conference):
        assert seed_readiness_gates(conference) == 2
        assert seed_readiness_gates(conference) == 0

    def test_gates_and_waits_clone_into_next_year(self, world, conference):
        line = item(world["ada"], "Join the PyLadiesCon Discord").template_item
        guide_line = item(world["ada"], "Read the workshop guide").template_item
        line.waits_for = guide_line
        line.save()
        gate = ReadinessGate.objects.get(code="tech-check-open")
        gate.set_open(True)
        next_year = type(conference).objects.create(
            year=2027, name="Next", slug="next", is_active=False
        )
        clone_checklists(next_year, conference)
        copied = ReadinessGate.objects.get(conference=next_year, code="tech-check-open")
        # Last year's answer says nothing about this year's work.
        assert copied.is_open is False
        copied_discord = ChecklistTemplateItem.objects.get(
            template__conference=next_year, title="Join the PyLadiesCon Discord"
        )
        assert copied_discord.waits_for is not None
        assert copied_discord.waits_for.template.conference == next_year
        assert copied_discord.waits_for.title == "Read the workshop guide"

    def test_the_nightly_task_refreshes_readiness(self, world, conference):
        from speakers.tasks import reevaluate_checklists_task

        make_slot(world["session"])
        assert "changed readiness" in reevaluate_checklists_task()
        assert not item(world["ada"], "Confirm your scheduled slot").is_waiting


@pytest.mark.django_db
class TestStatusGuard:
    def test_reopening_a_waiting_item_is_allowed(self, world, organizer):
        """An item ticked before its source shut again can still be put
        back: reopening is not work, it is a correction."""
        slot_item = item(world["ada"], "Confirm your scheduled slot")
        slot_item.ready_override = ReadyOverride.OPEN
        slot_item.save()
        apply_readiness(slot_item)
        complete_item(slot_item, actor=organizer)
        slot_item.ready_override = ""
        slot_item.save()
        apply_readiness(slot_item)
        assert slot_item.is_waiting
        reopen_item(slot_item, actor=organizer)
        assert item(world["ada"], "Confirm your scheduled slot").status == (
            ItemStatus.TODO
        )

    def test_the_message_falls_back_when_there_is_no_reason(self, world, organizer):
        discord = item(world["ada"], "Join the PyLadiesCon Discord")
        discord.is_waiting = True
        discord.save()
        with pytest.raises(ChecklistError, match="not ready to be worked on yet"):
            complete_item(discord, actor=organizer)


@pytest.mark.django_db
class TestRuleEdges:
    def test_the_slot_rule_answers_for_an_item_with_no_session(self, world, conference):
        general = add_adhoc_item(
            conference, "General", ItemOwner.SPEAKER, presenter=world["ada"]
        )
        general.ready_rule = ReadyRule.SESSION_SCHEDULED
        general.save()
        assert evaluate_readiness(general)[0] is True
