"""Open proposals, and speakers adding sessions of their own (task 2.21).

A proposal is the mirror of an invitation: a person asking the organizers
rather than the organizers asking a person. Approving runs the same path an
accepted invitation takes, which is what these tests check hardest.
"""

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.urls import reverse

from speakers.constants import (
    MAX_PENDING_PROPOSALS,
    MAX_SELF_SESSIONS,
    ItemOwner,
    ProposalDecision,
    SessionStatus,
)
from speakers.models import ChecklistItem, Proposal, Session
from speakers.program_types import session_type
from speakers.seeds import seed_checklists
from speakers.services import ProposalError, add_own_session, submit_proposal

from .factories import add_presenter, make_presenter, make_session, make_settings

PROPOSE = reverse("speakers:propose")
MINE = reverse("speakers:my_proposals")
QUEUE = reverse("speakers:proposal_queue")


@pytest.fixture
def enabled(conference):
    """The module on and proposals open, which is the interesting state."""
    settings_row = make_settings(conference, proposals_open=True)
    seed_checklists(conference)
    return settings_row


@pytest.fixture
def organizer(db):
    return User.objects.create_user(
        username="org", email="org@example.com", is_staff=True
    )


@pytest.fixture
def stranger(db):
    """Someone with a portal account and nothing else."""
    return User.objects.create_user(username="sam", email="sam@example.com")


def propose(client, conference, title="A talk about testing"):
    """Post the form the way the page does."""
    return client.post(
        PROPOSE,
        {
            "you-display_name": "Sam Newcomer",
            "you-bio_md": "I write tests.",
            "you-timezone": "UTC",
            "session-kind": session_type(conference, "TALK").pk,
            "session-title": title,
            "session-summary_md": "What testing is for.",
            "session-level": "ALL",
            "session-language": "en",
        },
        follow=True,
    )


@pytest.mark.django_db
class TestProposing:
    def test_a_stranger_proposes_and_sees_it_pending(
        self, client, conference, enabled, stranger, organizer
    ):
        client.force_login(stranger)
        response = propose(client, conference)
        assert "We have" in response.content.decode()
        proposal = Proposal.objects.get()
        assert proposal.decision == ProposalDecision.PENDING
        assert proposal.session.status == SessionStatus.PROPOSED
        assert proposal.session.created_by_presenter is True
        presenter = proposal.presenter
        assert presenter.user == stranger and presenter.email == stranger.email
        # Real rows from the start, including the link they will be
        # confirmed on.
        link = proposal.session.session_presenters.get()
        assert link.presenter == presenter and not link.is_confirmed
        # Two emails: a receipt, and a nudge to the organizers.
        subjects = [m.subject for m in mail.outbox]
        assert any("We have your proposal" in s for s in subjects)
        assert any("New session proposal" in s for s in subjects)
        assert MINE in response.redirect_chain[-1][0]

    def test_the_speaker_area_is_not_theirs_until_someone_says_yes(
        self, client, conference, enabled, stranger
    ):
        client.force_login(stranger)
        propose(client, conference)
        assert client.get(reverse("speakers:my_dashboard")).status_code == 403
        assert client.get(reverse("speakers:my_checklist")).status_code == 403
        content = client.get(MINE).content.decode()
        assert "A talk about testing" in content and "Pending review" in content

    def test_editing_and_withdrawing_while_nobody_has_answered(
        self, client, conference, enabled, stranger
    ):
        client.force_login(stranger)
        propose(client, conference)
        proposal = Proposal.objects.get()
        client.post(
            reverse("speakers:proposal_edit", args=[proposal.pk]),
            {
                "session-kind": session_type(conference, "WORKSHOP").pk,
                "session-title": "Now a workshop",
                "session-summary_md": "Hands on.",
                "session-level": "ALL",
                "session-language": "en",
            },
        )
        proposal.session.refresh_from_db()
        assert proposal.session.title == "Now a workshop"
        assert proposal.session.kind.code == "WORKSHOP"
        client.post(reverse("speakers:proposal_withdraw", args=[proposal.pk]))
        assert not Proposal.objects.exists()
        # The session goes with it: nothing else refers to it.
        assert not Session.objects.filter(title="Now a workshop").exists()

    def test_a_fourth_pending_proposal_is_refused(
        self, client, conference, enabled, stranger
    ):
        client.force_login(stranger)
        for n in range(MAX_PENDING_PROPOSALS):
            propose(client, conference, title=f"Talk {n}")
        response = propose(client, conference, title="One too many")
        assert "waiting for an answer" in response.content.decode()
        assert Proposal.objects.count() == MAX_PENDING_PROPOSALS

    def test_proposals_closed_shows_the_door_shut(self, client, conference, stranger):
        make_settings(conference)
        client.force_login(stranger)
        content = client.get(PROPOSE).content.decode()
        assert "not taking proposals" in content
        assert client.post(PROPOSE, {}).status_code == 403

    def test_signed_out_is_asked_to_sign_in(self, client, conference, enabled):
        content = client.get(PROPOSE).content.decode()
        assert "Create an account" in content and "Sign in" in content
        assert reverse("account_login") in content

    def test_the_form_is_two_sections_that_fold(
        self, client, conference, enabled, stranger
    ):
        """The form is long: someone rewriting their summary can fold their
        own details away without losing what they typed."""
        client.force_login(stranger)
        content = client.get(PROPOSE).content.decode()
        assert "About you" in content and "Your session" in content
        assert content.count("accordion-item") == 2
        # Both open on arrival: nothing is hidden from a first-time reader.
        assert content.count("accordion-collapse collapse show") == 2

    def test_a_returning_proposer_only_sees_the_session_half(
        self, client, conference, enabled, stranger
    ):
        client.force_login(stranger)
        propose(client, conference)
        content = client.get(PROPOSE).content.decode()
        assert "About you" not in content
        assert "Your details are already with us" in content
        assert content.count("accordion-item") == 1

    def test_the_page_sits_below_the_navbar(self, client, conference, enabled):
        """The base template's body block is the hero above the navbar; a
        page that fills it renders above the site's own navigation."""
        content = client.get(PROPOSE).content.decode()
        assert content.index("navbar-expand-md") < content.index(
            "Propose a session for"
        )


