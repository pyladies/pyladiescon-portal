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
from django.db.models.signals import post_save

from volunteer.constants import ApplicationStatus, Region
from volunteer.models import PyladiesChapter, Role, Team, VolunteerProfile, volunteer_profile_signal


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
        self._generate_volunteer_profiles()

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

    def _generate_volunteer_profiles(self):
        """Generate sample volunteer profiles with various statuses."""
        self.stdout.write("Generating volunteer profiles...")

        # Temporarily disable the post_save signal to avoid sending emails during data generation
        post_save.disconnect(volunteer_profile_signal, sender=VolunteerProfile)
        
        try:
            self._create_volunteer_profiles()
        finally:
            # Re-enable the signal
            post_save.connect(volunteer_profile_signal, sender=VolunteerProfile)

    def _create_volunteer_profiles(self):
        """Create the actual volunteer profiles."""
        # Get the volunteers (non-staff users)
        volunteers = User.objects.filter(username__startswith="volunteer")
        
        # Get teams, roles, and chapters for assignment
        teams = list(Team.objects.all())
        roles = list(Role.objects.all())
        chapters = list(PyladiesChapter.objects.all())
        
        if not volunteers.exists():
            self.stdout.write(
                self.style.WARNING("  ! No volunteer users found. Skipping profile generation.\n")
            )
            return
        
        profiles_data = [
            {
                "user": volunteers[0],  # volunteer1
                "status": ApplicationStatus.APPROVED,
                "discord_username": "alice_vol",
                "github_username": "alice-volunteer",
                "region": Region.NORTH_AMERICA,
                "availability_hours_per_week": 10,
                "teams": teams[:2] if len(teams) >= 2 else teams,  # Website & Social Media
                "roles": roles[:2] if len(roles) >= 2 else roles,  # Frontend & Backend
                "chapter": chapters[0] if chapters else None,  # San Francisco
            },
            {
                "user": volunteers[1],  # volunteer2
                "status": ApplicationStatus.APPROVED,
                "discord_username": "bob_helper",
                "instagram_username": "bob_pyladies",
                "region": Region.EUROPE,
                "availability_hours_per_week": 5,
                "teams": teams[1:3] if len(teams) >= 3 else teams,  # Social Media & Content
                "roles": [roles[3]] if len(roles) >= 4 else [],  # Social Media Manager
                "chapter": chapters[2] if len(chapters) >= 3 else None,  # London
            },
            {
                "user": volunteers[2],  # volunteer3
                "status": ApplicationStatus.PENDING,
                "discord_username": "carol_smith",
                "github_username": "carol-codes",
                "region": Region.ASIA,
                "availability_hours_per_week": 8,
                "teams": [],  # No team assignment yet (pending)
                "roles": [roles[2]] if len(roles) >= 3 else [],  # Content Writer
                "chapter": chapters[4] if len(chapters) >= 5 else None,  # Tokyo
            },
            {
                "user": volunteers[3],  # volunteer4
                "status": ApplicationStatus.WAITLISTED,
                "discord_username": "diana_jones",
                "bluesky_username": "diana.bsky.social",
                "region": Region.SOUTH_AMERICA,
                "availability_hours_per_week": 3,
                "teams": [],  # No team assignment (waitlisted)
                "roles": [roles[4]] if len(roles) >= 5 else [],  # Designer
                "chapter": chapters[5] if len(chapters) >= 6 else None,  # São Paulo
            },
            {
                "user": volunteers[4],  # volunteer5
                "status": ApplicationStatus.REJECTED,
                "discord_username": "eve_brown",
                "x_username": "eve_pyladies",
                "region": Region.AFRICA,
                "availability_hours_per_week": 2,
                "teams": [],  # No team assignment (rejected)
                "roles": [],  # No roles assigned
                "chapter": chapters[6] if len(chapters) >= 7 else None,  # Lagos
            },
        ]
        
        created_count = 0
        for profile_data in profiles_data:
            profile, created = VolunteerProfile.objects.get_or_create(
                user=profile_data["user"],
                defaults={
                    "application_status": profile_data["status"],
                    "discord_username": profile_data["discord_username"],
                    "github_username": profile_data.get("github_username", ""),
                    "instagram_username": profile_data.get("instagram_username", ""),
                    "bluesky_username": profile_data.get("bluesky_username", ""),
                    "x_username": profile_data.get("x_username", ""),
                    "region": profile_data["region"],
                    "availability_hours_per_week": profile_data["availability_hours_per_week"],
                    "chapter": profile_data["chapter"],
                },
            )
            
            if created:
                # Add many-to-many relationships
                if profile_data["teams"]:
                    profile.teams.set(profile_data["teams"])
                if profile_data["roles"]:
                    profile.roles.set(profile_data["roles"])
                
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ Created profile for {profile.user.username} ({profile.application_status})"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"  ~ Profile already exists for {profile.user.username}"
                    )
                )
        
        self.stdout.write(
            self.style.SUCCESS(f"Created {created_count} new volunteer profiles\n")
        )
