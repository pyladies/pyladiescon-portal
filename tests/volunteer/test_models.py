import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.urls import reverse

from volunteer.constants import ApplicationStatus, Region, RoleTypes
from volunteer.languages import LANGUAGES
from volunteer.models import (
    PyladiesChapter,
    Role,
    Team,
    VolunteerProfile,
    send_internal_volunteer_onboarding_email,
    send_volunteer_onboarding_email,
)


@pytest.mark.django_db
class TestVolunteerModel:
    def test_volunteer_profile(self, portal_user):
        """Test basic volunteer profile creation and URL generation."""
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0][0]]
        profile.region = Region.NORTH_AMERICA
        profile.discord_username = "mydiscord"
        profile.save()

        assert profile.get_absolute_url() == reverse(
            "volunteer:volunteer_profile_edit", kwargs={"pk": profile.pk}
        )

    def test_profile_str_representation(self, portal_user):
        """Test string representation of VolunteerProfile."""
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0][0]]
        profile.region = Region.NORTH_AMERICA
        profile.discord_username = "mydiscord"
        assert str(profile) == portal_user.username

    def test_team_str_representation(self):
        """Test string representation of Team."""
        team = Team(short_name="Test Team", description="Test Description")
        team.save()
        assert str(team) == "Test Team"

    def test_role_str_representation(self):
        """Test string representation of Role."""
        role = Role(short_name="Test Role", description="Test Description")
        role.save()
        assert str(role) == "Test Role"

    def test_pyladies_chapter_representation(self):
        """Test string representation of PyLadies Chapter."""
        chapter = PyladiesChapter(
            chapter_name="vancouver", chapter_description="Vancouver, Canada"
        )
        chapter.save()
        assert str(chapter) == "Vancouver, Canada"

    def test_pyladies_chapter_is_unique_ignore_case(self):
        """Test PyLadies chapter is unique."""
        chapter = PyladiesChapter(
            chapter_name="vancouver", chapter_description="Vancouver, Canada"
        )
        chapter.save()
        with pytest.raises(IntegrityError):
            PyladiesChapter.objects.create(
                chapter_name="Vancouver", chapter_description="Vancouver, Canada"
            )

    def test_team_relationships(self, portal_user):
        """Test team relationships with volunteers."""
        team = Team.objects.create(
            short_name="Dev Team", description="Development Team"
        )
        profile = VolunteerProfile.objects.create(
            user=portal_user,
            languages_spoken=["en"],
            region=Region.NORTH_AMERICA,
            discord_username="mydiscord",
        )
        team.team_leads.add(profile)
        profile.teams.add(team)

        assert profile in team.team_leads.all()
        assert team in profile.teams.all()

    def test_role_relationships(self, portal_user):
        """Test role relationships with volunteers."""
        role = Role.objects.create(
            short_name="Developer", description="Software Developer"
        )
        profile = VolunteerProfile.objects.create(
            user=portal_user, languages_spoken=["en"], region=Region.NORTH_AMERICA
        )
        profile.roles.add(role)

        assert role in profile.roles.all()
        assert profile in role.roles.all()

    def test_volunteer_profile_validation(self, portal_user):
        """Test validation of volunteer profile fields."""
        profile = VolunteerProfile(
            user=portal_user,
            languages_spoken=["en"],
            region=Region.NORTH_AMERICA,
            github_username="valid-username",
            discord_username="valid.username",
            instagram_username="valid.username",
            bluesky_username="valid.username",
            mastodon_url="@user@instance.social",
            x_username="valid_username",
            linkedin_url="linkedin.com/in/username",
        )
        profile.full_clean()

    @pytest.mark.parametrize(
        "field,value,expected_error",
        [
            ("github_username", "-invalid", "GitHub username can only contain"),
            ("discord_username", "invalid@name", "Discord username must consist"),
            (
                "instagram_username",
                "invalid@name",
                "Instagram username can only contain",
            ),
            ("bluesky_username", "_invalid", "Invalid Bluesky username format"),
            ("mastodon_url", "invalid@format", "Invalid Mastodon URL format"),
            ("x_username", "invalid-name", "X/Twitter username can only contain"),
            ("linkedin_url", "invalid-url", "Invalid LinkedIn URL format"),
        ],
    )
    def test_invalid_social_media_fields(
        self, portal_user, field, value, expected_error
    ):
        """Test validation of invalid social media fields."""
        profile = VolunteerProfile(
            user=portal_user,
            languages_spoken=["en"],
            region=Region.NORTH_AMERICA,
            **{field: value},
        )

        with pytest.raises(ValidationError) as excinfo:
            profile.full_clean()

        assert expected_error in str(excinfo.value)

    def test_application_status_default(self, portal_user):
        """Test that application_status defaults to PENDING."""
        profile = VolunteerProfile.objects.create(
            user=portal_user, languages_spoken=["en"], region=Region.NORTH_AMERICA
        )
        assert profile.application_status == "Pending Review"

    def test_region_choices(self, portal_user):
        """Test that region must be from the predefined choices."""
        profile = VolunteerProfile(
            user=portal_user, languages_spoken=["en"], region="INVALID"
        )

        with pytest.raises(ValidationError) as excinfo:
            profile.full_clean()

        assert "region" in str(excinfo.value)

    def test_languages_spoken_validation(self, portal_user):
        """Test that languages_spoken must be from LANGUAGES."""
        profile = VolunteerProfile(
            user=portal_user,
            languages_spoken=["invalid_language"],
            region=Region.NORTH_AMERICA,
        )

        with pytest.raises(ValidationError) as excinfo:
            profile.full_clean()

        assert "languages_spoken" in str(excinfo.value)

    def test_linkedin_url_protocol_not_added_in_model(self, portal_user):
        """Test that LinkedIn URL protocol isn't added during model validation."""
        profile = VolunteerProfile(
            user=portal_user,
            languages_spoken=["en"],
            region=Region.NORTH_AMERICA,
            discord_username="validuser123",
            linkedin_url="linkedin.com/in/username",
        )
        profile.full_clean()
        assert profile.linkedin_url == "linkedin.com/in/username"

    def test_linkedin_url_validation(self, portal_user):
        """Test LinkedIn URL validation in the model."""
        valid_urls = [
            "https://linkedin.com/in/username",
            "http://linkedin.com/in/username",
            "https://www.linkedin.com/in/username",
            "linkedin.com/in/username",
            "https://linkedin.com/company/pyladiescon",
            "https://www.linkedin.com/school/some-school",
            "https://linkedin.com/in/rãé-gómez-Łukasz-Schröder-Jürgen-süß",
        ]

        for url in valid_urls:
            profile = VolunteerProfile(
                user=portal_user,
                languages_spoken=["en"],
                region=Region.NORTH_AMERICA,
                discord_username="validuser123",
                linkedin_url=url,
            )
            profile.full_clean()

    def test_linkedin_url_with_path_slash(self, portal_user):
        """Test that LinkedIn URL with trailing slash is valid."""
        profile = VolunteerProfile(
            user=portal_user,
            languages_spoken=["en"],
            region=Region.NORTH_AMERICA,
            discord_username="validuser123",
            linkedin_url="https://linkedin.com/in/username/",
        )
        profile.full_clean()
        assert profile.linkedin_url == "https://linkedin.com/in/username/"

    def test_linkedin_url_validation_error_message(self, portal_user):
        """Test LinkedIn URL validation error message."""
        profile = VolunteerProfile(
            user=portal_user,
            languages_spoken=["en"],
            region=Region.NORTH_AMERICA,
            discord_username="validuser123",
            linkedin_url="invalid-url",
        )

        with pytest.raises(ValidationError) as excinfo:
            profile.full_clean()

        assert "linkedin_url" in str(excinfo.value)
        assert "Invalid LinkedIn URL format" in str(excinfo.value)

    def test_linkedin_url_validation_with_invalid_chars(self, portal_user):
        """Test LinkedIn URL validation with invalid characters.

        For now as long as it starts with linkedin domain, we'll consider it valid.
        """
        profile = VolunteerProfile(
            user=portal_user,
            languages_spoken=["en"],
            region=Region.NORTH_AMERICA,
            discord_username="validuser123",
            linkedin_url="linkedin.com/in/user@name",
        )

        profile.full_clean()

    def test_linkedin_url_invalid_domain(self, portal_user):
        """Test LinkedIn URL validation with invalid domain format."""
        profile = VolunteerProfile(
            user=portal_user,
            languages_spoken=["en"],
            region=Region.NORTH_AMERICA,
            discord_username="validuser123",
            linkedin_url="https://invalid-domain.com/in/username",
        )

        with pytest.raises(ValidationError) as excinfo:
            profile.full_clean()

        assert "linkedin_url" in str(excinfo.value)
        assert "Invalid LinkedIn URL format" in str(excinfo.value)

    def test_linkedin_url_missing_in_path(self, portal_user):
        """Test LinkedIn URL validation when missing '/in/' in path."""
        profile = VolunteerProfile(
            user=portal_user,
            languages_spoken=["en"],
            region=Region.NORTH_AMERICA,
            discord_username="validuser123",
            linkedin_url="https://linkedin.com/username",
        )

        with pytest.raises(ValidationError) as excinfo:
            profile.full_clean()

        assert "linkedin_url" in str(excinfo.value)
        assert "Invalid LinkedIn URL format" in str(excinfo.value)

    def test_linkedin_url_with_uppercase(self, portal_user):
        """Test LinkedIn URL validation with uppercase letters in path."""
        profile = VolunteerProfile(
            user=portal_user,
            languages_spoken=["en"],
            region=Region.NORTH_AMERICA,
            discord_username="validuser123",
            linkedin_url="https://linkedin.com/in/UserName",
        )
        profile.full_clean()
        assert profile.linkedin_url == "https://linkedin.com/in/UserName"

    def test_discord_username_length_validation(self, portal_user):
        """Test Discord username validation for length constraints."""
        profile = VolunteerProfile(
            user=portal_user,
            languages_spoken=["en"],
            region=Region.NORTH_AMERICA,
            discord_username="a",
        )

        with pytest.raises(ValidationError) as excinfo:
            profile.full_clean()

        assert "Discord username must be between 2 and 32 characters" in str(
            excinfo.value
        )

        profile.discord_username = "a" * 33

        with pytest.raises(ValidationError) as excinfo:
            profile.full_clean()

        assert "Discord username must be between 2 and 32 characters" in str(
            excinfo.value
        )

    def test_email_is_sent_after_saved(self, portal_user):
        # set up an admin account to receive internal notification email
        admin_role = Role.objects.create(
            short_name=RoleTypes.ADMIN, description="Admin role"
        )
        admin_user_to_notify = User.objects.create_superuser(
            username="testadmin",
            email="test-admin@example.com",
            password="pyladiesadmin123",
        )
        admin_profile = VolunteerProfile(user=admin_user_to_notify)
        admin_profile.languages_spoken = [LANGUAGES[0]]
        admin_profile.region = Region.NORTH_AMERICA
        admin_profile.save()

        User.objects.create_superuser(
            username="testsuperuser",
            email="superusertest@example.com",
            password="supersuper123",
        )

        admin_profile.roles.add(admin_role)
        admin_profile.save()

        mail.outbox.clear()

        # the actual process to test
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.region = Region.NORTH_AMERICA
        profile.save()

        # 3 emails were sent:
        # - #1 to the user with admin role
        # - #2 to the super user
        # - #3 to the applicant
        assert len(mail.outbox) == 3
        assert (  # user creation, to internal staff
            str(mail.outbox[0].subject)
            == f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} New Volunteer Application"
        )
        assert (  # user creation, to internal staff
            str(mail.outbox[1].subject)
            == f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} New Volunteer Application"
        )

        assert (  # user creation, to user
            str(mail.outbox[2].subject)
            == f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Volunteer Application Received"
        )

    def test_email_is_sent_after_updated(self, portal_user):
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.region = Region.NORTH_AMERICA
        profile.save()
        mail.outbox.clear()

        profile.region = Region.ASIA
        profile.save()

        assert (
            str(mail.outbox[0].subject)
            == f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Volunteer Application Updated"
        )

    def test_volunteer_notification_email_contains_info(self, portal_user):
        chapter = PyladiesChapter.objects.create(
            chapter_name="vancouver", chapter_description="Vancouver, Canada"
        )

        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0], LANGUAGES[1]]
        profile.region = Region.NORTH_AMERICA
        profile.bluesky_username = "mybsky"
        profile.discord_username = "mydiscord"
        profile.github_username = "mygithub"
        profile.instagram_username = "myinstagram"
        profile.mastodon_url = "mymastodon"
        profile.x_username = "myxusername"
        profile.linkedin_url = "mylinkedin"
        profile.chapter = chapter
        profile.additional_comments = "mycomments"
        profile.availability_hours_per_week = 30

        profile.save()

        body = str(mail.outbox[0].body)
        assert profile.bluesky_username in body
        assert profile.discord_username in body
        assert profile.github_username in body
        assert profile.instagram_username in body
        assert profile.mastodon_url in body
        assert profile.x_username in body
        assert profile.linkedin_url in body
        assert profile.region in body
        assert profile.languages_spoken[0][0] in body
        assert profile.user.first_name in body
        assert profile.chapter.chapter_description in body
        assert profile.additional_comments in body
        assert str(profile.availability_hours_per_week) in body

        assert reverse("volunteer:index") in body

    def test_volunteer_onboarding_email_contains_info(self, portal_user, settings):
        settings.GDRIVE_FOLDER_ID = "super-secret-folder-id"

        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0], LANGUAGES[1]]
        profile.region = Region.NORTH_AMERICA
        profile.discord_username = "mydiscord"
        profile.save()

        team = Team.objects.create(
            short_name="Super random team name", description="Development Team"
        )
        profile.teams.add(team)
        role = Role.objects.create(
            short_name="Obscure Role name", description="Test role desc"
        )
        profile.roles.add(role)

        profile.application_status = "Approved"

        mail.outbox.clear()
        send_volunteer_onboarding_email(profile)
        assert len(mail.outbox) == 1
        assert (
            str(mail.outbox[0].subject)
            == f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Welcome to the PyLadiesCon Volunteer Team"
        )
        # role name and team name in the body
        assert role.short_name in str(mail.outbox[0].body)
        assert team.short_name in str(mail.outbox[0].body)

        # gdrive info not in the body. It's for admin onboarding only
        assert "super-secret-folder-id" not in str(mail.outbox[0].body)

    def test_admin_onboarding_email_contains_info(self, portal_user, settings):
        settings.GDRIVE_FOLDER_ID = "super-secret-folder-id"

        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0], LANGUAGES[1]]
        profile.region = Region.NORTH_AMERICA
        profile.discord_username = "mydiscord"
        profile.save()

        team = Team.objects.create(
            short_name="Super random team name", description="Development Team"
        )
        profile.teams.add(team)
        admin_role = Role.objects.create(
            short_name=RoleTypes.ADMIN, description="Test role desc"
        )
        profile.roles.add(admin_role)

        profile.application_status = ApplicationStatus.APPROVED

        mail.outbox.clear()
        send_volunteer_onboarding_email(profile)
        assert len(mail.outbox) == 1
        assert (
            str(mail.outbox[0].subject)
            == f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Welcome to the PyLadiesCon Volunteer Team"
        )
        # role name and team name in the body
        assert admin_role.short_name in str(mail.outbox[0].body)
        assert team.short_name in str(mail.outbox[0].body)

        # gdrive info is in the body because this is an admin
        assert "super-secret-folder-id" in str(mail.outbox[0].body)

    @pytest.mark.parametrize(
        "application_status",
        [
            ApplicationStatus.PENDING,
            ApplicationStatus.REJECTED,
            ApplicationStatus.CANCELLED,
        ],
    )
    def test_onboarding_email_not_sent_if_not_approved(
        self, portal_user, application_status
    ):

        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0], LANGUAGES[1]]
        profile.region = Region.NORTH_AMERICA
        profile.discord_username = "mydiscord"
        profile.save()

        team = Team.objects.create(
            short_name="Super random team name", description="Development Team"
        )
        profile.teams.add(team)
        admin_role = Role.objects.create(
            short_name=RoleTypes.ADMIN, description="Test role desc"
        )
        profile.roles.add(admin_role)

        profile.application_status = application_status

        mail.outbox.clear()
        send_volunteer_onboarding_email(profile)
        assert len(mail.outbox) == 0

    def test_internal_volunteer_onboarding_email_contains_info(
        self, portal_user, settings
    ):
        settings.GDRIVE_FOLDER_ID = "super-secret-folder-id"

        admin_user_to_notify = User.objects.create_superuser(
            username="testadmin",
            email="test-admin@example.com",
            password="pyladiesadmin123",
        )
        admin_profile = VolunteerProfile(user=admin_user_to_notify)
        admin_profile.languages_spoken = [LANGUAGES[0]]
        admin_profile.region = Region.NORTH_AMERICA
        admin_profile.save()

        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0], LANGUAGES[1]]
        profile.region = Region.NORTH_AMERICA
        profile.discord_username = "mydiscord"
        profile.save()

        team = Team.objects.create(
            short_name="Super random team name", description="Development Team"
        )
        profile.teams.add(team)

        role = Role.objects.create(
            short_name="Obscure Role name", description="Test role desc"
        )
        profile.roles.add(role)

        profile.application_status = "Approved"

        mail.outbox.clear()
        send_internal_volunteer_onboarding_email(profile)
        assert len(mail.outbox) == 1
        assert (
            str(mail.outbox[0].subject)
            == f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Complete the Volunteer Onboarding for: {profile.user.first_name} {profile.user.last_name}"
        )
        # role name and team name in the body
        assert role.short_name in str(mail.outbox[0].body)
        assert team.short_name in str(mail.outbox[0].body)

        # gdrive info not in the body. It's for admin onboarding only
        assert "super-secret-folder-id" not in str(mail.outbox[0].body)

    def test_internal_admin_onboarding_email_contains_info(self, portal_user, settings):
        settings.GDRIVE_FOLDER_ID = "super-secret-folder-id"

        admin_user_to_notify = User.objects.create_superuser(
            username="testadmin",
            email="test-admin@example.com",
            password="pyladiesadmin123",
        )
        admin_profile = VolunteerProfile(user=admin_user_to_notify)
        admin_profile.languages_spoken = [LANGUAGES[0]]
        admin_profile.region = Region.NORTH_AMERICA
        admin_profile.save()

        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0], LANGUAGES[1]]
        profile.region = Region.NORTH_AMERICA
        profile.discord_username = "mydiscord"
        profile.save()

        team = Team.objects.create(
            short_name="Super random team name", description="Development Team"
        )
        profile.teams.add(team)
        admin_role = Role.objects.create(
            short_name=RoleTypes.ADMIN, description="Test role desc"
        )
        profile.roles.add(admin_role)

        profile.application_status = ApplicationStatus.APPROVED

        mail.outbox.clear()
        send_internal_volunteer_onboarding_email(profile)
        assert len(mail.outbox) == 1
        assert (
            str(mail.outbox[0].subject)
            == f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Complete the Volunteer Onboarding for: {profile.user.first_name} {profile.user.last_name}"
        )
        # role name and team name in the body
        assert admin_role.short_name in str(mail.outbox[0].body)
        assert team.short_name in str(mail.outbox[0].body)

        # gdrive info is in the body because this is an admin
        assert "super-secret-folder-id" in str(mail.outbox[0].body)

    @pytest.mark.parametrize(
        "application_status",
        [
            ApplicationStatus.PENDING,
            ApplicationStatus.REJECTED,
            ApplicationStatus.CANCELLED,
        ],
    )
    def test_internal_onboarding_email_not_sent_if_not_approved(
        self, portal_user, application_status
    ):

        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0], LANGUAGES[1]]
        profile.region = Region.NORTH_AMERICA
        profile.discord_username = "mydiscord"
        profile.save()

        team = Team.objects.create(
            short_name="Super random team name", description="Development Team"
        )
        profile.teams.add(team)
        admin_role = Role.objects.create(
            short_name=RoleTypes.ADMIN, description="Test role desc"
        )
        profile.roles.add(admin_role)

        profile.application_status = application_status

        mail.outbox.clear()
        send_internal_volunteer_onboarding_email(profile)
        assert len(mail.outbox) == 0

    def test_email_if_waitlisted(self, portal_user):
        profile = VolunteerProfile(user=portal_user)
        profile.languages_spoken = [LANGUAGES[0]]
        profile.region = Region.NORTH_AMERICA
        profile.application_status = ApplicationStatus.WAITLISTED
        profile.save()
        mail.outbox.clear()

        profile.region = Region.ASIA
        profile.save()

        assert (
            str(mail.outbox[0].subject)
            == f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Volunteer Application Updated"
        )

        # message about being waitslisted is in the body
        assert "and we're not able to accept everyone" in str(mail.outbox[0].body)
