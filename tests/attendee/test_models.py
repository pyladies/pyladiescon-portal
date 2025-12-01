import pytest

from attendee.models import (
    PRETIX_ATTENDEE_AGE_RANGE_QUESTION_IDENTIFIER,
    PRETIX_ATTENDEE_CITY_QUESTION_IDENTIFIER,
    PRETIX_ATTENDEE_COUNTRY_QUESTION_IDENTIFIER,
    PRETIX_ATTENDEE_CURRENT_POSITION_QUESTION_IDENTIFIER,
    PRETIX_ATTENDEE_EXPECTATION_FROM_EVENT_QUESTION_IDENTIFIER,
    PRETIX_ATTENDEE_EXPERIENCE_LEVEL_QUESTION_IDENTIFIER,
    PRETIX_ATTENDEE_HEARD_ABOUT_EVENT_QUESTION_IDENTIFIER,
    PRETIX_ATTENDEE_MAY_SHARE_EMAIL_WITH_SPONSOR_QUESTION_IDENTIFIER,
    PRETIX_ATTENDEE_ORGANIZATION_NAME_QUESTION_IDENTIFIER,
    PRETIX_ATTENDEE_PARTICIPATED_IN_PREVIOUS_EVENT_QUESTION_IDENTIFIER,
    PRETIX_ATTENDEE_PYLADIES_CHAPTER_QUESTION_IDENTIFIER,
    PRETIX_STAY_ANONYMOUS_ANSWER_IDENTIFIER,
    AttendeeProfile,
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


@pytest.mark.django_db
class TestAttendeeProfileModel:

    def test_attendee_profile_str_representation(self):
        """Test string representation of AttendeeProfile."""
        order = PretixOrder.objects.create(order_code="ORDER123")
        profile = AttendeeProfile(order=order)
        assert str(profile) == "Profile for ORDER123"

    def test_populate_from_pretix_data(self):
        """Test populating AttendeeProfile from pretix data."""
        order = PretixOrder.objects.create(order_code="ORDER123")
        profile = AttendeeProfile(order=order)

        # Create sample pretix data with demographic answers
        pretix_data = {
            "code": "ORDER123",
            "positions": [
                {
                    "answers": [
                        {
                            "answer": "Vancouver",
                            "question_identifier": PRETIX_ATTENDEE_CITY_QUESTION_IDENTIFIER,
                        },
                        {
                            "answer": "United States",
                            "question_identifier": PRETIX_ATTENDEE_COUNTRY_QUESTION_IDENTIFIER,
                        },
                        {
                            "answer": "Networking, Learn new things, Support community activities",
                            "question_identifier": PRETIX_ATTENDEE_EXPECTATION_FROM_EVENT_QUESTION_IDENTIFIER,
                        },
                        {
                            "answer": "Social Media, Other",
                            "question_identifier": PRETIX_ATTENDEE_HEARD_ABOUT_EVENT_QUESTION_IDENTIFIER,
                        },
                        {
                            "answer": "No, this is my first one",
                            "question_identifier": PRETIX_ATTENDEE_PARTICIPATED_IN_PREVIOUS_EVENT_QUESTION_IDENTIFIER,
                        },
                        {
                            "answer": "San Francisco",
                            "question_identifier": PRETIX_ATTENDEE_PYLADIES_CHAPTER_QUESTION_IDENTIFIER,
                        },
                        {
                            "answer": "19-25",
                            "question_identifier": PRETIX_ATTENDEE_AGE_RANGE_QUESTION_IDENTIFIER,
                        },
                        {
                            "answer": "Umbrella Corp",
                            "question_identifier": PRETIX_ATTENDEE_ORGANIZATION_NAME_QUESTION_IDENTIFIER,
                        },
                        {
                            "answer": "Student/Intern, Other",
                            "question_identifier": PRETIX_ATTENDEE_CURRENT_POSITION_QUESTION_IDENTIFIER,
                        },
                        {
                            "answer": "Junior",
                            "question_identifier": PRETIX_ATTENDEE_EXPERIENCE_LEVEL_QUESTION_IDENTIFIER,
                        },
                        {
                            "answer": "Yes, I'm interested",
                            "question_identifier": PRETIX_ATTENDEE_MAY_SHARE_EMAIL_WITH_SPONSOR_QUESTION_IDENTIFIER,
                        },
                    ],
                }
            ],
        }

        profile.from_pretix_data(pretix_data)

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
        assert profile.raw_answers is not None

    def test_populate_from_pretix_data_handles_missing_fields(self):
        """Test that from_pretix_data handles missing fields gracefully."""
        order = PretixOrder.objects.create(order_code="ORDER456")
        profile = AttendeeProfile(order=order)

        # Pretix data with minimal answers
        pretix_data = {
            "code": "ORDER456",
            "positions": [{"answers": []}],
        }

        profile.from_pretix_data(pretix_data)

        assert profile.city is None
        assert profile.country is None
        assert profile.may_share_email_with_sponsor is None
        assert profile.experience_level is None
        assert len(profile.expectation_from_event) == 0
        assert len(profile.heard_about) == 0
        assert len(profile.participated_in_previous_event) == 0
        assert profile.pyladies_chapter is None
        assert profile.age_range is None
        assert profile.organization_name is None
        assert len(profile.current_position) == 0
        assert profile.raw_answers is not None

    def test_populate_from_pretix_data_none_value_for_chapter(self):
        """Test populating AttendeeProfile with all demographic fields."""
        order = PretixOrder.objects.create(order_code="ORDER123")
        profile = AttendeeProfile(order=order)

        pretix_data = {
            "code": "ORDER123",
            "positions": [
                {
                    "answers": [
                        {
                            "answer": "Vancouver",
                            "question_identifier": PRETIX_ATTENDEE_CITY_QUESTION_IDENTIFIER,
                        },
                        {
                            "answer": "United States",
                            "question_identifier": PRETIX_ATTENDEE_COUNTRY_QUESTION_IDENTIFIER,
                        },
                        {
                            "answer": "Networking, Learn new things, Support community activities",
                            "question_identifier": PRETIX_ATTENDEE_EXPECTATION_FROM_EVENT_QUESTION_IDENTIFIER,
                        },
                        {
                            "answer": "Social Media, Other",
                            "question_identifier": PRETIX_ATTENDEE_HEARD_ABOUT_EVENT_QUESTION_IDENTIFIER,
                        },
                        {
                            "answer": "No, this is my first one",
                            "question_identifier": PRETIX_ATTENDEE_PARTICIPATED_IN_PREVIOUS_EVENT_QUESTION_IDENTIFIER,
                        },
                        {
                            "answer": "None",
                            "question_identifier": PRETIX_ATTENDEE_PYLADIES_CHAPTER_QUESTION_IDENTIFIER,
                        },
                        {
                            "answer": "19-25",
                            "question_identifier": PRETIX_ATTENDEE_AGE_RANGE_QUESTION_IDENTIFIER,
                        },
                        {
                            "answer": "Umbrella Corp",
                            "question_identifier": PRETIX_ATTENDEE_ORGANIZATION_NAME_QUESTION_IDENTIFIER,
                        },
                        {
                            "answer": "Student/Intern, Other",
                            "question_identifier": PRETIX_ATTENDEE_CURRENT_POSITION_QUESTION_IDENTIFIER,
                        },
                        {
                            "answer": "Junior",
                            "question_identifier": PRETIX_ATTENDEE_EXPERIENCE_LEVEL_QUESTION_IDENTIFIER,
                        },
                        {
                            "answer": "Yes, I'm interested",
                            "question_identifier": PRETIX_ATTENDEE_MAY_SHARE_EMAIL_WITH_SPONSOR_QUESTION_IDENTIFIER,
                        },
                    ],
                }
            ],
        }

        profile.from_pretix_data(pretix_data)

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
        assert profile.pyladies_chapter is None
        assert profile.age_range == "19-25"
        assert profile.organization_name == "Umbrella Corp"
        assert profile.current_position == ["Student/Intern", "Other"]
        assert profile.raw_answers is not None
