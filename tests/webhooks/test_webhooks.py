import json
from unittest.mock import patch

import pytest
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from attendee.models import (
    PRETIX_ANONYMOUS_DONATION_QUESTION_IDENTIFIER,
    PRETIX_NOT_ANONYMOUS_ANSWER_IDENTIFIER,
    AttendeeProfile,
    PretixOrder,
    PretixOrderstatus,
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

    def test_pretix_webhook_creates_attendee_profile_for_paid_order(self):
        """Test that webhook creates AttendeeProfile for paid orders."""
        order_code = "PAID_ORDER_123"
        paid_order_data = {
            "code": order_code,
            "event": "2025",
            "status": "p",  # Paid status
            "testmode": False,
            "email": "attendee@example.com",
            "datetime": "2025-11-13T17:12:03.989259+01:00",
            "total": "50.00",
            "positions": [
                {
                    "attendee_name": "Example Attendee",
                    "answers": [
                        {
                            "answer": "Vancouver",
                            "question_identifier": "PMJY8XDM",
                        },
                        {
                            "answer": "United States",
                            "question_identifier": "LR7T8ARU",
                        },
                        {
                            "answer": "Networking, Learn new things, Support community activities",
                            "question_identifier": "ZMLKUBDP",
                        },
                        {
                            "answer": "Social Media, Other",
                            "question_identifier": "MHYVZZWR",
                        },
                        {
                            "answer": "No, this is my first one",
                            "question_identifier": "BFVYGGR7",
                        },
                        {
                            "answer": "San Francisco",
                            "question_identifier": "BBW9W7R8",
                        },
                        {
                            "answer": "19-25",
                            "question_identifier": "7LT7RP37",
                        },
                        {
                            "answer": "Umbrella Corp",
                            "question_identifier": "YFVMKV3Z",
                        },
                        {
                            "answer": "Student/Intern, Other",
                            "question_identifier": "AZRBXNA8",
                        },
                        {
                            "answer": "Junior",
                            "question_identifier": "RH8Y38TD",
                        },
                        {
                            "answer": "Yes, I'm interested",
                            "question_identifier": "9PTNRCKV",
                        },
                    ],
                }
            ],
            "last_modified": "2025-11-13T17:12:07.002602+01:00",
            "url": "https://someurl/",
            "cancellation_date": None,
        }

        payload = {
            "notification_id": 456,
            "organizer": PRETIX_ORG,
            "event": PRETIX_EVENT_SLUG,
            "code": order_code,
            "action": "pretix.event.order.paid",
        }

        with patch(
            "common.pretix_wrapper.PretixWrapper.get_order_by_code"
        ) as mock_get_order:
            mock_get_order.return_value = paid_order_data
            response = self.client.post(
                f"{self.url}",
                query_params={"secret": "supersecret"},
                data=json.dumps(payload),
                content_type="application/json",
            )
            assert response.status_code == 200

            # Verify order was created
            order = PretixOrder.objects.get(order_code=order_code)
            assert order.status == PretixOrderstatus.PAID

            # Verify attendee profile was created
            assert AttendeeProfile.objects.filter(order=order).exists()
            profile = AttendeeProfile.objects.get(order=order)
            assert profile.city == "Vancouver"
            assert profile.country == "United States"
            assert profile.may_share_email_with_sponsor is True
            assert profile.experience_level == "Junior"
            assert profile.expectation_from_event == [
                "Networking",
                "Learn new things",
                "Support community activities",
            ]
            assert profile.heard_about == ["Social Media", "Other"]
            assert profile.participated_in_previous_event == ["No this is my first one"]
            assert profile.pyladies_chapter == "San Francisco"
            assert profile.age_range == "19-25"
            assert profile.organization_name == "Umbrella Corp"
            assert profile.current_position == ["Student/Intern", "Other"]

    def test_pretix_webhook_does_not_create_profile_for_cancelled_order(self):
        """Test that webhook does not create AttendeeProfile for cancelled orders."""
        order_code = "CANCELLED_ORDER_123"
        cancelled_order_data = {
            "code": order_code,
            "event": "2025",
            "status": "c",  # Cancelled status
            "testmode": False,
            "email": "cancelled@example.com",
            "datetime": "2025-11-13T17:12:03.989259+01:00",
            "total": "50.00",
            "positions": [
                {
                    "attendee_name": "Cancelled User",
                    "answers": [
                        {"question_identifier": "ROLE", "answer": "Data Scientist"},
                    ],
                }
            ],
            "last_modified": "2025-11-13T17:12:07.002602+01:00",
            "url": "https://someurl/",
            "cancellation_date": "2025-11-14T10:00:00.000000+01:00",
        }

        payload = {
            "notification_id": 789,
            "organizer": PRETIX_ORG,
            "event": PRETIX_EVENT_SLUG,
            "code": order_code,
            "action": PRETIX_WEBHOOK_ORDER_CANCELLED,
        }

        with patch(
            "common.pretix_wrapper.PretixWrapper.get_order_by_code"
        ) as mock_get_order:
            mock_get_order.return_value = cancelled_order_data
            response = self.client.post(
                f"{self.url}",
                query_params={"secret": "supersecret"},
                data=json.dumps(payload),
                content_type="application/json",
            )
            assert response.status_code == 200

            # Verify order was created
            order = PretixOrder.objects.get(order_code=order_code)
            assert order.status == PretixOrderstatus.CANCELLED

            # Verify attendee profile was NOT created for cancelled order
            assert not AttendeeProfile.objects.filter(order=order).exists()
