from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command

from sponsorship.models import IndividualDonation, SponsorshipProfile, SponsorshipTier
from volunteer.models import PyladiesChapter, Role, Team, VolunteerProfile


@pytest.mark.django_db
class TestMakeSuperuserCommand:
    def test_makesuperuser_no_such_user(self):
        out = StringIO()
        call_command("makesuperuser", "testuser", stdout=out)
        assert "No such user" in out.getvalue()

    def test_makesuperuser_success(self):
        user = User.objects.create_user(username="testuser")
        assert user.is_superuser is False

        out = StringIO()
        call_command("makesuperuser", "testuser", stdout=out)
        assert f"{user.username} is now a superuser" in out.getvalue()
        user.refresh_from_db()
        assert user.is_superuser


@pytest.mark.django_db
class TestGenerateSampleDataCommand:
    def test_command_fails_without_debug_mode(self, settings):
        """Test that the command refuses to run when DEBUG=False."""
        settings.DEBUG = False
        out = StringIO()

        with pytest.raises(CommandError) as exc_info:
            call_command("generate_sample_data", stdout=out)

        assert "can only be run in development mode" in str(exc_info.value)

    def test_command_succeeds_in_debug_mode(self, settings):
        """Test that the command runs successfully when DEBUG=True."""
        settings.DEBUG = True
        out = StringIO()

        call_command("generate_sample_data", stdout=out)
        output = out.getvalue()

        assert "Starting sample data generation" in output
        assert "Sample data generation completed successfully" in output

    def test_generates_users(self, settings):
        """Test that users are created with correct attributes."""
        settings.DEBUG = True
        initial_count = User.objects.count()

        call_command("generate_sample_data", stdout=StringIO())

        # Check that users were created
        assert User.objects.count() > initial_count

        # Check admin user
        admin = User.objects.get(username="admin_user")
        assert admin.is_staff
        assert admin.is_superuser

        # Check staff user
        staff = User.objects.get(username="staff_user")
        assert staff.is_staff
        assert not staff.is_superuser

        # Check volunteer users
        volunteers = User.objects.filter(username__startswith="volunteer")
        assert volunteers.count() >= 5
        for volunteer in volunteers:
            assert not volunteer.is_staff
            assert not volunteer.is_superuser

    def test_generates_chapters(self, settings):
        """Test that PyLadies chapters are created."""
        settings.DEBUG = True
        initial_count = PyladiesChapter.objects.count()

        call_command("generate_sample_data", stdout=StringIO())

        assert PyladiesChapter.objects.count() > initial_count
        assert PyladiesChapter.objects.filter(chapter_name="San Francisco").exists()
        assert PyladiesChapter.objects.filter(chapter_name="Tokyo").exists()

    def test_generates_roles(self, settings):
        """Test that volunteer roles are created."""
        settings.DEBUG = True
        initial_count = Role.objects.count()

        call_command("generate_sample_data", stdout=StringIO())

        assert Role.objects.count() > initial_count
        assert Role.objects.filter(short_name="Frontend Developer").exists()
        assert Role.objects.filter(short_name="Designer").exists()

    def test_generates_teams(self, settings):
        """Test that teams are created with correct attributes."""
        settings.DEBUG = True
        initial_count = Team.objects.count()

        call_command("generate_sample_data", stdout=StringIO())

        assert Team.objects.count() > initial_count

        # Check open team
        website_team = Team.objects.get(short_name="Website Team")
        assert website_team.open_to_new_members

        # Check closed team
        program_committee = Team.objects.get(short_name="Program Committee")
        assert not program_committee.open_to_new_members

    def test_generates_volunteer_profiles(self, settings):
        """Test that volunteer profiles are created with various statuses."""
        settings.DEBUG = True
        initial_count = VolunteerProfile.objects.count()

        call_command("generate_sample_data", stdout=StringIO())

        assert VolunteerProfile.objects.count() > initial_count

        # Check approved profile
        approved_profiles = VolunteerProfile.objects.filter(
            application_status="Approved"
        )
        assert approved_profiles.count() >= 2

        # Check pending profile
        assert VolunteerProfile.objects.filter(
            application_status="Pending Review"
        ).exists()

        # Check waitlisted profile
        assert VolunteerProfile.objects.filter(application_status="Waitlisted").exists()

    def test_generates_sponsorship_tiers(self, settings):
        """Test that sponsorship tiers are created."""
        settings.DEBUG = True
        initial_count = SponsorshipTier.objects.count()

        call_command("generate_sample_data", stdout=StringIO())

        assert SponsorshipTier.objects.count() > initial_count

        championship = SponsorshipTier.objects.get(name="Championship")
        assert championship.amount == 25000.00

        community = SponsorshipTier.objects.get(name="Community")
        assert community.amount == 2500.00

    def test_generates_sponsorship_profiles(self, settings):
        """Test that sponsorship profiles are created."""
        settings.DEBUG = True
        initial_count = SponsorshipProfile.objects.count()

        call_command("generate_sample_data", stdout=StringIO())

        assert SponsorshipProfile.objects.count() > initial_count
        assert SponsorshipProfile.objects.filter(
            organization_name="TechCorp International"
        ).exists()
        assert SponsorshipProfile.objects.filter(
            organization_name="PyTools Foundation"
        ).exists()

    def test_command_is_idempotent(self, settings):
        """Test that running the command multiple times doesn't create duplicates."""
        settings.DEBUG = True

        # Run command twice
        call_command("generate_sample_data", stdout=StringIO())
        first_run_counts = {
            "users": User.objects.count(),
            "chapters": PyladiesChapter.objects.count(),
            "roles": Role.objects.count(),
            "teams": Team.objects.count(),
            "profiles": VolunteerProfile.objects.count(),
            "tiers": SponsorshipTier.objects.count(),
            "sponsorships": SponsorshipProfile.objects.count(),
            "donations": IndividualDonation.objects.count(),
        }

        call_command("generate_sample_data", stdout=StringIO())
        second_run_counts = {
            "users": User.objects.count(),
            "chapters": PyladiesChapter.objects.count(),
            "roles": Role.objects.count(),
            "teams": Team.objects.count(),
            "profiles": VolunteerProfile.objects.count(),
            "tiers": SponsorshipTier.objects.count(),
            "sponsorships": SponsorshipProfile.objects.count(),
            "donations": IndividualDonation.objects.count(),
        }

        # Counts should be the same
        assert first_run_counts == second_run_counts

    def test_volunteer_profiles_have_relationships(self, settings):
        """Test that volunteer profiles are properly associated with teams and roles."""
        settings.DEBUG = True

        call_command("generate_sample_data", stdout=StringIO())

        # Check that approved volunteers have teams and roles
        approved_profile = VolunteerProfile.objects.filter(
            application_status="Approved"
        ).first()
        assert approved_profile is not None
        assert approved_profile.teams.count() > 0
        assert approved_profile.roles.count() > 0

    def test_sponsorship_profiles_have_tiers(self, settings):
        """Test that sponsorship profiles are associated with tiers."""
        settings.DEBUG = True

        call_command("generate_sample_data", stdout=StringIO())

        sponsorship = SponsorshipProfile.objects.filter(
            organization_name="TechCorp International"
        ).first()
        assert sponsorship is not None
        assert sponsorship.sponsorship_tier is not None
        assert sponsorship.main_contact_user is not None

    def test_skips_volunteer_profiles_without_volunteers(self, settings, monkeypatch):
        """Test that volunteer profile generation is skipped when no volunteers exist."""
        settings.DEBUG = True
        out = StringIO()

        # Mock the User queryset to return no volunteers
        original_filter = User.objects.filter

        def mock_filter(*args, **kwargs):
            result = original_filter(*args, **kwargs)
            # If filtering for volunteers, return empty queryset
            if (
                "username__startswith" in kwargs
                and kwargs["username__startswith"] == "volunteer"
            ):
                return User.objects.none()
            return result

        monkeypatch.setattr(User.objects, "filter", mock_filter)

        call_command("generate_sample_data", stdout=out)
        output = out.getvalue()

        assert "No volunteer users found" in output

    def test_skips_sponsorship_profiles_without_sponsors(self, settings, monkeypatch):
        """Test that sponsorship profile generation is skipped when no sponsor contacts exist."""
        settings.DEBUG = True
        out = StringIO()

        # Mock the User queryset to return no sponsor contacts
        original_filter = User.objects.filter

        def mock_filter(*args, **kwargs):
            result = original_filter(*args, **kwargs)
            # If filtering for sponsor contacts, return empty queryset
            if (
                "username__startswith" in kwargs
                and kwargs["username__startswith"] == "sponsor_contact"
            ):
                return User.objects.none()
            return result

        monkeypatch.setattr(User.objects, "filter", mock_filter)

        call_command("generate_sample_data", stdout=out)
        output = out.getvalue()

        assert "No sponsor contact users found" in output

    def test_skips_sponsorship_profiles_without_tiers(self, settings, monkeypatch):
        """Test that sponsorship profile generation is skipped when no tiers exist."""
        settings.DEBUG = True
        out = StringIO()

        # Mock SponsorshipTier.objects.all() to return empty queryset
        def mock_all():
            return SponsorshipTier.objects.none()

        monkeypatch.setattr(SponsorshipTier.objects, "all", mock_all)

        call_command("generate_sample_data", stdout=out)
        output = out.getvalue()

        assert "No sponsorship tiers found" in output

    def test_generates_donations(self, settings):
        """Test that Donations are generated are associated with tiers."""
        settings.DEBUG = True

        assert IndividualDonation.objects.count() == 0

        call_command("generate_sample_data", stdout=StringIO())

        assert IndividualDonation.objects.count() == 5
