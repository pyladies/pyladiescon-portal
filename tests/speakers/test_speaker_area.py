import io

import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from pytest_django.asserts import assertRedirects

from portal_account.models import PortalProfile
from speakers.constants import SessionStatus
from speakers.context_processors import speaker_module
from speakers.emails import organizer_recipients
from speakers.mixins import PresenterRequiredMixin
from speakers.models import ActivityLog, Session, SpeakerSettings
from speakers.tasks import send_copresenter_suggestion_task
from volunteer.models import VolunteerProfile

from .factories import (
    add_presenter,
    make_invitation,
    make_presenter,
    make_session,
    make_settings,
)

DASHBOARD = reverse("speakers:my_dashboard")
PROFILE = reverse("speakers:my_profile")
SESSIONS = reverse("speakers:my_sessions")


@pytest.fixture
def enabled(conference):
    return make_settings(conference)


@pytest.fixture
def speaker(db):
    return User.objects.create_user(
        username="ada", email="ada@example.com", first_name="Ada"
    )


@pytest.fixture
def other_speaker(db):
    return User.objects.create_user(username="grace", email="grace@example.com")


@pytest.fixture
def presenter(conference, enabled, speaker):
    """A speaker on the program: a presenter with a confirmed session.

    The speaker area belongs to people who are on the program, which is
    what accepting an invitation makes them; a proposal that nobody has
    answered does not (``Presenter.is_onboarded``).
    """
    presenter = make_presenter(
        conference, display_name="Ada Lovelace", email="ada@example.com", user=speaker
    )
    add_presenter(
        make_session(conference, title="Her session"), presenter, confirmed=True
    )
    return presenter


@pytest.fixture
def other_presenter(conference, enabled, other_speaker):
    return make_presenter(
        conference, display_name="Grace", email="grace@example.com", user=other_speaker
    )


@pytest.fixture
def my_session(conference, presenter, other_presenter):
    session = make_session(conference, title="Django 101")
    add_presenter(session, presenter, confirmed=True)
    add_presenter(session, other_presenter, role="PRESENTER")
    return session


@pytest.fixture
def their_session(conference, other_presenter):
    session = make_session(conference, title="Grace's talk", kind="TALK")
    add_presenter(session, other_presenter)
    return session


def rf_request(user):
    request = RequestFactory().get("/")
    request.user = user
    return request


def png_upload(name="headshot.png"):
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "purple").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@pytest.mark.django_db
class TestAccess:
    def test_anonymous_redirected(self, client, enabled):
        assertRedirects(
            client.get(DASHBOARD), reverse("account_login") + "?next=" + DASHBOARD
        )

    def test_non_presenter_forbidden(self, client, portal_user, enabled):
        client.force_login(portal_user)
        response = client.get(DASHBOARD)
        assert response.status_code == 403
        assert client.get(PROFILE).status_code == 403
        # The refusal is a portal page, not Django's bare one: the navbar
        # with its sign-out is there, and so is a way home.
        content = response.content.decode()
        assert "Sign Out" in content and reverse("index") in content
        assert reverse("account_logout") in content

    def test_general_acceptance_opens_the_area(
        self, client, conference, enabled, speaker
    ):
        """Someone who accepted an invitation to the conference itself has no
        session to be confirmed on yet; the acceptance is what puts them on
        the program (``PresenterQuerySet.onboarded``)."""
        presenter = make_presenter(conference, user=speaker)
        make_invitation(presenter, accepted_at=timezone.now())
        client.force_login(speaker)
        assert client.get(DASHBOARD).status_code == 200
        assertRedirects(client.get(reverse("speakers:index")), DASHBOARD)
        request = rf_request(speaker)
        assert speaker_module(request)["is_speaker_presenter"] is True

    def test_presenter_not_on_program_is_explained_to(
        self, client, conference, enabled, speaker
    ):
        """A presenter row with nothing confirmed (a proposal nobody has
        answered) must not be sent to a page that refuses them."""
        presenter = make_presenter(conference, user=speaker)
        add_presenter(make_session(conference), presenter)
        client.force_login(speaker)
        response = client.get(reverse("speakers:index"))
        assert response.status_code == 200
        assert "not on the program" in response.content.decode()
        assert speaker_module(rf_request(speaker))["is_speaker_presenter"] is False

    def test_module_off_404(self, client, speaker, conference):
        make_presenter(conference, user=speaker)
        client.force_login(speaker)
        assert client.get(DASHBOARD).status_code == 404

    def test_index_routes_presenter_to_dashboard(self, client, speaker, presenter):
        client.force_login(speaker)
        assertRedirects(client.get(reverse("speakers:index")), DASHBOARD)

    def test_index_explains_to_outsiders(self, client, portal_user, enabled):
        client.force_login(portal_user)
        content = client.get(reverse("speakers:index")).content.decode()
        assert "not on the program" in content

    def test_navbar_shows_speaking(self, client, speaker, presenter):
        client.force_login(speaker)
        content = client.get(DASHBOARD).content.decode()
        assert "Speaking" in content and DASHBOARD in content

    def test_context_processor_flag(self, rf, speaker, presenter):
        request = rf.get("/")
        request.user = speaker
        assert speaker_module(request)["is_speaker_presenter"] is True


