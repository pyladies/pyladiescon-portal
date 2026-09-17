import re
from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from pytest_django.asserts import assertRedirects

from speakers.checklists import add_adhoc_item, block_item, complete_item, skip_item
from speakers.constants import (
    AutoRule,
    Delivery,
    ItemOwner,
    ItemStatus,
    SessionStatus,
)
from speakers.models import ChecklistItem
from volunteer.models import Team

from .factories import (
    add_presenter,
    make_presenter,
    make_session,
    make_settings,
    make_slot,
)

DASHBOARD = reverse("speakers:my_dashboard")
CHECKLIST = reverse("speakers:my_checklist")


def lagos_today():
    """Today for the test presenter (Africa/Lagos), which the checklist
    measures deadlines against; the machine's own date can differ."""
    return timezone.now().astimezone(ZoneInfo("Africa/Lagos")).date()


def toggle(item):
    return reverse("speakers:my_item_toggle", args=[item.pk])


@pytest.fixture
def speaker(db):
    return User.objects.create_user(username="ada", email="ada@example.com")


@pytest.fixture
def presenter(conference, speaker):
    make_settings(conference)
    return make_presenter(
        conference,
        display_name="Ada",
        email="ada@example.com",
        user=speaker,
        timezone="Africa/Lagos",
    )


@pytest.fixture
def session(conference, presenter):
    session = make_session(conference, title="Django 101")
    add_presenter(session, presenter, confirmed=True)
    return session


