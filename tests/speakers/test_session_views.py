import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from portal.models import Conference
from speakers.checklists import add_adhoc_item
from speakers.constants import Delivery, ItemOwner, SessionStatus
from speakers.context_processors import speaker_module
from speakers.forms import ProgramItemForm, SessionForm
from speakers.models import ActivityLog, ChecklistItem, Session
from speakers.permissions import can_work_sessions, is_speaker_liaison
from speakers.program_types import session_type

from .factories import (
    add_presenter,
    make_channel,
    make_presenter,
    make_session,
    make_settings,
    make_slot,
)


@pytest.fixture
def enabled(conference):
    return make_settings(conference)


@pytest.fixture
def organizer(db):
    return User.objects.create_user(
        username="organizer", email="org@example.com", is_staff=True
    )


@pytest.fixture
def liaison(db):
    return User.objects.create_user(
        username="liaison", email="liaison@example.com", first_name="Lena"
    )


@pytest.fixture
def sessions(conference, enabled, liaison):
    """Two content sessions (one liaised by ``liaison``) and a break."""
    mine = make_session(conference, title="Liaised workshop")
    theirs = make_session(conference, title="Other panel", kind="PANEL")
    coffee = make_session(conference, title="Coffee", kind="BREAK")
    add_presenter(mine, make_presenter(conference, display_name="Ada", liaison=liaison))
    add_presenter(
        theirs,
        make_presenter(conference, display_name="Grace"),
        role="PANELIST",
        confirmed=True,
    )
    return {"mine": mine, "theirs": theirs, "coffee": coffee}


LIST = reverse("speakers:session_list")


@pytest.mark.django_db
class TestAccess:
    def test_anonymous_redirected(self, client, enabled):
        assertRedirects(client.get(LIST), reverse("account_login") + "?next=" + LIST)

    def test_plain_user_forbidden(self, client, portal_user, enabled):
        client.force_login(portal_user)
        assert client.get(LIST).status_code == 403

    def test_module_off_is_404_even_for_organizer(self, client, organizer):
        client.force_login(organizer)
        assert client.get(LIST).status_code == 404

    def test_organizer_sees_everything(self, client, organizer, sessions):
        client.force_login(organizer)
        response = client.get(LIST)
        assert response.status_code == 200
        titles = [row.title for row in response.context["table"].data]
        assert titles == ["Coffee", "Liaised workshop", "Other panel"]

    def test_liaison_sees_only_assigned_sessions(self, client, liaison, sessions):
        client.force_login(liaison)
        response = client.get(LIST)
        assert response.status_code == 200
        titles = [row.title for row in response.context["table"].data]
        assert titles == ["Liaised workshop"]
        assert client.get(sessions["theirs"].get_absolute_url()).status_code == 404
        assert client.get(sessions["mine"].get_absolute_url()).status_code == 200

    def test_liaison_cannot_create(self, client, liaison, sessions):
        client.force_login(liaison)
        assert client.get(reverse("speakers:session_create")).status_code == 403
        assert client.get(reverse("speakers:program_item_create")).status_code == 403

    def test_index_redirects_staff_to_sessions(self, client, organizer, enabled):
        client.force_login(organizer)
        assertRedirects(client.get(reverse("speakers:index")), LIST)

    def test_index_placeholder_for_others(self, client, portal_user, enabled):
        client.force_login(portal_user)
        assert client.get(reverse("speakers:index")).status_code == 200

    def test_predicates(self, liaison, portal_user, organizer, sessions, conference):
        assert is_speaker_liaison(liaison, conference) is True
        assert is_speaker_liaison(portal_user, conference) is False
        assert is_speaker_liaison(liaison, None) is False
        assert can_work_sessions(organizer, conference) is True
        assert can_work_sessions(portal_user, conference) is False


