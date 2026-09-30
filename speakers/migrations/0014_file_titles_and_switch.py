# File titles (design §8.8, task 5.9) and the speaker-side switch: a title
# carried by every version on a file line, and the per-edition setting that
# shows or hides the media pipeline on the speaker's pages.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("speakers", "0013_post_production"),
    ]

    operations = [
        migrations.AddField(
            model_name="mediaasset",
            name="title",
            field=models.CharField(
                blank=True, db_default="", default="", max_length=200
            ),
        ),
        migrations.AddField(
            model_name="mediaupload",
            name="title",
            field=models.CharField(
                blank=True, db_default="", default="", max_length=200
            ),
        ),
        migrations.AddField(
            model_name="speakersettings",
            name="media_for_speakers",
            field=models.BooleanField(
                db_default=False,
                default=False,
                help_text="While on, speakers upload their video from their session page and see the files the team shares with them. Off, the team gathers videos by other means and uploads them; organizers see everything either way.",
            ),
        ),
    ]
