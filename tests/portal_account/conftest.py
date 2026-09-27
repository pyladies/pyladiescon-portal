"""Fixtures shared by the portal_account tests."""

import importlib

import pytest
from django.apps import apps
from django.contrib.auth.models import Group, User

from portal_account.permissions import MAINTAINERS_GROUP

migration = importlib.import_module("portal_account.migrations.0004_maintenance_setup")


@pytest.fixture
def maintainers_group(db):
    """The group the data migration creates; tests run without migrations."""
    migration.create_maintainers_group(apps, None)
    return Group.objects.get(name=MAINTAINERS_GROUP)


@pytest.fixture
def maintainer(maintainers_group):
    """A non-staff user whose only capability is the maintainers group."""
    user = User.objects.create_user(username="maintainer", email="m@example.com")
    user.groups.add(maintainers_group)
    return user
