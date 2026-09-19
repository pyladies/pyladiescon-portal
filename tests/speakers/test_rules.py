from datetime import datetime, timezone

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone as dj_timezone

from attendee.models import PretixOrder, PretixOrderstatus
from portal.models import Conference
from speakers.checklists import add_adhoc_item, complete_item, skip_item
from speakers.constants import (
    AutoRule,
    Delivery,
    ItemOwner,
    ItemStatus,
    MediaKind,
    MediaStatus,
)
from speakers.models import (
    ChecklistItem,
    Handbook,
    HandbookReadReceipt,
    MediaAsset,
)
from speakers.rules import RULES, evaluate_item, reevaluate_all
from speakers.seeds import seed_checklists
from speakers.services import accept_invitation, send_invitation
from speakers.tasks import reevaluate_checklists_task

from .factories import (
    add_presenter,
    make_invitation,
    make_presenter,
    make_session,
    make_settings,
    make_slot,
)


def auto_item(conference, rule, *, presenter=None, session=None, **extra):
    """An automatic item for one rule, saved without triggering evaluation."""
    item = ChecklistItem.objects.create(
        conference=conference,
        owner=ItemOwner.SPEAKER,
        title=f"auto {rule}",
        presenter=presenter,
        session=session,
        auto_complete_rule=rule,
        **extra,
    )
    return item


def status_of(item):
    return ChecklistItem.objects.get(pk=item.pk).status


class TestRegistry:
    def test_every_named_rule_has_code(self):
        assert set(RULES) == set(AutoRule.values)


@pytest.mark.django_db
class TestEvaluateItem:
    def test_manual_item_ignored(self, conference):
        item = add_adhoc_item(
            conference, "x", ItemOwner.SPEAKER, presenter=make_presenter(conference)
        )
        assert evaluate_item(item) is None

    def test_skipped_item_left_alone(self, conference):
        presenter = make_presenter(
            conference, bio_md="hi", headshot="speakers/headshots/x.png"
        )
        item = auto_item(conference, AutoRule.BIO_AND_HEADSHOT, presenter=presenter)
        skip_item(item)
        assert evaluate_item(item) is None
        assert status_of(item) == ItemStatus.SKIPPED

    def test_rule_completion_is_not_reopened_when_done_by_hand(self, conference):
        presenter = make_presenter(conference)
        item = auto_item(conference, AutoRule.BIO_AND_HEADSHOT, presenter=presenter)
        complete_item(item, manual=False)
        # An organizer completing it (completed_by set) sticks even if the rule is false.
        organizer = User.objects.create_user(username="org", is_staff=True)
        item.completed_by = organizer
        item.save()
        assert evaluate_item(item) is None
        assert status_of(item) == ItemStatus.DONE


@pytest.mark.django_db
class TestBioAndHeadshot:
    def test_flips_on_presenter_save(self, conference):
        presenter = make_presenter(conference)
        item = auto_item(conference, AutoRule.BIO_AND_HEADSHOT, presenter=presenter)
        assert status_of(item) == ItemStatus.TODO
        presenter.bio_md = "I write programs."
        presenter.save()
        assert status_of(item) == ItemStatus.TODO  # still no headshot
        presenter.headshot = "speakers/headshots/ada.png"
        presenter.save()
        assert status_of(item) == ItemStatus.DONE
        done = ChecklistItem.objects.get(pk=item.pk)
        assert done.completed_by is None and done.completed_at is not None
        presenter.bio_md = "  "
        presenter.save()
        assert status_of(item) == ItemStatus.TODO


