from unittest.mock import Mock, patch

import pytest
import requests
from django.test import TestCase, override_settings

from attendee.models import (
    PRETIX_ANONYMOUS_DONATION_QUESTION_IDENTIFIER,
    PRETIX_NOT_ANONYMOUS_ANSWER_IDENTIFIER,
)
from common.pretix_wrapper import PretixWrapper


@override_settings(
    PRETIX_API_TOKEN=None,
)
def test_pretix_wrapper_error_if_api_token_not_set():
    with pytest.raises(ValueError):
        PretixWrapper("test_org", "test_event")


@pytest.mark.django_db
@override_settings(
    PRETIX_API_TOKEN="test_token",
)
class TestPretixWrapper(TestCase):

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
        self.wrapper = PretixWrapper("test_org", "test_event")
        self.order_code = "ORDER123"

    def test_pretix_wrapper_initialization(self):
        """Test PretixWrapper initialization with valid settings."""
        assert self.wrapper.org == "test_org"
        assert self.wrapper.event_slug == "test_event"
        assert self.wrapper.headers == {"Authorization": "Token test_token"}

    def test_get_order_by_code(self):
        """Test get_order_by_code method."""
        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = self._pretix_order_data
            mock_get.return_value = mock_response
            order_result = self.wrapper.get_order_by_code(self.order_code)

            assert order_result == self._pretix_order_data

    def test_get_order_by_code_error_handling(self):
        """Test get_order_by_code method error handling."""
        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
                "404 Not Found"
            )
            mock_get.return_value = mock_response
            with self.assertRaises(Exception):
                self.wrapper.get_order_by_code(self.order_code)

    def test_get_orders(self):
        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "count": 1,
                "next": None,
                "previous": None,
                "results": [self._pretix_order_data],
            }
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
                "404 Not Found"
            )
            mock_get.return_value = mock_response
            orders = self.wrapper.get_orders()
            for order in orders:
                assert order == self._pretix_order_data
