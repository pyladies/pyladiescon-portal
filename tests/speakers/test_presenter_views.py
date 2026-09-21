import re

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from portal.models import Conference
from speakers.constants import SessionStatus
from speakers.forms import PresenterForm, liaison_candidates
from speakers.models import ActivityLog, Invitation, InvitationStatus, Presenter
from speakers.program_types import presenter_role, session_type
from speakers.services import send_invitation
from speakers.tables import invitation_badge
from volunteer.constants import ApplicationStatus
from volunteer.models import VolunteerProfile

from .factories import (
    add_presenter,
    make_invitation,
    make_presenter,
    make_session,
    make_settings,
)

LIST = reverse("speakers:presenter_list")


@pytest.fixture
def enabled(conference):
    return make_settings(conference)


@pytest.fixture
def organizer(db):
    return User.objects.create_user(
        username="organizer", email="org@example.com", is_staff=True
    )


@pytest.fixture
def liaison(db, conference):
    """An approved volunteer of the edition, so they qualify as a liaison."""
    user = User.objects.create_user(
        username="liaison", email="liaison@example.com", first_name="Lena"
    )
    VolunteerProfile.objects.create(
        user=user,
        conference=conference,
        application_status=ApplicationStatus.APPROVED,
    )
    return user


@pytest.fixture
def presenters(conference, enabled, liaison):
    session = make_session(conference, title="Django 101")
    ada = make_presenter(
        conference, display_name="Ada", email="ada@example.com", liaison=liaison
    )
    grace = make_presenter(conference, display_name="Grace", email="grace@example.com")
    add_presenter(session, ada)
    return {"session": session, "ada": ada, "grace": grace}


def _link_from_mail():
    return re.search(r"/speakers/invitations/[^\s)]+/", mail.outbox[-1].body).group(0)


@pytest.mark.django_db
class TestPresenterList:
    def test_access(self, client, portal_user, enabled):
        assertRedirects(client.get(LIST), reverse("account_login") + "?next=" + LIST)
        client.force_login(portal_user)
        assert client.get(LIST).status_code == 403

    def test_organizer_sees_all_with_columns(self, client, organizer, presenters):
        make_invitation(presenters["ada"], presenters["session"])
        client.force_login(organizer)
        response = client.get(LIST)
        content = response.content.decode()
        assert [p.display_name for p in response.context["table"].data] == [
            "Ada",
            "Grace",
        ]
        assert "Django 101" in content and "Presenter" in content
        assert "Not sent" in content
        assert "not yet" in content  # account column
        assert "Lena" in content

    def test_liaison_scoped(self, client, liaison, presenters):
        client.force_login(liaison)
        response = client.get(LIST)
        assert [p.display_name for p in response.context["table"].data] == ["Ada"]
        assert client.get(presenters["grace"].get_absolute_url()).status_code == 404
        assert client.get(presenters["ada"].get_absolute_url()).status_code == 200

    def test_filters(self, client, organizer, presenters, liaison):
        client.force_login(organizer)
        rows = client.get(LIST, {"search": "grace@"}).context["table"].data
        assert [p.display_name for p in rows] == ["Grace"]
        rows = client.get(LIST, {"liaison": liaison.pk}).context["table"].data
        assert [p.display_name for p in rows] == ["Ada"]

    def test_query_count_constant(self, client, organizer, presenters, conference):
        client.force_login(organizer)
        with CaptureQueriesContext(connection) as before:
            client.get(LIST)
        for n in range(6):
            presenter = make_presenter(conference, user=organizer, liaison=organizer)
            add_presenter(presenters["session"], presenter)
            make_invitation(presenter, presenters["session"])
        with CaptureQueriesContext(connection) as after:
            client.get(LIST)
        assert len(after) == len(before)

    def test_rail_has_presenters(self, client, organizer, enabled):
        client.force_login(organizer)
        assert LIST in client.get(reverse("organizer_dashboard")).content.decode()

    def test_invitation_badge_none(self):
        assert "—" in invitation_badge(None)


