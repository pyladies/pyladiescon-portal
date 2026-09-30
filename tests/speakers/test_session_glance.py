"""The at-a-glance strip and work-first layout on the two session pages:
the counts under the title, the quick actions, and the sections they
link to (organizer: presenters, checklist, video, schedule; speaker:
to-dos, video, session)."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from speakers.constants import ItemOwner, ItemStatus, MediaKind, MediaStatus
from speakers.models import ChecklistItem, MediaAsset

from .factories import (
    add_presenter,
    make_invitation,
    make_presenter,
    make_session,
    make_settings,
    make_slot,
)


@pytest.fixture
def enabled(conference):
    return make_settings(conference, default_video_length_limit_minutes=10)


@pytest.fixture
def organizer(db):
    return User.objects.create_user("org", email="org@x.org", is_staff=True)


@pytest.fixture
def performer(db):
    return User.objects.create_user("maria", email="maria@x.org")


@pytest.fixture
def bucket(settings):
    """The performer's video tile appears only once the portal has a bucket."""
    settings.SPEAKER_MEDIA_BUCKET = "test-speaker-media"


@pytest.fixture
def session(conference, enabled, performer):
    session = make_session(conference, title="A PyJam set", kind="PYJAM")
    presenter = make_presenter(conference, display_name="Maria", user=performer)
    add_presenter(session, presenter, confirmed=True)
    return session


def item(session, **kwargs):
    kwargs.setdefault("owner", ItemOwner.ORGANIZER)
    kwargs.setdefault("title", "an item")
    return ChecklistItem.objects.create(
        conference=session.conference, session=session, **kwargs
    )


def org_page(session):
    return reverse("speakers:session_detail", args=[session.slug])


def my_page(session):
    return reverse("speakers:my_session_detail", args=[session.slug])


