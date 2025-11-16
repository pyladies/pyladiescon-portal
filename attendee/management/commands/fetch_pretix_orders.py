"""
Management command to fetch orders from Pretix and collect Attendee data.
"""

from django.core.management.base import BaseCommand

from attendee.models import PretixOrder
from common.pretix_wrapper import PRETIX_EVENT_SLUG, PRETIX_ORG, PretixWrapper


class Command(BaseCommand):
    help = "Fetch Pretix orders"

    def handle(self, *args, **options):
        pretix_wrapper = PretixWrapper(PRETIX_ORG, PRETIX_EVENT_SLUG)
        for order in pretix_wrapper.get_orders():
            order_code = order["code"]
            pretix_order, created = PretixOrder.objects.get_or_create(
                order_code=order_code
            )
            pretix_order.from_pretix_data(order)
            pretix_order.save()
