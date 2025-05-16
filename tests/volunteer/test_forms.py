import pytest

from volunteer.forms import LanguageSelectMultiple, VolunteerProfileForm
from volunteer.models import VolunteerProfile


@pytest.mark.django_db
class TestVolunteerProfileForm:
    BASE_VALID_DATA = {
        "languages_spoken": ["en"],
        "timezone": "UTC-12",
        "discord_username": "validuser123",
    }

    def test_form_saves_correctly(self, portal_user):
        """Test that form saves with required fields and associates user correctly."""
        form = VolunteerProfileForm(user=portal_user, data=self.BASE_VALID_DATA)
        assert form.is_valid()
        profile = form.save()

        assert profile.user == portal_user
        assert profile.languages_spoken == ["en"]
        assert profile.timezone == "UTC-12"
        assert profile.discord_username == "validuser123"
        assert profile.application_status == "Pending Review"

    def test_required_fields(self, portal_user):
        """Test validation of required fields."""
        form = VolunteerProfileForm(user=portal_user, data={})
        assert not form.is_valid()
        assert "languages_spoken" in form.errors
        assert "timezone" in form.errors
        assert "discord_username" in form.errors

        form = VolunteerProfileForm(user=portal_user, data={"timezone": "UTC-12"})
        assert not form.is_valid()
        assert "languages_spoken" in form.errors
        assert "discord_username" in form.errors

        form = VolunteerProfileForm(user=portal_user, data={"languages_spoken": ["en"]})
        assert not form.is_valid()
        assert "timezone" in form.errors
        assert "discord_username" in form.errors

        form = VolunteerProfileForm(
            user=portal_user, data={"languages_spoken": ["en"], "timezone": "UTC-12"}
        )
        assert not form.is_valid()
        assert "discord_username" in form.errors

    @pytest.mark.parametrize(
        "username,valid",
        [
            ("username", True),
            ("user.name", True),
            ("user_name", True),
            ("user-name", True),
            ("a" * 32, True),
            ("", False),
            (".username", False),
            ("_username", False),
            ("-username", False),
            ("username.", False),
            ("username_", False),
            ("username-", False),
            ("user..name", False),
            ("user__name", False),
            ("user--name", False),
            ("a" * 33, False),
            ("a", False),
            ("user@name", False),
        ],
    )
    def test_discord_username_validation(self, portal_user, username, valid):
        """Test Discord username validation with various cases."""
        form_data = {**self.BASE_VALID_DATA, "discord_username": username}
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
            ("", True),
            ("-username", False),
            ("username-", False),
            ("user--name", False),
            ("a" * 40, False),
            ("user@name", False),
        ],
    )
    def test_github_username_validation(self, portal_user, username, valid):
        """Test GitHub username validation with various cases."""
        form_data = {**self.BASE_VALID_DATA, "github_username": username}
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
        form_data = {**self.BASE_VALID_DATA, "instagram_username": username}
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
        form_data = {**self.BASE_VALID_DATA, "bluesky_username": username}
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
        form_data = {**self.BASE_VALID_DATA, "x_username": username}
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
        form_data = {**self.BASE_VALID_DATA, "mastodon_url": url}
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
        ],
    )
    def test_linkedin_url_validation(self, portal_user, url, valid, cleaned_prefix):
        """Test LinkedIn URL validation and protocol addition."""
        form_data = {**self.BASE_VALID_DATA, "linkedin_url": url}
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert form.is_valid() == valid
        if valid and url:
            assert form.cleaned_data["linkedin_url"].startswith(cleaned_prefix)
        elif not valid:
            assert "linkedin_url" in form.errors

    def test_form_updates_existing_profile(self, portal_user):
        """Test that form can update an existing profile."""
        profile = VolunteerProfile.objects.create(
            user=portal_user,
            languages_spoken=["en"],
            timezone="UTC-12",
            github_username="olduser",
            discord_username="olddiscord",
        )

        update_data = {
            "languages_spoken": ["en", "es"],
            "timezone": "UTC-10",
            "github_username": "newuser",
            "discord_username": "newdiscord",
        }
        form = VolunteerProfileForm(
            user=portal_user, data=update_data, instance=profile
        )

        assert form.is_valid()
        updated_profile = form.save()

        assert updated_profile.pk == profile.pk
        assert updated_profile.github_username == "newuser"
        assert updated_profile.discord_username == "newdiscord"
        assert updated_profile.timezone == "UTC-10"
        assert set(updated_profile.languages_spoken) == {"en", "es"}

    def test_optional_social_fields(self, portal_user):
        """Test that all social media fields except Discord are optional."""
        form_data = {
            **self.BASE_VALID_DATA,
            "github_username": "",
            "instagram_username": "",
            "bluesky_username": "",
            "mastodon_url": "",
            "x_username": "",
            "linkedin_url": "",
        }
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert form.is_valid()

    def test_empty_optional_fields(self, portal_user):
        """Test that optional fields can be empty (Discord is required)."""
        form_data = {
            **self.BASE_VALID_DATA,
            "github_username": "",
            "instagram_username": "",
            "bluesky_username": "",
            "mastodon_url": "",
            "x_username": "",
            "linkedin_url": "",
        }
        form = VolunteerProfileForm(user=portal_user, data=form_data)
        assert form.is_valid()
        assert form.cleaned_data["github_username"] is None
        assert form.cleaned_data["bluesky_username"] is None

    def test_form_clean_method(self, portal_user):
        """Test that the clean method works correctly."""
        form = VolunteerProfileForm(user=portal_user, data=self.BASE_VALID_DATA)
        assert form.is_valid()
        cleaned_data = form.clean()
        assert cleaned_data == form.cleaned_data

    def test_form_init_with_instance(self, portal_user):
        """Test form initialization with existing instance."""
        profile = VolunteerProfile.objects.create(
            user=portal_user,
            languages_spoken=["en"],
            timezone="UTC-12",
            github_username="testuser",
            discord_username="testdiscord",
        )

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
            **self.BASE_VALID_DATA,
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

    def test_bluesky_username_with_multiple_domains(self, portal_user):
        """Test Bluesky username with multiple domain levels."""
        valid_usernames = [
            "username.domain.bsky.social",
            "user.name.multi.domain.bsky.social",
        ]
        for username in valid_usernames:
            form = VolunteerProfileForm(
                user=portal_user,
                data={**self.BASE_VALID_DATA, "bluesky_username": username},
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
                user=portal_user, data={**self.BASE_VALID_DATA, "mastodon_url": url}
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
                user=portal_user, data={**self.BASE_VALID_DATA, "linkedin_url": url}
            )
            assert form.is_valid(), f"Expected '{url}' to be valid"
            assert form.cleaned_data["linkedin_url"].startswith("http")

    def test_validation_error_messages(self, portal_user):
        """Test that validation errors include the correct messages."""
        invalid_data = {
            **self.BASE_VALID_DATA,
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
            if field in self.BASE_VALID_DATA:
                continue
            assert field in form.errors
            assert len(form.errors[field]) > 0

    def test_discord_username_length_error(self, portal_user):
        """Test Discord username length error message."""
        form = VolunteerProfileForm(
            user=portal_user, data={**self.BASE_VALID_DATA, "discord_username": "a"}
        )
        assert not form.is_valid()
        assert "must be between 2 and 32 characters" in str(
            form.errors["discord_username"]
        )

        form = VolunteerProfileForm(
            user=portal_user,
            data={**self.BASE_VALID_DATA, "discord_username": "a" * 33},
        )
        assert not form.is_valid()
        assert "must be between 2 and 32 characters" in str(
            form.errors["discord_username"]
        )

    def test_discord_username_special_chars_error(self, portal_user):
        """Test Discord username special characters error message."""
        form = VolunteerProfileForm(
            user=portal_user,
            data={**self.BASE_VALID_DATA, "discord_username": "user@name"},
        )
        assert not form.is_valid()
        assert "must consist of alphanumeric characters" in str(
            form.errors["discord_username"]
        )

    def test_linkedin_url_no_protocol(self, portal_user):
        """Test LinkedIn URL with no protocol is properly handled."""
        form = VolunteerProfileForm(
            user=portal_user,
            data={**self.BASE_VALID_DATA, "linkedin_url": "linkedin.com/in/username"},
        )
        assert form.is_valid()
        assert form.cleaned_data["linkedin_url"] == "https://linkedin.com/in/username"


class TestLanguageSelectMultiple:
    """Tests for the LanguageSelectMultiple widget."""

    def test_init_with_attrs(self):
        """Test initialization with custom attributes."""
        custom_attrs = {"class": "custom-class", "data-test": "test-value"}
        widget = LanguageSelectMultiple(attrs=custom_attrs)

        # Verify that the custom attributes were merged with default attributes
        assert "custom-class" in widget.attrs["class"]
        assert widget.attrs["data-test"] == "test-value"
        assert (
            "data-placeholder" in widget.attrs
        )  # Default attribute should still be present