@pytest.mark.django_db
class TestOrganizerStrip:
    def test_counts_and_links(self, client, session, organizer, conference, bucket):
        yesterday = date.today() - timedelta(days=1)
        item(session, due_date=yesterday)
        item(session, status=ItemStatus.BLOCKED)
        item(session, is_waiting=True)
        item(session, status=ItemStatus.DONE)
        other = make_presenter(conference, display_name="Grace")
        add_presenter(session, other)  # unconfirmed, never invited
        make_slot(session)
        client.force_login(organizer)
        response = client.get(org_page(session))
        assert response.status_code == 200
        glance = response.context["glance"]
        assert glance["presenters_total"] == 2 and glance["presenters_confirmed"] == 1
        assert glance["invites_unsent"] == 1
        assert glance["open"] == 3 and glance["overdue"] == 1
        assert glance["blocked"] == 1 and glance["waiting"] == 1
        assert glance["slot"] is not None
        html = response.content.decode()
        assert 'id="glance"' in html
        assert "1 of 2 confirmed" in html and "1 invitation not sent" in html
        assert "3 open items" in html and "1 overdue" in html
        assert "Sat 5 Dec 14:00 UTC" in html
        # The header offers the work: Invite (someone is uninvited), Add file,
        # Add item, Edit; the tiles link to the sections they count.
        for anchor in ("#presenters", "#add-file", "#add-item", "#checklist", "#files"):
            assert f'href="{anchor}"' in html
        assert 'id="presenters"' in html and 'id="add-item"' in html
        # The description is folded below the work, and the sections keep
        # the headings people know.
        assert 'id="description"' in html
        assert (
            html.index('id="glance"')
            < html.index('id="description"')
            < html.index('id="checklist"')
        )
        assert "Checklists for this session" in html

    def test_four_tabs_and_the_anchors_inside_them(self, client, session, organizer):
        """The page is split into tabs; the strip's tiles, the quick actions
        and the redirects keep their anchors, which the script resolves to
        the tab they live in."""
        item(session)
        client.force_login(organizer)
        html = client.get(org_page(session)).content.decode()
        for pane in ("tab-overview", "tab-checklists", "tab-files", "tab-details"):
            assert f'data-bs-target="#{pane}"' in html and f'id="{pane}"' in html
        assert "js/session-tabs" in html
        assert 'data-anchor="checklist"' in html and 'data-anchor="files"' in html

        # Each anchor sits inside its pane, in order.
        def inside(anchor, pane):
            start = html.index(f'id="{pane}"')
            nxt = [
                html.index(f'id="{p}"')
                for p in ("tab-overview", "tab-checklists", "tab-files", "tab-details")
                if html.index(f'id="{p}"') > start
            ]
            end = min(nxt) if nxt else len(html)
            return start < html.index(f'id="{anchor}"') < end

        assert inside("description", "tab-overview") and inside(
            "presenters", "tab-overview"
        )
        assert inside("checklist", "tab-checklists") and inside(
            "add-item", "tab-checklists"
        )
        assert inside("files", "tab-files") and inside("add-file", "tab-files")
        assert inside("details", "tab-details") and inside("activity", "tab-details")
        # The checklist tab carries the open count.
        assert (
            'data-anchor="checklist"' in html.split("Checklists")[0]
            or "1</span>" in html
        )

    def test_invite_action_only_when_someone_is_uninvited(
        self, client, session, organizer, conference
    ):
        client.force_login(organizer)
        html = client.get(org_page(session)).content.decode()
        assert 'href="#presenters">' not in html.split('id="glance"')[0]
        other = make_presenter(conference, display_name="Grace")
        add_presenter(session, other)
        make_invitation(other, session, sent_at=None)
        html = client.get(org_page(session)).content.decode()
        assert "Invite" in html.split('id="glance"')[0]
        assert response_glance(client, session)["invites_unsent"] == 1

    def test_video_tile_and_card(self, client, session, organizer, bucket):
        client.force_login(organizer)
        html = client.get(org_page(session)).content.decode()
        assert "No video yet" in html and "Final cut missing" in html
        assert "not uploaded yet" in html
        MediaAsset.objects.create(
            session=session,
            kind=MediaKind.RAW_VIDEO,
            status=MediaStatus.READY,
            storage_key="k",
            duration_seconds=11 * 60,
        )
        final = MediaAsset.objects.create(
            session=session,
            kind=MediaKind.PROCESSED_VIDEO,
            status=MediaStatus.READY,
            storage_key="k2",
        )
        response = client.get(org_page(session))
        assert response.context["processed"] == final
        html = response.content.decode()
        assert "Raw v1" in html and "11 min 00 s" in html
        assert "Over the limit" in html and "Final cut v1" in html
        assert "over the 10-minute limit" in html
        assert reverse("speakers:media_download", args=[session.slug, final.pk]) in html

    def test_no_bucket_no_video_and_no_upload(self, client, session, organizer):
        """The same rule as the performer's page: a portal deployed ahead
        of its bucket says nothing about uploads or video to anyone."""
        client.force_login(organizer)
        response = client.get(org_page(session))
        html = response.content.decode()
        assert response.context["video"] is None
        assert response.context["media_on"] is False
        assert 'id="video-card"' not in html and 'id="add-file"' not in html
        assert "media-upload.js" not in html and "Final cut" not in html
        assert 'id="files"' in html  # the list itself stays

    def test_the_card_is_gated_on_download_rights(
        self, client, session, organizer, bucket
    ):
        """Like the blocks around it, the card asks a right, not the page:
        it holds if the page's own gate ever widens."""
        client.force_login(organizer)
        assert client.get(org_page(session)).context["can_download_media"] is True
        with patch("speakers.views.can_download", return_value=False):
            response = client.get(org_page(session))
        assert response.context["can_download_media"] is False
        assert response.context["video"] is None
        assert 'id="video-card"' not in response.content.decode()

    def test_live_session_has_no_video_tile(
        self, client, conference, organizer, enabled
    ):
        session = make_session(conference, kind="TALK")
        client.force_login(organizer)
        response = client.get(org_page(session))
        assert response.context["video"] is None
        html = response.content.decode()
        assert "Final cut" not in html and 'id="video-card"' not in html
        assert "0 of 0 confirmed" in html and "Nobody added yet" in html
        assert "All done" in html and "Not scheduled" in html


