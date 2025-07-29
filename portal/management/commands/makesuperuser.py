from django.contrib.auth.models import User
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Make the user a superuser"

    def add_arguments(self, parser):
        parser.add_argument("username", help="Username to be made into superuser")

    def handle(self, *args, **options):

        users = User.objects.filter(username=options["username"])
        if len(users) > 0:
            user = users[0]
            user.is_staff = True
            user.is_superuser = True
            user.save()
            self.stdout.write(
                self.style.SUCCESS(f"User {user.username} is now a superuser")
            )
        else:
            self.stdout.write(self.style.ERROR(f"No such user {options['username']}"))
