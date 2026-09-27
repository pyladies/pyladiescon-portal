# The record of every email the portal sent (design §13.1, task 2.23), and
# the django-celery-beat periodic task that prunes it nightly. Names are
# copied literally rather than imported: a data migration is a historical
# record and must stay replayable on a fresh database.

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

TASK_NAME = "Prune email records"
TASK_PATH = "common.tasks.prune_email_records_task"


def seed_periodic_tasks(apps, schema_editor):
    """Schedule the prune nightly at 03:30 UTC, after the account cleanup.

    The schedule is data (editable under "Periodic tasks" in the Django
    admin); this only gives a fresh database the same default.
    """
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    nightly, _ = CrontabSchedule.objects.get_or_create(
        minute="30",
        hour="3",
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
                "Delete sent-email records older than the edition plus "
                "EMAIL_RECORD_RETENTION_DAYS."
            ),
        },
    )


def unseed_periodic_tasks(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("django_celery_beat", "0019_alter_periodictasks_options"),
        ("portal", "0007_conference_coc_url_conference_donate_url_and_more"),
        ("speakers", "0011_proposals"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SentEmail",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "to",
                    models.TextField(
                        help_text="The addresses as sent.", verbose_name="to"
                    ),
                ),
                ("subject", models.CharField(max_length=500)),
                (
                    "template",
                    models.CharField(
                        help_text="The Markdown template: what kind of email.",
                        max_length=200,
                    ),
                ),
                (
                    "body_md",
                    models.TextField(
                        blank=True,
                        help_text="The rendered Markdown, the source of both parts.",
                    ),
                ),
                (
                    "context_digest",
                    models.JSONField(
                        blank=True, default=dict, help_text="Ids of what it was about."
                    ),
                ),
                (
                    "sent_at",
                    models.DateTimeField(
                        db_index=True, default=django.utils.timezone.now
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("SENT", "Sent"), ("FAILED", "Failed")],
                        default="SENT",
                        max_length=8,
                    ),
                ),
                ("error", models.TextField(blank=True)),
                (
                    "conference",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sent_emails",
                        to="portal.conference",
                    ),
                ),
                (
                    "presenter",
                    models.ForeignKey(
                        blank=True,
                        help_text="The presenter it was sent to, when it went to one.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sent_emails",
                        to="speakers.presenter",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sent_emails",
                        to="speakers.session",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        help_text="The account it was sent to, when the sender knew it.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="emails_received",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "sent email",
                "verbose_name_plural": "sent emails",
                "ordering": ["-sent_at", "-id"],
            },
        ),
        migrations.RunPython(seed_periodic_tasks, unseed_periodic_tasks),
    ]