@pytest.mark.django_db
class TestPresenterForms:
    def test_create(self, client, organizer, enabled, conference, liaison):
        client.force_login(organizer)
        assert client.get(reverse("speakers:presenter_create")).status_code == 200
        response = client.post(
            reverse("speakers:presenter_create"),
            {
                "display_name": "Grace Hopper",
                "email": "Grace@Example.com",
                "timezone": "America/New_York",
                "is_public": "on",
            },
        )
        presenter = Presenter.objects.get(email="grace@example.com")
        assertRedirects(response, presenter.get_absolute_url())
        assert presenter.conference == conference
        assert presenter.timezone == "America/New_York"
        assert ActivityLog.for_target(presenter).get().action == "presenter.created"

    def test_duplicate_email_rejected(self, presenters, conference):
        form = PresenterForm(
            data={"display_name": "Dup", "email": "ADA@example.com", "timezone": "UTC"},
            conference=conference,
        )
        assert form.errors == {
            "email": ["A presenter with this email already exists in this edition."]
        }

    def test_edit_keeps_own_email(self, presenters, conference):
        form = PresenterForm(
            data={
                "display_name": "Ada L",
                "email": "ada@example.com",
                "timezone": "UTC",
            },
            conference=conference,
            instance=presenters["ada"],
        )
        assert form.is_valid(), form.errors

    def test_liaison_candidates(self, conference, organizer, liaison, portal_user):
        VolunteerProfile.objects.create(user=portal_user, conference=conference)
        # Pending volunteers and plain users are not offered; sorted by name,
        # and a blank first name sorts first.
        assert list(liaison_candidates(conference)) == [organizer, liaison]

    def test_liaison_reads_but_cannot_edit(self, client, liaison, presenters):
        """A liaison sees their presenter but must not change the email an
        invitation goes to, nor hand the presenter to someone else."""
        ada = presenters["ada"]
        client.force_login(liaison)
        content = client.get(ada.get_absolute_url()).content.decode()
        assert content.count(reverse("speakers:presenter_edit", args=[ada.slug])) == 0
        url = reverse("speakers:presenter_edit", args=[ada.slug])
        assert client.get(url).status_code == 403
        response = client.post(
            url,
            {
                "display_name": "Mallory",
                "email": "attacker@example.com",
                "timezone": "Europe/London",
                "liaison": "",
            },
        )
        assert response.status_code == 403
        ada.refresh_from_db()
        assert ada.email == "ada@example.com" and ada.liaison == liaison
        other = reverse("speakers:presenter_edit", args=[presenters["grace"].slug])
        assert client.get(other).status_code == 403
        assert client.get(reverse("speakers:presenter_create")).status_code == 403

    def test_organizer_edits_a_presenter(self, client, organizer, presenters, liaison):
        ada = presenters["ada"]
        client.force_login(organizer)
        url = reverse("speakers:presenter_edit", args=[ada.slug])
        assert client.get(url).status_code == 200
        response = client.post(
            url,
            {
                "display_name": "Ada Lovelace",
                "email": "ada@example.com",
                "timezone": "Europe/London",
                "liaison": liaison.pk,
            },
        )
        assertRedirects(response, ada.get_absolute_url())
        ada.refresh_from_db()
        assert ada.display_name == "Ada Lovelace" and ada.timezone == "Europe/London"