@pytest.mark.django_db
class TestPortalIndexRouting:
    def test_presenter_lands_on_speaker_dashboard(self, client, speaker, presenter):
        PortalProfile.objects.get_or_create(user=speaker)
        client.force_login(speaker)
        assertRedirects(
            client.get(reverse("index")), DASHBOARD, fetch_redirect_response=False
        )

    def test_presenter_not_on_program_lands_on_volunteer_hub(
        self, client, conference, enabled, speaker
    ):
        presenter = make_presenter(conference, user=speaker)
        add_presenter(make_session(conference), presenter)
        client.force_login(speaker)
        assertRedirects(
            client.get(reverse("index")),
            reverse("volunteer:index"),
            fetch_redirect_response=False,
        )

    def test_presenter_who_volunteers_keeps_volunteer_hub(
        self, client, speaker, presenter, conference
    ):
        PortalProfile.objects.get_or_create(user=speaker)
        VolunteerProfile.objects.create(user=speaker, conference=conference)
        client.force_login(speaker)
        assertRedirects(
            client.get(reverse("index")),
            reverse("volunteer:index"),
            fetch_redirect_response=False,
        )


@pytest.mark.django_db
class TestSessionListCost:
    def test_query_count_does_not_grow_with_sessions(
        self, client, speaker, presenter, my_session, conference
    ):
        """The page reads each row's role and kind, so both are fetched with
        the links rather than one query per session."""
        client.force_login(speaker)
        with CaptureQueriesContext(connection) as before:
            client.get(SESSIONS)
        for name in ("Second", "Third", "Fourth"):
            add_presenter(
                make_session(conference, title=name), presenter, confirmed=True
            )
        with CaptureQueriesContext(connection) as after:
            client.get(SESSIONS)
        assert len(after) == len(before)


@pytest.mark.django_db
class TestDashboard:
    def test_lists_sessions_and_profile_nudge(
        self, client, speaker, presenter, my_session
    ):
        client.force_login(speaker)
        content = client.get(DASHBOARD).content.decode()
        assert "Welcome, Ada Lovelace" in content
        assert "Django 101" in content
        assert "Not yet public" in content
        assert "Your bio or photo is still missing" in content
        assert "Open my checklist" in content

    def test_nudge_gone_when_complete(self, client, speaker, presenter):
        presenter.bio_md = "Hi"
        presenter.headshot = "speakers/headshots/x.png"
        presenter.save()
        client.force_login(speaker)
        content = client.get(DASHBOARD).content.decode()
        assert "still missing" not in content
        assert "Nothing open on your to-do list" in content
        assert "Her session" in content

    def test_schedule_placeholder(self, client, speaker, presenter):
        presenter.timezone = "Africa/Lagos"
        presenter.save()
        client.force_login(speaker)
        content = client.get(reverse("speakers:my_schedule")).content.decode()
        assert "Africa/Lagos" in content


