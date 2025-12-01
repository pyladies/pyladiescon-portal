import pytest

from attendee.models import (
    PRETIX_ANONYMOUS_DONATION_QUESTION_IDENTIFIER,
    PRETIX_NOT_ANONYMOUS_ANSWER_IDENTIFIER,
)
from volunteer.models import Language


@pytest.fixture
def portal_user(db, django_user_model):
    username = "testuser"
    password = "testpassword"
    email = "test@example.com"
    first_name = "fname"
    last_name = "lname"
    return django_user_model.objects.create_user(
        username=username,
        password=password,
        email=email,
        first_name=first_name,
        last_name=last_name,
    )


@pytest.fixture
def admin_user(db, django_user_model):
    username = "adminuser"
    password = "adminpassword"
    email = "admin@example.com"
    first_name = "admin_fname"
    last_name = "admin_lname"
    return django_user_model.objects.create_superuser(
        username=username,
        password=password,
        email=email,
        first_name=first_name,
        last_name=last_name,
    )


@pytest.fixture
def language(db):
    return Language.objects.create(code="en", name="English")


@pytest.fixture
def pretix_order_data():
    return {
        "code": "ORDER123",
        "event": "2025",
        "status": "p",
        "testmode": False,
        "email": "attendee@example.com",
        "datetime": "2025-11-13T17:12:03.989259+01:00",
        "total": "30.00",
        "positions": [
            {
                "attendee_name": "Example Attendee",
                "answers": [
                    {"question_identifier": "QUESTION123", "option_identifiers": []},
                    {
                        "option_identifiers": [PRETIX_NOT_ANONYMOUS_ANSWER_IDENTIFIER],
                        "question_identifier": PRETIX_ANONYMOUS_DONATION_QUESTION_IDENTIFIER,
                    },
                ],
            }
        ],
        "last_modified": "2025-11-13T17:12:07.002602+01:00",
        "url": "https://someurl/",
        "cancellation_date": None,
    }
