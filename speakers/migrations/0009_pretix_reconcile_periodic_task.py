# Schedules the nightly pretix reconciliation (design §12.1) with
# django-celery-beat. The schedule is data, editable under "Periodic tasks";
# names are literal so the migration stays replayable.

from django.db import migrations

TASK_NAME = "Reconcile pretix orders for the speaker portal"
TASK_PATH = "speakers.tasks.pretix_reconcile_task"


def seed_periodic_task(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    nightly, _ = CrontabSchedule.objects.get_or_create(
        minute="0",
        hour="2",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone="UTC",
    )
    PeriodicTask.objects.get_or_create(
        name=TASK_NAME,
        defaults={
            "task": TASK_PATH,
            "crontab": nightly,
            "description": (
                "Page through pretix orders modified since the last run so "
                "missed webhooks and backend edits are caught."
            ),
        },
    )


def unseed_periodic_task(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("django_celery_beat", "0019_alter_periodictasks_options"),
        ("speakers", "0008_pretix_settings"),
    ]

    operations = [migrations.RunPython(seed_periodic_task, unseed_periodic_task)]
