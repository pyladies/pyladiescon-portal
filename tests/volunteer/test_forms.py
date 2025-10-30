import pytest

from volunteer.constants import Region
from volunteer.forms import SelectMultipleWidget, VolunteerProfileForm
from volunteer.models import Language, VolunteerProfile


@pytest.mark.django_db
class TestVolunteerProfileForm:

    @pytest.fixture(autouse=True)
    def set_valid_data(self, language):
        self._base_valid_data = {
            "language": [language.id],
            "region": Region.NORTH_AMERICA,
            "discord_username": "validuser123",
            "github_username": "validuser123",
            "availability_hours_per_week": 5,
        }

    def test_form_saves_correctly(self, portal_user, language):
        """Test that form saves with required fields and associates user correctly."""
        form = VolunteerProfileForm(user=portal_user, data=self._base_valid_data)
        assert form.is_valid()
        profile = form.save()

        assert profile.user == portal_user
        assert profile.language.first() == language
        assert profile.region == Region.NORTH_AMERICA
        assert profile.discord_username == "validuser123"
        assert profile.availability_hours_per_week == 5
        assert profile.application_status == "Pending Review"

    def test_required_fields(self, portal_user, language):
        """Test validation of required fields."""
        form = VolunteerProfileForm(user=portal_user, data={})
        assert not form.is_valid()
        assert "language" in form.errors
        assert "region" in form.errors
        assert "discord_username" in form.errors
        assert "github_username" in form.errors
        assert "availability_hours_per_week" in form.errors

        form = VolunteerProfileForm(
            user=portal_user, data={"region": Region.NORTH_AMERICA}
        )
        assert not form.is_valid()
        assert "language" in form.errors
        assert "discord_username" in form.errors
        assert "github_username" in form.errors
        assert "availability_hours_per_week" in form.errors

        form = VolunteerProfileForm(user=portal_user, data={"language": [language.id]})
        assert not form.is_valid()
        assert "region" in form.errors
        assert "discord_username" in form.errors
        assert "github_username" in form.errors
        assert "availability_hours_per_week" in form.errors

        form = VolunteerProfileForm(user=portal_user, data={"discord_username": ["en"]})
        assert not form.is_valid()
        assert "region" in form.errors
        assert "language" in form.errors
        assert "github_username" in form.errors
        assert "availability_hours_per_week" in form.errors

        form = VolunteerProfileForm(
            user=portal_user, data={"availability_hours_per_week": [40]}
        )
        assert not form.is_valid()
        assert "region" in form.errors
        assert "language" in form.errors
        assert "discord_username" in form.errors
        assert "github_username" in form.errors

        form = VolunteerProfileForm(
            user=portal_user, data={"language": [language.id], "timezone": "UTC-12"}
        )
        assert not form.is_valid()
        assert "discord_username" in form.errors
        assert "github_username" in form.errors

    @pytest.mark.parametrize(
        "username,valid",
        [
            ("username", True),
            ("user.name", True),
            ("user_name", True),
            ("user-name", False),
            ("a" * 32, True),
            ("", False),
            (".username", True),
            ("_username", True),
            ("-username", False),
            ("username.", True),
            ("username_", True),
            ("username-", False),
            ("user..name", False),
            ("user__name", True),
            ("user--name", False),
            ("a" * 33, False),
            ("a", False),
            ("user@name", False),
        ],
    )
    def test_discord_username_validation(self, portal_user, username, valid):
        """Test Discord username validation with various cases."""
        form_data = {**self._base_valid_data, "discord_username": username}
        if username == "":
            form_data.pop("discord_username")

        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert form.is_valid() == valid
        if not valid:
            assert "discord_username" in form.errors

    @pytest.mark.parametrize(
        "username,valid",
        [
            ("username", True),
            ("user-name", True),
            ("user123", True),
            ("User123-Name", True),
            ("a" * 39, True),
            ("", False),
            ("-username", False),
            ("username-", False),
            ("user--name", False),
            ("a" * 40, False),
            ("user@name", False),
        ],
    )
    def test_github_username_validation(self, portal_user, username, valid):
        """Test GitHub username validation with various cases."""
        form_data = {**self._base_valid_data, "github_username": username}
        if username == "":
            form_data.pop("github_username")
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert form.is_valid() == valid
        if not valid:
            assert "github_username" in form.errors

    @pytest.mark.parametrize(
        "username,valid",
        [
            ("username", True),
            ("user.name", True),
            ("user_name", True),
            ("a" * 30, True),
            ("", True),
            ("user-name", False),
            ("a" * 31, False),
            ("user@name", False),
        ],
    )
    def test_instagram_username_validation(self, portal_user, username, valid):
        """Test Instagram username validation with various cases."""
        form_data = {**self._base_valid_data, "instagram_username": username}
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert form.is_valid() == valid
        if not valid:
            assert "instagram_username" in form.errors

    @pytest.mark.parametrize(
        "username,valid",
        [
            ("username", True),
            ("user-name", True),
            ("username.bsky.social", True),
            ("user.name.bsky.social", True),
            ("a1", True),
            ("a" * 30, True),
            ("", True),
            ("_username", False),
            ("username_", False),
            ("user_name", False),
            ("a", False),
            ("a" * 31, False),
            ("user@name", False),
            (".username", False),
            ("username.", False),
        ],
    )
    def test_bluesky_username_validation(self, portal_user, username, valid):
        """Test Bluesky username validation with various cases."""
        form_data = {**self._base_valid_data, "bluesky_username": username}
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert form.is_valid() == valid
        if not valid:
            assert "bluesky_username" in form.errors

    @pytest.mark.parametrize(
        "username,valid",
        [
            ("username", True),
            ("user_name", True),
            ("a" * 15, True),
            ("", True),
            ("user.name", False),
            ("user-name", False),
            ("a" * 16, False),
            ("user@name", False),
        ],
    )
    def test_x_username_validation(self, portal_user, username, valid):
        """Test X/Twitter username validation with various cases."""
        form_data = {**self._base_valid_data, "x_username": username}
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert form.is_valid() == valid
        if not valid:
            assert "x_username" in form.errors

    @pytest.mark.parametrize(
        "url,valid",
        [
            ("@user@instance.tld", True),
            ("https://instance.tld/@user", True),
            ("http://instance.tld/@user", True),
            ("", True),
            ("user@instance.tld", False),
            ("@user@instance", False),
            ("https://instance.tld/user", False),
            ("https://instance/@user", False),
        ],
    )
    def test_mastodon_url_validation(self, portal_user, url, valid):
        """Test Mastodon URL validation with various formats."""
        form_data = {**self._base_valid_data, "mastodon_url": url}
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert form.is_valid() == valid
        if not valid:
            assert "mastodon_url" in form.errors

    @pytest.mark.parametrize(
        "url,valid,cleaned_prefix",
        [
            ("linkedin.com/in/username", True, "https://"),
            ("www.linkedin.com/in/username", True, "https://"),
            ("https://linkedin.com/in/username", True, "https://"),
            ("http://linkedin.com/in/username", True, "http://"),
            ("", True, ""),
            ("linkedin.com", False, None),
            ("linkedin.com/username", False, None),
            ("https://othersite.com/in/username", False, None),
            ("https://linkedin.com/company/pyladiescon", True, "https://"),
            ("https://www.linkedin.com/school/some-school", True, "https://"),
            (
                "https://linkedin.com/in/rãé-gómez-Łukasz-Schröder-Jürgen-süß",
                True,
                "https://",
            ),
        ],
    )
    def test_linkedin_url_validation(self, portal_user, url, valid, cleaned_prefix):
        """Test LinkedIn URL validation and protocol addition."""
        form_data = {**self._base_valid_data, "linkedin_url": url}
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert form.is_valid() == valid
        if valid and url:
            assert form.cleaned_data["linkedin_url"].startswith(cleaned_prefix)
        elif not valid:
            assert "linkedin_url" in form.errors

    def test_form_updates_existing_profile(self, portal_user, language):
        """Test that form can update an existing profile."""
        other_language = Language.objects.create(code="es", name="Spanish")
        profile = VolunteerProfile.objects.create(
            user=portal_user,
            discord_username="olddiscord",
            github_username="olduser",
            availability_hours_per_week=40,
            region=Region.NORTH_AMERICA,
        )
        profile.language.add(language)

        update_data = {
            "language": [language.id, other_language.id],
            "discord_username": "newdiscord",
            "github_username": "newuser",
            "availability_hours_per_week": 20,
            "region": Region.ASIA,
        }
        form = VolunteerProfileForm(
            user=portal_user, data=update_data, instance=profile
        )

        assert form.is_valid()
        updated_profile = form.save()

        assert updated_profile.pk == profile.pk
        assert updated_profile.github_username == "newuser"
        assert updated_profile.region == Region.ASIA
        assert language in updated_profile.language.all()
        assert other_language in updated_profile.language.all()
        assert updated_profile.discord_username == "newdiscord"
        assert updated_profile.availability_hours_per_week == 20

    def test_optional_social_fields(self, portal_user):
        """Test that all social media fields except Discord and GitHub are optional."""
        form_data = {
            **self._base_valid_data,
            "instagram_username": "",
            "bluesky_username": "",
            "mastodon_url": "",
            "x_username": "",
            "linkedin_url": "",
        }
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert form.is_valid()

    def test_empty_optional_fields(self, portal_user):
        """Test that optional fields can be empty (Discord and GitHub are required)."""
        form_data = {
            **self._base_valid_data,
            "instagram_username": "",
            "bluesky_username": "",
            "mastodon_url": "",
            "x_username": "",
            "linkedin_url": "",
        }
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert form.is_valid()
        assert form.cleaned_data["bluesky_username"] is None

    def test_form_clean_method(self, portal_user):
        """Test that the clean method works correctly."""
        form = VolunteerProfileForm(user=portal_user, data=self._base_valid_data)
        assert form.is_valid()
        cleaned_data = form.clean()
        assert cleaned_data == form.cleaned_data

    def test_form_init_with_instance(self, portal_user, language):
        """Test form initialization with existing instance."""
        profile = VolunteerProfile.objects.create(
            user=portal_user,
            region=Region.NORTH_AMERICA,
            github_username="testuser",
            discord_username="testdiscord",
        )
        profile.language.add(language)

        form = VolunteerProfileForm(user=portal_user, instance=profile)
        assert form.instance == profile
        assert form.initial["github_username"] == "testuser"
        assert form.initial["discord_username"] == "testdiscord"

    def test_form_init_without_user(self):
        """Test form initialization without user."""
        form = VolunteerProfileForm()
        assert form.user is None

    def test_save_method_with_commit_false(self, portal_user):
        """Test save method with commit=False."""
        form_data = {
            **self._base_valid_data,
            "github_username": "testuser",
        }
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert form.is_valid()

        profile = form.save(commit=False)
        assert profile.user == portal_user
        assert profile.github_username == "testuser"
        assert profile.discord_username == "validuser123"
        assert profile.pk is None

        profile.save()
        assert profile.pk is not None

    def test_all_optional_fields_empty(self, portal_user):
        """Test that all optional fields can be empty."""
        form_data = {
            **self._base_valid_data,
            "instagram_username": "",
            "bluesky_username": "",
            "mastodon_url": "",
            "x_username": "",
            "linkedin_url": "",
        }
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert form.is_valid()

    def test_bluesky_username_with_multiple_domains(self, portal_user):
        """Test Bluesky username with multiple domain levels."""
        valid_usernames = [
            "username.domain.bsky.social",
            "user.name.multi.domain.bsky.social",
        ]
        for username in valid_usernames:
            form = VolunteerProfileForm(
                user=portal_user,
                data={**self._base_valid_data, "bluesky_username": username},
            )
            assert form.is_valid(), f"Expected '{username}' to be valid"

    def test_mastodon_url_with_subdomains(self, portal_user):
        """Test Mastodon URLs with subdomains."""
        valid_urls = [
            "@user@sub.instance.tld",
            "https://sub.instance.tld/@user",
            "https://deep.sub.instance.tld/@user",
        ]
        for url in valid_urls:
            form = VolunteerProfileForm(
                user=portal_user, data={**self._base_valid_data, "mastodon_url": url}
            )
            assert form.is_valid(), f"Expected '{url}' to be valid"

    def test_linkedin_url_with_different_protocols(self, portal_user):
        """Test LinkedIn URL with different protocol variations."""
        valid_urls = [
            "http://linkedin.com/in/username",
            "http://www.linkedin.com/in/username",
            "linkedin.com/in/username",
            "www.linkedin.com/in/username",
        ]
        for url in valid_urls:
            form = VolunteerProfileForm(
                user=portal_user, data={**self._base_valid_data, "linkedin_url": url}
            )
            assert form.is_valid(), f"Expected '{url}' to be valid"
            assert form.cleaned_data["linkedin_url"].startswith("http")

    def test_validation_error_messages(self, portal_user):
        """Test that validation errors include the correct messages."""
        invalid_data = {
            **self._base_valid_data,
            "github_username": "-invalid",
            "discord_username": "user@name",
            "instagram_username": "user@name",
            "bluesky_username": "_invalid",
            "mastodon_url": "invalid@format",
            "x_username": "user@name",
            "linkedin_url": "invalid-url",
        }

        form = VolunteerProfileForm(user=portal_user, data=invalid_data)
        assert not form.is_valid()

        for field in invalid_data:
            if field in self._base_valid_data:
                continue
            assert field in form.errors
            assert len(form.errors[field]) > 0

    def test_discord_username_length_error(self, portal_user):
        """Test Discord username length error message."""
        form = VolunteerProfileForm(
            user=portal_user, data={**self._base_valid_data, "discord_username": "a"}
        )
        assert not form.is_valid()
        assert "must be between 2 and 32 characters" in str(
            form.errors["discord_username"]
        )

        form = VolunteerProfileForm(
            user=portal_user,
            data={**self._base_valid_data, "discord_username": "a" * 33},
        )
        assert not form.is_valid()
        assert "must be between 2 and 32 characters" in str(
            form.errors["discord_username"]
        )

    def test_discord_username_special_chars_error(self, portal_user):
        """Test Discord username special characters error message."""
        form = VolunteerProfileForm(
            user=portal_user,
            data={**self._base_valid_data, "discord_username": "user@name"},
        )
        assert not form.is_valid()
        assert "must consist of alphanumeric characters" in str(
            form.errors["discord_username"]
        )

    def test_linkedin_url_no_protocol(self, portal_user):
        """Test LinkedIn URL with no protocol is properly handled."""
        form = VolunteerProfileForm(
            user=portal_user,
            data={**self._base_valid_data, "linkedin_url": "linkedin.com/in/username"},
        )
        assert form.is_valid()
        assert form.cleaned_data["linkedin_url"] == "https://linkedin.com/in/username"

    def test_github_username_required_field(self, portal_user):
        """Test that GitHub username is a required field."""
        # Test form without github_username
        form_data = {**self._base_valid_data}
        form_data.pop("github_username")
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert not form.is_valid()
        assert "github_username" in form.errors
        assert "GitHub username is required." in str(form.errors["github_username"])

    def test_github_username_required_error_message(self, portal_user):
        """Test the specific error message when GitHub username is missing."""
        form_data = {**self._base_valid_data}
        form_data.pop("github_username")
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert not form.is_valid()
        assert form.errors["github_username"] == ["GitHub username is required."]

    def test_github_username_empty_string_validation(self, portal_user):
        """Test that empty string for GitHub username fails validation."""
        form_data = {**self._base_valid_data, "github_username": ""}
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert not form.is_valid()
        assert "github_username" in form.errors
        assert "GitHub username is required." in str(form.errors["github_username"])

    def test_github_username_whitespace_only_validation(self, portal_user):
        """Test that whitespace-only GitHub username fails validation."""
        form_data = {**self._base_valid_data, "github_username": "   "}
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert not form.is_valid()
        assert "github_username" in form.errors

    def test_github_username_field_properties(self, portal_user):
        """Test that GitHub username field has correct properties."""
        form = VolunteerProfileForm(user=portal_user)
        github_field = form.fields["github_username"]

        assert github_field.required is True
        assert github_field.max_length == 50
        assert "Required - Your GitHub username" in github_field.help_text
        assert "PyLadiesCon repos" in github_field.help_text
        assert github_field.label == "GitHub Username"

    def test_github_username_valid_with_required_value(self, portal_user):
        """Test that form is valid when GitHub username is provided."""
        form_data = {**self._base_valid_data, "github_username": "validuser123"}
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert form.is_valid()
        assert form.cleaned_data["github_username"] == "validuser123"

    def test_github_username_help_text_content(self, portal_user):
        """Test that GitHub username help text explains the requirement."""
        form = VolunteerProfileForm(user=portal_user)
        help_text = form.fields["github_username"].help_text

        assert "Required" in help_text
        assert "GitHub username" in help_text
        assert "PyLadiesCon repos" in help_text
        assert "volunteers" in help_text

    def test_form_save_with_github_username(self, portal_user):
        """Test that form saves correctly with required GitHub username."""
        form_data = {**self._base_valid_data, "github_username": "testuser123"}
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert form.is_valid()

        profile = form.save()
        assert profile.github_username == "testuser123"
        assert profile.user == portal_user

    def test_github_username_clean_method_coverage(self, portal_user):
        """Test clean_github_username method for complete coverage."""
        # Test with None value (should not raise ValidationError since required validation is handled by field)
        form = VolunteerProfileForm(user=portal_user, data={**self._base_valid_data})
        form.cleaned_data = {**self._base_valid_data}
        form.cleaned_data["github_username"] = None

        # Should not raise ValidationError - None values are handled by required field validation
        result = form.clean_github_username()
        assert result is None

        # Test with empty string (should not raise ValidationError since required validation is handled by field)
        form.cleaned_data["github_username"] = ""
        result = form.clean_github_username()
        assert result == ""

    def test_github_username_validation_and_cleaning(self, portal_user):
        """Test the complete validation flow for GitHub username."""
        # Test valid username goes through validation
        form_data = {**self._base_valid_data, "github_username": "valid-user123"}
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert form.is_valid()

        # Test invalid username format
        form_data = {**self._base_valid_data, "github_username": "-invalid-start"}
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert not form.is_valid()
        assert "github_username" in form.errors

    def test_github_username_error_message_override(self, portal_user):
        """Test that the custom required error message is used."""
        form = VolunteerProfileForm(user=portal_user)
        error_messages = form.fields["github_username"].error_messages
        assert "required" in error_messages
        assert error_messages["required"] == "GitHub username is required."

    def test_github_username_form_validation_integration(self, portal_user):
        """Test complete form validation behavior for GitHub username."""
        # Test form with missing github_username shows our custom error

        form_data = self._base_valid_data
        form_data.pop("github_username")
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert not form.is_valid()
        assert "github_username" in form.errors

        # Test form with valid github_username passes validation
        form_data = {**self._base_valid_data, "github_username": "validuser"}
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert form.is_valid()
        assert form.cleaned_data["github_username"] == "validuser"


class TestSelectMultipleWidget:
    """Tests for the SelectMultipleWidget widget."""

    def test_init_with_attrs(self):
        """Test initialization with custom attributes."""
        custom_attrs = {"class": "custom-class", "data-test": "test-value"}
        widget = SelectMultipleWidget(attrs=custom_attrs)

        # Verify that the custom attributes were merged with default attributes
        assert "custom-class" in widget.attrs["class"]
        assert widget.attrs["data-test"] == "test-value"
        assert (
            "data-placeholder" in widget.attrs
        )  # Default attribute should still be present