@pytest.mark.django_db
class TestDashboardLists:
    def test_lock_icon_once_scheduled(
        self, client, speaker, presenter, session, conference
    ):
        client.force_login(speaker)
        page = client.get(DASHBOARD).content.decode()
        assert "locked now that the session is scheduled" not in page
        session.status = SessionStatus.SCHEDULED
        session.save()
        page = client.get(DASHBOARD).content.decode()
        assert "locked now that the session is scheduled" in page

    def test_item_descriptions_render_on_the_checklist(
        self, client, speaker, presenter, conference
    ):
        """The items moved off the dashboard to their own page; their
        descriptions went with them."""
        add_adhoc_item(
            conference,
            "Bring snacks",
            ItemOwner.SPEAKER,
            presenter=presenter,
            description_md="Something **salty** for the tech check.",
        )
        add_adhoc_item(conference, "Wave hello", ItemOwner.SPEAKER, presenter=presenter)
        client.force_login(speaker)
        page = client.get(CHECKLIST).content.decode()
        assert "Bring snacks" in page and "Wave hello" in page
        assert "<strong>salty</strong>" in page
        assert page.count('class="small text-body-secondary item-description"') == 1

    def test_dashboard_summarises_sessions_and_todos(
        self, client, speaker, presenter, session
    ):
        client.force_login(speaker)
        content = client.get(DASHBOARD).content.decode()
        assert 'id="my-sessions"' in content and "Your sessions" in content
        assert "Django 101" in content and "Not yet public" in content
        assert "Workshop" in content and "Presenter" in content
        assert "tasks done" not in content
        assert "Nothing open on your to-do list" in content
        assert "Your to-dos" not in content  # the lists live on the checklist page
        # The per-session checklist button lands on the session page's
        # checklist section, so the reader keeps the session context.
        session_checklist = (
            f"{reverse('speakers:my_session_detail', args=[session.slug])}#checklist"
        )
        assert session_checklist in content
        assert f"{CHECKLIST}?session=" not in content
        content = client.get(reverse("speakers:my_sessions")).content.decode()
        assert session_checklist in content
        assert f"{CHECKLIST}?session=" not in content

    def test_checklist_page_with_zero_items(self, client, speaker, presenter, session):
        client.force_login(speaker)
        content = client.get(CHECKLIST).content.decode()
        assert "Nothing on your list here" in content
        assert "Dates are in Africa/Lagos" in content
        assert "All, by due date" in content and "By session" in content

    def test_two_lists_summary_and_assignee(
        self, client, speaker, presenter, session, conference
    ):
        lena = User.objects.create_user(
            username="lena", first_name="Lena", last_name="K"
        )
        mine = add_adhoc_item(
            conference,
            "Read the guide",
            ItemOwner.SPEAKER,
            presenter=presenter,
            session=session,
        )
        done = add_adhoc_item(
            conference,
            "Register",
            ItemOwner.SPEAKER,
            presenter=presenter,
            session=session,
        )
        complete_item(done)
        theirs = add_adhoc_item(
            conference,
            "Promo materials",
            ItemOwner.ORGANIZER,
            presenter=presenter,
            session=session,
            assignee=lena,
        )
        unassigned = add_adhoc_item(
            conference,
            "Schedule confirmation",
            ItemOwner.ORGANIZER,
            presenter=presenter,
        )
        client.force_login(speaker)
        dashboard = client.get(DASHBOARD).content.decode()
        assert "1 of 2 tasks done" in dashboard
        assert "1 open to-do" in dashboard
        content = client.get(CHECKLIST).content.decode()
        assert toggle(mine) in content and toggle(done) in content
        assert toggle(theirs) not in content and toggle(unassigned) not in content
        assert "Lena K is on it" in content and "not yet assigned" in content
        assert "A team task: nothing for you to do here." in content
        assert re.search(r'data-item-id="%d"\s+data-status="DONE"' % done.pk, content)

    def test_team_owned_item_named(self, client, speaker, presenter, conference):
        team = Team.objects.create(
            conference=conference, short_name="Design", description="d"
        )
        add_adhoc_item(
            conference, "Poster", ItemOwner.ORGANIZER, presenter=presenter, team=team
        )
        client.force_login(speaker)
        assert "Design team is on it" in client.get(CHECKLIST).content.decode()

    def test_speaker_sees_who_completed_a_team_task(
        self, client, speaker, presenter, session, conference
    ):
        volunteer = User.objects.create_user(
            username="vol", first_name="Volunteer", last_name="A"
        )
        uploaded = add_adhoc_item(
            conference,
            "Upload the transcript",
            ItemOwner.ORGANIZER,
            presenter=presenter,
            session=session,
            assignee=volunteer,
        )
        complete_item(uploaded, actor=volunteer)
        automatic = add_adhoc_item(
            conference, "Session scheduled", ItemOwner.ORGANIZER, presenter=presenter
        )
        complete_item(automatic, manual=False)
        client.force_login(speaker)
        content = client.get(CHECKLIST).content.decode()
        assert "done by Volunteer A on" in content
        assert "done automatically on" in content
        assert "nothing for you to do here" not in content.split("Session scheduled")[1]

    def test_automatic_item_is_dashed_and_not_tickable(
        self, client, speaker, presenter, session, conference
    ):
        auto = ChecklistItem.objects.create(
            conference=conference,
            owner=ItemOwner.SPEAKER,
            title="Bio and headshot",
            presenter=presenter,
            session=session,
            auto_complete_rule=AutoRule.BIO_AND_HEADSHOT,
        )
        client.force_login(speaker)
        content = client.get(CHECKLIST).content.decode()
        assert "checklist-item-auto" in content
        assert toggle(auto) not in content
        assert "Ticks itself" in content

    def test_blocked_item_and_video_items(self, client, speaker, presenter, conference):
        jam = make_session(conference, kind="PYJAM", delivery=Delivery.PRE_RECORDED)
        add_presenter(jam, presenter, role="PERFORMER", confirmed=True)
        length = add_adhoc_item(
            conference, "Check video length", ItemOwner.ORGANIZER, session=jam
        )
        block_item(length, "Video is 2:05 over the 10-minute limit.")
        client.force_login(speaker)
        content = client.get(CHECKLIST).content.decode()
        assert "What we're preparing for your video" in content
        assert "Blocked" in content
        assert "2:05 over the 10-minute limit" in content

    def test_overdue_in_presenter_timezone(
        self, client, speaker, presenter, session, conference
    ):
        late = add_adhoc_item(
            conference,
            "Late thing",
            ItemOwner.SPEAKER,
            presenter=presenter,
            due_date=lagos_today() - timedelta(days=2),
        )
        soon = add_adhoc_item(
            conference,
            "Soon thing",
            ItemOwner.SPEAKER,
            presenter=presenter,
            due_date=lagos_today() + timedelta(days=30),
        )
        tomorrow = add_adhoc_item(
            conference,
            "Tomorrow thing",
            ItemOwner.SPEAKER,
            presenter=presenter,
            due_date=lagos_today() + timedelta(days=1),
        )
        done = add_adhoc_item(
            conference,
            "Done thing",
            ItemOwner.SPEAKER,
            presenter=presenter,
            due_date=lagos_today() - timedelta(days=5),
        )
        complete_item(done)
        client.force_login(speaker)
        response = client.get(CHECKLIST)
        content = response.content.decode()
        assert "checklist-due-overdue" in content
        by_id = {i.pk: i for i in response.context["speaker_items"]}
        assert by_id[late.pk].overdue is True and by_id[late.pk].due_tone == "overdue"
        assert by_id[soon.pk].overdue is False and by_id[soon.pk].due_tone == "later"
        assert by_id[tomorrow.pk].due_tone == "soon"
        assert by_id[done.pk].due_tone == "quiet"  # finished: no colour
        assert "checklist-due-overdue" in content and "· overdue" in content
        assert "tomorrow" in content
        # Done titles are struck through; open ones get an empty box.
        assert re.search(r'checklist-title-done">Done thing</a>', content)
        assert not re.search(r'checklist-title-done">Late thing</a>', content)
        assert re.search(
            r'<button[^>]*class="checklist-box "[^>]*>\s*</button>', content
        )
        assert "checklist-box checklist-box-done" in content


