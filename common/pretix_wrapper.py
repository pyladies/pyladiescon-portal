import requests
from django.conf import settings

from portal.constants import BASE_PRETIX_URL

statuses = []

PRETIX_CANCELLED_STATUS = "c"
PRETIX_PAID_STATUS = "p"

PRETIX_WEBHOOK_ORDER_PAID = "pretix.event.order.paid"
PRETIX_WEBHOOK_ORDER_CANCELLED = "pretix.event.order.canceled"

PRETIX_ALLOWED_WEBHOOK_ACTIONS = [
    PRETIX_WEBHOOK_ORDER_PAID,
    PRETIX_WEBHOOK_ORDER_CANCELLED,
]
PRETIX_ORG = "pyladiescon"
PRETIX_EVENT_SLUG = "2025"


class PretixWrapper:
    def __init__(self, org, event_slug):
        token = settings.PRETIX_API_TOKEN
        if not token:
            raise ValueError("PRETIX_API_TOKEN not set")
        self.headers = {"Authorization": f"Token {settings.PRETIX_API_TOKEN}"}
        self.org = org
        self.event_slug = event_slug

    def get_orders(self):
        """Get all orders from pretix for the given event.

        We only want to care about non-testmode orders, fully paid orders, and canceled orders.
        If we found fully-paid orders: record the values to add to our stats.
        If we found cancelled orders: lookup the order and mark it as cancelled so that we can exclude from stats.
        """
        params = {}
        has_next = True
        url = (
            BASE_PRETIX_URL + f"organizers/{self.org}/events/{self.event_slug}/orders/"
        )
        index = 0

        while has_next:
            response = requests.get(url, headers=self.headers, params=params)
            url = response.json()["next"]
            has_next = url is not None
            for r in response.json()["results"]:
                index += 1
                if r["testmode"] is False:
                    if r["status"] in [PRETIX_PAID_STATUS, PRETIX_CANCELLED_STATUS]:
                        yield r

    def get_order_by_code(self, order_code):
        """Get a single order by its code."""
        url = (
            BASE_PRETIX_URL
            + f"organizers/{self.org}/events/{self.event_slug}/orders/{order_code}/"
        )
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(
                f"Failed to get order {order_code}: {response.status_code} {response.text}"
            )