@pytest.mark.django_db
class TestSessionList:
    def test_columns(self, client, organizer, sessions, conference):
        make_slot(sessions["theirs"], channel=make_channel(conference, name="stage"))
        make_slot(sessions["coffee"])
        client.force_login(organizer)
        content = client.get(LIST).content.decode()
        assert "Ada" in content and "Presenter" in content
        assert "Not yet confirmed" in content
        assert "Grace" in content and "Panelist" in content
        assert "Lena" in content  # liaison column
        assert 'text-bg-secondary">Draft</span>' in content
        assert "14:00 UTC · stage" in content
        assert "14:00 UTC · all channels" in content

    def test_filters(self, client, organizer, sessions, conference):
        sessions["theirs"].confirm()
        client.force_login(organizer)
        rows = client.get(LIST, {"status": SessionStatus.CONFIRMED}).context["table"]
        assert [r.title for r in rows.data] == ["Other panel"]
        coffee = session_type(conference, "BREAK").pk
        rows = client.get(LIST, {"kind": coffee}).context["table"]
        assert [r.title for r in rows.data] == ["Coffee"]
        rows = client.get(LIST, {"search": "work"}).context["table"]
        assert [r.title for r in rows.data] == ["Liaised workshop"]

    def test_query_count_does_not_grow_with_rows(
        self, client, organizer, sessions, conference
    ):
        client.force_login(organizer)
        with CaptureQueriesContext(connection) as before:
            client.get(LIST)
        for n in range(6):
            session = make_session(conference, title=f"Extra {n}")
            add_presenter(session, make_presenter(conference, liaison=organizer))
            make_slot(session)
        with CaptureQueriesContext(connection) as after:
            client.get(LIST)
        assert len(after) == len(before)

    def test_rail_shows_speakers_group(self, client, organizer, enabled):
        client.force_login(organizer)
        content = client.get(reverse("organizer_dashboard")).content.decode()
        assert "Sessions" in content and LIST in content

    def test_rail_hidden_when_module_off(self, client, organizer):
        client.force_login(organizer)
        content = client.get(reverse("organizer_dashboard")).content.decode()
        assert LIST not in content

    def test_volunteer_rail_offers_liaison_sessions(self, client, liaison, sessions):
        client.force_login(liaison)
        content = client.get(reverse("volunteer:index")).content.decode()
        assert "My speakers" in content and LIST in content


@pytest.mark.django_db
class TestContextProcessor:
    def test_anonymous(self, rf):
        request = rf.get("/")
        request.user = AnonymousUser()
        assert speaker_module(request) == {
            "speaker_module_enabled": False,
            "is_speaker_liaison": False,
            "is_speaker_presenter": False,
        }

    def test_no_request_user(self, rf):
        assert speaker_module(rf.get("/"))["speaker_module_enabled"] is False

    def test_liaison_flag(self, rf, liaison, organizer, sessions):
        request = rf.get("/")
        request.user = liaison
        assert speaker_module(request) == {
            "speaker_module_enabled": True,
            "is_speaker_liaison": True,
            "is_speaker_presenter": False,
        }
        request.user = organizer
        assert speaker_module(request)["is_speaker_liaison"] is False


@pytest.mark.django_db
class TestSlugUrls:
    """Sessions are addressed by slug: no number a speaker could read as an
    ordinal. Slugs are unique per edition, editable by organizers, and never
    rotate when a title changes."""

    def test_absolute_url_has_no_number(self, sessions):
        session = sessions["mine"]
        assert session.get_absolute_url() == f"/speakers/sessions/{session.slug}/"
        assert not any(ch.isdigit() for ch in session.get_absolute_url())

    def test_same_title_gets_a_suffix_within_the_edition(self, conference, enabled):
        first = make_session(conference, title="Django 101")
        second = make_session(conference, title="Django 101")
        assert first.slug == "django-101" and second.slug == "django-101-2"

    def test_rename_keeps_the_slug(self, sessions):
        session = sessions["mine"]
        slug = session.slug
        session.title = "Renamed"
        session.save()
        assert session.slug == slug

    def test_other_edition_slug_does_not_resolve(self, client, organizer, sessions):
        other = Conference.objects.create(year=2024, name="Old", slug="2024")
        foreign = make_session(other, title="Elsewhere")
        client.force_login(organizer)
        assert client.get(f"/speakers/sessions/{foreign.slug}/").status_code == 404
        assert client.get("/speakers/sessions/no-such-session/").status_code == 404

    def test_organizer_edits_slug_with_clash_and_reserved_refused(
        self, client, organizer, sessions, conference
    ):
        session = sessions["mine"]
        taken = sessions["theirs"].slug
        client.force_login(organizer)
        url = reverse("speakers:session_edit", args=[session.slug])
        base = {
            "kind": session.kind_id,
            "delivery": Delivery.LIVE,
            "title": session.title,
            "duration_minutes": 120,
            "level": "BEGINNER",
            "language": "en",
        }
        response = client.post(url, {**base, "slug": taken})
        assert "already uses this address" in response.content.decode()
        response = client.post(url, {**base, "slug": "new"})
        assert "reserved" in response.content.decode()
        response = client.post(url, {**base, "slug": "Intro To Django!"})
        assert response.status_code == 302, response.context["form"].errors
        session.refresh_from_db()
        assert session.slug == "intro-to-django"
        assertRedirects(response, "/speakers/sessions/intro-to-django/")
        response = client.post(
            url.replace(session.slug, "intro-to-django"), {**base, "slug": ""}
        )
        session.refresh_from_db()
        assert session.slug == "intro-to-django"  # blank keeps the current address


