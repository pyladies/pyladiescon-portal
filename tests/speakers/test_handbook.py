import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from pytest_django.asserts import assertRedirects

from speakers.constants import AutoRule, ItemOwner, ItemStatus
from speakers.models import ActivityLog, ChecklistItem, Handbook, HandbookReadReceipt

from .factories import make_presenter, make_settings

GUIDE = reverse("speakers:my_guide")
READ = reverse("speakers:my_guide_read")
EDITOR = reverse("speakers:handbook_editor")


@pytest.fixture
def enabled(conference):
    return make_settings(conference)


@pytest.fixture
def speaker(db):
    return User.objects.create_user(username="ada", email="ada@example.com")


@pytest.fixture
def presenter(conference, enabled, speaker):
    return make_presenter(conference, email="ada@example.com", user=speaker)


@pytest.fixture
def organizer(db):
    return User.objects.create_user(username="organizer", is_staff=True)


def publish(conference, version, body="Be **kind**."):
    handbook = Handbook.objects.create(
        conference=conference, version=version, body_md=body
    )
    handbook.publish()
    return handbook


def guide_item(conference, presenter):
    return ChecklistItem.objects.create(
        conference=conference,
        owner=ItemOwner.SPEAKER,
        title="Read the speaker guide",
        presenter=presenter,
        auto_complete_rule=AutoRule.HANDBOOK_READ,
    )


@pytest.mark.django_db
class TestSpeakerGuide:
    def test_coming_soon_without_published_version(
        self, client, speaker, presenter, conference
    ):
        Handbook.objects.create(conference=conference, version=1, body_md="draft")
        client.force_login(speaker)
        content = client.get(GUIDE).content.decode()
        assert "still writing the guide" in content
        assert client.post(READ).status_code == 400

    def test_renders_and_records_receipt_per_version(
        self, client, speaker, presenter, conference
    ):
        first = publish(conference, 1)
        client.force_login(speaker)
        content = client.get(GUIDE).content.decode()
        assert "<strong>kind</strong>" in content
        assert "Version 1, published" in content
        assert 'data-read="false"' in content and "speakers-guide" in content
        response = client.post(READ)
        assertRedirects(response, GUIDE)
        receipt = HandbookReadReceipt.objects.get(presenter=presenter, handbook=first)
        assert receipt.conference == conference
        content = client.get(GUIDE).content.decode()
        assert 'data-read="true"' in content
        assert ActivityLog.objects.get(action="handbook.read").data == {"version": 1}
        client.post(READ)  # reading again is a no-op
        assert HandbookReadReceipt.objects.count() == 1
        assert ActivityLog.objects.filter(action="handbook.read").count() == 1
        second = publish(conference, 2, body="New rules")
        assert 'data-read="false"' in client.get(GUIDE).content.decode()
        client.post(READ)
        assert HandbookReadReceipt.objects.filter(presenter=presenter).count() == 2
        assert HandbookReadReceipt.objects.filter(handbook=second).exists()

    def test_fetch_request_gets_json(self, client, speaker, presenter, conference):
        publish(conference, 1)
        client.force_login(speaker)
        response = client.post(READ, HTTP_X_REQUESTED_WITH="fetch")
        assert response.status_code == 200
        assert response.json() == {"read": True, "version": 1}

    def test_new_version_reopens_the_item(self, client, speaker, presenter, conference):
        item = guide_item(conference, presenter)
        publish(conference, 1)
        client.force_login(speaker)
        client.post(READ)
        item.refresh_from_db()
        assert item.status == ItemStatus.DONE
        publish(conference, 2)
        item.refresh_from_db()
        assert item.status == ItemStatus.TODO
        client.post(READ)
        item.refresh_from_db()
        assert item.status == ItemStatus.DONE

    def test_rail_has_guide(self, client, speaker, presenter):
        client.force_login(speaker)
        assert GUIDE in client.get(reverse("speakers:my_dashboard")).content.decode()

    def test_requires_presenter(self, client, portal_user, enabled):
        client.force_login(portal_user)
        assert client.get(GUIDE).status_code == 403


@pytest.mark.django_db
class TestHandbookEditor:
    def test_organizer_only(self, client, portal_user, enabled, organizer):
        client.force_login(portal_user)
        assert client.get(EDITOR).status_code == 403
        client.force_login(organizer)
        assert client.get(EDITOR).status_code == 200
        assert EDITOR in client.get(reverse("organizer_dashboard")).content.decode()

    def test_save_draft_then_publish(
        self, client, organizer, enabled, conference, presenter
    ):
        client.force_login(organizer)
        response = client.post(
            EDITOR, {"title": "Guide", "body_md": "Hello", "action": "save"}
        )
        assertRedirects(response, EDITOR)
        draft = Handbook.draft(conference)
        assert draft.version == 1 and not draft.is_published
        assert Handbook.current(conference) is None
        content = client.get(EDITOR).content.decode()
        assert "Editing draft version 1" in content and "draft" in content
        client.post(
            EDITOR, {"title": "Guide", "body_md": "Hello *there*", "action": "publish"}
        )
        current = Handbook.current(conference)
        assert current.pk == draft.pk and current.body_md == "Hello *there*"
        assert Handbook.draft(conference) is None
        assert ActivityLog.objects.get(action="handbook.published").data == {
            "version": 1
        }
        content = client.get(EDITOR).content.decode()
        assert "Version 1 is live" in content
        assert 'value="Hello *there*"' in content or "Hello *there*" in content

    def test_publish_directly_and_version_increments(
        self, client, organizer, enabled, conference
    ):
        client.force_login(organizer)
        client.post(EDITOR, {"title": "Guide", "body_md": "v1", "action": "publish"})
        client.post(EDITOR, {"title": "Guide", "body_md": "v2", "action": "publish"})
        assert Handbook.current(conference).version == 2
        assert Handbook.next_version(conference) == 3
        content = client.get(EDITOR).content.decode()
        assert "v2 · Guide" in content and "v1 · Guide" in content

    def test_publish_empty_refused(self, client, organizer, enabled, conference):
        client.force_login(organizer)
        response = client.post(
            EDITOR, {"title": "Guide", "body_md": "  ", "action": "publish"}
        )
        assert response.status_code == 200
        assert "before publishing" in response.context["form"].errors["body_md"][0]
        assert Handbook.objects.count() == 0

    def test_invalid_form_rerenders(self, client, organizer, enabled):
        client.force_login(organizer)
        response = client.post(EDITOR, {"title": "", "body_md": "x", "action": "save"})
        assert (
            response.status_code == 200 and "title" in response.context["form"].errors
        )

    def test_reader_counts(self, client, organizer, enabled, conference, presenter):
        handbook = publish(conference, 1)
        handbook.record_read(presenter)
        assert str(handbook) == "Speaker guide v1"
        assert handbook.published_at <= timezone.now()
        client.force_login(organizer)
        versions = client.get(EDITOR).context["versions"]
        assert versions[0].reader_count == 1