def response_glance(client, session):
    return client.get(org_page(session)).context["glance"]


@pytest.mark.django_db
class TestSpeakerStrip:
    def test_todos_video_and_session(self, client, session, performer, bucket):
        presenter = session.session_presenters.first().presenter
        yesterday = date.today() - timedelta(days=1)
        soon = date.today() + timedelta(days=3)
        item(
            session,
            owner=ItemOwner.SPEAKER,
            presenter=presenter,
            title="Confirm the title",
            due_date=soon,
        )
        item(
            session,
            owner=ItemOwner.SPEAKER,
            presenter=presenter,
            title="Old one",
            due_date=yesterday,
        )
        item(
            session,
            owner=ItemOwner.SPEAKER,
            presenter=presenter,
            status=ItemStatus.DONE,
        )
        client.force_login(performer)
        response = client.get(my_page(session))
        assert response.status_code == 200
        glance = response.context["glance"]
        assert glance["open"] == 2 and glance["overdue"] == 1
        assert glance["done"] == 1 and glance["total"] == 3
        assert glance["next_due"].title == "Old one"
        html = response.content.decode()
        assert "2 open" in html and "1 overdue" in html
        assert "Not uploaded yet" in html and "Upload it when it is ready" in html
        assert "Upload video" in html and 'href="#video"' in html
        assert "Not scheduled yet" in html and "Not yet public" in html
        # Three tabs under the strip: Overview, Checklist, Files; headings
        # people know kept.
        for pane in ("tab-overview", "tab-checklist", "tab-files"):
            assert f'data-bs-target="#{pane}"' in html and f'id="{pane}"' in html
        assert "js/session-tabs" in html
        assert (
            html.index('id="glance"')
            < html.index('id="description"')
            < html.index('id="checklist"')
            < html.index('id="video"')
        )
        assert "Checklist for this session" in html and "No description yet" in html

    def test_next_due_and_all_done(self, client, session, performer):
        presenter = session.session_presenters.first().presenter
        soon = date.today() + timedelta(days=3)
        todo = item(
            session,
            owner=ItemOwner.SPEAKER,
            presenter=presenter,
            title="Confirm the title",
            due_date=soon,
        )
        client.force_login(performer)
        html = client.get(my_page(session)).content.decode()
        assert f"Next: Confirm the title, {soon:%-d %b}" in html
        todo.status = ItemStatus.DONE
        todo.save()
        html = client.get(my_page(session)).content.decode()
        assert "All done" in html and "1 of 1 done" in html

    def test_video_tile_states(self, client, session, performer, bucket):
        asset = MediaAsset.objects.create(
            session=session,
            kind=MediaKind.RAW_VIDEO,
            status=MediaStatus.READY,
            storage_key="k",
        )
        client.force_login(performer)
        html = client.get(my_page(session)).content.decode()
        assert "Replace video" in html and "Length not checked yet" in html
        asset.duration_seconds = 5 * 60
        asset.save()
        html = client.get(my_page(session)).content.decode()
        assert "5 min 00 s" in html and "Within the limit" in html
        asset.duration_seconds = 12 * 60
        asset.save()
        html = client.get(my_page(session)).content.decode()
        assert "Over the 10-minute limit" in html

    def test_live_session_strip(self, client, conference, performer, enabled):
        session = make_session(conference, kind="TALK")
        add_presenter(
            session, make_presenter(conference, user=performer), confirmed=True
        )
        client.force_login(performer)
        html = client.get(my_page(session)).content.decode()
        assert "Your video" not in html and "Nothing yet" in html
        assert "Your list appears once the team sets it up" in html
        assert "Files the team shares with you appear on this tab" in html