@pytest.mark.django_db
class TestProfile:
    def test_edit_own_profile_with_headshot(
        self, client, speaker, presenter, settings, tmp_path
    ):
        settings.MEDIA_ROOT = tmp_path
        client.force_login(speaker)
        assert "Signed in as ada@example.com" in client.get(PROFILE).content.decode()
        response = client.post(
            PROFILE,
            {
                "display_name": "Ada L.",
                "pronouns": "she/her",
                "bio_md": "I write **programs**.",
                "location": "London",
                "timezone": "Europe/London",
                "website_url": "https://ada.example.com",
                "github_username": "ada",
                "headshot": png_upload(),
            },
        )
        assertRedirects(response, PROFILE)
        presenter.refresh_from_db()
        assert presenter.display_name == "Ada L."
        assert presenter.timezone == "Europe/London"
        assert presenter.is_public is False
        assert presenter.headshot.name.startswith("speakers/headshots/headshot")
        assert (tmp_path / presenter.headshot.name).exists()
        assert (
            ActivityLog.for_target(presenter).get().action
            == "presenter.profile_updated"
        )
        content = client.get(PROFILE).content.decode()
        assert presenter.headshot.url in content

    def test_cannot_change_email_or_liaison(
        self, client, speaker, presenter, portal_user
    ):
        client.force_login(speaker)
        client.post(
            PROFILE,
            {
                "display_name": "Ada",
                "timezone": "UTC",
                "email": "hacker@example.com",
                "liaison": portal_user.pk,
            },
        )
        presenter.refresh_from_db()
        assert presenter.email == "ada@example.com"
        assert presenter.liaison is None

    def test_rejects_unknown_timezone(self, client, speaker, presenter):
        client.force_login(speaker)
        response = client.post(
            PROFILE, {"display_name": "Ada", "timezone": "Mars/Base"}
        )
        assert response.status_code == 200
        assert "timezone" in response.context["form"].errors