@pytest.mark.django_db
class TestWhereProposalsLive:
    """A speaker's proposals sit with the rest of their speaking; a
    proposer who is not a speaker yet keeps them in their own rail."""

    def test_a_speaker_sees_them_under_speaking(self, client, conference, enabled):
        user = User.objects.create_user(username="ada", email="ada@example.com")
        presenter = make_presenter(conference, display_name="Ada", user=user)
        add_presenter(make_session(conference), presenter, confirmed=True)
        submit_proposal(presenter, make_session(conference, title="Another idea"))
        client.force_login(user)
        content = client.get(MINE).content.decode()
        assert "Speaking" in content and "My speaker checklist" in content
        assert "My proposals" in content and "Another idea" in content
        # And from the speaker pages, the entry is there to click.
        assert (
            "My proposals"
            in client.get(reverse("speakers:my_dashboard")).content.decode()
        )

    def test_a_proposer_keeps_them_in_their_own_rail(
        self, client, conference, enabled, stranger
    ):
        client.force_login(stranger)
        propose(client, conference)
        content = client.get(MINE).content.decode()
        assert "My volunteering" in content and "My proposals" in content
        assert "My speaker checklist" not in content

    def test_a_speaker_is_offered_add_a_session(self, client, conference, enabled):
        user = User.objects.create_user(username="ada", email="ada@example.com")
        presenter = make_presenter(conference, display_name="Ada", user=user)
        add_presenter(make_session(conference), presenter, confirmed=True)
        client.force_login(user)
        content = client.get(reverse("speakers:my_sessions")).content.decode()
        assert reverse("speakers:my_session_add") in content

    def test_a_speaker_sees_which_sessions_are_real_and_which_are_asked_for(
        self, client, conference, enabled
    ):
        """My sessions lists a proposal too, so it has to say which is
        which: "draft" and "confirmed" are the organizers' words, and a
        proposal is not a session of the conference's at all yet.
        """
        user = User.objects.create_user(username="ada", email="ada@example.com")
        presenter = make_presenter(conference, display_name="Ada", user=user)
        confirmed = make_session(conference, title="The real one")
        add_presenter(confirmed, presenter, confirmed=True)
        confirmed.confirm()
        asked_for = make_session(conference, title="The asked-for one")
        add_presenter(asked_for, presenter)
        submit_proposal(presenter, asked_for)
        client.force_login(user)
        content = client.get(reverse("speakers:my_sessions")).content.decode()
        assert "Confirmed" in content and "Waiting for an answer" in content
        # A proposal has no checklist and is edited where it was sent.
        assert reverse("speakers:my_proposals") in content
        assert reverse("speakers:my_session_edit", args=[asked_for.slug]) not in content
        assert reverse("speakers:my_session_edit", args=[confirmed.slug]) in content
        # The dashboard says the same thing.
        dashboard = client.get(reverse("speakers:my_dashboard")).content.decode()
        assert "Waiting for an answer" in dashboard

    def test_pyjam_can_be_proposed(self, conference, enabled):
        """A performance is something people bring, like a talk or a
        workshop; the furniture of the program is not."""
        from speakers.services import proposable_types

        codes = set(proposable_types(conference).values_list("code", flat=True))
        assert {"TALK", "WORKSHOP", "PYJAM"} <= codes
        assert "BREAK" not in codes and "OPENING" not in codes


