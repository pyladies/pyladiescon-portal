from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command


@pytest.mark.django_db
class TestMakeSuperuserCommand:
    def test_makesuperuser_no_such_user(self):
        out = StringIO()
        call_command("makesuperuser", "testuser", stdout=out)
        assert "No such user" in out.getvalue()

    def test_makesuperuser_success(self):
        user = User.objects.create_user(username="testuser")
        assert user.is_superuser is False

        out = StringIO()
        call_command("makesuperuser", "testuser", stdout=out)
        assert f"{user.username} is now a superuser" in out.getvalue()
        user.refresh_from_db()
        assert user.is_superuser
