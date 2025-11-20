"""
Management command to fetch orders from Pretix and collect Attendee data.
"""

from django.core.management.base import BaseCommand

from attendee.models import AttendeeProfile, PretixOrder
from common.pretix_wrapper import PRETIX_EVENT_SLUG, PRETIX_ORG, PretixWrapper


class Command(BaseCommand):
    help = "Fetch Pretix orders and sync attendee demographics"

    def handle(self, *args, **options):
        pretix_wrapper = PretixWrapper(PRETIX_ORG, PRETIX_EVENT_SLUG)
        orders_synced = 0
        profiles_synced = 0

        for order in pretix_wrapper.get_orders():
            order_code = order["code"]
            pretix_order, created = PretixOrder.objects.get_or_create(
                order_code=order_code
            )
            pretix_order.from_pretix_data(order)
            pretix_order.save()
            orders_synced += 1

            # Sync attendee profile for paid orders
            if pretix_order.status == "p":
                profile, profile_created = AttendeeProfile.objects.get_or_create(
                    order=pretix_order
                )
                profile.populate_from_pretix_data(order)
                profile.save()
                profiles_synced += 1

                if profile_created:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Created attendee profile for order {order_code}"
                        )
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully synced {orders_synced} orders and {profiles_synced} attendee profiles"
            )
        )
