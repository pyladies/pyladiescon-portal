from enum import StrEnum

from django.db import models

from portal.models import BaseModel, ChoiceArrayField


class PretixOrderstatus(StrEnum):
    """Order status from Pretix.

    We only care about the ones canceled or paid.
    """

    CANCELLED = "c"
    PAID = "p"


EXPECTATION_FROM_EVENTS_CHOICES = [
    (
        "Learn new things",
        "Learn new things",
    ),
    ("Networking", "Networking"),
    ("Support community activities", "Support community activities"),
    ("Share Knowledge", "Share Knowledge"),
    ("Other", "Other"),
]
HEARD_ABOUT_CHOICES = [
    ("Social Media", "Social Media"),
    ("Other", "Other"),
    ("Conferences", "Conferences"),
    ("Local meetups", "Local meetups"),
]
PARTICIPATED_IN_PREVIOUS_EVENT_CHOICES = [
    ("PyLadiesCon 2024", "PyLadiesCon 2024"),
    ("PyLadiesCon 2023", "PyLadiesCon 2023"),
    ("No this is my first one", "No this is my first one"),
]
CURRENT_POSITION_CHOICES = [
    ("Engineer", "Engineer"),
    ("Student/Intern", "Student/Intern"),
    ("Other", "Other"),
    ("Scientist", "Scientist"),
    ("Engineering/Scientist Manager", "Engineering/Scientist Manager"),
    ("Product Owner/Manager", "Product Owner/Manager"),
    ("Hobbyist", "Hobbyist"),
    ("I'm currently retired", "I'm currently retired"),
    ("", ""),
]

PRETIX_ORDER_STATUS_CHOICES = [
    (PretixOrderstatus.CANCELLED, "Cancelled"),
    (PretixOrderstatus.PAID, "Paid"),
]

# Donations questions
PRETIX_ANONYMOUS_DONATION_QUESTION_IDENTIFIER = "RU3GSQ7Y"
PRETIX_STAY_ANONYMOUS_ANSWER_IDENTIFIER = "JPVJMTFG"
PRETIX_NOT_ANONYMOUS_ANSWER_IDENTIFIER = "YR8TYFQ7"

# Demographic questions
PRETIX_ATTENDEE_CITY_QUESTION_IDENTIFIER = "PMJY8XDM"
PRETIX_ATTENDEE_COUNTRY_QUESTION_IDENTIFIER = "LR7T8ARU"
PRETIX_ATTENDEE_CURRENT_POSITION_QUESTION_IDENTIFIER = "AZRBXNA8"
PRETIX_ATTENDEE_EXPERIENCE_LEVEL_QUESTION_IDENTIFIER = "RH8Y38TD"
PRETIX_ATTENDEE_MAY_SHARE_EMAIL_WITH_SPONSOR_QUESTION_IDENTIFIER = "9PTNRCKV"
PRETIX_ATTENDEE_EXPECTATION_FROM_EVENT_QUESTION_IDENTIFIER = "ZMLKUBDP"
PRETIX_ATTENDEE_HEARD_ABOUT_EVENT_QUESTION_IDENTIFIER = "MHYVZZWR"
PRETIX_ATTENDEE_PARTICIPATED_IN_PREVIOUS_EVENT_QUESTION_IDENTIFIER = "BFVYGGR7"
PRETIX_ATTENDEE_PYLADIES_CHAPTER_QUESTION_IDENTIFIER = "BBW9W7R8"
PRETIX_ATTENDEE_AGE_RANGE_QUESTION_IDENTIFIER = "7LT7RP37"
PRETIX_ATTENDEE_ORGANIZATION_NAME_QUESTION_IDENTIFIER = "YFVMKV3Z"

PRETIX_ATTENDEE_QUESTIONS = [
    PRETIX_ATTENDEE_CITY_QUESTION_IDENTIFIER,
    PRETIX_ATTENDEE_COUNTRY_QUESTION_IDENTIFIER,
    PRETIX_ATTENDEE_EXPERIENCE_LEVEL_QUESTION_IDENTIFIER,
    PRETIX_ATTENDEE_MAY_SHARE_EMAIL_WITH_SPONSOR_QUESTION_IDENTIFIER,
    PRETIX_ATTENDEE_EXPECTATION_FROM_EVENT_QUESTION_IDENTIFIER,
    PRETIX_ATTENDEE_HEARD_ABOUT_EVENT_QUESTION_IDENTIFIER,
    PRETIX_ATTENDEE_PARTICIPATED_IN_PREVIOUS_EVENT_QUESTION_IDENTIFIER,
    PRETIX_ATTENDEE_PYLADIES_CHAPTER_QUESTION_IDENTIFIER,
    PRETIX_ATTENDEE_AGE_RANGE_QUESTION_IDENTIFIER,
    PRETIX_ATTENDEE_ORGANIZATION_NAME_QUESTION_IDENTIFIER,
    PRETIX_ATTENDEE_CURRENT_POSITION_QUESTION_IDENTIFIER,
]

