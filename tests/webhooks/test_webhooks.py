import json
from unittest.mock import patch

import pytest
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from attendee.models import (
    PRETIX_ANONYMOUS_DONATION_QUESTION_IDENTIFIER,
    PRETIX_NOT_ANONYMOUS_ANSWER_IDENTIFIER,
    PretixOrder,
)
from common.pretix_wrapper import (
    PRETIX_EVENT_SLUG,
    PRETIX_ORG,
    PRETIX_WEBHOOK_ORDER_CANCELLED,
)


@pytest.mark.django_db
@override_settings(PRETIX_WEBHOOK_SECRET="supersecret")
@override_settings(PRETIX_API_TOKEN="test_token")
class TestPretixWebhook(TestCase):
    @pytest.fixture(autouse=True)
    def pretix_order_data(self):
        self._pretix_order_data = {
            "code": "ORDER123",
            "event": "2025",
            "status": "p",
            "testmode": False,
            "email": "attendee@example.com",
            "datetime": "2025-11-13T17:12:03.989259+01:00",
            "total": "30.00",
            "positions": [
                {
                    "attendee_name": "Example Attendee",
                    "answers": [
                        {
                            "question_identifier": "QUESTION123",
                            "option_identifiers": [],
                        },
                        {
                            "option_identifiers": [
                                PRETIX_NOT_ANONYMOUS_ANSWER_IDENTIFIER
                            ],
                            "question_identifier": PRETIX_ANONYMOUS_DONATION_QUESTION_IDENTIFIER,
                        },
                    ],
                }
            ],
            "last_modified": "2025-11-13T17:12:07.002602+01:00",
            "url": "https://someurl/",
            "cancellation_date": None,
        }

    def setUp(self):
        self.client = Client()
        self.url = reverse("webhooks:pretix_webhook")

    def test_pretix_webhook_endpoint_require_post(self):
        response = self.client.get(self.url, query_params={"secret": "supersecret"})
        assert response.status_code == 405

    def test_pretix_webhook_endpoint_missing_query_parameter(self):
        response = self.client.post(self.url)
        assert response.status_code == 400
        assert "Missing required query parameter" in str(response.content)

    def test_pretix_webhook_endpoint_invalid_secret(self):
        response = self.client.post(self.url, query_params={"secret": "invalid"})
        assert response.status_code == 401
        assert "Unauthorized" in str(response.content)

    def test_pretix_webhook_endpoint_invalid_payload(self):
        # wrong action
        payload = {
            "notification_id": 123,
            "organizer": PRETIX_ORG,
            "event": PRETIX_EVENT_SLUG,
            "code": "ABC123",
            "action": "pretix.event.order.wrongaction",
        }
        response = self.client.post(
            f"{self.url}",
            query_params={"secret": "supersecret"},
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 400
        assert response.content == b"Unsupported pretix action"

        # wrong organizer
        payload = {
            "notification_id": 123,
            "organizer": "wrong_org",
            "event": PRETIX_EVENT_SLUG,
            "code": "ABC123",
            "action": PRETIX_WEBHOOK_ORDER_CANCELLED,
        }
        response = self.client.post(
            f"{self.url}",
            query_params={"secret": "supersecret"},
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 400
        assert response.content == b"Invalid organizer"

        # wrong event slug
        payload = {
            "notification_id": 123,
            "organizer": PRETIX_ORG,
            "event": "wrong event",
            "code": "ABC123",
            "action": PRETIX_WEBHOOK_ORDER_CANCELLED,
        }
        response = self.client.post(
            f"{self.url}",
            query_params={"secret": "supersecret"},
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 400
        assert response.content == b"Invalid event slug"

        # missing keys
        payload = {"notification_id": 123}
        response = self.client.post(
            f"{self.url}",
            query_params={"secret": "supersecret"},
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 400
        assert response.content == b"Invalid pretix payload structure"

    def test_pretix_webhook_endpoint_order_created_if_not_found(self):
        order_code = self._pretix_order_data["code"]
        assert PretixOrder.objects.filter(order_code=order_code).exists() is False
        payload = {
            "notification_id": 123,
            "organizer": PRETIX_ORG,
            "event": PRETIX_EVENT_SLUG,
            "code": order_code,
            "action": PRETIX_WEBHOOK_ORDER_CANCELLED,
        }
        with patch(
            "common.pretix_wrapper.PretixWrapper.get_order_by_code"
        ) as mock_get_order:
            mock_get_order.return_value = self._pretix_order_data
            response = self.client.post(
                f"{self.url}",
                query_params={"secret": "supersecret"},
                data=json.dumps(payload),
                content_type="application/json",
            )
            assert response.status_code == 200
            assert mock_get_order.call_count == 1

            assert PretixOrder.objects.filter(order_code=order_code).exists() is True
            order = PretixOrder.objects.get(order_code=order_code)
            assert order.order_code == order_code
            assert order.status == self._pretix_order_data["status"]
            assert order.email == self._pretix_order_data["email"]
            assert order.total == float(self._pretix_order_data["total"])
            assert order.url == self._pretix_order_data["url"]
            assert order.raw_data == self._pretix_order_data

    def test_pretix_webhook_endpoint_order_updated_if_exists(self):
        order_code = self._pretix_order_data["code"]
        order = PretixOrder.objects.create(order_code=order_code)
        assert order.email is None
        assert order.status is None
        assert order.total == 0
        assert order.raw_data is None

        payload = {
            "notification_id": 123,
            "organizer": PRETIX_ORG,
            "event": PRETIX_EVENT_SLUG,
            "code": order_code,
            "action": PRETIX_WEBHOOK_ORDER_CANCELLED,
        }
        with patch(
            "common.pretix_wrapper.PretixWrapper.get_order_by_code"
        ) as mock_get_order:
            mock_get_order.return_value = self._pretix_order_data
            response = self.client.post(
                f"{self.url}",
                query_params={"secret": "supersecret"},
                data=json.dumps(payload),
                content_type="application/json",
            )
            assert response.status_code == 200
            assert mock_get_order.call_count == 1

            order.refresh_from_db()
            assert order.order_code == order_code
            assert order.status == self._pretix_order_data["status"]
            assert order.email == self._pretix_order_data["email"]
            assert order.total == float(self._pretix_order_data["total"])
            assert order.url == self._pretix_order_data["url"]
            assert order.raw_data == self._pretix_order_data
