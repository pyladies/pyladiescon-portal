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
from speakers.checklists import complete_item
from speakers.constants import ItemStatus, SessionStatus
from speakers.forms import PresenterForm, liaison_candidates
from speakers.models import ActivityLog, Invitation, InvitationStatus, Presenter
from speakers.program_types import presenter_role, session_type
from speakers.seeds import seed_checklists
from speakers.services import (
    accept_invitation,
    change_presenter_role,
    send_invitation,
)
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
        # Superusers without the staff flag and any approved volunteer count too;
        # an inactive account never does.
        root = User.objects.create_user(username="root", is_superuser=True)
        helper = User.objects.create_user(username="helper", first_name="Zed")
        VolunteerProfile.objects.create(
            user=helper,
            conference=conference,
            application_status=ApplicationStatus.APPROVED,
        )
        gone = User.objects.create_user(username="gone", is_staff=True, is_active=False)
        candidates = list(liaison_candidates(conference))
        assert root in candidates and helper in candidates and gone not in candidates

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

    def test_adding_a_presenter_who_accepted_generally_confirms_them(
        self, client, organizer, presenters, conference
    ):
        """Accepting a general invitation covers sessions added afterwards:
        the link is confirmed, the checklist appears, the session can confirm."""
        seed_checklists(conference)
        grace = presenters["grace"]
        general = make_invitation(grace)
        send_invitation(general)
        accept_invitation(general)
        talk = make_session(conference, kind="TALK", title="Later talk")
        client.force_login(organizer)
        response = client.post(
            reverse("speakers:session_add_presenter", args=[talk.slug]),
            {
                "presenter": grace.pk,
                "role": presenter_role(conference, "PRESENTER").pk,
                "order": 1,
                "is_required": "on",
            },
            follow=True,
        )
        assert "already accepted, so they are confirmed" in response.content.decode()
        link = talk.session_presenters.get()
        assert link.is_confirmed is True
        titles = set(
            grace.checklist_items.filter(session=talk).values_list("title", flat=True)
        )
        assert "Confirm your session title and summary" in titles
        assert "Confirm your scheduled slot" in titles
        assert ActivityLog.objects.filter(action="session.presenter_confirmed").exists()
        talk.refresh_from_db()
        # Their link is the only required one and no seeded item is
        # required, so the session confirms itself on the spot.
        assert talk.status == SessionStatus.CONFIRMED
        # Someone who has not accepted anything is added unconfirmed, as before.
        client.post(
            reverse("speakers:session_add_presenter", args=[talk.slug]),
            {
                "presenter": presenters["ada"].pk,
                "role": presenter_role(conference, "PRESENTER").pk,
                "order": 2,
            },
        )
        assert (
            talk.session_presenters.get(presenter=presenters["ada"]).is_confirmed
            is False
        )

    def test_change_role_moves_the_checklist(self, client, organizer, conference):
        make_settings(conference)
        seed_checklists(conference)
        panel = make_session(conference, kind="PANEL", title="Panel")
        panelist = presenter_role(conference, "PANELIST")
        moderator = presenter_role(conference, "MODERATOR")
        # Added as a moderator by mistake: the panelist checklist is the one
        # they should have.
        presenter = make_presenter(conference, display_name="Dexter")
        link = add_presenter(panel, presenter, role=moderator, confirmed=True)
        before = set(presenter.checklist_items.values_list("title", flat=True))
        client.force_login(organizer)
        content = client.get(panel.get_absolute_url()).content.decode()
        assert "Change role" in content
        url = reverse("speakers:session_edit_presenter", args=[panel.slug, link.pk])
        response = client.post(
            url,
            {
                f"link{link.pk}-role": panelist.pk,
                f"link{link.pk}-order": 3,
                f"link{link.pk}-is_required": "on",
            },
            follow=True,
        )
        body = response.content.decode()
        assert "Dexter is now Panelist" in body and "open item(s) dropped" in body
        link.refresh_from_db()
        assert link.role == panelist and link.order == 3
        assert link.is_required is True and link.is_confirmed is True
        titles = set(presenter.checklist_items.values_list("title", flat=True))
        assert titles and titles != before
        assert presenter.checklist_items.filter(
            template_item__template__role=panelist
        ).exists()
        # Back to moderator: open panelist items go, anything done stays.
        done = presenter.checklist_items.filter(
            status=ItemStatus.TODO, auto_complete_rule=""
        ).first()
        complete_item(done, actor=organizer)
        client.post(
            url,
            {f"link{link.pk}-role": moderator.pk, f"link{link.pk}-order": 1},
        )
        titles = set(presenter.checklist_items.values_list("title", flat=True))
        assert done.title in titles  # kept, it was done
        assert presenter.checklist_items.filter(
            template_item__template__role=moderator
        ).exists()
        assert not presenter.checklist_items.filter(
            template_item__template__role=panelist, status=ItemStatus.TODO
        ).exists()
        entry = ActivityLog.objects.filter(
            action="session.presenter_role_changed"
        ).last()
        assert entry.data["presenter_id"] == presenter.pk and entry.actor == organizer

    def test_change_role_without_role_change_only_updates_order(
        self, client, organizer, presenters, conference
    ):
        session = presenters["session"]
        link = session.session_presenters.get()
        client.force_login(organizer)
        url = reverse("speakers:session_edit_presenter", args=[session.slug, link.pk])
        client.post(
            url,
            {
                f"link{link.pk}-role": presenter_role(conference, "PRESENTER").pk,
                f"link{link.pk}-order": 7,
            },
        )
        link.refresh_from_db()
        assert link.order == 7 and link.is_required is False
        assert not ActivityLog.objects.filter(
            action="session.presenter_role_changed"
        ).exists()
        # A role this session's type does not allow is refused.
        response = client.post(
            url,
            {
                f"link{link.pk}-role": presenter_role(conference, "PERFORMER").pk,
                f"link{link.pk}-order": 1,
            },
            follow=True,
        )
        assert "pick a valid role" in response.content.decode()

    def test_unconfirmed_presenter_role_change_creates_no_checklist(self, conference):
        make_settings(conference)
        seed_checklists(conference)
        session = make_session(conference, kind="PANEL")
        link = add_presenter(
            session,
            make_presenter(conference),
            role=presenter_role(conference, "PANELIST"),
        )
        moderator = presenter_role(conference, "MODERATOR")
        assert change_presenter_role(link, moderator) == (0, 0)
        assert link.presenter.checklist_items.count() == 0

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