@pytest.mark.django_db
class TestPresenterSlugUrls:
    def test_absolute_url_and_suffix(self, conference, enabled):
        ada = make_presenter(conference, display_name="Ada Lovelace")
        again = make_presenter(conference, display_name="Ada Lovelace")
        assert ada.get_absolute_url() == "/speakers/presenters/ada-lovelace/"
        assert again.slug == "ada-lovelace-2"
        ada.display_name = "Countess Lovelace"
        ada.save()
        assert ada.slug == "ada-lovelace"

    def test_edit_form_explains_the_address(self, client, organizer, presenters):
        client.force_login(organizer)
        page = client.get(
            reverse("speakers:presenter_edit", args=[presenters["grace"].slug])
        ).content.decode()
        assert "Web address" in page
        assert "organizers can always rename it" in page

    def test_reserved_name_and_non_latin_names(self, client, organizer, presenters):
        """Addresses are ASCII, so shared links never show percent-encoding;
        non-Latin names are transliterated rather than dropped, so no one
        gets a numbered placeholder."""
        conference = presenters["session"].conference
        me = make_presenter(conference, display_name="Me")
        assert me.slug == "me-2"
        li = make_presenter(conference, display_name="李华")
        theo = make_presenter(conference, display_name="Θεοδώρα")
        zoe = make_presenter(conference, display_name="Zoë Müller")
        assert (li.slug, theo.slug, zoe.slug) == ("li-hua", "theodora", "zoe-muller")
        assert li.get_absolute_url() == "/speakers/presenters/li-hua/"
        client.force_login(organizer)
        assert client.get(li.get_absolute_url()).status_code == 200
        assert client.get(theo.get_absolute_url()).status_code == 200
        # Organizer-typed non-Latin text is transliterated the same way.
        url = reverse("speakers:presenter_edit", args=[li.slug])
        client.post(
            url,
            {
                "display_name": "李华",
                "email": li.email,
                "timezone": "UTC",
                "slug": "Li 华",
            },
        )
        li.refresh_from_db()
        assert li.slug == "li-hua"
        li.slug = "me"
        with pytest.raises(ValidationError, match="reserved"):
            li.full_clean()

    def test_organizer_identity_change_logged_only_when_locked(
        self, client, organizer, presenters
    ):
        ada, grace = presenters["ada"], presenters["grace"]
        client.force_login(organizer)
        base = {"timezone": "UTC"}
        # Grace is on no scheduled session: a rename is routine.
        client.post(
            reverse("speakers:presenter_edit", args=[grace.slug]),
            {**base, "display_name": "Grace H.", "email": grace.email},
        )
        assert not ActivityLog.objects.filter(
            action="presenter.identity_changed"
        ).exists()
        session = presenters["session"]
        session.status = SessionStatus.SCHEDULED
        session.save()
        assert ada.identity_locked and not grace.identity_locked
        response = client.post(
            reverse("speakers:presenter_edit", args=[ada.slug]),
            {**base, "display_name": "Ada L.", "email": ada.email},
            follow=True,
        )
        entry = ActivityLog.objects.get(action="presenter.identity_changed")
        assert "Already scheduled: the display name changed" in (
            response.content.decode()
        )
        assert entry.data["changes"] == {
            "display_name": {"from": "Ada", "to": "Ada L."}
        }

    def test_organizer_edits_slug_clash_refused(self, client, organizer, presenters):
        grace = presenters["grace"]
        other = make_presenter(presenters["session"].conference, display_name="Mary")
        client.force_login(organizer)
        url = reverse("speakers:presenter_edit", args=[grace.slug])
        base = {
            "display_name": grace.display_name,
            "email": grace.email,
            "timezone": "UTC",
        }
        response = client.post(url, {**base, "slug": other.slug})
        assert "already uses this address" in response.content.decode()
        response = client.post(url, {**base, "slug": "grace-h"})
        grace.refresh_from_db()
        assert grace.slug == "grace-h"
        assertRedirects(response, "/speakers/presenters/grace-h/")
        assert client.get("/speakers/presenters/no-such-person/").status_code == 404


@pytest.mark.django_db
class TestPresenterDetail:
    def test_history_and_actions(self, client, organizer, presenters):
        ada, session = presenters["ada"], presenters["session"]
        ada.bio_md = "Wrote the **first** program"
        ada.pronouns = "she/her"
        ada.website_url = "https://ada.example.com"
        ada.github_username = "ada"
        ada.save()
        invitation = make_invitation(ada, session)
        send_invitation(invitation)
        client.force_login(organizer)
        content = client.get(ada.get_absolute_url()).content.decode()
        assert "<strong>first</strong>" in content
        assert "she/her" in content
        assert "Django 101" in content
        assert "Sent" in content
        assert reverse("speakers:invitation_resend", args=[invitation.pk]) in content
        assert reverse("speakers:invitation_cancel", args=[invitation.pk]) in content
        assert "not linked yet" in content
        assert "Lena" in content
        assert "https://ada.example.com" in content

    def test_latest_invitation_without_prefetch(self, presenters):
        ada = presenters["ada"]
        assert Presenter.objects.get(pk=ada.pk).latest_invitation is None
        first = make_invitation(ada, presenters["session"])
        second = make_invitation(ada)
        assert Presenter.objects.get(pk=ada.pk).latest_invitation == second
        assert first.status == InvitationStatus.DRAFT

    def test_no_invitations_yet(self, client, organizer, presenters):
        client.force_login(organizer)
        content = client.get(presenters["grace"].get_absolute_url()).content.decode()
        assert "No invitation sent yet" in content
        assert "Not on any session yet" in content


