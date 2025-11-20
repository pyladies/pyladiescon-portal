import pytest

from attendee.models import (
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
                        {"question_identifier": "ROLE", "answer": "Software Engineer"},
                        {"question_identifier": "COUNTRY", "answer": "United States"},
                        {"question_identifier": "REGION", "answer": "North America"},
                        {
                            "question_identifier": "EXPERIENCE",
                            "answer": "Intermediate",
                        },
                        {"question_identifier": "INDUSTRY", "answer": "Technology"},
                    ]
                }
            ],
        }

        profile.populate_from_pretix_data(pretix_data)

        assert profile.job_role == "Software Engineer"
        assert profile.country == "United States"
        assert profile.region == "North America"
        assert profile.experience_level == "Intermediate"
        assert profile.industry == "Technology"
        assert profile.raw_answers is not None

    def test_populate_from_pretix_data_handles_missing_fields(self):
        """Test that populate_from_pretix_data handles missing fields gracefully."""
        order = PretixOrder.objects.create(order_code="ORDER456")
        profile = AttendeeProfile(order=order)

        # Pretix data with minimal answers
        pretix_data = {
            "code": "ORDER456",
            "positions": [
                {
                    "answers": [
                        {"question_identifier": "ROLE", "answer": "Data Scientist"},
                    ]
                }
            ],
        }

        profile.populate_from_pretix_data(pretix_data)

        assert profile.job_role == "Data Scientist"
        assert profile.country is None
        assert profile.region is None
        assert profile.experience_level is None

    def test_populate_from_pretix_data_with_all_fields(self):
        """Test populating AttendeeProfile with all demographic fields."""
        order = PretixOrder.objects.create(order_code="ORDER789")
        profile = AttendeeProfile(order=order)

        pretix_data = {
            "code": "ORDER789",
            "positions": [
                {
                    "answers": [
                        {"question_identifier": "ROLE", "answer": "Data Scientist"},
                        {"question_identifier": "JOB_TITLE", "answer": "Senior DS"},
                        {"question_identifier": "COUNTRY", "answer": "Brazil"},
                        {"question_identifier": "REGION", "answer": "South America"},
                        {"question_identifier": "EXPERIENCE", "answer": "Advanced"},
                        {
                            "question_identifier": "LANGUAGES",
                            "answer": "Portuguese, English, Spanish",
                        },
                        {"question_identifier": "INDUSTRY", "answer": "Finance"},
                        {"question_identifier": "COMPANY_SIZE", "answer": "1000+"},
                        {
                            "question_identifier": "HEARD_ABOUT",
                            "answer": "Social Media",
                        },
                    ]
                }
            ],
        }

        profile.populate_from_pretix_data(pretix_data)

        assert profile.job_role == "Data Scientist"
        assert profile.job_title == "Senior DS"
        assert profile.country == "Brazil"
        assert profile.region == "South America"
        assert profile.experience_level == "Advanced"
        assert profile.languages == ["Portuguese", "English", "Spanish"]
        assert profile.industry == "Finance"
        assert profile.company_size == "1000+"
        assert profile.heard_about == "Social Media"