@pytest.mark.django_db
class TestDeciding:
    def test_approving_runs_the_acceptance_path(
        self, client, conference, enabled, stranger, organizer
    ):
        client.force_login(stranger)
        propose(client, conference)
        proposal = Proposal.objects.get()
        mail.outbox.clear()
        client.force_login(organizer)
        response = client.post(
            reverse("speakers:proposal_decide", args=[proposal.pk]),
            {"decision": "APPROVED"},
            follow=True,
        )
        assert "is in" in response.content.decode()
        proposal.refresh_from_db()
        assert proposal.decision == ProposalDecision.APPROVED
        assert proposal.decided_by == organizer and proposal.decided_at
        session = proposal.session
        session.refresh_from_db()
        # Confirmed on it, with the checklist a speaker always gets, dated
        # from the approval rather than from some earlier moment.
        link = session.session_presenters.get()
        assert link.is_confirmed and link.confirmed_at == proposal.decided_at
        items = ChecklistItem.objects.filter(presenter=proposal.presenter)
        assert items.filter(owner=ItemOwner.SPEAKER).exists()
        assert session.status == SessionStatus.CONFIRMED
        assert any("Your session is in" in m.subject for m in mail.outbox)
        # And now the speaker area is theirs.
        client.force_login(stranger)
        assert client.get(reverse("speakers:my_dashboard")).status_code == 200

    def test_rejecting_is_short_and_keeps_the_record(
        self, client, conference, enabled, stranger, organizer
    ):
        client.force_login(stranger)
        propose(client, conference)
        proposal = Proposal.objects.get()
        mail.outbox.clear()
        client.force_login(organizer)
        client.post(
            reverse("speakers:proposal_decide", args=[proposal.pk]),
            {"decision": "REJECTED"},
        )
        proposal.refresh_from_db()
        assert proposal.decision == ProposalDecision.REJECTED
        assert proposal.session.status == SessionStatus.REJECTED
        body = mail.outbox[-1].body
        assert "not able to take it" in body and "propose again" in body
        # The proposer can still read what they sent.
        client.force_login(stranger)
        content = client.get(MINE).content.decode()
        assert "A talk about testing" in content and "Not accepted" in content

    def test_a_decided_proposal_cannot_be_decided_again(
        self, conference, enabled, stranger, organizer, client
    ):
        client.force_login(stranger)
        propose(client, conference)
        proposal = Proposal.objects.get()
        client.force_login(organizer)
        url = reverse("speakers:proposal_decide", args=[proposal.pk])
        client.post(url, {"decision": "APPROVED"})
        response = client.post(url, {"decision": "REJECTED"}, follow=True)
        assert "already been answered" in response.content.decode()

    def test_an_unknown_answer_is_refused(
        self, client, conference, enabled, stranger, organizer
    ):
        client.force_login(stranger)
        propose(client, conference)
        proposal = Proposal.objects.get()
        client.force_login(organizer)
        assert (
            client.post(
                reverse("speakers:proposal_decide", args=[proposal.pk]),
                {"decision": "MAYBE"},
            ).status_code
            == 400
        )

    def test_the_queue_is_organizers_and_liaisons(
        self, client, conference, enabled, stranger, organizer
    ):
        client.force_login(stranger)
        propose(client, conference)
        client.force_login(organizer)
        content = client.get(QUEUE).content.decode()
        assert "A talk about testing" in content and "Approve" in content
        client.force_login(stranger)
        assert client.get(QUEUE).status_code == 403


