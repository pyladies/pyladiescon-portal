from django.core.management.base import BaseCommand

from volunteer.languages import LANGUAGES
from volunteer.models import Language, VolunteerProfile


def populate_language_choices():
    """Populate the languages"""
    for code, name in LANGUAGES:
        if not Language.objects.filter(code=code).exists():
            Language.objects.create(code=code, name=name)


class Command(BaseCommand):
    help = "Migrate Volunteer languages_spoken field to the Language model."

    def handle(self, *args, **options):
        populate_language_choices()
        for volunteer in VolunteerProfile.objects.filter(
            languages_spoken__isnull=False
        ):
            for lang_code in volunteer.languages_spoken:
                language = Language.objects.filter(code=lang_code).first()
                if language and not volunteer.language.filter(code=lang_code).exists():
                    volunteer.language.add(language)
