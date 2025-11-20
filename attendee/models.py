from enum import StrEnum

from django.contrib.postgres.fields import ArrayField
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


class AttendeeProfile(BaseModel):
    """
    Model to store anonymized attendee demographic data.
    This data is collected from pretix registration forms.
    """

    order = models.OneToOneField(
        PretixOrder, on_delete=models.CASCADE, related_name="profile"
    )

    # Demographics - all fields are nullable as responses are optional
    job_role = models.CharField(
        max_length=255, null=True, blank=True, help_text="Professional role/occupation"
    )
    job_title = models.CharField(max_length=255, null=True, blank=True)
    country = models.CharField(
        max_length=100, null=True, blank=True, help_text="Country of residence"
    )
    region = models.CharField(
        max_length=100, null=True, blank=True, help_text="Geographic region"
    )
    experience_level = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Python/programming experience level",
    )
    languages = ArrayField(
        models.CharField(max_length=50),
        null=True,
        blank=True,
        help_text="Spoken languages",
    )
    industry = models.CharField(max_length=255, null=True, blank=True)
    company_size = models.CharField(max_length=100, null=True, blank=True)
    heard_about = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="How they heard about PyLadiesCon",
    )

    # Store raw answers from pretix in case we need additional data
    raw_answers = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = "Attendee Profile"
        verbose_name_plural = "Attendee Profiles"

    def __str__(self):
        return f"Profile for {self.order.order_code}"

    def populate_from_pretix_data(self, pretix_data):
        """
        Extract attendee demographic data from pretix order data.
        This method maps pretix question identifiers to model fields.
        """
        # Store all answers for reference
        all_answers = []

        for position in pretix_data.get("positions", []):
            answers = position.get("answers", [])
            all_answers.extend(answers)

            # Map pretix question identifiers to our fields
            # These identifiers should be configured based on the actual pretix form
            for answer in answers:
                question_id = answer.get("question_identifier")
                answer_value = answer.get("answer")

                # Map based on question identifiers (these are examples and should be updated)
                if question_id == "ROLE":
                    self.job_role = answer_value
                elif question_id == "JOB_TITLE":
                    self.job_title = answer_value
                elif question_id == "COUNTRY":
                    self.country = answer_value
                elif question_id == "REGION":
                    self.region = answer_value
                elif question_id == "EXPERIENCE":
                    self.experience_level = answer_value
                elif question_id == "LANGUAGES":
                    # Handle multi-select language field
                    if answer_value:
                        self.languages = [
                            lang.strip() for lang in answer_value.split(",")
                        ]
                elif question_id == "INDUSTRY":
                    self.industry = answer_value
                elif question_id == "COMPANY_SIZE":
                    self.company_size = answer_value
                elif question_id == "HEARD_ABOUT":
                    self.heard_about = answer_value

        self.raw_answers = all_answers
        return self
