# Schedules the daily checklist reminder digests (design §9.4) with
# django-celery-beat. The schedule is data, editable under "Periodic tasks";
# names are literal so the migration stays replayable.

from django.db import migrations

TASK_NAME = "Send speaker checklist digests"
TASK_PATH = "speakers.tasks.send_checklist_digests_task"


def seed_periodic_task(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    morning, _ = CrontabSchedule.objects.get_or_create(
        minute="0",
        hour="7",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone="UTC",
    )
    PeriodicTask.objects.get_or_create(
        name=TASK_NAME,
        defaults={
            "task": TASK_PATH,
            "crontab": morning,
            "description": (
                "Email each presenter and assignee their open checklist items "
                "due within 7, 3 and 1 days; each reminder is sent once."
            ),
        },
    )


def unseed_periodic_task(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("django_celery_beat", "0019_alter_periodictasks_options"),
        ("speakers", "0010_reminders"),
    ]

    operations = [migrations.RunPython(seed_periodic_task, unseed_periodic_task)]
