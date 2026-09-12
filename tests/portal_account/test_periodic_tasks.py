import importlib

import pytest
from django.apps import apps
from django_celery_beat.models import PeriodicTask

from portal_account.tasks import delete_unverified_accounts_task

migration = importlib.import_module("portal_account.migrations.0004_maintenance_setup")


@pytest.mark.django_db
class TestSeedPeriodicTasks:
    """The deletion job's schedule is seeded once; tests run without
    migrations, so the migration function is exercised directly."""

    def test_seeds_daily_deletion_task(self):
        migration.seed_periodic_tasks(apps, None)

        task = PeriodicTask.objects.get(name=migration.TASK_NAME)
        assert task.task == delete_unverified_accounts_task.name
        assert task.enabled is True
        assert (task.crontab.hour, task.crontab.minute) == ("3", "0")
        assert str(task.crontab.timezone) == "UTC"

    def test_is_idempotent(self):
        migration.seed_periodic_tasks(apps, None)
        migration.seed_periodic_tasks(apps, None)
        assert PeriodicTask.objects.filter(name=migration.TASK_NAME).count() == 1

    def test_reverse_removes_task(self):
        migration.seed_periodic_tasks(apps, None)
        migration.unseed_periodic_tasks(apps, None)
        assert not PeriodicTask.objects.filter(name=migration.TASK_NAME).exists()
