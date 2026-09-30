# Multipart uploads (design §8.8, task 5.1): the MediaUpload row, the fields a
# finished upload leaves on MediaAsset, and the nightly task that aborts
# uploads nobody finished. Task 5.3 adds the probe's error field; task 5.4
# the "final cut is in" ready rule and its backfill onto the seeded
# "Approve the final cut" lines and their items. Names are written
# literally: a data migration is a historical record and must stay
# replayable.

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


APPROVAL_TITLE = "Approve the final cut"
FINAL_CUT_RULE = "final_cut_ready"
FINAL_CUT_NOTE = "we are still editing your video"


def wait_for_the_final_cut(apps, schema_editor):
    """Editions seeded before the rule existed carry the approval line
    with no wait source; give it, and the items made from it, the rule.
    Only lines still without one: an organizer's own choice stands. The
    items' waiting state follows at the next readiness pass."""
    ChecklistTemplateItem = apps.get_model("speakers", "ChecklistTemplateItem")
    ChecklistItem = apps.get_model("speakers", "ChecklistItem")
    lines = ChecklistTemplateItem.objects.filter(
        title=APPROVAL_TITLE, ready_rule="", ready_gate_code="", waits_for__isnull=True
    )
    ChecklistItem.objects.filter(
        template_item__in=lines, ready_rule="", ready_gate_code=""
    ).update(ready_rule=FINAL_CUT_RULE, template_waiting_note=FINAL_CUT_NOTE)
    lines.update(ready_rule=FINAL_CUT_RULE, waiting_note=FINAL_CUT_NOTE)


PROMO_TITLE = "Promo materials prepared"


def promo_ticks_on_the_first_file(apps, schema_editor):
    """The seeded "Promo materials prepared" line was a manual tick; it now
    completes when a promo file is on the session. Only lines still without
    a rule, and the open items made from them."""
    ChecklistTemplateItem = apps.get_model("speakers", "ChecklistTemplateItem")
    ChecklistItem = apps.get_model("speakers", "ChecklistItem")
    lines = ChecklistTemplateItem.objects.filter(
        title=PROMO_TITLE, auto_complete_rule="", requires_asset_kind=""
    )
    ChecklistItem.objects.filter(
        template_item__in=lines, auto_complete_rule="", status="TODO"
    ).update(auto_complete_rule="asset_exists", requires_asset_kind="PROMO")
    lines.update(auto_complete_rule="asset_exists", requires_asset_kind="PROMO")


SHARED_TITLE = "Promo materials shared with presenter"


def shared_ticks_on_the_first_shared_file(apps, schema_editor):
    """The seeded "shared with presenter" line was a manual tick; it now
    completes when a promo file is shared with the speaker. Only lines
    still without a rule, and the open items made from them."""
    ChecklistTemplateItem = apps.get_model("speakers", "ChecklistTemplateItem")
    ChecklistItem = apps.get_model("speakers", "ChecklistItem")
    lines = ChecklistTemplateItem.objects.filter(
        title=SHARED_TITLE, auto_complete_rule="", requires_asset_kind=""
    )
    ChecklistItem.objects.filter(
        template_item__in=lines, auto_complete_rule="", status="TODO"
    ).update(auto_complete_rule="asset_shared", requires_asset_kind="PROMO")
    lines.update(auto_complete_rule="asset_shared", requires_asset_kind="PROMO")


def shared_back_to_a_tick(apps, schema_editor):
    ChecklistTemplateItem = apps.get_model("speakers", "ChecklistTemplateItem")
    ChecklistItem = apps.get_model("speakers", "ChecklistItem")
    for model in (ChecklistItem, ChecklistTemplateItem):
        model.objects.filter(auto_complete_rule="asset_shared").update(
            auto_complete_rule="", requires_asset_kind=""
        )


def promo_back_to_a_tick(apps, schema_editor):
    ChecklistTemplateItem = apps.get_model("speakers", "ChecklistTemplateItem")
    ChecklistItem = apps.get_model("speakers", "ChecklistItem")
    ChecklistItem.objects.filter(requires_asset_kind="PROMO").update(
        auto_complete_rule="", requires_asset_kind=""
    )
    ChecklistTemplateItem.objects.filter(requires_asset_kind="PROMO").update(
        auto_complete_rule="", requires_asset_kind=""
    )