@pytest.mark.django_db
class TestInviteFromPresenterPage:
    def test_not_invited_hides_checklists_and_offers_send(
        self, client, organizer, presenters, conference
    ):
        ada = presenters["ada"]
        client.force_login(organizer)
        content = client.get(ada.get_absolute_url()).content.decode()
        assert "Not invited yet" in content
        assert "Send invitation" in content and "Their to-dos" not in content
        assert reverse("speakers:presenter_invite", args=[ada.slug]) in content
        assert "Django 101 (Presenter)" in content
        assert "The conference in general" in content

    def test_send_to_session_then_resend(self, client, organizer, presenters):
        ada, session = presenters["ada"], presenters["session"]
        client.force_login(organizer)
        mail.outbox.clear()
        url = reverse("speakers:presenter_invite", args=[ada.slug])
        response = client.post(
            url, {"session": session.pk, "message_md": "Please *come*"}, follow=True
        )
        assert f"Invitation sent to {ada.email}" in response.content.decode()
        invitation = Invitation.objects.get()
        assert invitation.session == session and invitation.invited_by == organizer
        assert invitation.message_md == "Please *come*"
        first_link = _link_from_mail()
        content = client.get(ada.get_absolute_url()).content.decode()
        assert "Invited on" in content and "not yet accepted" in content
        assert "Not opened yet" in content
        assert "Resend invitation" in content
        assert "Their to-dos" in content
        response = client.post(
            url, {"session": session.pk, "message_md": ""}, follow=True
        )
        assert "Invitation resent" in response.content.decode()
        assert Invitation.objects.count() == 1 and len(mail.outbox) == 2
        client.logout()
        assert client.get(first_link).context["reason"] == "superseded"

    def test_general_invitation_and_accepted_state(self, client, organizer, presenters):
        ada = presenters["ada"]
        client.force_login(organizer)
        client.post(
            reverse("speakers:presenter_invite", args=[ada.slug]), {"session": ""}
        )
        invitation = Invitation.objects.get()
        assert invitation.session is None
        invitation.opened_at = invitation.accepted_at = invitation.sent_at
        invitation.save()
        content = client.get(ada.get_absolute_url()).content.decode()
        assert "Accepted on" in content and "Last invitation sent" in content
        assert reverse("speakers:presenter_invite", args=[ada.slug]) not in content

    def test_opened_shown(self, client, organizer, presenters):
        ada = presenters["ada"]
        invitation = make_invitation(ada, presenters["session"])
        send_invitation(invitation)
        invitation.opened_at = invitation.sent_at
        invitation.save()
        client.force_login(organizer)
        assert "Opened" in client.get(ada.get_absolute_url()).content.decode()

    def test_rejects_session_the_presenter_is_not_on(
        self, client, organizer, presenters
    ):
        ada, other = presenters["ada"], presenters["session"]
        stranger = make_session(other.conference, title="Not hers")
        client.force_login(organizer)
        response = client.post(
            reverse("speakers:presenter_invite", args=[ada.slug]),
            {"session": stranger.pk},
            follow=True,
        )
        assert "Pick one of the presenter" in response.content.decode()
        assert Invitation.objects.count() == 0

    def test_organizer_only(self, client, liaison, presenters):
        client.force_login(liaison)
        url = reverse("speakers:presenter_invite", args=[presenters["ada"].slug])
        assert client.post(url, {"session": ""}).status_code == 403


