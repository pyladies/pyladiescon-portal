import re

from django import forms
from django.core.exceptions import ValidationError
from django.forms import ModelForm

from .models import VolunteerProfile


class VolunteerProfileForm(ModelForm):

    class Meta:
        model = VolunteerProfile
        exclude = ["user", "application_status"]
        help_texts = {
            "github_username": "GitHub username (e.g., username)",
            "discord_username": "Discord username (e.g., username)",
            "instagram_username": "Instagram username without @ (e.g., username)",
            "bluesky_username": "Bluesky username (e.g., username or username.bsky.social)",
            "mastodon_url": "Mastodon handle (e.g., @username@instance.tld or https://instance.tld/@username)",
            "x_username": "X/Twitter username without @ (e.g., username)",
            "linkedin_url": "LinkedIn URL (e.g., linkedin.com/in/username)",
        }

    def clean_github_username(self):
        github_username = self.cleaned_data.get("github_username")
        if github_username:
            if not re.match(
                r"^[a-zA-Z0-9](?:[a-zA-Z0-9]|-(?=[a-zA-Z0-9])){0,38}$", github_username
            ):
                raise ValidationError(
                    "GitHub username can only contain alphanumeric characters and hyphens, "
                    "cannot start or end with a hyphen, and must be between 1-39 characters."
                )
        return github_username

    def clean_discord_username(self):
        discord_username = self.cleaned_data.get("discord_username")
        if discord_username:
            if not re.match(
                r"^[a-zA-Z0-9](?:[a-zA-Z0-9]|[._-](?=[a-zA-Z0-9])){0,30}[a-zA-Z0-9]$",
                discord_username,
            ):
                if len(discord_username) < 2 or len(discord_username) > 32:
                    raise ValidationError(
                        "Discord username must be between 2 and 32 characters."
                    )
                else:
                    raise ValidationError(
                        "Discord username must consist of alphanumeric characters, "
                        "dots, underscores, or hyphens, and cannot have consecutive special characters."
                    )
        return discord_username

    def clean_instagram_username(self):
        instagram_username = self.cleaned_data.get("instagram_username")
        if instagram_username:
            if instagram_username.startswith("@"):
                instagram_username = instagram_username[1:]

            if not re.match(r"^[a-zA-Z0-9._]{1,30}$", instagram_username):
                raise ValidationError(
                    "Instagram username can only contain alphanumeric characters, "
                    "periods, and underscores, and must be between 1-30 characters."
                )
        return instagram_username

    def clean_bluesky_username(self):
        bluesky_username = self.cleaned_data.get("bluesky_username")
        if bluesky_username:
            if bluesky_username.startswith("@"):
                bluesky_username = bluesky_username[1:]

            if not re.match(
                r"^[a-zA-Z0-9][a-zA-Z0-9.-]{0,28}[a-zA-Z0-9](\.[a-zA-Z0-9][\w.-]*\.[a-zA-Z]{2,})?$",
                bluesky_username,
            ):
                raise ValidationError(
                    "Invalid Bluesky username format. "
                    "Should be either a simple username or a full handle (e.g., username.bsky.social)."
                )
        return bluesky_username

    def clean_mastodon_url(self):
        mastodon_url = self.cleaned_data.get("mastodon_url")
        if mastodon_url:
            mastodon_pattern1 = r"^@[a-zA-Z0-9_]+@[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"  # @user@instance.tld
            mastodon_pattern2 = r"^https?://[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/@[a-zA-Z0-9_]+$"  # https://instance.tld/@user

            if not (
                re.match(mastodon_pattern1, mastodon_url)
                or re.match(mastodon_pattern2, mastodon_url)
            ):
                raise ValidationError(
                    "Invalid Mastodon URL format. "
                    "Should be either @username@instance.tld or https://instance.tld/@username."
                )
        return mastodon_url

    def clean_x_username(self):
        x_username = self.cleaned_data.get("x_username")
        if x_username:
            if x_username.startswith("@"):
                x_username = x_username[1:]

            if not re.match(r"^[a-zA-Z0-9_]{1,15}$", x_username):
                raise ValidationError(
                    "X/Twitter username can only contain alphanumeric characters and underscores, "
                    "and must be between 1-15 characters."
                )
        return x_username

    def clean_linkedin_url(self):
        linkedin_url = self.cleaned_data.get("linkedin_url")
        if linkedin_url:
            if not linkedin_url.startswith(("http://", "https://")):
                linkedin_url = "https://" + linkedin_url

            linkedin_pattern = (
                r"^(https?://)?(www\.)?linkedin\.com/in/[a-zA-Z0-9_-]+/?$"
            )

            if not re.match(linkedin_pattern, linkedin_url):
                raise ValidationError(
                    "Invalid LinkedIn URL format. "
                    "Should be in the format: linkedin.com/in/username or https://www.linkedin.com/in/username."
                )
        return linkedin_url

    def clean(self):
        cleaned_data = super().clean()
        return cleaned_data

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            pass

    def save(self, commit=True):
        """ """
        user = self.user
        self.instance.user = user
        volunteer_profile = super().save(commit)
        return volunteer_profile
