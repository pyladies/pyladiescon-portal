import json
from datetime import datetime, timezone
from unittest import mock

import pytest
import requests
from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.test import override_settings
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from attendee.models import AttendeeProfile, PretixOrder
from portal.models import Conference
from speakers.constants import AutoRule, ItemOwner, ItemStatus
from speakers.models import ActivityLog, ChecklistItem, SpeakerSettings
from speakers.pretix import (
    PretixClient,
    PretixError,
    client_for,
    create_voucher,
    link_presenter_order,
    lookup_presenter_orders,
    reconcile,
    upsert_order,
)
from speakers.tasks import pretix_reconcile_task

from .factories import make_presenter, make_settings


@pytest.fixture
def pretix_settings(conference):
    return make_settings(
        conference,
        pretix_organizer="pyladiescon",
        pretix_api_token="tok-secret",
        pretix_webhook_secret="hook-secret",
    )


@pytest.fixture
def organizer(db):
    return User.objects.create_user(username="organizer", is_staff=True)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def order_payload(code, email, status="p", modified="2025-11-13T17:12:07+01:00"):
    return {
        "code": code,
        "event": "2025",
        "status": status,
        "testmode": False,
        "email": email,
        "datetime": "2025-11-13T17:12:03+01:00",
        "total": "30.00",
        "positions": [
            {"attendee_name": "Someone", "attendee_email": email, "answers": []}
        ],
        "last_modified": modified,
        "url": "https://pretix.example/order/",
        "cancellation_date": None,
    }


@pytest.mark.django_db
class TestEncryptedField:
    def test_stored_encrypted_read_decrypted(self, conference, pretix_settings):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pretix_api_token FROM speakers_speakersettings WHERE id = %s",
                [pretix_settings.pk],
            )
            raw = cursor.fetchone()[0]
        assert raw != "tok-secret" and raw.startswith("gAAAA")
        assert (
            SpeakerSettings.objects.get(pk=pretix_settings.pk).pretix_api_token
            == "tok-secret"
        )

    def test_blank_stays_blank(self, conference):
        row = make_settings(conference)
        assert SpeakerSettings.objects.get(pk=row.pk).pretix_api_token == ""

    def test_missing_key_refuses_to_save(self, conference):
        with override_settings(FERNET_KEY=None):
            with pytest.raises(ImproperlyConfigured, match="FERNET_KEY is not set"):
                make_settings(conference, pretix_api_token="x")

    def test_wrong_key_refuses_to_read(self, conference, pretix_settings):
        with override_settings(FERNET_KEY=Fernet.generate_key().decode()):
            with pytest.raises(ImproperlyConfigured, match="cannot be decrypted"):
                SpeakerSettings.objects.get(pk=pretix_settings.pk)

    def test_settings_helpers(self, conference, pretix_settings):
        assert pretix_settings.pretix_event_slug == "2025"
        assert pretix_settings.pretix_configured is True
        pretix_settings.pretix_event = "special"
        assert pretix_settings.pretix_event_slug == "special"
        pretix_settings.pretix_api_token = ""
        assert pretix_settings.pretix_configured is False