def stop_waiting_for_the_final_cut(apps, schema_editor):
    ChecklistTemplateItem = apps.get_model("speakers", "ChecklistTemplateItem")
    ChecklistItem = apps.get_model("speakers", "ChecklistItem")
    ChecklistItem.objects.filter(ready_rule=FINAL_CUT_RULE).update(
        ready_rule="", template_waiting_note="", is_waiting=False, waiting_reason=""
    )
    ChecklistTemplateItem.objects.filter(ready_rule=FINAL_CUT_RULE).update(
        ready_rule="", waiting_note=""
    )


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
            name="variant",
            field=models.CharField(
                blank=True, default="", db_default="", max_length=40
            ),
        ),
        migrations.AddField(
            model_name="mediaasset",
            name="shared_with_speaker",
            field=models.BooleanField(db_default=False, default=False),
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
                            ("PROMO", "Promo material"),
                            ("OTHER", "Other"),
                        ],
                        max_length=16,
                    ),
                ),
                ("language", models.CharField(blank=True, default="", max_length=10)),
                ("variant", models.CharField(blank=True, default="", max_length=40)),
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
        migrations.AlterField(
            model_name="checklistitem",
            name="ready_rule",
            field=models.CharField(
                blank=True,
                choices=[
                    ("session_scheduled", "The session has a slot"),
                    ("guide_published", "The guide it points at is published"),
                    ("registration_open", "Registration is set up on pretix"),
                    ("final_cut_ready", "The final cut is in"),
                ],
                db_default="",
                default="",
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="checklisttemplateitem",
            name="ready_rule",
            field=models.CharField(
                blank=True,
                choices=[
                    ("session_scheduled", "The session has a slot"),
                    ("guide_published", "The guide it points at is published"),
                    ("registration_open", "Registration is set up on pretix"),
                    ("final_cut_ready", "The final cut is in"),
                ],
                db_default="",
                default="",
                help_text="Wait for something the portal can check.",
                max_length=32,
            ),
        ),
        migrations.RunPython(wait_for_the_final_cut, stop_waiting_for_the_final_cut),
        migrations.AlterField(
            model_name="mediaasset",
            name="kind",
            field=models.CharField(
                choices=[
                    ("RAW_VIDEO", "Raw video (performer upload)"),
                    ("INTRO", "Intro (MC)"),
                    ("OUTRO", "Outro (MC)"),
                    ("PROCESSED_VIDEO", "Processed video (final cut)"),
                    ("TRANSCRIPT", "Transcript"),
                    ("TRANSLATION", "Translation"),
                    ("TITLE_CARD", "Title card"),
                    ("THUMBNAIL", "Thumbnail"),
                    ("PROMO", "Promo material"),
                    ("OTHER", "Other"),
                ],
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="checklistitem",
            name="requires_asset_kind",
            field=models.CharField(
                blank=True,
                choices=[
                    ("RAW_VIDEO", "Raw video (performer upload)"),
                    ("INTRO", "Intro (MC)"),
                    ("OUTRO", "Outro (MC)"),
                    ("PROCESSED_VIDEO", "Processed video (final cut)"),
                    ("TRANSCRIPT", "Transcript"),
                    ("TRANSLATION", "Translation"),
                    ("TITLE_CARD", "Title card"),
                    ("THUMBNAIL", "Thumbnail"),
                    ("PROMO", "Promo material"),
                    ("OTHER", "Other"),
                ],
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="checklisttemplateitem",
            name="requires_asset_kind",
            field=models.CharField(
                blank=True,
                choices=[
                    ("RAW_VIDEO", "Raw video (performer upload)"),
                    ("INTRO", "Intro (MC)"),
                    ("OUTRO", "Outro (MC)"),
                    ("PROCESSED_VIDEO", "Processed video (final cut)"),
                    ("TRANSCRIPT", "Transcript"),
                    ("TRANSLATION", "Translation"),
                    ("TITLE_CARD", "Title card"),
                    ("THUMBNAIL", "Thumbnail"),
                    ("PROMO", "Promo material"),
                    ("OTHER", "Other"),
                ],
                max_length=16,
            ),
        ),
        migrations.RunPython(promo_ticks_on_the_first_file, promo_back_to_a_tick),
        migrations.AlterField(
            model_name="checklistitem",
            name="auto_complete_rule",
            field=models.CharField(
                blank=True,
                choices=[
                    ("bio_and_headshot", "Bio and headshot are filled in"),
                    ("handbook_read", "Speaker guide read (current version)"),
                    ("invitation_sent", "Invitation sent"),
                    ("invitation_accepted", "Invitation accepted"),
                    ("session_scheduled", "Session has a slot"),
                    ("pretix_registered", "Registered on pretix"),
                    ("asset_exists", "A ready asset of the required kind exists"),
                    (
                        "asset_shared",
                        "A ready asset of the required kind is shared with the speaker",
                    ),
                    ("video_length_ok", "Video length within the limit"),
                    ("youtube_published", "YouTube URL and publish time set"),
                ],
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="checklisttemplateitem",
            name="auto_complete_rule",
            field=models.CharField(
                blank=True,
                choices=[
                    ("bio_and_headshot", "Bio and headshot are filled in"),
                    ("handbook_read", "Speaker guide read (current version)"),
                    ("invitation_sent", "Invitation sent"),
                    ("invitation_accepted", "Invitation accepted"),
                    ("session_scheduled", "Session has a slot"),
                    ("pretix_registered", "Registered on pretix"),
                    ("asset_exists", "A ready asset of the required kind exists"),
                    (
                        "asset_shared",
                        "A ready asset of the required kind is shared with the speaker",
                    ),
                    ("video_length_ok", "Video length within the limit"),
                    ("youtube_published", "YouTube URL and publish time set"),
                ],
                max_length=32,
            ),
        ),
        migrations.RunPython(
            shared_ticks_on_the_first_shared_file, shared_back_to_a_tick
        ),
    ]
