import unittest
from datetime import date, timedelta

import pytest

from attendee.models import (
    PRETIX_ANONYMOUS_DONATION_QUESTION_IDENTIFIER,
    PRETIX_NOT_ANONYMOUS_ANSWER_IDENTIFIER,
)
from portal.models import Conference
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


@pytest.fixture(autouse=True)
def conference(request):
    """The active conference every year-bound record is scoped to.

    Autouse so production paths calling ``Conference.get_active()`` resolve in
    every test, and so inline model construction can request it by name. Tests
    that manage their own Conference rows override this fixture locally (see
    ``tests/portal/test_models.py``).

    ``unittest.TestCase`` classes manage their own transactions, so this
    db-backed row would leak across them and clash on the unique year; those
    classes are skipped here and seed their own Conference in ``setUp``.
    """
    if request.cls is not None and issubclass(request.cls, unittest.TestCase):
        return None
    request.getfixturevalue("db")
    return Conference.objects.create(
        year=2025,
        name="PyLadiesCon 2025",
        slug="2025",
        is_active=True,
        pretix_event_slug="2025",
        sponsorship_goal=15000,
        donation_goal=2500,
        # In the past, so the active edition is "over" by default and the
        # start-a-new-year flow is available. Gate-specific tests override this.
        conference_date=date.today() - timedelta(days=30),
    )


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
