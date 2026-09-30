# Post-production (design §8.8, tasks 5.4 and 5.5): the "final cut is in"
# ready rule and its backfill onto the seeded "Approve the final cut" lines
# and their items; promo materials as a kind with variants, files an
# organizer shares with the speaker, and the two seeded promo lines
# switched from a manual tick to a rule. Names are written literally: a data
# migration is a historical record and must stay replayable.

from django.db import migrations, models

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


def stop_waiting_for_the_final_cut(apps, schema_editor):
    ChecklistTemplateItem = apps.get_model("speakers", "ChecklistTemplateItem")
    ChecklistItem = apps.get_model("speakers", "ChecklistItem")
    ChecklistItem.objects.filter(ready_rule=FINAL_CUT_RULE).update(
        ready_rule="", template_waiting_note="", is_waiting=False, waiting_reason=""
    )
    ChecklistTemplateItem.objects.filter(ready_rule=FINAL_CUT_RULE).update(
        ready_rule="", waiting_note=""
    )


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


def promo_back_to_a_tick(apps, schema_editor):
    ChecklistTemplateItem = apps.get_model("speakers", "ChecklistTemplateItem")
    ChecklistItem = apps.get_model("speakers", "ChecklistItem")
    ChecklistItem.objects.filter(requires_asset_kind="PROMO").update(
        auto_complete_rule="", requires_asset_kind=""
    )
    ChecklistTemplateItem.objects.filter(requires_asset_kind="PROMO").update(
        auto_complete_rule="", requires_asset_kind=""
    )


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


class Migration(migrations.Migration):

    dependencies = [
        ("speakers", "0012_media_uploads"),
    ]

    operations = [
        migrations.AddField(
            model_name="mediaasset",
            name="shared_with_speaker",
            field=models.BooleanField(db_default=False, default=False),
        ),
        migrations.AddField(
            model_name="mediaasset",
            name="variant",
            field=models.CharField(
                blank=True, db_default="", default="", max_length=40
            ),
        ),
        migrations.AddField(
            model_name="mediaupload",
            name="variant",
            field=models.CharField(
                blank=True, db_default="", default="", max_length=40
            ),
        ),
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
            model_name="mediaupload",
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
        migrations.RunPython(wait_for_the_final_cut, stop_waiting_for_the_final_cut),
        migrations.RunPython(promo_ticks_on_the_first_file, promo_back_to_a_tick),
        migrations.RunPython(
            shared_ticks_on_the_first_shared_file, shared_back_to_a_tick
        ),
    ]