@pytest.mark.django_db
class TestSessionPresenterActions:
    def test_add_and_remove(self, client, organizer, presenters, conference):
        session, grace = presenters["session"], presenters["grace"]
        presenter_role_pk = presenter_role(conference, "PRESENTER").pk
        client.force_login(organizer)
        content = client.get(session.get_absolute_url()).content.decode()
        assert "Add presenter" in content
        # The role select offers only what a workshop allows, preselected.
        form = client.get(session.get_absolute_url()).context["add_presenter_form"]
        assert [r.code for r in form.fields["role"].queryset] == ["PRESENTER"]
        assert form.fields["role"].initial == presenter_role_pk
        url = reverse("speakers:session_add_presenter", args=[session.slug])
        response = client.post(
            url, {"presenter": grace.pk, "role": presenter_role_pk, "order": 2}
        )
        assertRedirects(response, session.get_absolute_url())
        link = session.session_presenters.get(presenter=grace)
        assert link.role.code == "PRESENTER"
        assert link.is_required is False
        # Already on the session: the select no longer offers them.
        response = client.post(
            url,
            {"presenter": grace.pk, "role": presenter_role_pk, "order": 3},
            follow=True,
        )
        assert "Could not add the presenter" in response.content.decode()
        assert session.session_presenters.count() == 2
        # A role the type does not allow is refused by the form.
        panelist = presenter_role(conference, "PANELIST").pk
        ada_two = make_presenter(conference, display_name="Zed")
        response = client.post(
            url, {"presenter": ada_two.pk, "role": panelist, "order": 4}, follow=True
        )
        assert "Could not add the presenter" in response.content.decode()
        assert "role" in response.content.decode()
        remove = reverse(
            "speakers:session_remove_presenter", args=[session.slug, link.pk]
        )
        assertRedirects(client.post(remove), session.get_absolute_url())
        assert session.session_presenters.filter(presenter=grace).exists() is False
        actions = [e.action for e in ActivityLog.for_target(session)]
        assert actions == ["session.presenter_removed", "session.presenter_added"]

    def test_remove_cancels_their_invitation_and_reverts_the_session(
        self, client, organizer, presenters, send
    ):
        """A removed presenter's link must stop working, and a session left
        with no open invitation goes back to Draft."""
        session, ada = presenters["session"], presenters["ada"]
        invitation = make_invitation(ada, session)
        send(invitation)
        link_url = _link_from_mail()
        session.refresh_from_db()
        assert session.status == SessionStatus.INVITED
        client.force_login(organizer)
        link = session.session_presenters.get(presenter=ada)
        client.post(
            reverse("speakers:session_remove_presenter", args=[session.slug, link.pk])
        )
        invitation.refresh_from_db()
        session.refresh_from_db()
        assert invitation.status == InvitationStatus.CANCELLED
        assert session.status == SessionStatus.DRAFT
        client.logout()
        assert client.get(link_url).context["reason"] == "cancelled"
        assert ActivityLog.objects.filter(
            action="session.presenter_removed", data__presenter_id=ada.pk
        ).exists()

    def test_remove_keeps_session_invited_while_others_are_pending(
        self, client, organizer, presenters, send
    ):
        session, ada = presenters["session"], presenters["ada"]
        grace = presenters["grace"]
        add_presenter(session, grace)
        send(make_invitation(ada, session))
        send(make_invitation(grace, session))
        client.force_login(organizer)
        link = session.session_presenters.get(presenter=ada)
        client.post(
            reverse("speakers:session_remove_presenter", args=[session.slug, link.pk])
        )
        session.refresh_from_db()
        assert session.status == SessionStatus.INVITED  # Grace is still invited

    def test_invite_refuses_an_over_long_note(self, client, organizer, presenters):
        session, ada = presenters["session"], presenters["ada"]
        link = session.session_presenters.get(presenter=ada)
        client.force_login(organizer)
        mail.outbox.clear()
        response = client.post(
            reverse("speakers:session_invite", args=[session.slug, link.pk]),
            {"message_md": "x" * 2001},
            follow=True,
        )
        assert "Could not send" in response.content.decode()
        assert mail.outbox == [] and not Invitation.objects.exists()

    def test_liaison_cannot_add(self, client, liaison, presenters):
        client.force_login(liaison)
        url = reverse(
            "speakers:session_add_presenter", args=[presenters["session"].slug]
        )
        assert (
            client.post(url, {"presenter": presenters["grace"].pk}).status_code == 403
        )

    def test_invite_then_resend_reuses_open_invitation(
        self, client, organizer, presenters
    ):
        session = presenters["session"]
        link = session.session_presenters.get()
        client.force_login(organizer)
        mail.outbox.clear()
        url = reverse("speakers:session_invite", args=[session.slug, link.pk])
        assertRedirects(
            client.post(url, {"message_md": "Please *come*"}),
            session.get_absolute_url(),
        )
        invitation = Invitation.objects.get()
        assert invitation.invited_by == organizer
        assert invitation.message_md == "Please *come*"
        assert invitation.status == InvitationStatus.SENT
        session.refresh_from_db()
        assert session.status == SessionStatus.INVITED
        first_link = _link_from_mail()
        content = client.get(session.get_absolute_url()).content.decode()
        assert "Resend invitation" in content and "Please *come*" in content
        client.post(url, {"message_md": "Please come!"})
        assert Invitation.objects.count() == 1
        assert len(mail.outbox) == 2
        client.logout()
        assert client.get(first_link).context["reason"] == "superseded"
        assert client.get(_link_from_mail()).status_code == 200

    def test_invite_after_accept_creates_new_invitation(
        self, client, organizer, presenters
    ):
        session, ada = presenters["session"], presenters["ada"]
        link = session.session_presenters.get()
        invitation = make_invitation(ada, session)
        send_invitation(invitation)
        invitation.accepted_at = invitation.sent_at
        invitation.save()
        client.force_login(organizer)
        client.post(reverse("speakers:session_invite", args=[session.slug, link.pk]))
        assert Invitation.objects.count() == 2


