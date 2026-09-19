# Checklist templates, items, rules, media/handbook shells, and the nightly
# re-evaluation schedule (design §9). The periodic task is data (editable
# under "Periodic tasks" in the admin); seeding it here only gives a fresh
# database the same default. Names are literal so the migration stays
# replayable.


import django.contrib.postgres.fields
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

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
        ("attendee", "0005_alter_pretixorder_conference"),
        ("portal", "0007_conference_coc_url_conference_donate_url_and_more"),
        ("speakers", "0002_repair_invitation_sent_to"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="presenter",
            name="pretix_order",
            field=models.ForeignKey(
                blank=True,
                help_text="Manual link when the presenter registered under another email address; wins over email matching.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="linked_presenters",
                to="attendee.pretixorder",
            ),
        ),
        migrations.AddField(
            model_name="speakersettings",
            name="default_video_length_limit_minutes",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Length limit for pre-recorded videos unless a session says otherwise.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="speakersettings",
            name="translation_languages",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(max_length=10),
                blank=True,
                default=list,
                help_text="Language codes the team translates transcripts into; one post-production item is created per language.",
                size=None,
            ),
        ),
        migrations.CreateModel(
            name="ChecklistTemplate",
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
                    "scope",
                    models.CharField(
                        choices=[
                            ("PRESENTER", "Per presenter (keyed by kind and role)"),
                            ("SESSION", "Per session (keyed by kind and delivery)"),
                        ],
                        max_length=16,
                    ),
                ),
                ("name", models.CharField(max_length=100)),
                (
                    "delivery",
                    models.CharField(
                        blank=True,
                        choices=[("LIVE", "Live"), ("PRE_RECORDED", "Pre-recorded")],
                        help_text="Session scope only.",
                        max_length=16,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                (
                    "conference",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="checklist_templates",
                        to="portal.conference",
                    ),
                ),
                (
                    "kind",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="checklist_templates",
                        to="speakers.sessiontype",
                    ),
                ),
                (
                    "role",
                    models.ForeignKey(
                        blank=True,
                        help_text="Presenter templates only.",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="checklist_templates",
                        to="speakers.presenterrole",
                    ),
                ),
            ],
            options={
                "ordering": ["scope", "kind", "role", "delivery"],
            },
        ),
        migrations.CreateModel(
            name="ChecklistTemplateItem",
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
                ("order", models.PositiveSmallIntegerField(default=0)),
                (
                    "owner",
                    models.CharField(
                        choices=[("SPEAKER", "Speaker"), ("ORGANIZER", "Organizer")],
                        max_length=16,
                    ),
                ),
                ("title", models.CharField(max_length=200)),
                ("description_md", models.TextField(blank=True, help_text="Markdown.")),
                (
                    "due_anchor",
                    models.CharField(
                        blank=True,
                        choices=[
                            (
                                "INVITATION_ACCEPTED",
                                "Days after the invitation is accepted",
                            ),
                            ("CONFERENCE_START", "Days before the conference starts"),
                            ("SESSION_START", "Days before the session starts"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "due_offset_days",
                    models.IntegerField(
                        default=0,
                        help_text="Days after the invitation is accepted, or days before the conference or session starts.",
                    ),
                ),
                (
                    "auto_complete_rule",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("bio_and_headshot", "Bio and headshot are filled in"),
                            ("handbook_read", "Speaker guide read (current version)"),
                            ("invitation_sent", "Invitation sent"),
                            ("invitation_accepted", "Invitation accepted"),
                            ("session_scheduled", "Session has a slot"),
                            ("pretix_registered", "Registered on pretix"),
                            (
                                "asset_exists",
                                "A ready asset of the required kind exists",
                            ),
                            ("video_length_ok", "Video length within the limit"),
                            ("youtube_published", "YouTube URL and publish time set"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "requires_asset_kind",
                    models.CharField(
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
                            ("OTHER", "Other"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "requires_asset_language",
                    models.CharField(
                        blank=True,
                        help_text='A language code, or "session" for the session language.',
                        max_length=10,
                    ),
                ),
                (
                    "per_translation_language",
                    models.BooleanField(
                        default=False,
                        help_text="Instantiate one item per translation language of the edition.",
                    ),
                ),
                (
                    "is_required",
                    models.BooleanField(
                        default=False,
                        help_text="Required items gate the session being confirmed.",
                    ),
                ),
                (
                    "assignee_default",
                    models.CharField(
                        choices=[
                            ("UNASSIGNED", "Unassigned"),
                            ("LIAISON", "The presenter's liaison"),
                        ],
                        default="UNASSIGNED",
                        help_text="Organizer items only.",
                        max_length=16,
                    ),
                ),
                (
                    "template",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="speakers.checklisttemplate",
                    ),
                ),
            ],
            options={
                "ordering": ["order", "id"],
            },
        ),
        migrations.CreateModel(
            name="ChecklistItem",
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
                ("order", models.PositiveSmallIntegerField(default=0)),
                (
                    "owner",
                    models.CharField(
                        choices=[("SPEAKER", "Speaker"), ("ORGANIZER", "Organizer")],
                        max_length=16,
                    ),
                ),
                ("title", models.CharField(max_length=200)),
                ("description_md", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("TODO", "To do"),
                            ("DONE", "Done"),
                            ("SKIPPED", "Skipped"),
                            ("BLOCKED", "Blocked"),
                        ],
                        default="TODO",
                        max_length=16,
                    ),
                ),
                ("due_date", models.DateField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("note", models.TextField(blank=True)),
                ("is_required", models.BooleanField(default=False)),
                (
                    "auto_complete_rule",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("bio_and_headshot", "Bio and headshot are filled in"),
                            ("handbook_read", "Speaker guide read (current version)"),
                            ("invitation_sent", "Invitation sent"),
                            ("invitation_accepted", "Invitation accepted"),
                            ("session_scheduled", "Session has a slot"),
                            ("pretix_registered", "Registered on pretix"),
                            (
                                "asset_exists",
                                "A ready asset of the required kind exists",
                            ),
                            ("video_length_ok", "Video length within the limit"),
                            ("youtube_published", "YouTube URL and publish time set"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "requires_asset_kind",
                    models.CharField(
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
                            ("OTHER", "Other"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "requires_asset_language",
                    models.CharField(blank=True, max_length=10),
                ),
                (
                    "assignee",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assigned_checklist_items",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "completed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "conference",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="checklist_items",
                        to="portal.conference",
                    ),
                ),
                (
                    "presenter",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="checklist_items",
                        to="speakers.presenter",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="checklist_items",
                        to="speakers.session",
                    ),
                ),
                (
                    "template_item",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="instances",
                        to="speakers.checklisttemplateitem",
                    ),
                ),
            ],
            options={
                "ordering": ["order", "id"],
            },
        ),
        migrations.CreateModel(
            name="Handbook",
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
                ("version", models.PositiveIntegerField(default=1)),
                ("title", models.CharField(default="Speaker guide", max_length=200)),
                ("body_md", models.TextField(blank=True, help_text="Markdown.")),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                (
                    "conference",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="handbooks",
                        to="portal.conference",
                    ),
                ),
            ],
            options={
                "ordering": ["-version"],
            },
        ),
        migrations.CreateModel(
            name="HandbookReadReceipt",
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
                ("read_at", models.DateTimeField(auto_now_add=True)),
                (
                    "conference",
                    models.ForeignKey(
                        editable=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="handbook_receipts",
                        to="portal.conference",
                    ),
                ),
                (
                    "handbook",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="receipts",
                        to="speakers.handbook",
                    ),
                ),
                (
                    "presenter",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="handbook_receipts",
                        to="speakers.presenter",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="MediaAsset",
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
                (
                    "language",
                    models.CharField(
                        blank=True,
                        help_text="Transcripts and translations.",
                        max_length=10,
                    ),
                ),
                ("version", models.PositiveIntegerField(default=1)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("UPLOADING", "Uploading"),
                            ("READY", "Ready"),
                            ("FAILED", "Failed"),
                            ("SUPERSEDED", "Superseded"),
                        ],
                        default="UPLOADING",
                        max_length=16,
                    ),
                ),
                ("file", models.FileField(blank=True, upload_to="speakers/media/")),
                (
                    "duration_seconds",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                (
                    "notes_md",
                    models.TextField(blank=True, help_text="Reviewer notes. Markdown."),
                ),
                (
                    "conference",
                    models.ForeignKey(
                        editable=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="media_assets",
                        to="portal.conference",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="media_assets",
                        to="speakers.session",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="uploaded_media_assets",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-version", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="checklisttemplate",
            constraint=models.UniqueConstraint(
                fields=("conference", "scope", "kind", "role", "delivery"),
                name="speakers_template_key_per_edition",
                nulls_distinct=False,
            ),
        ),
        migrations.AddConstraint(
            model_name="checklistitem",
            constraint=models.UniqueConstraint(
                condition=models.Q(("template_item__isnull", False)),
                fields=(
                    "template_item",
                    "presenter",
                    "session",
                    "requires_asset_language",
                ),
                name="speakers_item_once_per_target",
                nulls_distinct=False,
            ),
        ),
        migrations.AddConstraint(
            model_name="checklistitem",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("presenter__isnull", False),
                    ("session__isnull", False),
                    _connector="OR",
                ),
                name="speakers_item_has_target",
            ),
        ),
        migrations.AddConstraint(
            model_name="handbook",
            constraint=models.UniqueConstraint(
                fields=("conference", "version"), name="speakers_handbook_version"
            ),
        ),
        migrations.AddConstraint(
            model_name="handbookreadreceipt",
            constraint=models.UniqueConstraint(
                fields=("presenter", "handbook"), name="speakers_receipt_once"
            ),
        ),
        migrations.RunPython(seed_periodic_task, unseed_periodic_task),
    ]