@pytest.mark.django_db
class TestToggle:
    def test_tick_and_untick_own_item(
        self, client, speaker, presenter, session, conference
    ):
        item = add_adhoc_item(
            conference, "Read the guide", ItemOwner.SPEAKER, presenter=presenter
        )
        client.force_login(speaker)
        # Ticking lands back on the item, not at the top of the page.
        assertRedirects(client.post(toggle(item)), f"{CHECKLIST}#item-{item.pk}")
        item.refresh_from_db()
        assert item.status == ItemStatus.DONE
        assert item.completed_by == speaker
        # The form sends the page it was on; anything off-site is ignored.
        assertRedirects(
            client.post(toggle(item), {"next": f"{CHECKLIST}?view=session#x"}),
            f"{CHECKLIST}?view=session#item-{item.pk}",
        )
        assertRedirects(
            client.post(toggle(item), {"next": "https://evil.example/x"}),
            f"{CHECKLIST}#item-{item.pk}",
        )
        client.post(toggle(item))
        item.refresh_from_db()
        assert item.status == ItemStatus.TODO
        skip_item(item, note="not needed")
        response = client.post(toggle(item), follow=True)
        item.refresh_from_db()
        assert item.status == ItemStatus.SKIPPED
        assert "An organizer skipped" in response.content.decode()

    def test_htmx_tick_swaps_the_row_and_toasts_in_place(
        self, client, speaker, presenter, session, conference
    ):
        """With htmx the response is just the row and the toast container,
        so the page neither reloads nor scrolls."""
        item = add_adhoc_item(
            conference,
            "Send slides",
            ItemOwner.SPEAKER,
            presenter=presenter,
            session=session,
            due_date=lagos_today() + timedelta(days=2),
        )
        client.force_login(speaker)
        page = client.get(CHECKLIST).content.decode()
        assert "htmx.min.js" in page and 'id="portal-toasts"' in page
        assert f'hx-target="#item-{item.pk}"' in page
        response = client.post(toggle(item), HTTP_HX_REQUEST="true")
        assert response.status_code == 200
        content = response.content.decode()
        assert "<!DOCTYPE" not in content
        assert re.search(r'id="item-%d"[^>]*data-status="DONE"' % item.pk, content)
        assert "checklist-box checklist-box-done" in content
        assert 'checklist-title-done">Send slides</a>' in content
        assert 'id="portal-toasts"' in content and 'hx-swap-oob="true"' in content
        assert "Done: Send slides" in content and "portal-toast" in content
        # Untick the same way; the due badge comes back coloured.
        content = client.post(toggle(item), HTTP_HX_REQUEST="true").content.decode()
        assert "Reopened: Send slides" in content
        assert "checklist-due-soon" in content and "in 2 days" in content
        # A refused tick (automatic item) still answers with the row and the error toast.
        item.auto_complete_rule = AutoRule.BIO_AND_HEADSHOT
        item.save()
        content = client.post(toggle(item), HTTP_HX_REQUEST="true").content.decode()
        assert "text-bg-danger" in content and f'id="item-{item.pk}"' in content

    def test_cannot_tick_organizer_item(self, client, speaker, presenter, conference):
        item = add_adhoc_item(
            conference, "Promo", ItemOwner.ORGANIZER, presenter=presenter
        )
        client.force_login(speaker)
        assert client.post(toggle(item)).status_code == 403
        item.refresh_from_db()
        assert item.status == ItemStatus.TODO

    def test_cannot_tick_another_presenters_item(
        self, client, speaker, presenter, conference
    ):
        other = make_presenter(conference)
        item = add_adhoc_item(conference, "Theirs", ItemOwner.SPEAKER, presenter=other)
        client.force_login(speaker)
        assert client.post(toggle(item)).status_code == 404

    def test_cannot_tick_automatic_item(self, client, speaker, presenter, conference):
        item = ChecklistItem.objects.create(
            conference=conference,
            owner=ItemOwner.SPEAKER,
            title="Registered",
            presenter=presenter,
            auto_complete_rule=AutoRule.PRETIX_REGISTERED,
        )
        client.force_login(speaker)
        response = client.post(toggle(item), follow=True)
        assert "completes itself" in response.content.decode()
        item.refresh_from_db()
        assert item.status == ItemStatus.TODO

    def test_requires_presenter(self, client, portal_user, conference):
        make_settings(conference)
        item = add_adhoc_item(
            conference, "x", ItemOwner.SPEAKER, presenter=make_presenter(conference)
        )
        client.force_login(portal_user)
        assert client.post(toggle(item)).status_code == 403