class TestClient:
    def make_client(self):
        row = mock.Mock(
            pretix_base_url="https://pretix.example/api/v1",
            pretix_organizer="org",
            pretix_event_slug="ev",
            pretix_api_token="tok",
        )
        return PretixClient(row, backoff=0)

    def test_orders_url(self):
        assert (
            self.make_client().orders_url
            == "https://pretix.example/api/v1/organizers/org/events/ev/orders/"
        )

    @mock.patch("speakers.pretix.time.sleep")
    @mock.patch("speakers.pretix.requests.get")
    def test_pagination_and_params(self, get, sleep):
        client = self.make_client()
        get.side_effect = [
            FakeResponse(payload={"results": [{"code": "A"}], "next": "https://n/2"}),
            FakeResponse(payload={"results": [{"code": "B"}], "next": None}),
        ]
        since = datetime(2026, 1, 1, tzinfo=timezone.utc)
        codes = [
            o["code"] for o in client.iter_orders(modified_since=since, email="a@b")
        ]
        assert codes == ["A", "B"]
        first, second = get.call_args_list
        assert first.kwargs["params"] == {
            "modified_since": since.isoformat(),
            "email": "a@b",
        }
        assert first.kwargs["headers"] == {"Authorization": "Token tok"}
        assert second.args[0] == "https://n/2" and second.kwargs["params"] is None
        sleep.assert_not_called()

    @mock.patch("speakers.pretix.time.sleep")
    @mock.patch("speakers.pretix.requests.get")
    def test_retries_then_succeeds(self, get, sleep):
        get.side_effect = [
            FakeResponse(status_code=503, text="down"),
            FakeResponse(payload={"code": "A"}),
        ]
        assert self.make_client().get_order("A") == {"code": "A"}
        assert sleep.call_count == 1

    @mock.patch("speakers.pretix.time.sleep")
    @mock.patch("speakers.pretix.requests.get")
    def test_gives_up_after_attempts(self, get, sleep):
        get.side_effect = requests.ConnectionError("boom")
        with pytest.raises(PretixError, match="ConnectionError"):
            self.make_client().get_order("A")
        assert get.call_count == 3 and sleep.call_count == 2

    @mock.patch("speakers.pretix.time.sleep")
    @mock.patch("speakers.pretix.requests.get")
    def test_no_retry_on_client_error(self, get, sleep):
        get.return_value = FakeResponse(status_code=404, text="nope")
        with pytest.raises(PretixError, match="404"):
            self.make_client().get_order("A")
        assert get.call_count == 1


@pytest.mark.django_db
class TestUpsert:
    def test_paid_order_creates_profile_and_updates(
        self, conference, pretix_order_data
    ):
        order, created = upsert_order(conference, pretix_order_data)
        assert created and order.conference == conference and order.status == "p"
        assert AttendeeProfile.objects.filter(order=order).exists()
        changed = dict(
            pretix_order_data, status="c", last_modified="2025-12-01T00:00:00+00:00"
        )
        order, created = upsert_order(conference, changed)
        assert not created and order.status == "c"
        assert PretixOrder.objects.count() == 1


@pytest.mark.django_db
class TestWebhook:
    def url(self, conference, secret="hook-secret"):
        return (
            reverse("speakers:pretix_webhook", args=[conference.slug])
            + f"?secret={secret}"
        )

    def payload(self, **overrides):
        data = {
            "notification_id": 1,
            "organizer": "pyladiescon",
            "event": "2025",
            "code": "ORDER123",
            "action": "pretix.event.order.paid",
        }
        data.update(overrides)
        return json.dumps(data)

    @mock.patch("speakers.webhooks.PretixClient.get_order")
    def test_recorded_payload_upserts_and_ticks_item(
        self, get_order, client, conference, pretix_settings, pretix_order_data
    ):
        presenter = make_presenter(conference, email="attendee@example.com")
        item = ChecklistItem.objects.create(
            conference=conference,
            owner=ItemOwner.SPEAKER,
            title="Register",
            presenter=presenter,
            auto_complete_rule=AutoRule.PRETIX_REGISTERED,
        )
        get_order.return_value = pretix_order_data
        response = client.post(
            self.url(conference), self.payload(), content_type="application/json"
        )
        assert response.status_code == 200
        assert response.json() == {"order": "ORDER123", "status": "p"}
        get_order.assert_called_once_with("ORDER123")
        order = PretixOrder.objects.get(order_code="ORDER123")
        assert order.conference == conference and order.email == "attendee@example.com"
        item.refresh_from_db()
        assert item.status == ItemStatus.DONE

    def test_rejections(self, client, conference, pretix_settings):
        assert client.get(self.url(conference)).status_code == 405
        assert (
            client.post(
                self.url(conference, "wrong"),
                self.payload(),
                content_type="application/json",
            ).status_code
            == 401
        )
        assert (
            client.post(
                self.url(conference), "{not json", content_type="application/json"
            ).status_code
            == 400
        )
        assert (
            client.post(
                self.url(conference),
                self.payload(action="pretix.event.item.added"),
                content_type="application/json",
            ).status_code
            == 400
        )
        assert (
            client.post(
                self.url(conference),
                self.payload(code=""),
                content_type="application/json",
            ).status_code
            == 400
        )
        assert (
            client.post(
                self.url(conference),
                self.payload(event="other"),
                content_type="application/json",
            ).status_code
            == 400
        )
        assert (
            client.post(
                reverse("speakers:pretix_webhook", args=["nope"]) + "?secret=x",
                self.payload(),
                content_type="application/json",
            ).status_code
            == 404
        )

    def test_unconfigured_or_no_secret(self, client, conference):
        assert (
            client.post(
                self.url(conference), self.payload(), content_type="application/json"
            ).status_code
            == 404
        )
        make_settings(conference, pretix_organizer="o", pretix_api_token="t")
        assert (
            client.post(
                self.url(conference), self.payload(), content_type="application/json"
            ).status_code
            == 401
        )

    @mock.patch(
        "speakers.webhooks.PretixClient.get_order", side_effect=PretixError("down")
    )
    def test_pretix_unavailable(self, get_order, client, conference, pretix_settings):
        response = client.post(
            self.url(conference), self.payload(), content_type="application/json"
        )
        assert response.status_code == 502