@pytest.mark.django_db
class TestSessions:
    def test_list_shows_co_presenters(self, client, speaker, presenter, my_session):
        client.force_login(speaker)
        content = client.get(SESSIONS).content.decode()
        assert "Django 101" in content
        assert "Grace" in content and "Presenter" in content
        assert reverse("speakers:my_session_edit", args=[my_session.slug]) in content

    def test_co_presenter_address_change_is_logged(
        self, client, speaker, presenter, my_session
    ):
        """Ada renames the shared session's address; Bob's bookmark breaks,
        and the trail must say what the old address was."""
        client.force_login(speaker)
        url = reverse("speakers:my_session_edit", args=[my_session.slug])
        client.post(
            url,
            {
                "title": "Django 101",
                "slug": "ada-picked-this",
                "level": "BEGINNER",
                "language": "en",
            },
        )
        entry = ActivityLog.for_target(my_session).get(
            action="session.updated_by_presenter"
        )
        assert entry.actor == speaker
        assert entry.data == {
            "changes": {"slug": {"from": "django-101", "to": "ada-picked-this"}}
        }
        # A content-only save records no changes block.
        client.post(
            url.replace("django-101", "ada-picked-this"),
            {
                "title": "Django 101",
                "slug": "",
                "level": "BEGINNER",
                "language": "en",
                "summary_md": "x",
            },
        )
        latest = (
            ActivityLog.for_target(my_session)
            .filter(action="session.updated_by_presenter")
            .first()
        )
        assert latest.data == {}
        # Profile renames are recorded the same way.
        client.post(
            reverse("speakers:my_profile"),
            {"display_name": "Ada L.", "timezone": "UTC"},
        )
        prof = ActivityLog.for_target(presenter).get(action="presenter.profile_updated")
        assert prof.data["changes"]["display_name"]["to"] == "Ada L."

    def test_identity_locks_once_scheduled(
        self, client, speaker, presenter, my_session
    ):
        """After an organizer schedules the session, the title and address
        leave the form: shown read-only, and a stale POST carrying them is
        ignored rather than rejected. Content still saves."""
        my_session.status = SessionStatus.SCHEDULED
        my_session.save()
        client.force_login(speaker)
        url = reverse("speakers:my_session_edit", args=[my_session.slug])
        page = client.get(url).content.decode()
        assert "Locked now that the session is scheduled" in page
        assert 'name="title"' not in page and 'name="slug"' not in page
        response = client.post(
            url,
            {
                "summary_md": "Still editable",
                "level": "BEGINNER",
                "language": "en",
                "title": "Hacked title",
                "slug": "hacked",
            },
        )
        assertRedirects(
            response,
            reverse("speakers:my_session_detail", args=[my_session.slug]),
        )
        my_session.refresh_from_db()
        assert my_session.summary_md == "Still editable"
        assert my_session.title == "Django 101" and my_session.slug == "django-101"

    def test_profile_identity_locks_once_scheduled(
        self, client, speaker, presenter, my_session
    ):
        client.force_login(speaker)
        url = reverse("speakers:my_profile")
        response = client.post(
            url, {"display_name": "Ada L.", "slug": "ada-l", "timezone": "UTC"}
        )
        assertRedirects(response, url)
        presenter.refresh_from_db()
        assert presenter.display_name == "Ada L." and presenter.slug == "ada-l"
        my_session.status = SessionStatus.SCHEDULED
        my_session.save()
        page = client.get(url).content.decode()
        assert "Locked now that the session is scheduled" in page
        assert 'name="display_name"' not in page and 'name="slug"' not in page
        client.post(
            url, {"display_name": "Someone Else", "slug": "x", "timezone": "UTC"}
        )
        presenter.refresh_from_db()
        assert presenter.display_name == "Ada L." and presenter.slug == "ada-l"

    def test_edit_own_session(self, client, speaker, presenter, my_session):
        client.force_login(speaker)
        url = reverse("speakers:my_session_edit", args=[my_session.slug])
        content = client.get(url).content.decode()
        assert "Duration: 90 minutes" in content
        assert "Grace" in content
        response = client.post(
            url,
            {
                "summary_md": "Learn *Django*",
                "outline_md": "1. Models",
                "level": "BEGINNER",
                "language": "en",
                "title": "Django 101, revised",
                "slug": "Django 101 Revised",
                "duration_minutes": 5,
            },
        )
        # Renaming it moves its address, so read that back before checking.
        my_session.refresh_from_db()
        assertRedirects(
            response, reverse("speakers:my_session_detail", args=[my_session.slug])
        )
        assert my_session.summary_md == "Learn *Django*"
        assert my_session.level == "BEGINNER"
        # Title and address are the speaker's until the session is scheduled;
        # the duration never is.
        assert my_session.title == "Django 101, revised"
        assert my_session.slug == "django-101-revised"
        assert my_session.duration_minutes == 90
        assert (
            ActivityLog.for_target(my_session).get().action
            == "session.updated_by_presenter"
        )

    def test_other_presenters_session_forbidden(
        self, client, speaker, presenter, their_session
    ):
        client.force_login(speaker)
        url = reverse("speakers:my_session_edit", args=[their_session.slug])
        assert client.get(url).status_code == 403
        assert client.post(url, {"summary_md": "x"}).status_code == 403
        suggest = reverse("speakers:my_session_suggest", args=[their_session.slug])
        assert (
            client.post(suggest, {"name": "X", "email": "x@example.com"}).status_code
            == 403
        )

    def test_unknown_session_404(self, client, speaker, presenter):
        client.force_login(speaker)
        assert (
            client.get(
                reverse("speakers:my_session_edit", args=["no-such-session"])
            ).status_code
            == 404
        )