class TestSessionDetail:
    def test_renders(self, client, organizer, sessions):
        session = sessions["mine"]
        session.summary_md = "A **great** workshop"
        session.outline_md = "1. one"
        session.prerequisites_md = "Laptop"
        session.audience_md = "Everyone"
        session.notes_md = "internal"
        session.save()
        ActivityLog.record(session.conference, "session.created", target=session)
        client.force_login(organizer)
        content = client.get(session.get_absolute_url()).content.decode()
        assert "<strong>great</strong>" in content
        assert "Ada" in content and "Not yet confirmed" in content
        assert "Lena" in content
        assert "session.created" in content
        assert "Not scheduled" in content

    def test_waiting_on_required_items(self, client, organizer, sessions, conference):
        session = sessions["mine"]
        ada = session.session_presenters.get().presenter
        item = add_adhoc_item(
            conference,
            "Sign the form",
            ItemOwner.SPEAKER,
            presenter=ada,
            session=session,
        )
        client.force_login(organizer)
        assert (
            "Waiting on:" not in client.get(session.get_absolute_url()).content.decode()
        )
        ChecklistItem.objects.filter(pk=item.pk).update(is_required=True)
        content = client.get(session.get_absolute_url()).content.decode()
        assert "Waiting on:" in content
        assert "Sign the form (Ada)" in content

    def test_pre_recorded_and_slot(self, client, organizer, sessions, conference):
        session = sessions["theirs"]
        session.delivery = Delivery.PRE_RECORDED
        session.save()
        make_slot(session)
        client.force_login(organizer)
        content = client.get(session.get_absolute_url()).content.decode()
        assert "Premiere" in content and "DISCORD" in content
        assert "14:00 UTC" in content
        assert "Confirmed" in content


