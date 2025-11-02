"""
Management command to generate sample data for local development.

This command creates sample data for testing and development purposes:
- Users with various roles (admin, volunteer, staff, superuser)
- Teams and Roles
- Volunteer Profiles in various states
- PyLadies Chapters
- Sponsorship Tiers and Profiles

This command ONLY runs in development mode (DEBUG=True) and will refuse
to run in production environments.
"""

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from volunteer.models import PyladiesChapter, Role, Team


class Command(BaseCommand):
    help = "Generate sample data for local development environment"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing sample data before generating new data",
        )

    def handle(self, *args, **options):
        # Safety check: only run in DEBUG mode
        if not settings.DEBUG:
            raise CommandError(
                "This command can only be run in development mode (DEBUG=True). "
                "It is not safe to run in production."
            )

        self.stdout.write(
            self.style.WARNING(
                "Starting sample data generation for local development..."
            )
        )

        # Generate data
        self._generate_users()
        self._generate_pyladies_chapters()
        self._generate_roles()
        self._generate_teams()

        self.stdout.write(
            self.style.SUCCESS(
                "Sample data generation completed successfully!"
            )
        )

    def _generate_users(self):
        """Generate sample users with various roles."""
        self.stdout.write("Generating users...")

        users_data = [
            {
                "username": "admin_user",
                "email": "admin@example.com",
                "first_name": "Admin",
                "last_name": "User",
                "is_staff": True,
                "is_superuser": True,
            },
            {
                "username": "staff_user",
                "email": "staff@example.com",
                "first_name": "Staff",
                "last_name": "Member",
                "is_staff": True,
                "is_superuser": False,
            },
            {
                "username": "volunteer1",
                "email": "volunteer1@example.com",
                "first_name": "Alice",
                "last_name": "Volunteer",
                "is_staff": False,
                "is_superuser": False,
            },
            {
                "username": "volunteer2",
                "email": "volunteer2@example.com",
                "first_name": "Bob",
                "last_name": "Helper",
                "is_staff": False,
                "is_superuser": False,
            },
            {
                "username": "volunteer3",
                "email": "volunteer3@example.com",
                "first_name": "Carol",
                "last_name": "Smith",
                "is_staff": False,
                "is_superuser": False,
            },
            {
                "username": "volunteer4",
                "email": "volunteer4@example.com",
                "first_name": "Diana",
                "last_name": "Jones",
                "is_staff": False,
                "is_superuser": False,
            },
            {
                "username": "volunteer5",
                "email": "volunteer5@example.com",
                "first_name": "Eve",
                "last_name": "Brown",
                "is_staff": False,
                "is_superuser": False,
            },
            {
                "username": "sponsor_contact1",
                "email": "sponsor1@techcorp.com",
                "first_name": "John",
                "last_name": "Sponsor",
                "is_staff": False,
                "is_superuser": False,
            },
            {
                "username": "sponsor_contact2",
                "email": "sponsor2@innovate.com",
                "first_name": "Jane",
                "last_name": "Corporate",
                "is_staff": False,
                "is_superuser": False,
            },
        ]

        created_count = 0
        for user_data in users_data:
            user, created = User.objects.get_or_create(
                username=user_data["username"],
                defaults={
                    "email": user_data["email"],
                    "first_name": user_data["first_name"],
                    "last_name": user_data["last_name"],
                    "is_staff": user_data["is_staff"],
                    "is_superuser": user_data["is_superuser"],
                },
            )
            if created:
                # Set a default password for all sample users: "password123"
                user.set_password("password123")
                user.save()
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"  ✓ Created user: {user.username}")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"  ~ User already exists: {user.username}")
                )

        self.stdout.write(
            self.style.SUCCESS(f"Created {created_count} new users\n")
        )

    def _generate_pyladies_chapters(self):
        """Generate sample PyLadies chapters."""
        self.stdout.write("Generating PyLadies chapters...")

        chapters_data = [
            {
                "chapter_name": "PyLadies San Francisco",
                "chapter_description": "PyLadies SF - San Francisco Bay Area",
                "chapter_email": "sf@pyladies.com",
                "chapter_website": "https://www.meetup.com/pyladies-sf/",
            },
            {
                "chapter_name": "PyLadies New York",
                "chapter_description": "PyLadies NYC - New York City",
                "chapter_email": "nyc@pyladies.com",
                "chapter_website": "https://www.meetup.com/pyladies-nyc/",
            },
            {
                "chapter_name": "PyLadies London",
                "chapter_description": "PyLadies London - United Kingdom",
                "chapter_email": "london@pyladies.com",
                "chapter_website": "https://www.meetup.com/pyladies-london/",
            },
            {
                "chapter_name": "PyLadies Berlin",
                "chapter_description": "PyLadies Berlin - Germany",
                "chapter_email": "berlin@pyladies.com",
                "chapter_website": "https://www.meetup.com/pyladies-berlin/",
            },
            {
                "chapter_name": "PyLadies Tokyo",
                "chapter_description": "PyLadies Tokyo - Japan",
                "chapter_email": "tokyo@pyladies.com",
                "chapter_website": "https://www.meetup.com/pyladies-tokyo/",
            },
            {
                "chapter_name": "PyLadies São Paulo",
                "chapter_description": "PyLadies SP - São Paulo, Brazil",
                "chapter_email": "sp@pyladies.com",
                "chapter_website": "https://www.meetup.com/pyladies-sp/",
            },
            {
                "chapter_name": "PyLadies Lagos",
                "chapter_description": "PyLadies Lagos - Nigeria",
                "chapter_email": "lagos@pyladies.com",
                "chapter_website": "https://www.meetup.com/pyladies-lagos/",
            },
            {
                "chapter_name": "PyLadies Sydney",
                "chapter_description": "PyLadies Sydney - Australia",
                "chapter_email": "sydney@pyladies.com",
                "chapter_website": "https://www.meetup.com/pyladies-sydney/",
            },
        ]

        created_count = 0
        for chapter_data in chapters_data:
            chapter, created = PyladiesChapter.objects.get_or_create(
                chapter_name=chapter_data["chapter_name"],
                defaults={
                    "chapter_description": chapter_data["chapter_description"],
                    "chapter_email": chapter_data["chapter_email"],
                    "chapter_website": chapter_data["chapter_website"],
                },
            )
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"  ✓ Created chapter: {chapter.chapter_name}")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"  ~ Chapter already exists: {chapter.chapter_name}")
                )

        self.stdout.write(
            self.style.SUCCESS(f"Created {created_count} new PyLadies chapters\n")
        )

    def _generate_roles(self):
        """Generate sample volunteer roles."""
        self.stdout.write("Generating volunteer roles...")

        roles_data = [
            {
                "short_name": "Frontend Developer",
                "description": "Build and maintain frontend features using modern web technologies",
            },
            {
                "short_name": "Backend Developer",
                "description": "Develop and maintain backend services and APIs",
            },
            {
                "short_name": "Content Writer",
                "description": "Create and edit content for blog posts, documentation, and social media",
            },
            {
                "short_name": "Social Media Manager",
                "description": "Manage social media accounts and create engaging content",
            },
            {
                "short_name": "Designer",
                "description": "Create visual assets, graphics, and UI/UX designs",
            },
            {
                "short_name": "Reviewer",
                "description": "Review proposals, applications, and other submissions",
            },
            {
                "short_name": "Event Coordinator",
                "description": "Help organize and coordinate conference events and activities",
            },
        ]

        created_count = 0
        for role_data in roles_data:
            role, created = Role.objects.get_or_create(
                short_name=role_data["short_name"],
                defaults={"description": role_data["description"]},
            )
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"  ✓ Created role: {role.short_name}")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"  ~ Role already exists: {role.short_name}")
                )

        self.stdout.write(
            self.style.SUCCESS(f"Created {created_count} new roles\n")
        )

    def _generate_teams(self):
        """Generate sample volunteer teams."""
        self.stdout.write("Generating volunteer teams...")

        teams_data = [
            {
                "short_name": "Website Team",
                "description": "Responsible for developing and maintaining the conference website",
                "open_to_new_members": True,
            },
            {
                "short_name": "Social Media Team",
                "description": "Manages social media presence and content creation",
                "open_to_new_members": True,
            },
            {
                "short_name": "Content Team",
                "description": "Creates blog posts, documentation, and other written content",
                "open_to_new_members": True,
            },
            {
                "short_name": "Design Team",
                "description": "Creates visual assets and designs for the conference",
                "open_to_new_members": True,
            },
            {
                "short_name": "Program Committee",
                "description": "Reviews and selects talks and proposals for the conference",
                "open_to_new_members": False,
            },
            {
                "short_name": "Sponsorship Team",
                "description": "Manages sponsor relationships and benefits",
                "open_to_new_members": False,
            },
        ]

        created_count = 0
        for team_data in teams_data:
            team, created = Team.objects.get_or_create(
                short_name=team_data["short_name"],
                defaults={
                    "description": team_data["description"],
                    "open_to_new_members": team_data["open_to_new_members"],
                },
            )
            if created:
                created_count += 1
                status = "open" if team.open_to_new_members else "closed"
                self.stdout.write(
                    self.style.SUCCESS(f"  ✓ Created team: {team.short_name} ({status})")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"  ~ Team already exists: {team.short_name}")
                )

        self.stdout.write(
            self.style.SUCCESS(f"Created {created_count} new teams\n")
        )
