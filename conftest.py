import pytest


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
