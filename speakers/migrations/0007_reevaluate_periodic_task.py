# Schedules the nightly checklist re-evaluation (design §9.3) with
# django-celery-beat. The schedule is data, editable under "Periodic tasks"
# in the admin; this only gives a fresh database the same default. Names
# are literal so the migration stays replayable.

from django.db import migrations

TASK_NAME = "Re-evaluate speaker checklists"
TASK_PATH = "speakers.tasks.reevaluate_checklists_task"


def seed_periodic_task(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    nightly, _ = CrontabSchedule.objects.get_or_create(
        minute="30",
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
                "Re-run every checklist auto-completion rule as a safety net "
                "for changes the signal receivers missed."
            ),
        },
    )


def unseed_periodic_task(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("django_celery_beat", "0019_alter_periodictasks_options"),
        ("speakers", "0006_rules_and_shells"),
    ]

    operations = [migrations.RunPython(seed_periodic_task, unseed_periodic_task)]
