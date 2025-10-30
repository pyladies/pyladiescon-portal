from django.core.management.base import BaseCommand, CommandError

from volunteer.models import VolunteerProfile


class Command(BaseCommand):
    help = "Reverse Volunteer languages_spoken field to the Language model."

    def handle(self, *args, **options):
        for volunteer in VolunteerProfile.objects.all():
            for lang in volunteer.language.all():
                print(lang)
                languages_to_add = volunteer.languages_spoken or []
                if (
                    not volunteer.languages_spoken
                    or lang.code not in volunteer.languages_spoken
                ):
                    print(f"adding {lang.code}")
                    volunteer.languages_spoken = languages_to_add

            if volunteer.language.count() == 0:
                volunteer.languages_spoken = ["en"]
            volunteer.save()
