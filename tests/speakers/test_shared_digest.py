"""The files the team shared ride in the daily digest (design §13.2, task
5.11): once each, only to presenters who may see them, and the email
goes out when there are files even with nothing due."""

from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.urls import reverse

from common.models import SentEmail
from speakers.checklists import add_adhoc_item
from speakers.constants import ItemOwner, MediaKind, MediaStatus, SessionStatus
from speakers.media import new_shared_files, record_asset
from speakers.models import MediaAsset, SharedFileNotice
from speakers.reminders import send_checklist_digests

from .factories import (
    add_presenter,
    make_presenter,
    make_proposal,
    make_session,
    make_settings,
)

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def enabled(conference):
    return make_settings(conference)


@pytest.fixture
def ada(conference):
    return make_presenter(conference, display_name="Ada", email="ada@example.com")


@pytest.fixture
def panel(conference, ada):
    session = make_session(conference, title="The panel", kind="PANEL")
    add_presenter(session, ada, confirmed=True)
    return session


def share(session, kind=MediaKind.PROMO, variant="", title="", version=1, **kw):
    """A ready file the team has shared, as the share button leaves it."""
    kw.setdefault("shared_with_speaker", True)
    kw.setdefault("shared_at", NOW - timedelta(hours=3))
    kw.setdefault("status", MediaStatus.READY)
    return MediaAsset.objects.create(
        session=session,
        kind=kind,
        variant=variant,
        title=title,
        version=version,
        storage_key=f"speaker-media/{session.slug}/{kind.lower()}/{variant}{version}.png",
        original_filename=f"{variant or kind.lower()}-v{version}.png",
        **kw,
    )


def digest(conference):
    mail.outbox.clear()
    return send_checklist_digests(conference, now=NOW)


@pytest.mark.django_db
class TestWhatGoesOut:
    def test_one_digest_with_every_session_then_nothing(
        self, conference, enabled, ada, panel
    ):
        workshop = make_session(conference, title="The workshop", kind="WORKSHOP")
        add_presenter(workshop, ada, confirmed=True)
        poster = share(panel, variant="square", title="Poster for the panel")
        cut = share(panel, kind=MediaKind.PROCESSED_VIDEO)
        slides = share(workshop, kind=MediaKind.OTHER)
        assert digest(conference) == 1
        message = mail.outbox[0]
        assert message.to == ["ada@example.com"]
        assert message.subject.endswith("3 new file(s) from the team")
        body = message.body
        assert "The team has shared new files with you" in body
        assert "todos have deadlines" not in body
        assert body.index("The panel") < body.index("The workshop")
        assert (
            "Poster for the panel (Promo material (square)), v1, shared 20 November"
            in body
        )
        assert "Processed video (final cut), v1" in body
        assert (
            reverse("speakers:my_session_detail", args=[panel.slug]) + "#files" in body
        )
        assert reverse("speakers:my_session_detail", args=[workshop.slug]) in body
        assert "speaker-media/" not in body
        told = SharedFileNotice.objects.filter(presenter=ada)
        assert set(told.values_list("asset_id", flat=True)) == {
            poster.pk,
            cut.pk,
            slides.pk,
        }
        assert told.first().recipient == "ada@example.com"
        assert told.first().conference == conference
        assert str(told.get(asset=poster)) == "Poster for the panel to ada@example.com"
        record = SentEmail.objects.get()
        assert record.presenter == ada
        # Told once: the next day has nothing to say.
        assert digest(conference) == 0 and mail.outbox == []

    def test_todos_and_files_share_one_email(self, conference, enabled, ada, panel):
        add_adhoc_item(
            conference,
            "Read the guide",
            ItemOwner.SPEAKER,
            presenter=ada,
            session=panel,
            due_date=NOW.date() + timedelta(days=2),
        )
        share(panel, variant="square")
        assert digest(conference) == 1
        message = mail.outbox[0]
        assert message.subject.endswith(
            "1 todo(s) with deadlines coming up and 1 new file(s) from the team"
        )
        assert "These todos have deadlines coming up" in message.body
        assert "Read the guide" in message.body
        assert "The team has also shared new files with you" in message.body
        assert message.body.index("Read the guide") < message.body.index("also shared")

    def test_nothing_new_and_nothing_due_sends_nothing(
        self, conference, enabled, ada, panel
    ):
        share(panel, variant="square", shared_with_speaker=False, shared_at=None)
        assert digest(conference) == 0 and mail.outbox == []
        assert not SharedFileNotice.objects.exists()

    def test_unshared_is_not_mentioned_and_reshared_is_not_repeated(
        self, conference, enabled, ada, panel
    ):
        poster = share(panel, variant="square")
        assert digest(conference) == 1
        poster.shared_with_speaker, poster.shared_at = False, None
        poster.save()
        assert digest(conference) == 0
        poster.shared_with_speaker, poster.shared_at = True, NOW
        poster.save()
        assert digest(conference) == 0
        assert SharedFileNotice.objects.count() == 1

    def test_a_replaced_version_is_announced_once_shared(
        self, conference, enabled, ada, panel
    ):
        share(panel, kind=MediaKind.PROCESSED_VIDEO)
        assert digest(conference) == 1
        v2 = record_asset(
            session=panel,
            kind=MediaKind.PROCESSED_VIDEO,
            storage_key="speaker-media/x/v2.mp4",
            filename="cut-v2.mp4",
            content_type="video/mp4",
            size_bytes=3,
            announce=False,
        )
        v1 = MediaAsset.objects.get(kind=MediaKind.PROCESSED_VIDEO, version=1)
        # Withdrawn with its status: no longer shared, and the stamp is gone.
        assert v1.status == MediaStatus.SUPERSEDED
        assert v1.shared_with_speaker is False and v1.shared_at is None
        assert digest(conference) == 0
        v2.shared_with_speaker, v2.shared_at = True, NOW
        v2.save()
        assert digest(conference) == 1
        assert (
            "cut-v2.mp4" not in mail.outbox[0].body
        )  # the line's name, not the file's
        assert "Processed video (final cut), v2" in mail.outbox[0].body

    def test_a_presenter_added_later_is_told(self, conference, enabled, ada, panel):
        share(panel, variant="square")
        assert digest(conference) == 1
        grace = make_presenter(
            conference, display_name="Grace", email="grace@example.com"
        )
        add_presenter(grace_session := panel, grace, confirmed=True)
        assert digest(conference) == 1
        assert mail.outbox[0].to == ["grace@example.com"]
        assert grace_session == panel
        assert SharedFileNotice.objects.filter(presenter=grace).count() == 1


