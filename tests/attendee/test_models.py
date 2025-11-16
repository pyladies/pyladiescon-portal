import pytest

from attendee.models import (
    PRETIX_STAY_ANONYMOUS_ANSWER_IDENTIFIER,
    PretixOrder,
)


@pytest.mark.django_db
class TestPretixOrderModel:

    def test_pretix_order_str_representation(self):
        """Test string representation of PretixOrder."""
        order = PretixOrder(order_code="ORDER123")
        assert str(order) == order.order_code

    def test_set_name_from_data(self, pretix_order_data):
        """Test populating PretixOrder name from pretix data."""
        order = PretixOrder(order_code="ORDER123")
        order.set_name_from_data(pretix_order_data)
        assert order.name == "Example Attendee"

    def test_anonymous_from_data(self, pretix_order_data):
        """Test populating PretixOrder name from pretix data."""
        order = PretixOrder(order_code="ORDER123")
        order.set_is_anonymous_from_data(pretix_order_data)
        assert order.is_anonymous is False

        pretix_order_data["positions"][0]["answers"][1]["option_identifiers"] = [
            PRETIX_STAY_ANONYMOUS_ANSWER_IDENTIFIER
        ]
        order.set_is_anonymous_from_data(pretix_order_data)
        assert order.is_anonymous is True

    def test_set_data_from_pretix(self, pretix_order_data):
        """Test populating PretixOrder from pretix data."""
        order = PretixOrder(order_code=pretix_order_data["code"])
        order.from_pretix_data(pretix_order_data)
        assert order.status == pretix_order_data["status"]
        assert order.email == pretix_order_data["email"]
        assert order.total == pretix_order_data["total"]
        assert order.cancellation_date == pretix_order_data["cancellation_date"]
        assert order.url == pretix_order_data["url"]
        assert order.datetime == pretix_order_data["datetime"]
        assert order.last_modified == pretix_order_data["last_modified"]
        assert order.event_slug == pretix_order_data["event"]
        assert order.name == "Example Attendee"
        assert order.is_anonymous is False
        assert order.raw_data == pretix_order_data