@pytest.mark.django_db
class TestChecklistViews:
    @pytest.fixture
    def items(self, conference, presenter, session):
        panel = make_session(conference, title="Careers panel", kind="PANEL")
        add_presenter(panel, presenter, role="PANELIST", confirmed=True)
        return {
            "late": add_adhoc_item(
                conference,
                "Slides",
                ItemOwner.SPEAKER,
                presenter=presenter,
                session=session,
                due_date=lagos_today() + timedelta(days=9),
            ),
            "soon": add_adhoc_item(
                conference,
                "Bio",
                ItemOwner.SPEAKER,
                presenter=presenter,
                session=panel,
                due_date=lagos_today() + timedelta(days=2),
            ),
            "undated": add_adhoc_item(
                conference, "Discord", ItemOwner.SPEAKER, presenter=presenter
            ),
            "team": add_adhoc_item(
                conference,
                "Promo",
                ItemOwner.ORGANIZER,
                presenter=presenter,
                session=session,
                due_date=lagos_today() + timedelta(days=5),
            ),
            "panel": panel,
        }

    def test_all_view_sorts_by_due_date_undated_last(
        self, client, speaker, presenter, items
    ):
        client.force_login(speaker)
        response = client.get(CHECKLIST)
        assert [i.title for i in response.context["speaker_items"]] == [
            "Bio",
            "Slides",
            "Discord",
        ]
        assert response.context["view"] == "all"

    def test_session_view_groups(self, client, speaker, presenter, session, items):
        client.force_login(speaker)
        response = client.get(CHECKLIST, {"view": "session"})
        groups = response.context["groups"]
        assert [g["session"].title if g["session"] else None for g in groups] == [
            None,
            "Careers panel",
            "Django 101",
        ]
        assert [i.title for i in groups[2]["speaker"]] == ["Slides"]
        assert [i.title for i in groups[2]["organizer"]] == ["Promo"]
        assert [i.title for i in groups[0]["speaker"]] == ["Discord"]
        complete_item(items["late"])
        response = client.get(CHECKLIST, {"view": "session"})
        groups = response.context["groups"]
        assert (groups[2]["done"], groups[2]["total"]) == (1, 1)
        assert (groups[1]["done"], groups[1]["total"]) == (0, 1)
        content = response.content.decode()
        assert "1 of 1 tasks done" in content and "0 of 1 tasks done" in content
        assert (
            'data-session-group="general"' in content
            and "For you as a speaker" in content
        )

    def test_single_session_filter(self, client, speaker, presenter, session, items):
        client.force_login(speaker)
        response = client.get(CHECKLIST, {"session": session.slug})
        assert response.context["only"] == session
        assert [g["session"] for g in response.context["groups"]] == [session]
        assert "Checklist for Django 101" in response.content.decode()
        other = make_session(session.conference, title="Not mine")
        assert client.get(CHECKLIST, {"session": other.slug}).status_code == 404


