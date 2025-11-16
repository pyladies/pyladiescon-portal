from enum import StrEnum

from django.db import models

from portal.models import BaseModel


class PretixOrderstatus(StrEnum):
    """Order status from Pretix.

    We only care about the ones canceled or paid.
    """

    CANCELLED = "c"
    PAID = "p"


PRETIX_ORDER_STATUS_CHOICES = [
    (PretixOrderstatus.CANCELLED, "Cancelled"),
    (PretixOrderstatus.PAID, "Paid"),
]

PRETIX_ANONYMOUS_DONATION_QUESTION_IDENTIFIER = "RU3GSQ7Y"
PRETIX_STAY_ANONYMOUS_ANSWER_IDENTIFIER = "JPVJMTFG"
PRETIX_NOT_ANONYMOUS_ANSWER_IDENTIFIER = "YR8TYFQ7"


class PretixOrder(BaseModel):
    order_code = models.CharField(max_length=100, unique=True)
    status = models.CharField(
        max_length=50, choices=PRETIX_ORDER_STATUS_CHOICES, null=True
    )
    email = models.EmailField(null=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    total = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, default=0
    )
    cancellation_date = models.DateTimeField(null=True, blank=True)
    datetime = models.DateTimeField(null=True, blank=True)
    last_modified = models.DateTimeField(null=True, blank=True)
    url = models.URLField(null=True, blank=True)
    is_anonymous = models.BooleanField(default=True, null=True, blank=True)
    event_slug = models.CharField(max_length=100, null=True)
    raw_data = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.order_code

    def from_pretix_data(self, data):
        """Populate the PretixOrder instance from pretix order data."""
        if self.last_modified != data["last_modified"]:
            # update only if there are changes
            self.status = data["status"]
            self.email = data.get("email", "")
            self.total = data.get("total", 0.0)
            self.cancellation_date = data.get("cancellation_date", None)
            self.url = data.get("url", "")
            self.datetime = data.get("datetime", None)
            self.last_modified = data.get("last_modified", None)
            self.event_slug = data["event"]
            self.set_name_from_data(data)
            self.set_is_anonymous_from_data(data)
            self.raw_data = data
        return self

    def set_name_from_data(self, data):
        """Set the name field from pretix order data."""
        for pos in data["positions"]:
            if pos["attendee_name"]:
                self.name = pos["attendee_name"]
                return

    def set_is_anonymous_from_data(self, data):
        """Set the is_anonymous field from pretix order data."""
        for pos in data["positions"]:
            for answer in pos["answers"]:
                if (
                    answer["question_identifier"]
                    == PRETIX_ANONYMOUS_DONATION_QUESTION_IDENTIFIER
                ):
                    self.is_anonymous = (
                        PRETIX_STAY_ANONYMOUS_ANSWER_IDENTIFIER
                        in answer["option_identifiers"]
                    )
                    return