@pytest.mark.django_db
class TestWhoHears:
    def test_not_without_a_confirmed_link_on_an_accepted_session(
        self, conference, enabled, ada
    ):
        """A pending proposal, an unconfirmed link and a cancelled session
        are not sessions the page would show files for."""
        proposal_session = make_session(
            conference, title="Maybe", status=SessionStatus.PROPOSED
        )
        make_proposal(proposal_session, ada)
        add_presenter(proposal_session, ada, confirmed=True)
        share(proposal_session, variant="square")
        unconfirmed = make_session(conference, title="Not yet")
        add_presenter(unconfirmed, ada, confirmed=False)
        share(unconfirmed, variant="square")
        cancelled = make_session(conference, title="Gone")
        add_presenter(cancelled, ada, confirmed=True)
        cancelled.cancel()
        share(cancelled, variant="square")
        assert new_shared_files(ada) == []
        assert digest(conference) == 0

    def test_not_with_the_speaker_side_off(self, conference, ada, panel):
        make_settings(conference, media_for_speakers=False)
        share(panel, variant="square")
        assert new_shared_files(ada) == []
        assert digest(conference) == 0

    def test_only_the_newest_shared_version_of_a_line(
        self, conference, enabled, ada, panel
    ):
        share(panel, variant="square", version=1, status=MediaStatus.SUPERSEDED)
        current = share(panel, variant="square", version=2)
        assert new_shared_files(ada) == [(panel, [current])]


@pytest.mark.django_db
class TestFailure:
    def test_a_failed_send_records_nothing(self, conference, enabled, ada, panel):
        share(panel, variant="square")
        with mock.patch(
            "speakers.reminders.send_email", side_effect=RuntimeError("smtp down")
        ):
            emails = send_checklist_digests(conference, now=NOW)
        assert emails == 0 and emails.failed == 1
        assert not SharedFileNotice.objects.exists()
        assert digest(conference) == 1


@pytest.mark.django_db
class TestTheStamp:
    def test_sharing_stamps_the_moment_and_unsharing_clears_it(
        self, client, conference, enabled, panel
    ):
        organizer = User.objects.create_user("org", email="org@x.org", is_staff=True)
        asset = share(
            panel, variant="square", shared_with_speaker=False, shared_at=None
        )
        client.force_login(organizer)
        url = reverse("speakers:media_share", args=[panel.slug, asset.pk])
        client.post(url, {"shared": "1"})
        asset.refresh_from_db()
        assert asset.shared_with_speaker and asset.shared_at is not None
        client.post(url, {"shared": "0"})
        asset.refresh_from_db()
        assert not asset.shared_with_speaker and asset.shared_at is None

    def test_admin(self, client, admin_user, conference, enabled, ada, panel):
        share(panel, variant="square")
        digest(conference)
        client.force_login(admin_user)
        response = client.get(reverse("admin:speakers_sharedfilenotice_changelist"))
        assert response.status_code == 200
        assert "ada@example.com" in response.content.decode()
