import zoneinfo

from django import forms
from django.contrib.auth.models import User
from django.db.models import Q

from volunteer.constants import ApplicationStatus

from .constants import CONTENT_KINDS, DEFAULT_DURATION_MINUTES, Delivery, SessionKind
from .models import Presenter, Session, SessionPresenter

MARKDOWN_HELP = "Markdown supported: headings, lists, links, **bold**, *italics*."


class SessionForm(forms.ModelForm):
    """Create or edit a session. Every content field is optional markdown."""

    class Meta:
        model = Session
        fields = [
            "kind",
            "delivery",
            "title",
            "summary_md",
            "outline_md",
            "prerequisites_md",
            "audience_md",
            "level",
            "language",
            "duration_minutes",
            "video_length_limit_minutes",
            "premiere_location",
            "youtube_url",
            "youtube_publish_at",
            "notes_md",
        ]
        widgets = {
            "summary_md": forms.Textarea(attrs={"rows": 4}),
            "outline_md": forms.Textarea(attrs={"rows": 6}),
            "prerequisites_md": forms.Textarea(attrs={"rows": 3}),
            "audience_md": forms.Textarea(attrs={"rows": 3}),
            "notes_md": forms.Textarea(attrs={"rows": 3}),
            "youtube_publish_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }
        help_texts = {
            "summary_md": MARKDOWN_HELP,
            "outline_md": MARKDOWN_HELP,
            "prerequisites_md": MARKDOWN_HELP,
            "audience_md": MARKDOWN_HELP,
            "notes_md": MARKDOWN_HELP + " Internal, never shown to the public.",
            "duration_minutes": "Leave blank to use the default for the kind: "
            + ", ".join(
                f"{SessionKind(kind).label.lower()} {minutes}"
                for kind, minutes in DEFAULT_DURATION_MINUTES.items()
                if kind in CONTENT_KINDS
            )
            + ".",
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("delivery") == Delivery.LIVE:
            for field in (
                "video_length_limit_minutes",
                "youtube_url",
                "youtube_publish_at",
                "premiere_location",
            ):
                if cleaned.get(field):
                    self.add_error(field, "Only applies to pre-recorded sessions.")
        return cleaned


class ProgramItemForm(forms.ModelForm):
    """The "+ program item" shortcut: an opening, break or social, confirmed
    on creation because it needs no presenter."""

    class Meta:
        model = Session
        fields = ["kind", "title", "duration_minutes", "summary_md"]
        widgets = {"summary_md": forms.Textarea(attrs={"rows": 2})}
        help_texts = {
            "duration_minutes": "Leave blank to use the default for the kind.",
            "summary_md": MARKDOWN_HELP,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kind"].choices = [
            (kind, label)
            for kind, label in SessionKind.choices
            if kind not in CONTENT_KINDS
        ]


def timezone_choices():
    return [(name, name) for name in sorted(zoneinfo.available_timezones())]


class PresenterForm(forms.ModelForm):
    """Organizer-side presenter create/edit, including the liaison."""

    timezone = forms.ChoiceField(choices=timezone_choices, initial="UTC")

    class Meta:
        model = Presenter
        fields = [
            "display_name",
            "email",
            "pronouns",
            "liaison",
            "bio_md",
            "headshot",
            "location",
            "timezone",
            "website_url",
            "github_username",
            "mastodon_url",
            "linkedin_url",
            "bluesky_username",
            "is_public",
        ]
        widgets = {"bio_md": forms.Textarea(attrs={"rows": 5})}
        help_texts = {"bio_md": MARKDOWN_HELP}

    def __init__(self, *args, conference, **kwargs):
        super().__init__(*args, **kwargs)
        self.conference = conference
        self.fields["liaison"].queryset = liaison_candidates(conference)
        self.fields["liaison"].label_from_instance = _user_label

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        clash = Presenter.objects.filter(conference=self.conference, email=email)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError(
                "A presenter with this email already exists in this edition."
            )
        return email


def _user_label(user):
    return user.get_full_name() or user.username


def liaison_candidates(conference):
    """Who can be a liaison: staff, or an approved volunteer of the edition."""
    return (
        User.objects.filter(
            Q(is_staff=True)
            | Q(
                volunteerprofile__conference=conference,
                volunteerprofile__application_status=ApplicationStatus.APPROVED,
            )
        )
        .distinct()
        .order_by("first_name", "last_name", "username")
    )


class SessionPresenterForm(forms.ModelForm):
    """Add a presenter to a session with a role and display order."""

    class Meta:
        model = SessionPresenter
        fields = ["presenter", "role", "order", "is_required"]
        widgets = {
            "presenter": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "role": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "order": forms.NumberInput(
                attrs={"class": "form-control form-control-sm", "placeholder": "Order"}
            ),
            "is_required": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, session, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = session
        self.fields["presenter"].queryset = (
            Presenter.objects.for_conference(session.conference)
            .exclude(session_presenters__session=session)
            .order_by("display_name")
        )
        self.instance.session = session


class InviteForm(forms.Form):
    """The personal note that goes into an invitation email."""

    message_md = forms.CharField(
        label="Personal message",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text=MARKDOWN_HELP,
    )


class SpeakerProfileForm(forms.ModelForm):
    """What a presenter edits about themselves (design §2.3)."""

    timezone = forms.ChoiceField(
        choices=timezone_choices,
        help_text="Reminders and your schedule view use this.",
    )

    class Meta:
        model = Presenter
        fields = [
            "display_name",
            "pronouns",
            "bio_md",
            "headshot",
            "location",
            "timezone",
            "website_url",
            "github_username",
            "mastodon_url",
            "linkedin_url",
            "bluesky_username",
            "is_public",
        ]
        widgets = {"bio_md": forms.Textarea(attrs={"rows": 6})}
        labels = {"is_public": "Show my bio, photo and links on the public site"}
        help_texts = {
            "bio_md": MARKDOWN_HELP + " A couple of sentences is plenty.",
            "headshot": "A square photo works best.",
            "is_public": "Your name still appears on your sessions when this is off.",
        }


class SpeakerSessionForm(forms.ModelForm):
    """What a presenter edits about their session. Every field is optional
    markdown; the duration is set by the organizers."""

    class Meta:
        model = Session
        fields = [
            "summary_md",
            "outline_md",
            "prerequisites_md",
            "audience_md",
            "level",
            "language",
        ]
        widgets = {
            "summary_md": forms.Textarea(attrs={"rows": 4}),
            "outline_md": forms.Textarea(attrs={"rows": 6}),
            "prerequisites_md": forms.Textarea(attrs={"rows": 3}),
            "audience_md": forms.Textarea(attrs={"rows": 3}),
        }
        help_texts = {
            "summary_md": MARKDOWN_HELP + " What attendees see on the schedule.",
            "outline_md": MARKDOWN_HELP,
            "prerequisites_md": MARKDOWN_HELP,
            "audience_md": MARKDOWN_HELP,
        }


class SuggestCoPresenterForm(forms.Form):
    """ "Suggest a co-presenter": the organizers get an email and decide."""

    name = forms.CharField(max_length=200)
    email = forms.EmailField()
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Why they would be a great addition (optional).",
    )
