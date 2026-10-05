"""The published schedule: the snapshot speakers read (design §10.1).

The backfill copies the working slot of every SCHEDULED or PUBLISHED
session: those were speaker-visible under the old rule, so their
snapshot starts equal to the grid and nothing moves for anyone on
deploy.
"""

import django.db.models.deletion
from django.db import migrations, models
from django.utils import timezone


def backfill(apps, schema_editor):
    ScheduleSlot = apps.get_model("speakers", "ScheduleSlot")
    PublishedSlot = apps.get_model("speakers", "PublishedSlot")
    now = timezone.now()
    for slot in ScheduleSlot.objects.filter(
        session__status__in=["SCHEDULED", "PUBLISHED"]
    ):
        PublishedSlot.objects.create(
            conference_id=slot.conference_id,
            session_id=slot.session_id,
            room_id=slot.room_id,
            start_utc=slot.start_utc,
            end_utc=slot.end_utc,
            published_at=now,
        )


def unfill(apps, schema_editor):
    apps.get_model("speakers", "PublishedSlot").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0007_conference_coc_url_conference_donate_url_and_more"),
        ("speakers", "0017_rooms"),
    ]

    operations = [
        migrations.CreateModel(
            name="PublishedSlot",
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
                ("start_utc", models.DateTimeField()),
                ("end_utc", models.DateTimeField()),
                ("published_at", models.DateTimeField()),
                (
                    "ics_sequence",
                    models.PositiveIntegerField(db_default=0, default=0),
                ),
                (
                    "conference",
                    models.ForeignKey(
                        editable=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="published_slots",
                        to="portal.conference",
                    ),
                ),
                (
                    "room",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="published_slots",
                        to="speakers.room",
                    ),
                ),
                (
                    "session",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="published_slot",
                        to="speakers.session",
                    ),
                ),
            ],
            options={"ordering": ["start_utc"]},
        ),
        migrations.RunPython(backfill, unfill),
    ]