@pytest.mark.django_db
class TestInvitationActions:
    def test_resend_invalidates_previous_link(
        self, client, organizer, presenters, send
    ):
        invitation = make_invitation(presenters["ada"], presenters["session"])
        send(invitation)
        old_link = _link_from_mail()
        client.force_login(organizer)
        response = client.post(
            reverse("speakers:invitation_resend", args=[invitation.pk])
        )
        assertRedirects(response, presenters["ada"].get_absolute_url())
        client.logout()
        assert client.get(old_link).context["reason"] == "superseded"
        assert client.get(_link_from_mail()).status_code == 200

    def test_resend_accepted_refused(self, client, organizer, presenters):
        invitation = make_invitation(presenters["ada"], presenters["session"])
        send_invitation(invitation)
        invitation.accepted_at = invitation.sent_at
        invitation.save()
        client.force_login(organizer)
        response = client.post(
            reverse("speakers:invitation_resend", args=[invitation.pk]), follow=True
        )
        assert "already been accepted" in response.content.decode()

    def test_cancel(self, client, organizer, presenters, send):
        invitation = make_invitation(presenters["ada"], presenters["session"])
        send(invitation)
        link = _link_from_mail()
        client.force_login(organizer)
        response = client.post(
            reverse("speakers:invitation_cancel", args=[invitation.pk]), follow=True
        )
        assert "Invitation cancelled" in response.content.decode()
        invitation.refresh_from_db()
        assert invitation.status == InvitationStatus.CANCELLED
        response = client.post(
            reverse("speakers:invitation_cancel", args=[invitation.pk]), follow=True
        )
        assert "Only an open invitation" in response.content.decode()
        client.logout()
        assert client.get(link).context["reason"] == "cancelled"

    def test_other_edition_invitation_404(self, client, organizer, presenters):
        other = Conference.objects.create(year=2024, name="Old", slug="2024")
        invitation = make_invitation(make_presenter(other))
        client.force_login(organizer)
        url = reverse("speakers:invitation_cancel", args=[invitation.pk])
        assert client.post(url).status_code == 404


@pytest.mark.django_db
class TestEndToEnd:
    def test_create_session_add_presenter_invite_accept(
        self, client, organizer, enabled, conference
    ):
        client.force_login(organizer)
        client.post(
            reverse("speakers:session_create"),
            {
                "kind": session_type(conference, "WORKSHOP").pk,
                "delivery": "LIVE",
                "title": "Testing 101",
            },
        )
        session = conference.sessions.get()
        client.post(
            reverse("speakers:presenter_create"),
            {
                "display_name": "Ada Lovelace",
                "email": "ada@example.com",
                "timezone": "UTC",
            },
        )
        presenter = conference.presenters.get()
        client.post(
            reverse("speakers:session_add_presenter", args=[session.slug]),
            {
                "presenter": presenter.pk,
                "role": presenter_role(conference, "PRESENTER").pk,
                "order": 1,
                "is_required": "on",
            },
        )
        link = session.session_presenters.get()
        mail.outbox.clear()
        client.post(
            reverse("speakers:session_invite", args=[session.slug, link.pk]),
            {"message_md": "We'd love to have you."},
        )
        client.logout()
        accept_link = _link_from_mail()
        page = client.get(accept_link)
        assert "Testing 101" in page.content.decode()
        response = client.post(accept_link, {"action": "accept"})
        assertRedirects(
            response, reverse("speakers:index"), fetch_redirect_response=False
        )
        link.refresh_from_db()
        session.refresh_from_db()
        presenter.refresh_from_db()
        assert link.is_confirmed is True
        assert session.status == SessionStatus.CONFIRMED
        assert presenter.user.email == "ada@example.com"
        client.force_login(organizer)
        content = client.get(presenter.get_absolute_url()).content.decode()
        assert "Accepted" in content and "linked" not in content.split("Account")[0]
        assert "Accepted" in client.get(LIST).content.decode()