@pytest.mark.django_db
class TestSessionDetail:
    def test_detail_shows_content_and_checklist(
        self, client, speaker, presenter, session, conference
    ):
        session.summary_md = "Learn **Django**"
        session.level = "BEGINNER"
        session.save()
        add_adhoc_item(
            conference,
            "Slides",
            ItemOwner.SPEAKER,
            presenter=presenter,
            session=session,
        )
        add_adhoc_item(conference, "Elsewhere", ItemOwner.SPEAKER, presenter=presenter)
        client.force_login(speaker)
        url = reverse("speakers:my_session_detail", args=[session.slug])
        content = client.get(url).content.decode()
        assert "<strong>Django</strong>" in content and "Beginner" in content
        assert "Checklist for this session" in content
        assert "Slides" in content and "Elsewhere" not in content
        assert "Not scheduled yet" in content and "Just you so far" in content
        assert reverse("speakers:my_session_edit", args=[session.slug]) in content

    def test_detail_empty_description_and_slot(
        self, client, speaker, presenter, session, conference
    ):
        make_slot(session)
        client.force_login(speaker)
        content = client.get(
            reverse("speakers:my_session_detail", args=[session.slug])
        ).content.decode()
        assert "No description yet" in content and "14:00 UTC" in content

    def test_detail_forbidden_for_others_session(
        self, client, speaker, presenter, conference
    ):
        other = make_session(conference, title="Theirs")
        client.force_login(speaker)
        assert (
            client.get(
                reverse("speakers:my_session_detail", args=[other.slug])
            ).status_code
            == 403
        )

    def test_sessions_list_has_counts_and_buttons(
        self, client, speaker, presenter, session, conference
    ):
        done = add_adhoc_item(
            conference,
            "Slides",
            ItemOwner.SPEAKER,
            presenter=presenter,
            session=session,
        )
        add_adhoc_item(
            conference, "Bio", ItemOwner.SPEAKER, presenter=presenter, session=session
        )
        complete_item(done)
        client.force_login(speaker)
        content = client.get(reverse("speakers:my_sessions")).content.decode()
        assert "1 of 2 tasks done" in content
        # The per-session checklist button lands on the session page's
        # checklist section, so the reader keeps the session context.
        session_url = reverse("speakers:my_session_detail", args=[session.slug])
        assert f"{session_url}#checklist" in content
        assert f"{CHECKLIST}?session=" not in content