@pytest.mark.django_db
class TestSuggestCoPresenter:
    def test_emails_organizers_and_liaison(
        self, client, speaker, presenter, my_session, admin_user
    ):
        liaison = User.objects.create_user(username="lena", email="lena@example.com")
        User.objects.create_user(username="nomail", is_staff=True, email="")
        presenter.liaison = liaison
        presenter.save()
        client.force_login(speaker)
        mail.outbox.clear()
        url = reverse("speakers:my_session_suggest", args=[my_session.slug])
        response = client.post(
            url,
            {
                "name": "Grace Hopper",
                "email": "grace@navy.example",
                "note": "She's *great*",
            },
            follow=True,
        )
        assert "passed Grace Hopper on to the organizers" in response.content.decode()
        # One message per organizer, so the liaison never sees staff addresses.
        assert sorted(m.to[0] for m in mail.outbox) == [
            "admin@example.com",
            "lena@example.com",
        ]
        assert all(len(m.to) == 1 for m in mail.outbox)
        message = mail.outbox[0]
        assert "Co-presenter suggested for Django 101" in message.subject
        assert "grace@navy.example" in message.body
        # The note is shown verbatim, markdown and all, never rendered.
        assert "She's *great*" in message.body
        html = message.alternatives[0][0]
        assert "<code>" in html and "<em>great</em>" not in html
        assert my_session.get_absolute_url() in message.body
        entry = ActivityLog.for_target(my_session).get()
        assert entry.action == "session.copresenter_suggested"
        assert entry.data == {"name": "Grace Hopper", "email": "grace@navy.example"}

    def test_the_team_address_takes_it_when_there_is_one(
        self, client, speaker, presenter, my_session, admin_user, conference
    ):
        """Same rule as the proposal notice: the address the team reads,
        with this presenter's liaison alongside it."""
        settings_row = SpeakerSettings.objects.get(conference=conference)
        settings_row.organizers_email = "programs@example.com"
        settings_row.save(update_fields=["organizers_email"])
        liaison = User.objects.create_user(username="lena", email="lena@example.com")
        presenter.liaison = liaison
        presenter.save()
        client.force_login(speaker)
        mail.outbox.clear()
        client.post(
            reverse("speakers:my_session_suggest", args=[my_session.slug]),
            {"name": "Grace Hopper", "email": "grace@navy.example", "note": ""},
        )
        assert sorted(m.to[0] for m in mail.outbox) == [
            "lena@example.com",
            "programs@example.com",
        ]
        assert "admin@example.com" not in [m.to[0] for m in mail.outbox]

    def test_note_cannot_smuggle_links_or_break_out(
        self, client, speaker, presenter, my_session, admin_user
    ):
        client.force_login(speaker)
        mail.outbox.clear()
        client.post(
            reverse("speakers:my_session_suggest", args=[my_session.slug]),
            {
                "name": "Eve",
                "email": "eve@example.com",
                "note": "line one [click](https://evil.example)\n```\n# not a heading",
            },
        )
        html = mail.outbox[0].alternatives[0][0]
        assert "evil.example" in html and 'href="https://evil.example"' not in html
        assert "<h1>" not in html
        assert ("'" * 3) in mail.outbox[0].body  # fences are defused

    def test_invalid_suggestion(self, client, speaker, presenter, my_session):
        client.force_login(speaker)
        url = reverse("speakers:my_session_suggest", args=[my_session.slug])
        response = client.post(url, {"name": "", "email": "nope"}, follow=True)
        assert "valid email" in response.content.decode()
        assert not ActivityLog.for_target(my_session).exists()

    def test_no_recipients(self, presenter, my_session):
        assert organizer_recipients(presenter) == []
        result = send_copresenter_suggestion_task(
            presenter.pk, my_session.pk, "X", "x@example.com", ""
        )
        assert result == "Sent co-presenter suggestion to 0 organizer(s)"
        assert mail.outbox == []

    def test_task_with_missing_rows(self):
        assert "not found" in send_copresenter_suggestion_task(1, 2, "X", "x@e.com", "")


@pytest.mark.django_db
class TestPresenterRequiredMixin:
    def test_anonymous_fails_even_without_login_mixin(self, rf, enabled, conference):
        mixin = PresenterRequiredMixin()
        mixin.request = rf.get("/")
        mixin.request.user = AnonymousUser()
        mixin.conference = conference
        assert mixin.test_func() is False


@pytest.mark.django_db
class TestLockedSessions:
    def test_no_presenter_edits_once_published_or_cancelled(
        self, client, speaker, presenter, my_session
    ):
        client.force_login(speaker)
        url = reverse("speakers:my_session_edit", args=[my_session.slug])
        assert client.get(url).status_code == 200
        Session.objects.filter(pk=my_session.pk).update(status=SessionStatus.PUBLISHED)
        assert client.get(url).status_code == 403
        assert client.post(url, {"title": "x"}).status_code == 403
        Session.objects.filter(pk=my_session.pk).update(status=SessionStatus.CANCELLED)
        assert client.get(url).status_code == 403
        Session.objects.filter(pk=my_session.pk).update(status=SessionStatus.SCHEDULED)
        assert client.get(url).status_code == 200


@pytest.mark.django_db
class TestSpeakerProfileWording:
    def test_menu_and_headers_say_speaker_profile(self, client, speaker, presenter):
        client.force_login(speaker)
        content = client.get(PROFILE).content.decode()
        assert "My speaker profile" in content
        assert ">My profile<" not in content
        assert "Update speaker profile" in client.get(DASHBOARD).content.decode()