@pytest.mark.django_db
class TestInvitationPreview:
    """The sender sees the whole email before it goes out."""

    URL = reverse("speakers:invitation_preview")

    def test_pages_offer_the_preview_without_rendering_it(
        self, client, organizer, presenters
    ):
        """The box arrives empty and htmx fills it when the form opens, so a
        page carries no email nobody asked to see."""
        ada, session = presenters["ada"], presenters["session"]
        make_invitation(ada, session, message_md="Bring *cake*")
        client.force_login(organizer)
        for url in (ada.get_absolute_url(), session.get_absolute_url()):
            content = client.get(url).content.decode()
            assert "Email preview" in content and self.URL in content
            assert "intersect once" in content
            assert "You&#x27;re invited to" not in content
            assert "<em>cake</em>" not in content and "personal-link" not in content

    def test_a_session_page_costs_the_same_however_many_await_an_invitation(
        self, client, organizer, presenters, conference
    ):
        session = presenters["session"]
        client.force_login(organizer)
        with CaptureQueriesContext(connection) as before:
            client.get(session.get_absolute_url())
        for name in ("Bea", "Cleo", "Dot", "Eve"):
            add_presenter(session, make_presenter(conference, display_name=name))
        with CaptureQueriesContext(connection) as after:
            client.get(session.get_absolute_url())
        assert len(after) == len(before)

    def test_live_preview_for_a_session(self, client, organizer, presenters):
        ada, session = presenters["ada"], presenters["session"]
        client.force_login(organizer)
        response = client.post(
            self.URL,
            {"presenter": ada.slug, "session": session.pk, "message_md": "So *glad*"},
        )
        content = response.content.decode()
        assert response.status_code == 200
        assert "Django 101" in content and "<em>glad</em>" in content
        assert "Subject:" in content and "personal-link" in content
        assert "Hello from" in content  # the wrapper is part of the preview
        assert "<strong>To:</strong> ada@example.com" in content
        assert Invitation.objects.count() == 0

    def test_the_placeholder_address_is_not_a_link(
        self, client, organizer, presenters, send
    ):
        """Copying the preview into a mail client must not carry a dead
        button: until the email goes out the address is shown as code."""
        ada, session = presenters["ada"], presenters["session"]
        client.force_login(organizer)
        content = client.post(
            self.URL, {"presenter": ada.slug, "session": session.pk}
        ).content.decode()
        assert "<code>" in content and "personal-link" in content
        # An anchor would render as <a href="...invitations/...">, so this
        # says the address is never the target of one.
        assert 'invitations/personal-link/">' not in content
        mail.outbox.clear()
        send(make_invitation(ada, session))
        sent = mail.outbox[-1].alternatives[0][0]
        assert 'href="https://example.com/speakers/invitations/' in sent
        assert "<code>" not in sent

    @pytest.mark.parametrize("session_value", ["", "abc", "999999"])
    def test_anything_but_their_session_previews_the_general_invitation(
        self, client, organizer, presenters, session_value
    ):
        ada = presenters["ada"]
        client.force_login(organizer)
        content = client.post(
            self.URL, {"presenter": ada.slug, "session": session_value}
        ).content.decode()
        assert "Django 101" not in content
        assert "part of <strong>" in content

    def test_personal_message_is_introduced_and_set_apart_in_the_preview(
        self, client, organizer, presenters, send
    ):
        ada, session = presenters["ada"], presenters["session"]
        client.force_login(organizer)
        with_note = client.post(
            self.URL,
            {"presenter": ada.slug, "session": session.pk, "message_md": "*Hi*"},
        ).content.decode()
        assert (
            "<p>Below is a message from organizer:</p>\n"
            '<div class="invitation-preview-note">\n<p><em>Hi</em></p>\n</div>'
        ) in with_note
        assert "goes here" not in with_note
        without = client.post(
            self.URL, {"presenter": ada.slug, "session": session.pk}
        ).content.decode()
        assert "<p>Below is a message from" not in without
        assert "invitation-preview-note" in without
        assert "goes here, introduced with" in without and "organizer:" in without
        assert "Highlighted" in without  # the legend under the preview
        # The sent email carries the introduction but none of the preview marks.
        mail.outbox.clear()
        send(make_invitation(ada, session, message_md="*Hi*", invited_by=organizer))
        sent = mail.outbox[-1].alternatives[0][0]
        assert "<p>Below is a message from organizer:</p>\n<p><em>Hi</em></p>" in sent
        assert "invitation-preview-note" not in sent and "goes here" not in sent
        mail.outbox.clear()
        send(make_invitation(ada, session))
        body = mail.outbox[-1].body
        assert "Below is a message" not in body and "goes here" not in body

    def test_resend_without_a_sender_signs_as_the_team(self, client, presenters, send):
        ada, session = presenters["ada"], presenters["session"]
        send(make_invitation(ada, session, message_md="Welcome"))
        assert "Below is a message from the organizing team:" in mail.outbox[-1].body

    def test_organizers_only(self, client, liaison, presenters):
        client.force_login(liaison)
        response = client.post(self.URL, {"presenter": presenters["ada"].slug})
        assert response.status_code == 403

    def test_unknown_presenter_is_404(self, client, organizer, presenters):
        client.force_login(organizer)
        assert client.post(self.URL, {"presenter": "nobody"}).status_code == 404
