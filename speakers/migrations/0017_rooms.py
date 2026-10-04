"""DiscordChannel becomes Room: the schedule's places are generic.

Pure renames (model, three fields, one constraint), so every existing
row and foreign key survives; nothing about the data changes. The
autodetector proposed delete-and-recreate for this, which is why the
file is written by hand.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("speakers", "0016_file_notices"),
    ]

    operations = [
        migrations.RenameModel(old_name="DiscordChannel", new_name="Room"),
        migrations.RenameField(
            model_name="room", old_name="channel_id", new_name="discord_id"
        ),
        migrations.RenameField(
            model_name="scheduleslot", old_name="channel", new_name="room"
        ),
        migrations.RenameField(
            model_name="sessiontype",
            old_name="spans_all_channels",
            new_name="spans_all_rooms",
        ),
        migrations.AlterField(
            model_name="room",
            name="conference",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="rooms",
                to="portal.conference",
            ),
        ),
        migrations.AlterField(
            model_name="room",
            name="discord_id",
            field=models.CharField(
                blank=True,
                help_text="The numeric Discord channel id, when the room is one.",
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="sessiontype",
            name="spans_all_rooms",
            field=models.BooleanField(
                default=False,
                help_text="On the schedule, takes the whole grid rather than one room.",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="room", name="speakers_channel_name_per_edition"
        ),
        migrations.AddConstraint(
            model_name="room",
            constraint=models.UniqueConstraint(
                fields=("conference", "name"), name="speakers_room_name_per_edition"
            ),
        ),
    ]