@pytest.mark.django_db
class TestHandbookRead:
    def test_receipt_completes_and_new_version_reopens(self, conference):
        presenter = make_presenter(conference)
        item = auto_item(conference, AutoRule.HANDBOOK_READ, presenter=presenter)
        assert evaluate_item(item) is None  # no handbook yet
        draft = Handbook.objects.create(conference=conference, version=1)
        assert status_of(item) == ItemStatus.TODO
        draft.published_at = dj_timezone.now()
        draft.save()
        assert status_of(item) == ItemStatus.TODO
        receipt = HandbookReadReceipt.objects.create(
            presenter=presenter, handbook=draft
        )
        assert receipt.conference == conference
        assert str(receipt) == f"{presenter} read Speaker guide v1"
        assert status_of(item) == ItemStatus.DONE
        Handbook.objects.create(
            conference=conference, version=2, published_at=dj_timezone.now()
        )
        assert status_of(item) == ItemStatus.TODO
        assert Handbook.current(conference).version == 2

    def test_item_without_presenter(self, conference):
        session = make_session(conference)
        Handbook.objects.create(
            conference=conference, version=1, published_at=dj_timezone.now()
        )
        item = auto_item(conference, AutoRule.HANDBOOK_READ, session=session)
        assert evaluate_item(item) is None


@pytest.mark.django_db
class TestInvitationRules:
    def test_sent_and_accepted_tick_on_accept(self, conference):
        make_settings(conference)
        seed_checklists(conference)
        session = make_session(conference, kind="WORKSHOP")
        presenter = make_presenter(conference)
        add_presenter(session, presenter)
        invitation = make_invitation(presenter, session)
        send_invitation(invitation)
        accept_invitation(invitation)
        sent = presenter.checklist_items.get(title="Invitation sent")
        accepted = presenter.checklist_items.get(title="Presenter in portal")
        assert sent.status == ItemStatus.DONE
        assert accepted.status == ItemStatus.DONE

    def test_sent_flips_when_invitation_sent_later(self, conference):
        session = make_session(conference)
        presenter = make_presenter(conference)
        link = add_presenter(session, presenter)
        item = auto_item(
            conference, AutoRule.INVITATION_SENT, presenter=presenter, session=session
        )
        accepted_item = auto_item(
            conference,
            AutoRule.INVITATION_ACCEPTED,
            presenter=presenter,
            session=session,
        )
        other_session_invite = make_invitation(presenter, make_session(conference))
        send_invitation(other_session_invite)
        assert status_of(item) == ItemStatus.TODO  # a different session's invitation
        general = make_invitation(presenter)
        send_invitation(general)
        assert status_of(item) == ItemStatus.DONE  # a general invitation counts
        assert status_of(accepted_item) == ItemStatus.TODO
        link.confirm()
        assert status_of(accepted_item) == ItemStatus.DONE


@pytest.mark.django_db
class TestSessionScheduled:
    def test_slot_create_and_delete(self, conference):
        session = make_session(conference)
        item = auto_item(conference, AutoRule.SESSION_SCHEDULED, session=session)
        slot = make_slot(session)
        assert status_of(item) == ItemStatus.DONE
        slot.delete()
        assert status_of(item) == ItemStatus.TODO