# maps the pretix question identifiers to AttendeeProfile model fields
ATTENDEE_FIELD_MAPPING = {
    PRETIX_ATTENDEE_ORGANIZATION_NAME_QUESTION_IDENTIFIER: "organization_name",
    PRETIX_ATTENDEE_AGE_RANGE_QUESTION_IDENTIFIER: "age_range",
    PRETIX_ATTENDEE_PYLADIES_CHAPTER_QUESTION_IDENTIFIER: "pyladies_chapter",
    PRETIX_ATTENDEE_PARTICIPATED_IN_PREVIOUS_EVENT_QUESTION_IDENTIFIER: "participated_in_previous_event",
    PRETIX_ATTENDEE_HEARD_ABOUT_EVENT_QUESTION_IDENTIFIER: "heard_about",
    PRETIX_ATTENDEE_EXPECTATION_FROM_EVENT_QUESTION_IDENTIFIER: "expectation_from_event",
    PRETIX_ATTENDEE_MAY_SHARE_EMAIL_WITH_SPONSOR_QUESTION_IDENTIFIER: "may_share_email_with_sponsor",
    PRETIX_ATTENDEE_EXPERIENCE_LEVEL_QUESTION_IDENTIFIER: "experience_level",
    PRETIX_ATTENDEE_COUNTRY_QUESTION_IDENTIFIER: "country",
    PRETIX_ATTENDEE_CITY_QUESTION_IDENTIFIER: "city",
    PRETIX_ATTENDEE_CURRENT_POSITION_QUESTION_IDENTIFIER: "current_position",
}


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
    current_position = ChoiceArrayField(
        base_field=models.CharField(
            null=True,
            blank=True,
            help_text="Current Position",
            choices=CURRENT_POSITION_CHOICES,
        ),
        default=list,
    )
    country = models.CharField(
        max_length=100, null=True, blank=True, help_text="Current Country"
    )
    city = models.CharField(
        max_length=100, null=True, blank=True, help_text="Current City"
    )
    experience_level = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Python/programming experience level",
    )
    may_share_email_with_sponsor = models.BooleanField(
        null=True,
        blank=True,
        help_text="Permission to share email with sponsors",
    )
    expectation_from_event = ChoiceArrayField(
        base_field=models.CharField(
            null=True,
            blank=True,
            help_text="Expectations from the event",
            choices=EXPECTATION_FROM_EVENTS_CHOICES,
        ),
        default=list,
    )

    heard_about = ChoiceArrayField(
        base_field=models.CharField(
            max_length=255,
            null=True,
            blank=True,
            help_text="How did you hear about the event?",
            choices=HEARD_ABOUT_CHOICES,
        ),
        default=list,
    )
    participated_in_previous_event = ChoiceArrayField(
        base_field=models.CharField(
            null=True,
            blank=True,
            help_text="Have you participated in a previous event?",
            choices=PARTICIPATED_IN_PREVIOUS_EVENT_CHOICES,
        ),
        default=list,
    )
    pyladies_chapter = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Your PyLadies chapter",
    )
    age_range = models.CharField(
        max_length=100, null=True, blank=True, help_text="Age range"
    )
    organization_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Organization you work for",
    )

    # Store raw answers from pretix in case we need additional data
    raw_answers = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = "Attendee Profile"
        verbose_name_plural = "Attendee Profiles"

    def __str__(self):
        return f"Profile for {self.order.order_code}"

    def from_pretix_data(self, pretix_data):
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
            has_pyladies_chapter = False
            for answer in answers:
                question_id = answer.get("question_identifier")
                answer_value = answer.get("answer")

                if question_id in ATTENDEE_FIELD_MAPPING:
                    field_name = ATTENDEE_FIELD_MAPPING[question_id]
                    field = AttendeeProfile._meta.get_field(field_name)
                    field_type = field.get_internal_type()
                    match field_type:
                        case "BooleanField":
                            setattr(self, field_name, "yes" in answer_value.lower())
                        case "ChoiceArrayField":
                            # remove extra comma in the specific case of participated_in_previous_event
                            answer_value = answer_value.replace(
                                "No, this is my first one", "No this is my first one"
                            )
                            answers = [
                                answer.strip() for answer in answer_value.split(",")
                            ]
                            setattr(self, field_name, answers)

                        case _:
                            # treat as CharField/Freetext field by default
                            if answer_value.lower() == "none":
                                setattr(self, field_name, None)
                            else:
                                setattr(self, field_name, answer_value)

                    if field_name == "pyladies_chapter":
                        has_pyladies_chapter = True
            if not has_pyladies_chapter:
                setattr(self, "pyladies_chapter", None)
        self.raw_answers = all_answers
        return self
