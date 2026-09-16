from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse

from speakers.checklists import (
    apply_new_template_item,
    complete_item,
    instantiate_general_checklist,
    instantiate_presenter_checklist,
)
from speakers.constants import (
    ChecklistScope,
    DueAnchor,
    ItemOwner,
    ItemStatus,
)
from speakers.models import ChecklistTemplate, ChecklistTemplateItem
from speakers.program_types import presenter_role, session_type
from speakers.seeds import seed_checklists
from speakers.services import accept_invitation, send_invitation

from .factories import (
    add_presenter,
    make_invitation,
    make_presenter,
    make_session,
    make_settings,
)


@pytest.fixture
def seeded(conference):
    make_settings(conference)
    seed_checklists(conference)
    return conference


@pytest.mark.django_db
class TestGeneralItems:
    def test_accepting_creates_general_items_once(self, seeded):
        workshop = make_session(seeded, kind="WORKSHOP")
        talk = make_session(seeded, kind="TALK")
        presenter = make_presenter(seeded)
        add_presenter(workshop, presenter)
        add_presenter(talk, presenter)
        invitation = make_invitation(presenter)  # general invitation covers both
        send_invitation(invitation)
        accept_invitation(invitation)
        general = presenter.checklist_items.filter(session__isnull=True)
        titles = list(general.values_list("title", flat=True))
        assert titles.count("Join the PyLadiesCon Discord") == 1
        assert titles.count("Register for the conference") == 1
        assert titles.count("Read the workshop guide") == 1
        assert "Presenter in portal" in titles
        assert not presenter.checklist_items.filter(
            session__isnull=False, title="Join the PyLadiesCon Discord"
        ).exists()
        assert instantiate_general_checklist(presenter) == []

    def test_two_workshops_share_one_guide_item(self, seeded):
        presenter = make_presenter(seeded)
        for title in ("A", "B"):
            session = make_session(seeded, kind="WORKSHOP", title=title)
            link = add_presenter(session, presenter, confirmed=True)
            instantiate_presenter_checklist(link)
        assert (
            presenter.checklist_items.filter(title="Read the workshop guide").count()
            == 1
        )
        assert presenter.checklist_items.filter(title="Do a tech check").count() == 2

    def test_general_lines_added_later_reach_accepted_presenters(self, seeded):
        presenter = make_presenter(seeded)
        add_presenter(make_session(seeded), presenter, confirmed=True)
        never_accepted = make_presenter(seeded)
        add_presenter(make_session(seeded), never_accepted)
        line = ChecklistTemplateItem.objects.create(
            template=ChecklistTemplate.for_general(seeded),
            owner=ItemOwner.SPEAKER,
            title="Send us a fun fact",
            due_anchor=DueAnchor.CONFERENCE_START,
            due_offset_days=3,
        )
        created = apply_new_template_item(line)
        assert [i.presenter for i in created] == [presenter]
        assert created[0].session is None

    def test_once_per_presenter_line_added_later(self, seeded):
        presenter = make_presenter(seeded)
        for title in ("A", "B"):
            add_presenter(
                make_session(seeded, kind="WORKSHOP", title=title),
                presenter,
                confirmed=True,
            )
        workshop = ChecklistTemplate.objects.get(
            conference=seeded,
            kind=session_type(seeded, "WORKSHOP"),
            role=presenter_role(seeded, "PRESENTER"),
        )
        line = ChecklistTemplateItem.objects.create(
            template=workshop,
            owner=ItemOwner.SPEAKER,
            title="Watch the intro",
            once_per_presenter=True,
        )
        assert len(apply_new_template_item(line)) == 1

    def test_general_line_refuses_session_anchor(self, seeded):
        with pytest.raises(ValidationError, match="not per session"):
            ChecklistTemplateItem.objects.create(
                template=ChecklistTemplate.for_general(seeded),
                owner=ItemOwner.SPEAKER,
                title="x",
                due_anchor=DueAnchor.SESSION_START,
            )

    def test_general_template_rules(self, conference):
        with pytest.raises(ValidationError, match="no kind"):
            ChecklistTemplate.objects.create(
                conference=conference,
                scope=ChecklistScope.GENERAL,
                name="g",
                kind=session_type(conference, "TALK"),
            )
        with pytest.raises(ValidationError, match="Pick the session kind"):
            ChecklistTemplate.objects.create(
                conference=conference,
                scope=ChecklistScope.PRESENTER,
                name="p",
                role=presenter_role(conference, "HOST"),
            )
        general = ChecklistTemplate.objects.create(
            conference=conference, scope=ChecklistScope.GENERAL, name="Everyone"
        )
        assert (
            general.is_general and ChecklistTemplate.for_general(conference) == general
        )