@pytest.mark.django_db
class TestPretixRegistered:
    def make_order(
        self, conference, code, email, status=PretixOrderstatus.PAID, positions=None
    ):
        return PretixOrder.objects.create(
            conference=conference,
            order_code=code,
            email=email,
            status=status,
            raw_data={"positions": positions or []},
        )

    def test_matches_order_email_case_insensitively(self, conference):
        presenter = make_presenter(conference, email="ada@example.com")
        item = auto_item(conference, AutoRule.PRETIX_REGISTERED, presenter=presenter)
        self.make_order(conference, "A1", "other@example.com")
        assert status_of(item) == ItemStatus.TODO
        self.make_order(conference, "A2", "ADA@Example.com")
        assert status_of(item) == ItemStatus.DONE

    def test_matches_attendee_email_in_positions(self, conference):
        presenter = make_presenter(conference, email="ada@example.com")
        item = auto_item(conference, AutoRule.PRETIX_REGISTERED, presenter=presenter)
        self.make_order(
            conference,
            "B1",
            "buyer@example.com",
            positions=[{"attendee_name": "Ada", "attendee_email": "ada@example.com"}],
        )
        assert status_of(item) == ItemStatus.DONE

    def test_cancelled_order_does_not_count(self, conference):
        presenter = make_presenter(conference, email="ada@example.com")
        item = auto_item(conference, AutoRule.PRETIX_REGISTERED, presenter=presenter)
        self.make_order(
            conference, "C1", "ada@example.com", status=PretixOrderstatus.CANCELLED
        )
        assert status_of(item) == ItemStatus.TODO

    def test_manual_link_wins(self, conference):
        presenter = make_presenter(conference, email="ada@example.com")
        item = auto_item(conference, AutoRule.PRETIX_REGISTERED, presenter=presenter)
        order = self.make_order(conference, "D1", "someone-else@example.com")
        presenter.pretix_order = order
        presenter.save()
        assert status_of(item) == ItemStatus.DONE
        order.status = PretixOrderstatus.CANCELLED
        order.save()
        assert status_of(item) == ItemStatus.TODO

    def test_item_without_presenter(self, conference):
        item = auto_item(
            conference, AutoRule.PRETIX_REGISTERED, session=make_session(conference)
        )
        assert evaluate_item(item) is None


@pytest.mark.django_db
class TestAssetExists:
    def test_ready_asset_of_kind_and_language(self, conference):
        session = make_session(conference, kind="PYJAM", delivery=Delivery.PRE_RECORDED)
        item = auto_item(
            conference,
            AutoRule.ASSET_EXISTS,
            session=session,
            requires_asset_kind=MediaKind.TRANSCRIPT,
            requires_asset_language="en",
        )
        other_lang = auto_item(
            conference,
            AutoRule.ASSET_EXISTS,
            session=session,
            requires_asset_kind=MediaKind.TRANSCRIPT,
            requires_asset_language="pt-br",
        )
        asset = MediaAsset.objects.create(
            session=session, kind=MediaKind.TRANSCRIPT, language="en"
        )
        assert asset.conference == conference
        assert str(asset) == f"Transcript v1 for {session}"
        assert status_of(item) == ItemStatus.TODO  # still uploading
        assert asset.is_ready is False
        asset.status = MediaStatus.READY
        asset.save()
        assert asset.is_ready is True
        assert status_of(item) == ItemStatus.DONE
        assert status_of(other_lang) == ItemStatus.TODO
        asset.delete()
        assert status_of(item) == ItemStatus.TODO

    def test_item_without_kind(self, conference):
        item = auto_item(
            conference, AutoRule.ASSET_EXISTS, session=make_session(conference)
        )
        assert evaluate_item(item) is None


@pytest.mark.django_db
class TestVideoLengthOk:
    @pytest.fixture
    def jam(self, conference):
        make_settings(conference, default_video_length_limit_minutes=10)
        return make_session(conference, kind="PYJAM", delivery=Delivery.PRE_RECORDED)

    def add_video(self, session, seconds, version=1):
        return MediaAsset.objects.create(
            session=session,
            kind=MediaKind.RAW_VIDEO,
            version=version,
            status=MediaStatus.READY,
            duration_seconds=seconds,
        )

    def test_blocks_with_overage_then_clears(self, conference, jam):
        item = auto_item(conference, AutoRule.VIDEO_LENGTH_OK, session=jam)
        assert status_of(item) == ItemStatus.TODO
        self.add_video(jam, 12 * 60 + 5)
        blocked = ChecklistItem.objects.get(pk=item.pk)
        assert blocked.status == ItemStatus.BLOCKED
        assert blocked.note == "Video is 2:05 over the 10-minute limit (v1)."
        assert evaluate_item(blocked) is None  # same note, no change
        self.add_video(jam, 9 * 60, version=2)
        done = ChecklistItem.objects.get(pk=item.pk)
        assert done.status == ItemStatus.DONE and done.note == ""

    def test_session_limit_overrides_default(self, conference, jam):
        jam.video_length_limit_minutes = 15
        jam.save()
        item = auto_item(conference, AutoRule.VIDEO_LENGTH_OK, session=jam)
        self.add_video(jam, 14 * 60)
        assert status_of(item) == ItemStatus.DONE
        jam.video_length_limit_minutes = 5
        jam.save()
        assert status_of(item) == ItemStatus.BLOCKED

    def test_no_limit_anywhere_passes(self, conference):
        jam = make_session(conference, kind="PYJAM", delivery=Delivery.PRE_RECORDED)
        item = auto_item(conference, AutoRule.VIDEO_LENGTH_OK, session=jam)
        self.add_video(jam, 3600)
        assert status_of(item) == ItemStatus.DONE

    def test_unknown_duration_waits(self, conference, jam):
        item = auto_item(conference, AutoRule.VIDEO_LENGTH_OK, session=jam)
        self.add_video(jam, None)
        assert status_of(item) == ItemStatus.TODO

    def test_blocked_reopens_when_video_removed(self, conference, jam):
        item = auto_item(conference, AutoRule.VIDEO_LENGTH_OK, session=jam)
        video = self.add_video(jam, 20 * 60)
        assert status_of(item) == ItemStatus.BLOCKED
        video.delete()
        reopened = ChecklistItem.objects.get(pk=item.pk)
        assert reopened.status == ItemStatus.TODO and reopened.note == ""