@pytest.mark.django_db
class TestSessionForms:
    def test_create_with_default_duration(self, client, organizer, enabled, conference):
        client.force_login(organizer)
        response = client.post(
            reverse("speakers:session_create"),
            {
                "kind": session_type(conference, "PANEL").pk,
                "delivery": Delivery.LIVE,
                "title": "Careers panel",
                "summary_md": "Talking careers",
            },
        )
        session = Session.objects.get(title="Careers panel")
        assertRedirects(response, session.get_absolute_url())
        assert session.conference == conference
        assert session.duration_minutes == 60
        assert session.status == SessionStatus.DRAFT
        assert ActivityLog.for_target(session).get().action == "session.created"

    def test_create_form_renders(self, client, organizer, enabled):
        client.force_login(organizer)
        content = client.get(reverse("speakers:session_create")).content.decode()
        assert "New session" in content
        assert "workshop 90" in content

    def test_edit(self, client, organizer, sessions):
        session = sessions["mine"]
        client.force_login(organizer)
        url = reverse("speakers:session_edit", args=[session.slug])
        assert "Edit" in client.get(url).content.decode()
        response = client.post(
            url,
            {
                "kind": session_type(session.conference, "WORKSHOP").pk,
                "delivery": Delivery.LIVE,
                "title": "Renamed workshop",
                "duration_minutes": 120,
                "level": "BEGINNER",
                "language": "en",
            },
        )
        assertRedirects(response, session.get_absolute_url())
        session.refresh_from_db()
        assert session.title == "Renamed workshop"
        assert session.duration_minutes == 120

    def test_liaison_reads_but_cannot_edit(self, client, liaison, sessions, conference):
        session = sessions["mine"]
        client.force_login(liaison)
        content = client.get(session.get_absolute_url()).content.decode()
        assert reverse("speakers:session_edit", args=[session.slug]) not in content
        url = reverse("speakers:session_edit", args=[session.slug])
        assert client.get(url).status_code == 403
        response = client.post(
            url,
            {
                "kind": session_type(conference, "WORKSHOP").pk,
                "delivery": "LIVE",
                "title": "Renamed by a liaison",
            },
        )
        assert response.status_code == 403
        session.refresh_from_db()
        assert session.title == "Liaised workshop"

    def test_video_fields_rejected_for_live_session(self, conference):
        form = SessionForm(
            conference=conference,
            data={
                "kind": session_type(conference, "PYJAM").pk,
                "delivery": Delivery.LIVE,
                "title": "Jam",
                "video_length_limit_minutes": 10,
                "youtube_url": "https://youtube.com/watch?v=x",
                "premiere_location": "YOUTUBE",
            },
        )
        assert form.is_valid() is False
        assert set(form.errors) == {
            "video_length_limit_minutes",
            "youtube_url",
            "premiere_location",
        }

    def test_video_fields_allowed_for_pre_recorded(self, conference):
        form = SessionForm(
            conference=conference,
            data={
                "kind": session_type(conference, "PYJAM").pk,
                "delivery": Delivery.PRE_RECORDED,
                "title": "Jam",
                "video_length_limit_minutes": 10,
                "youtube_publish_at": "2026-12-05T14:00",
            },
        )
        assert form.is_valid(), form.errors

    def test_title_required(self, conference):
        form = SessionForm(
            conference=conference,
            data={"kind": session_type(conference, "TALK").pk, "delivery": ""},
        )
        assert "title" in form.errors

    def test_blank_delivery_follows_the_type(self, conference):
        """A PyJam left on the blank delivery is pre-recorded, so the video
        fields are allowed; a talk on the blank delivery is live."""
        jam = session_type(conference, "PYJAM").pk
        form = SessionForm(
            conference=conference,
            data={
                "kind": jam,
                "delivery": "",
                "title": "Jam",
                "youtube_url": "https://youtube.com/watch?v=x",
            },
        )
        assert form.is_valid(), form.errors
        assert form.save(commit=False).delivery == ""  # filled in on save
        talk = session_type(conference, "TALK").pk
        form = SessionForm(
            conference=conference,
            data={
                "kind": talk,
                "delivery": "",
                "title": "T",
                "youtube_url": "https://youtube.com/watch?v=x",
            },
        )
        assert "youtube_url" in form.errors
        # Types of another edition are not offered.
        other = Conference.objects.create(year=2024, name="Old", slug="old")
        form = SessionForm(
            conference=conference,
            data={"kind": session_type(other, "TALK").pk, "title": "T"},
        )
        assert "kind" in form.errors


@pytest.mark.django_db
class TestSessionEditKeepsRetiredType:
    def test_inactive_type_stays_selectable_on_its_own_session(
        self, client, organizer, sessions, conference
    ):
        session = sessions["mine"]
        session.kind.is_active = False
        session.kind.save()
        client.force_login(organizer)
        form = client.get(
            reverse("speakers:session_edit", args=[session.slug])
        ).context["form"]
        assert session.kind_id in [t.pk for t in form.fields["kind"].queryset]
        # ... but not on a new session.
        form = client.get(reverse("speakers:session_create")).context["form"]
        assert session.kind_id not in [t.pk for t in form.fields["kind"].queryset]


@pytest.mark.django_db
class TestProgramItem:
    def test_only_program_types_offered(self, conference):
        session_type(conference, "BREAK")  # seeds the edition
        codes = [
            t.code
            for t in ProgramItemForm(conference=conference).fields["kind"].queryset
        ]
        assert "BREAK" in codes and "OPENING" in codes
        assert "WORKSHOP" not in codes
        form = ProgramItemForm(
            conference=conference,
            data={"kind": session_type(conference, "WORKSHOP").pk, "title": "x"},
        )
        assert "kind" in form.errors

    def test_created_confirmed_skipping_invited(
        self, client, organizer, enabled, conference
    ):
        client.force_login(organizer)
        assert client.get(reverse("speakers:program_item_create")).status_code == 200
        response = client.post(
            reverse("speakers:program_item_create"),
            {"kind": session_type(conference, "OPENING").pk, "title": "Opening"},
        )
        assertRedirects(response, LIST)
        session = Session.objects.get(title="Opening")
        assert session.status == SessionStatus.CONFIRMED
        assert session.duration_minutes == 15
        assert session.is_content is False
        entry = ActivityLog.for_target(session).get()
        assert entry.data == {"program_item": True}
        assert "Opening" in client.get(LIST).content.decode()