@pytest.mark.django_db
class TestSpeakerViews:
    @pytest.fixture
    def speaker(self, seeded):
        user = User.objects.create_user(username="ada", email="ada@example.com")
        presenter = make_presenter(seeded, email="ada@example.com", user=user)
        session = make_session(seeded, kind="WORKSHOP", title="Django 101")
        add_presenter(session, presenter)
        invitation = make_invitation(presenter, session)
        send_invitation(invitation)
        accept_invitation(invitation)
        return user, presenter, session

    def test_general_group_first_and_off_session_pages(self, client, speaker):
        user, presenter, session = speaker
        client.force_login(user)
        response = client.get(reverse("speakers:my_checklist"), {"view": "session"})
        groups = response.context["groups"]
        assert groups[0]["session"] is None and groups[1]["session"] == session
        assert "For you as a speaker" in response.content.decode()
        detail = client.get(
            reverse("speakers:my_session_detail", args=[session.slug])
        ).content.decode()
        assert "Join the PyLadiesCon Discord" not in detail
        assert "Do a tech check" in detail

    def test_dashboard_shows_general_status(self, client, speaker):
        user, presenter, session = speaker
        general = presenter.checklist_items.filter(
            session__isnull=True, owner=ItemOwner.SPEAKER
        )
        complete_item(general.get(title="Join the PyLadiesCon Discord"))
        client.force_login(user)
        content = client.get(reverse("speakers:my_dashboard")).content.decode()
        assert 'id="general-summary"' in content
        done = general.exclude(status=ItemStatus.TODO).count()
        assert f"{done} of {general.count()} tasks done" in content


@pytest.mark.django_db
class TestDedupeCommand:
    def test_collapses_old_per_session_copies(self, conference):
        make_settings(conference)
        # An edition seeded before the general template: recreate that shape.
        seed_checklists(conference)
        general = ChecklistTemplate.for_general(conference)
        general.delete()
        workshop = ChecklistTemplate.objects.get(
            conference=conference,
            kind=session_type(conference, "WORKSHOP"),
            role=presenter_role(conference, "PRESENTER"),
        )
        old_discord = ChecklistTemplateItem.objects.create(
            template=workshop,
            owner=ItemOwner.SPEAKER,
            title="Join the PyLadiesCon Discord",
        )
        guide = workshop.items.get(title="Read the workshop guide")
        guide.once_per_presenter = False
        guide.save()
        presenter = make_presenter(conference)
        for title in ("A", "B"):
            link = add_presenter(
                make_session(conference, kind="WORKSHOP", title=title),
                presenter,
                confirmed=True,
            )
            instantiate_presenter_checklist(link)
        assert (
            presenter.checklist_items.filter(
                title="Join the PyLadiesCon Discord"
            ).count()
            == 2
        )
        done = presenter.checklist_items.filter(title="Read the workshop guide").first()
        complete_item(done, manual=False)
        # Now the new defaults arrive, and this presenter already got the
        # general list (say, they accepted another session meanwhile).
        seed_checklists(conference)
        guide.once_per_presenter = True
        guide.save()
        instantiate_general_checklist(presenter)
        out = StringIO()
        call_command("dedupe_general_items", stdout=out)
        # The guide copy moves; the Discord copies are dropped in favour of
        # the general item that already exists.
        assert "moved 1 item(s)" in out.getvalue()
        assert "dropped 3 duplicate(s)" in out.getvalue()
        assert "redundant template line(s)" in out.getvalue()
        discord = presenter.checklist_items.get(title="Join the PyLadiesCon Discord")
        assert discord.session is None
        assert discord.template_item.template == ChecklistTemplate.for_general(
            conference
        )
        guide_item = presenter.checklist_items.get(title="Read the workshop guide")
        assert guide_item.session is None and guide_item.status == ItemStatus.DONE
        assert not ChecklistTemplateItem.objects.filter(pk=old_discord.pk).exists()
        call_command("dedupe_general_items", stdout=out)  # idempotent

    def test_without_general_template(self, conference):
        out = StringIO()
        call_command("dedupe_general_items", stdout=out)
        assert "moved 0 item(s)" in out.getvalue()
