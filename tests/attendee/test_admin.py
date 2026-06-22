import pytest

from attendee.admin import AttendeeProfileResource
from attendee.models import AttendeeProfile, PretixOrder


@pytest.mark.django_db
class TestAttendeeProfileResource:
    def test_export_includes_conference_year(self, conference):
        order = PretixOrder.objects.create(order_code="ORDER123", conference=conference)
        AttendeeProfile.objects.create(order=order)
        dataset = AttendeeProfileResource().export()
        assert "conference" in dataset.headers
        idx = dataset.headers.index("conference")
        assert str(dataset[0][idx]) == str(conference.year)
