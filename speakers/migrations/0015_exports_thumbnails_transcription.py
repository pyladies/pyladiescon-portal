# Bulk download, thumbnails and machine transcription (design §8.8, tasks
# 5.6, 5.7 and 5.8): the export record, the thumbnail the media worker
# makes for an image or a video, who or what generated an asset, the
# transcription job and the per-edition auto-transcribe setting, and the
# nightly task that fails jobs nobody picked up. Names are written
# literally: a data migration is a historical record and must stay
# replayable.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

STALE_TASK_NAME = "Fail stale transcription jobs"
STALE_TASK_PATH = "speakers.tasks.fail_stale_transcription_jobs_task"


def seed_stale_jobs_task(apps, schema_editor):
    """Nightly at 04:30 UTC: a job nobody picked up in twelve hours says so
    on the page (the media worker is not running)."""
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    nightly, _ = CrontabSchedule.objects.get_or_create(
        minute="30",
        hour="4",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone="UTC",
    )
    PeriodicTask.objects.get_or_create(
        name=STALE_TASK_NAME,
        defaults={
            "task": STALE_TASK_PATH,
            "crontab": nightly,
            "description": (
                "Mark transcription jobs still queued after twelve hours as "
                "failed: nothing is consuming the media queue."
            ),
        },
    )


def unseed_stale_jobs_task(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name=STALE_TASK_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("django_celery_beat", "0019_alter_periodictasks_options"),
        ("portal", "0007_conference_coc_url_conference_donate_url_and_more"),
        ("speakers", "0014_file_titles_and_switch"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="mediaasset",
            name="generated_by",
            field=models.CharField(
                blank=True, db_default="", default="", max_length=60
            ),
        ),
        migrations.AddField(
            model_name="mediaasset",
            name="thumbnail_error",
            field=models.CharField(
                blank=True, db_default="", default="", max_length=500
            ),
        ),
        migrations.AddField(
            model_name="mediaasset",
            name="thumbnail_key",
            field=models.CharField(
                blank=True, db_default="", default="", max_length=500
            ),
        ),
        migrations.AddField(
            model_name="speakersettings",
            name="auto_transcribe",
            field=models.BooleanField(
                db_default=False,
                default=False,
                help_text="While on, a performance video that lands is transcribed by the portal's own worker into a draft the team reviews; nothing is sent to an outside service. Organizers can also start one from a video's row. Needs the portal's transcription engine set up.",
            ),
        ),
        migrations.CreateModel(
            name="MediaExport",
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
                ("scope", models.JSONField(blank=True, default=dict)),
                ("file_count", models.PositiveIntegerField(default=0)),
                ("total_bytes", models.BigIntegerField(default=0)),
                ("expires_at", models.DateTimeField()),
                (
                    "zip_status",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("", "Not requested"),
                            ("QUEUED", "Queued"),
                            ("RUNNING", "Building"),
                            ("DONE", "Ready"),
                            ("FAILED", "Failed"),
                        ],
                        default="",
                        max_length=16,
                    ),
                ),
                ("zip_key", models.CharField(blank=True, default="", max_length=500)),
                ("zip_error", models.CharField(blank=True, default="", max_length=500)),
                ("zip_built_at", models.DateTimeField(blank=True, null=True)),
                (
                    "conference",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="media_exports",
                        to="portal.conference",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="media_exports",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-id"],
            },
        ),
        migrations.CreateModel(
            name="TranscriptionJob",
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
                ("engine", models.CharField(blank=True, default="", max_length=60)),
                ("language", models.CharField(blank=True, default="", max_length=10)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("QUEUED", "Queued"),
                            ("RUNNING", "Transcribing"),
                            ("DONE", "Done"),
                            ("FAILED", "Failed"),
                        ],
                        default="QUEUED",
                        max_length=16,
                    ),
                ),
                ("error", models.CharField(blank=True, default="", max_length=500)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                (
                    "asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transcription_jobs",
                        to="speakers.mediaasset",
                    ),
                ),
                (
                    "conference",
                    models.ForeignKey(
                        editable=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="transcription_jobs",
                        to="portal.conference",
                    ),
                ),
                (
                    "output",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="made_by_jobs",
                        to="speakers.mediaasset",
                    ),
                ),
                (
                    "started_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="transcription_jobs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-id"],
            },
        ),
        migrations.RunPython(seed_stale_jobs_task, unseed_stale_jobs_task),
    ]