@pytest.mark.django_db
class TestSpeakerAddsTheirOwn:
    def test_a_speaker_on_the_program_adds_one_without_review(
        self, client, conference, enabled, organizer
    ):
        user = User.objects.create_user(username="ada", email="ada@example.com")
        presenter = make_presenter(conference, display_name="Ada", user=user)
        add_presenter(make_session(conference), presenter, confirmed=True)
        client.force_login(user)
        mail.outbox.clear()
        response = client.post(
            reverse("speakers:my_session_add"),
            {
                "session-kind": session_type(conference, "TALK").pk,
                "session-title": "One more talk",
                "session-summary_md": "About more things.",
                "session-level": "ALL",
                "session-language": "en",
            },
            follow=True,
        )
        assert "is on your sessions" in response.content.decode()
        session = Session.objects.get(title="One more talk")
        assert session.status in (SessionStatus.DRAFT, SessionStatus.CONFIRMED)
        assert session.created_by_presenter is True
        assert not Proposal.objects.exists()  # no review for them
        link = session.session_presenters.get()
        assert link.presenter == presenter and link.is_confirmed
        assert ChecklistItem.objects.filter(session=session).exists()
        assert any("added a session" in m.subject for m in mail.outbox)

    def test_a_proposer_may_not_use_that_door(self, conference, enabled, stranger):
        presenter = make_presenter(conference, display_name="Sam", user=stranger)
        session = make_session(conference, title="Theirs")
        add_presenter(session, presenter)
        with pytest.raises(ProposalError, match="has accepted"):
            add_own_session(presenter, session)

    def test_the_fourth_one_is_refused(self, conference, enabled):
        user = User.objects.create_user(username="ada", email="ada@example.com")
        presenter = make_presenter(conference, display_name="Ada", user=user)
        add_presenter(make_session(conference), presenter, confirmed=True)
        for n in range(MAX_SELF_SESSIONS):
            session = make_session(
                conference, title=f"Mine {n}", created_by_presenter=True
            )
            add_presenter(session, presenter)
            add_own_session(presenter, session)
        session = make_session(
            conference, title="One too many", created_by_presenter=True
        )
        add_presenter(session, presenter)
        with pytest.raises(ProposalError, match="already added"):
            add_own_session(presenter, session)


@pytest.mark.django_db
class TestWhatOthersSee:
    def test_a_proposal_is_not_on_the_program_list(
        self, client, conference, enabled, stranger, organizer
    ):
        client.force_login(stranger)
        propose(client, conference)
        client.force_login(organizer)
        content = client.get(reverse("speakers:session_list")).content.decode()
        assert "A talk about testing" not in content
        # Asking for it by status shows it.
        content = client.get(
            reverse("speakers:session_list"), {"status": "PROPOSED"}
        ).content.decode()
        assert "A talk about testing" in content

    def test_submitting_twice_over_the_service_keeps_the_cap(
        self, conference, enabled, stranger
    ):
        presenter = make_presenter(conference, display_name="Sam", user=stranger)
        for n in range(MAX_PENDING_PROPOSALS):
            session = make_session(conference, title=f"S{n}")
            submit_proposal(presenter, session)
        session = make_session(conference, title="Over")
        with pytest.raises(ProposalError, match="waiting for an answer"):
            submit_proposal(presenter, session)