@pytest.mark.django_db
class TestYoutubePublished:
    def test_flips_when_url_and_time_set(self, conference):
        session = make_session(conference, kind="PYJAM", delivery=Delivery.PRE_RECORDED)
        item = auto_item(conference, AutoRule.YOUTUBE_PUBLISHED, session=session)
        session.youtube_url = "https://youtube.com/watch?v=abc"
        session.save()
        assert status_of(item) == ItemStatus.TODO
        session.youtube_publish_at = datetime(2026, 12, 5, 18, 0, tzinfo=timezone.utc)
        session.save()
        assert status_of(item) == ItemStatus.DONE


@pytest.mark.django_db
class TestNightly:
    def test_reevaluate_all_and_task(self, conference):
        presenter = make_presenter(
            conference, bio_md="hi", headshot="speakers/headshots/x.png"
        )
        item = auto_item(conference, AutoRule.BIO_AND_HEADSHOT, presenter=presenter)
        ChecklistItem.objects.filter(pk=item.pk).update(status=ItemStatus.TODO)
        assert reevaluate_all(conference) == 1
        assert status_of(item) == ItemStatus.DONE
        assert (
            reevaluate_checklists_task() == "Re-evaluated checklists; 0 item(s) changed"
        )

    def test_reevaluate_all_scopes_by_conference(self, conference):
        other = Conference.objects.create(year=2024, name="Old", slug="2024")
        presenter = make_presenter(
            other, bio_md="hi", headshot="speakers/headshots/x.png"
        )
        item = auto_item(other, AutoRule.BIO_AND_HEADSHOT, presenter=presenter)
        ChecklistItem.objects.filter(pk=item.pk).update(status=ItemStatus.TODO)
        assert reevaluate_all(conference) == 0
        assert reevaluate_all() == 1


@pytest.mark.django_db
class TestShellAdmin:
    def test_changelists(self, client, admin_user, conference):
        session = make_session(conference)
        MediaAsset.objects.create(session=session, kind=MediaKind.RAW_VIDEO)
        handbook = Handbook.objects.create(conference=conference, version=1)
        HandbookReadReceipt.objects.create(
            presenter=make_presenter(conference), handbook=handbook
        )
        client.force_login(admin_user)
        for name in ("mediaasset", "handbook"):
            assert (
                client.get(reverse(f"admin:speakers_{name}_changelist")).status_code
                == 200
            )
        assert (
            client.get(
                reverse("admin:speakers_handbook_change", args=[handbook.pk])
            ).status_code
            == 200
        )
        assert client.get(reverse("admin:speakers_presenter_add")).status_code == 200
