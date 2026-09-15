from django import forms

from .constants import CONTENT_KINDS, DEFAULT_DURATION_MINUTES, Delivery, SessionKind
from .models import Session

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
