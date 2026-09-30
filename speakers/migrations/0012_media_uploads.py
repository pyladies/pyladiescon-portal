# Multipart uploads (design §8.8, task 5.1): the MediaUpload row, the fields a
# finished upload leaves on MediaAsset, and the nightly task that aborts
# uploads nobody finished. Names are written literally: a data migration is a
# historical record and must stay replayable.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

TASK_NAME = "Expire abandoned uploads"
TASK_PATH = "speakers.tasks.expire_abandoned_uploads_task"


def seed_periodic_task(apps, schema_editor):
    """Nightly at 04:00 UTC; the bucket lifecycle rule is the backstop."""
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    nightly, _ = CrontabSchedule.objects.get_or_create(
        minute="0",
        hour="4",
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
                "Abort multipart uploads past their expiry and mark them EXPIRED."
            ),
        },
    )


def unseed_periodic_task(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("django_celery_beat", "0019_alter_periodictasks_options"),
        ("portal", "0007_conference_coc_url_conference_donate_url_and_more"),
        ("speakers", "0011_proposals"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="mediaasset",
            name="content_type",
            field=models.CharField(
                blank=True, default="", db_default="", max_length=100
            ),
        ),
        migrations.AddField(
            model_name="mediaasset",
            name="original_filename",
            field=models.CharField(
                blank=True, default="", db_default="", max_length=255
            ),
        ),
        migrations.AddField(
            model_name="mediaasset",
            name="size_bytes",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="mediaasset",
            name="probe_error",
            field=models.CharField(
                blank=True, default="", db_default="", max_length=500
            ),
        ),
        migrations.AddField(
            model_name="mediaasset",
            name="storage_key",
            field=models.CharField(
                blank=True, default="", db_default="", max_length=500
            ),
        ),
        migrations.CreateModel(
            name="MediaUpload",
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
                    "creation_date",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="creation_date"
                    ),
                ),
                (
                    "modified_date",
                    models.DateTimeField(auto_now=True, verbose_name="modified_date"),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("RAW_VIDEO", "Raw video (performer upload)"),
                            ("INTRO", "Intro (MC)"),
                            ("OUTRO", "Outro (MC)"),
                            ("PROCESSED_VIDEO", "Processed video (final cut)"),
                            ("TRANSCRIPT", "Transcript"),
                            ("TRANSLATION", "Translation"),
                            ("TITLE_CARD", "Title card"),
                            ("THUMBNAIL", "Thumbnail"),
                            ("OTHER", "Other"),
                        ],
                        max_length=16,
                    ),
                ),
                ("language", models.CharField(blank=True, default="", max_length=10)),
                ("filename", models.CharField(max_length=255)),
                (
                    "content_type",
                    models.CharField(
                        default="application/octet-stream", max_length=100
                    ),
                ),
                ("size_bytes", models.BigIntegerField()),
                ("part_size", models.PositiveIntegerField()),
                ("parts_total", models.PositiveIntegerField()),
                ("storage_key", models.CharField(max_length=500)),
                ("upload_id", models.CharField(max_length=1024)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("STARTED", "Started"),
                            ("COMPLETED", "Completed"),
                            ("ABORTED", "Aborted"),
                            ("EXPIRED", "Expired"),
                        ],
                        default="STARTED",
                        max_length=16,
                    ),
                ),
                ("expires_at", models.DateTimeField()),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "asset",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="upload",
                        to="speakers.mediaasset",
                    ),
                ),
                (
                    "conference",
                    models.ForeignKey(
                        editable=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="media_uploads",
                        to="portal.conference",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="media_uploads",
                        to="speakers.session",
                    ),
                ),
                (
                    "started_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="media_uploads",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-id"],
            },
        ),
        migrations.RunPython(seed_periodic_task, unseed_periodic_task),
    ]