@pytest.mark.django_db
class TestReconcile:
    def test_reconcile_uses_last_sync_and_advances_it(
        self, conference, pretix_settings
    ):
        client = mock.Mock()
        client.iter_orders.return_value = iter(
            [order_payload("A1", "a@example.com"), order_payload("B2", "b@example.com")]
        )
        assert reconcile(conference, client=client) == 2
        client.iter_orders.assert_called_once_with(modified_since=None)
        pretix_settings.refresh_from_db()
        assert pretix_settings.pretix_last_synced_at is not None
        assert PretixOrder.objects.filter(conference=conference).count() == 2
        assert (
            ActivityLog.objects.get(action="pretix.reconciled").message
            == "2 order(s) refreshed"
        )
        client.iter_orders.return_value = iter([])
        reconcile(conference, client=client)
        assert (
            client.iter_orders.call_args.kwargs["modified_since"]
            == pretix_settings.pretix_last_synced_at
        )

    @mock.patch("speakers.tasks.reconcile")
    def test_task_covers_configured_editions(
        self, reconcile_mock, conference, pretix_settings
    ):
        other = Conference.objects.create(year=2024, name="Skipped", slug="2024")
        make_settings(other)  # not configured: skipped
        failing = Conference.objects.create(
            year=2023, name="Older", slug="2023", pretix_event_slug="2023"
        )
        make_settings(failing, pretix_organizer="o", pretix_api_token="t")

        def fake(conf):
            if conf == failing:
                raise PretixError("down")
            return 3

        reconcile_mock.side_effect = fake
        result = pretix_reconcile_task()
        assert "PyLadiesCon 2025: 3 order(s)" in result
        assert "Older: failed (down)" in result
        assert "Skipped" not in result

    def test_task_with_nothing_configured(self, conference):
        assert pretix_reconcile_task() == "No edition has pretix configured"


@pytest.mark.django_db
class TestLookupAndLink:
    def test_lookup_records_orders(self, conference, pretix_settings):
        presenter = make_presenter(conference, email="ada@example.com")
        client = mock.Mock()
        client.iter_orders.return_value = iter([order_payload("X1", "ada@example.com")])
        orders = lookup_presenter_orders(presenter, client=client)
        assert [o.order_code for o in orders] == ["X1"]
        client.iter_orders.assert_called_once_with(email="ada@example.com")
        assert (
            ActivityLog.objects.get(action="pretix.lookup").message
            == "1 order(s) found for ada@example.com"
        )

    def test_lookup_unconfigured_returns_none(self, conference):
        assert lookup_presenter_orders(make_presenter(conference)) is None
        assert client_for(conference) is None

    def test_client_for_configured_edition(self, conference, pretix_settings):
        client = client_for(conference)
        assert isinstance(client, PretixClient)
        assert client.headers == {"Authorization": "Token tok-secret"}
        assert client.event == "2025"

    def test_link_local_or_fetched(self, conference, pretix_settings):
        presenter = make_presenter(conference, email="ada@example.com")
        item = ChecklistItem.objects.create(
            conference=conference,
            owner=ItemOwner.SPEAKER,
            title="Register",
            presenter=presenter,
            auto_complete_rule=AutoRule.PRETIX_REGISTERED,
        )
        upsert_order(conference, order_payload("LOCAL1", "other@example.com"))
        link_presenter_order(presenter, "LOCAL1")
        presenter.refresh_from_db()
        assert presenter.pretix_order.order_code == "LOCAL1"
        item.refresh_from_db()
        assert item.status == ItemStatus.DONE  # manual link wins over the mismatch
        client = mock.Mock()
        client.get_order.return_value = order_payload("REMOTE2", "third@example.com")
        link_presenter_order(presenter, "REMOTE2", client=client)
        presenter.refresh_from_db()
        assert presenter.pretix_order.order_code == "REMOTE2"

    def test_link_unknown_without_pretix(self, conference):
        with pytest.raises(PretixError, match="not configured"):
            link_presenter_order(make_presenter(conference), "NOPE")

    def test_voucher_stub(self, conference):
        presenter = make_presenter(conference)
        assert create_voucher(presenter) is None
        make_settings(conference, pretix_create_vouchers=True)
        with pytest.raises(NotImplementedError):
            create_voucher(presenter)

    def test_voucher_off_by_default(self, conference, pretix_settings):
        assert create_voucher(make_presenter(conference)) is None


