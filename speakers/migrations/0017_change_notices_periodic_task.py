# Schedules the daily checklist-update emails (new or changed items since
# the last notice). Names are literal so the migration stays replayable.

from django.db import migrations

TASK_NAME = "Send speaker checklist change notices"
TASK_PATH = "speakers.tasks.send_checklist_change_notices_task"


def seed_periodic_task(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    morning, _ = CrontabSchedule.objects.get_or_create(
        minute="30",
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
                "Email presenters and assignees the checklist items added or "
                "changed since they were last told; nothing is sent otherwise."
            ),
        },
    )


def unseed_periodic_task(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("django_celery_beat", "0019_alter_periodictasks_options"),
        ("speakers", "0016_change_notices"),
    ]

    operations = [migrations.RunPython(seed_periodic_task, unseed_periodic_task)]
