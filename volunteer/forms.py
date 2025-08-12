import re

from django import forms
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from django.forms.widgets import SelectMultiple
from django.utils.safestring import mark_safe

from portal.validators import validate_linked_in_pattern

from .constants import ApplicationStatus
from .languages import LANGUAGES
from .models import (
    Role,
    Team,
    VolunteerProfile,
    send_internal_volunteer_onboarding_email,
    send_volunteer_onboarding_email,
)


class SelectMultipleWidget(SelectMultiple):
    """
    A custom widget for selecting multiple values with autocomplete.
    """

    def __init__(self, attrs=None, choices=()):
        default_attrs = {
            "class": "form-control select2-multiple",
            "data-placeholder": "Start typing to select ...",
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs, choices)


class VolunteerProfileForm(ModelForm):

    github_username = forms.CharField(
        required=True,
        max_length=50,
        help_text="Required - Your GitHub username (e.g., username). We'll grant read access to PyLadiesCon repos to our volunteers.",
        label="GitHub Username",
        error_messages={"required": "GitHub username is required."},
    )
    additional_comments = forms.CharField(widget=forms.Textarea, required=False)
    teams = forms.ModelMultipleChoiceField(
        required=False,
        queryset=Team.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        help_text=mark_safe(
            "See <a href='https://conference.pyladies.com/docs/' "
            "target='_blank' rel='noopener'>the committee page</a> "
            "for information on each one."
        ),
        label="Which teams are you interested in joining?",
    )

    class Meta:
        model = VolunteerProfile
        exclude = ["user", "application_status", "roles"]
        help_texts = {
            "github_username": "Required - Your GitHub username (e.g., username). We'll grant read access to PyLadiesCon repos to our volunteers.",
            "discord_username": "Required - Your Discord username for team communication (e.g., username or username#1234)",
            "instagram_username": "Instagram username without @ (e.g., username)",
            "bluesky_username": "Bluesky username (e.g., username or username.bsky.social)",
            "mastodon_url": "Mastodon handle (e.g., @username@instance.tld or https://instance.tld/@username)",
            "x_username": "X/Twitter username without @ (e.g., username)",
            "linkedin_url": "LinkedIn URL (e.g., linkedin.com/in/username)",
            "region": mark_safe(
                "Which region do you normally reside in? "
                "See <a href='https://docs.google.com/document/"
                "d/1LTx1dhT0aUCk-_bWWKDaMx6c6bPkuFnZko39-rX_Utc/"
                "edit?tab=t.0#heading=h.whpl50rtq0dg' target='_blank' "
                "rel='noopener'>PSF’s D&amp;I Workgroup Membership handbook</a> "
                "under “Which region should I be representing?” for guidance."
            ),
            "pyladies_chapter": "What PyLadies chapter are you a part of? If you are not part of any chapter leave this blank.",
            "availability_hours_per_week": "Our volunteers are expected to commit at least 1 hour per week until the conference day."
            "By sharing your availability, we can better match you with tasks and teams.",
        }
        labels = {
            "availability_hours_per_week": "What is your volunteering availability?",
            "pyladies_chapter": "PyLadies Chapter",
        }

    def clean_github_username(self):
        github_username = self.cleaned_data.get("github_username")
        if github_username:  # Only validate format if field has value
            self.validate_github_username(github_username)
        return github_username

    def validate_github_username(self, value):
        if not re.match(r"^[a-zA-Z0-9](?:[a-zA-Z0-9]|-(?=[a-zA-Z0-9])){0,38}$", value):
            raise ValidationError(
                "GitHub username can only contain alphanumeric characters and hyphens, "
                "cannot start or end with a hyphen, and must be between 1-39 characters."
            )

    def clean_discord_username(self):
        discord_username = self.cleaned_data.get("discord_username")
        if discord_username:
            self.validate_discord_username(discord_username)
        return discord_username

    def validate_discord_username(self, value):
        if not re.match(
            r"^(?=.{2,32}$)(?!.*\.\.)[a-zA-Z0-9._]+$",
            value,
        ):
            if len(value) < 2 or len(value) > 32:
                raise ValidationError(
                    "Discord username must be between 2 and 32 characters."
                )
            else:
                raise ValidationError(
                    "discord_username": "Discord username must consist of alphanumeric characters, "
                    "periods, underscores, and cannot have two consecutive periods."
                )

    def clean_instagram_username(self):
        instagram_username = self.cleaned_data.get("instagram_username")
        if instagram_username:
            self.validate_instagram_username(instagram_username)
        return instagram_username

    def validate_instagram_username(self, value):
        if not re.match(r"^[a-zA-Z0-9._]{1,30}$", value):
            raise ValidationError(
                "Instagram username can only contain alphanumeric characters, "
                "periods, and underscores, and must be between 1-30 characters."
            )

    def clean_bluesky_username(self):
        bluesky_username = self.cleaned_data.get("bluesky_username")
        if bluesky_username:
            self.validate_bluesky_username(bluesky_username)
        return bluesky_username

    def validate_bluesky_username(self, value):
        if not re.match(
            r"^[a-zA-Z0-9][a-zA-Z0-9.-]{0,28}[a-zA-Z0-9](\.[a-zA-Z0-9][\w.-]*\.[a-zA-Z]{2,})?$",
            value,
        ):
            raise ValidationError(
                "Invalid Bluesky username format. "
                "Should be either a simple username or a full handle (e.g., username.bsky.social)."
            )

    def clean_mastodon_url(self):
        mastodon_url = self.cleaned_data.get("mastodon_url")
        if mastodon_url:
            self.validate_mastodon_url(mastodon_url)
        return mastodon_url

    def validate_mastodon_url(self, value):
        mastodon_pattern1 = r"^@[a-zA-Z0-9_]+@[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        mastodon_pattern2 = (
            r"^https?://[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/@[a-zA-Z0-9_]+$"
        )

        if not (
            re.match(mastodon_pattern1, value) or re.match(mastodon_pattern2, value)
        ):
            raise ValidationError(
                "Invalid Mastodon URL format. "
                "Should be either @username@instance.tld or https://instance.tld/@username."
            )

    def clean_x_username(self):
        x_username = self.cleaned_data.get("x_username")
        if x_username:
            self.validate_x_username(x_username)
        return x_username

    def validate_x_username(self, value):
        if not re.match(r"^[a-zA-Z0-9_]{1,15}$", value):
            raise ValidationError(
                "X/Twitter username can only contain alphanumeric characters and underscores, "
                "and must be between 1-15 characters."
            )

    def clean_linkedin_url(self):
        linkedin_url = self.cleaned_data.get("linkedin_url")
        if linkedin_url:
            if not linkedin_url.startswith(("http://", "https://")):
                linkedin_url = "https://" + linkedin_url
            self.validate_linkedin_url(linkedin_url)
        return linkedin_url

    def validate_linkedin_url(self, value):
        if not validate_linked_in_pattern(value):
            raise ValidationError(
                "Invalid LinkedIn URL format. "
                "Example: linkedin.com/in/username or https://www.linkedin.com/in/username."
            )

    def clean(self):
        cleaned_data = super().clean()
        return cleaned_data

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        sorted_languages = sorted(LANGUAGES, key=lambda x: x[1])

        self.fields["discord_username"].required = True
        self.fields["languages_spoken"].choices = sorted_languages
        self.fields["languages_spoken"].widget = SelectMultipleWidget(
            choices=sorted_languages,
            attrs={
                "data-placeholder": "Start typing to select languages...",
            },
        )

        if self.instance and self.instance.pk:
            pass

    def save(self, commit=True):
        if self.user:
            self.instance.user = self.user

        volunteer_profile = super().save(commit)
        return volunteer_profile


class VolunteerProfileReviewForm(ModelForm):

    additional_comments = forms.CharField(widget=forms.Textarea, required=False)
    teams = forms.ModelMultipleChoiceField(
        required=True,
        queryset=Team.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "Please assign at least one team."},
    )
    roles = forms.ModelMultipleChoiceField(
        required=True,
        queryset=Role.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "Please assign at least one role."},
    )

    class Meta:
        model = VolunteerProfile
        fields = ["teams", "roles"]

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        return cleaned_data

    def save(self, commit=True):
        newly_approved = False
        if self.instance.application_status == ApplicationStatus.PENDING:
            self.instance.application_status = ApplicationStatus.APPROVED
            newly_approved = True
        volunteer_profile = super().save(commit)

        if newly_approved:
            send_volunteer_onboarding_email(volunteer_profile)
            send_internal_volunteer_onboarding_email(volunteer_profile)
        return volunteer_profile