@pytest.mark.django_db
class TestPresenterPageActions:
    def test_registration_card(self, client, organizer, conference, pretix_settings):
        presenter = make_presenter(conference, email="ada@example.com")
        upsert_order(conference, order_payload("SEEN1", "ADA@example.com"))
        client.force_login(organizer)
        content = client.get(presenter.get_absolute_url()).content.decode()
        assert "Orders under this email" in content and "SEEN1" in content
        assert "Look up in pretix" in content
        assert reverse("speakers:presenter_pretix_link", args=[presenter.pk]) in content

    @mock.patch("speakers.pretix.client_for")
    def test_lookup_view_messages(
        self, client_for, client, organizer, conference, pretix_settings
    ):
        presenter = make_presenter(conference, email="ada@example.com")
        fake = mock.Mock()
        client_for.return_value = fake
        client.force_login(organizer)
        url = reverse("speakers:presenter_pretix_lookup", args=[presenter.pk])
        fake.iter_orders.return_value = iter([order_payload("F1", "ada@example.com")])
        response = client.post(url, follow=True)
        assert "Found 1 order(s): F1" in response.content.decode()
        fake.iter_orders.return_value = iter([])
        assert "No pretix order under" in client.post(url, follow=True).content.decode()
        fake.iter_orders.side_effect = PretixError("down")
        assert "Pretix lookup failed" in client.post(url, follow=True).content.decode()
        client_for.return_value = None
        assert "not configured" in client.post(url, follow=True).content.decode()

    def test_link_and_unlink_views(
        self, client, organizer, conference, pretix_settings
    ):
        presenter = make_presenter(conference, email="ada@example.com")
        upsert_order(conference, order_payload("LOCAL1", "other@example.com"))
        client.force_login(organizer)
        url = reverse("speakers:presenter_pretix_link", args=[presenter.pk])
        response = client.post(url, {"order_code": " local1 "})
        assertRedirects(response, presenter.get_absolute_url())
        presenter.refresh_from_db()
        assert presenter.pretix_order.order_code == "LOCAL1"
        content = client.get(presenter.get_absolute_url()).content.decode()
        assert "Linked to order LOCAL1" in content and "Unlink" in content
        client.post(url, {"action": "unlink"})
        presenter.refresh_from_db()
        assert presenter.pretix_order is None
        assert (
            "Give the pretix order code"
            in client.post(url, {"order_code": ""}, follow=True).content.decode()
        )
        with mock.patch("speakers.pretix.client_for", return_value=None):
            response = client.post(url, {"order_code": "NOPE"}, follow=True)
        assert "Could not link order NOPE" in response.content.decode()

    def test_organizer_only(self, client, conference, pretix_settings):
        liaison = User.objects.create_user(username="lena")
        presenter = make_presenter(conference, liaison=liaison)
        client.force_login(liaison)
        assert (
            client.post(
                reverse("speakers:presenter_pretix_lookup", args=[presenter.pk])
            ).status_code
            == 403
        )
        assert (
            client.post(
                reverse("speakers:presenter_pretix_link", args=[presenter.pk])
            ).status_code
            == 403
        )
