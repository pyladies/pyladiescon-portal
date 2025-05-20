import re

from django import forms
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from django.forms.widgets import SelectMultiple

from .languages import LANGUAGES
from .models import SpeakerProfile

class LanguageSelectMultiple(SelectMultiple):
    """
    A custom widget for selecting multiple languages with autocomplete.
    """

    def __init__(self, attrs=None, choices=()):
        default_attrs = {
            "class": "form-control select2-multiple",
            "data-placeholder": "Start typing to select languages...",
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs, choices)

class SpeakerProfileForm(ModelForm):

    # discord_username = forms.CharField(required=True)
    additional_comments = forms.CharField(widget=forms.Textarea, required=False)

    class Meta:
        model = SpeakerProfile
        exclude = ["user", "application_status"]
        help_texts = {
            # "github_username": "GitHub username (e.g., username)",
            # "discord_username": "Required - Your Discord username for team communication (e.g., username#1234)",
            # "instagram_username": "Instagram username without @ (e.g., username)",
            # "bluesky_username": "Bluesky username (e.g., username or username.bsky.social)",
            # "mastodon_url": "Mastodon handle (e.g., @username@instance.tld or https://instance.tld/@username)",
            # "x_username": "X/Twitter username without @ (e.g., username)",
            # "linkedin_url": "LinkedIn URL (e.g., linkedin.com/in/username)",
            "region": "Region where you normally reside",
        }

    def clean(self):
        cleaned_data = super().clean()
        return cleaned_data

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        sorted_languages = sorted(LANGUAGES, key=lambda x: x[1])

        self.fields["discord_username"].required = True
        self.fields["languages_spoken"].choices = sorted_languages
        self.fields["languages_spoken"].widget = LanguageSelectMultiple(
            choices=sorted_languages
        )

        if self.instance and self.instance.pk:
            pass

    def save(self, commit=True):
        if self.user:
            self.instance.user = self.user
        volunteer_profile = super().save(commit)
        return volunteer_profile
