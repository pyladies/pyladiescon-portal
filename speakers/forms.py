import zoneinfo

from django import forms
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils.text import slugify
from text_unidecode import unidecode

from .constants import (
    DEFAULT_GUIDE_KEY,
    RESERVED_SLUGS,
    SLUG_MAX_LENGTH,
    Delivery,
    ItemOwner,
)
from .models import (
    ChecklistTemplate,
    ChecklistTemplateItem,
    Handbook,
    Presenter,
    PresenterRole,
    Session,
    SessionPresenter,
    SessionType,
)
from .people import assignee_candidates, liaison_candidates, user_label

MARKDOWN_HELP = "Markdown supported: headings, lists, links, **bold**, *italics*."


def _slug_field(example, source, who):
    """The editable web-address field, declared (not generated) so it accepts
    free text that ``_clean_slug`` normalises; Meta.help_texts would be
    ignored for a declared field, so the text lives here."""
    return forms.CharField(
        required=False,
        max_length=SLUG_MAX_LENGTH,
        label="Web address",
        help_text=f"Seen publicly as {who} web address, e.g. {example}. Leave "
        f"blank to derive it from the {source}. Speakers can change it until "
        "the session is scheduled; organizers can always rename it. Links "
        "already shared break if it changes.",
    )


class IdentityLockMixin:
    """For the speaker forms: the identity fields (title or name, and the
    web address) are theirs until the session is scheduled. With
    ``locked=True`` those fields are dropped, so a stale POST carrying them
    is ignored rather than rejected, and listed in ``locked_fields`` for the
    template to show read-only."""

    IDENTITY_FIELDS = ()

    def __init__(self, *args, locked=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.conference = self.instance.conference
        self.locked = locked
        self.locked_fields = []
        if locked:
            for name, label in self.IDENTITY_FIELDS:
                self.fields.pop(name)
                self.locked_fields.append((label, getattr(self.instance, name)))


class SessionForm(forms.ModelForm):
    """Create or edit a session. Every content field is optional markdown."""

    # Free text, normalised to a slug in clean_slug; a SlugField would refuse
    # "Intro To Django" before the cleaner could turn it into intro-to-django.
    # Declared here, so label and help text live here too: Meta.help_texts
    # applies only to fields Django generates from the model.
    slug = _slug_field("/speakers/sessions/django-101/", "title", "this session's")

    class Meta:
        model = Session
        fields = [
            "kind",
            "delivery",
            "title",
            "slug",
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
            "delivery": "Leave blank to use the type's default.",
        }

    def __init__(self, *args, conference, **kwargs):
        super().__init__(*args, **kwargs)
        self.conference = conference
        if not self.instance.conference_id:
            self.instance.conference = conference
        types = SessionType.objects.filter(conference=conference).filter(
            Q(is_active=True) | Q(pk=self.instance.kind_id)  # keep a retired type
        )
        self.fields["kind"].queryset = types
        self.fields["kind"].label = "Type"
        self.fields["duration_minutes"].help_text = (
            "Leave blank to use the default for the type: "
            + ", ".join(
                f"{t.name.lower()} {t.default_duration_minutes}"
                for t in types
                if t.is_content
            )
            + "."
        )

    def clean_slug(self):
        return _clean_slug(self, Session, "session")

    def clean(self):
        cleaned = super().clean()
        delivery = cleaned.get("delivery")
        if not delivery and cleaned.get("kind"):
            delivery = cleaned["kind"].default_delivery
        if delivery == Delivery.LIVE:
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
            "duration_minutes": "Leave blank to use the default for the type.",
            "summary_md": MARKDOWN_HELP,
        }

    def __init__(self, *args, conference, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.conference_id:
            self.instance.conference = conference
        self.fields["kind"].queryset = SessionType.objects.filter(
            conference=conference, is_content=False, is_active=True
        )
        self.fields["kind"].label = "Type"


def timezone_choices():
    return [(name, name) for name in sorted(zoneinfo.available_timezones())]


class PresenterForm(forms.ModelForm):
    """Organizer-side presenter create/edit, including the liaison."""

    timezone = forms.ChoiceField(choices=timezone_choices, initial="UTC")
    slug = _slug_field("/speakers/presenters/ada-lovelace/", "name", "this presenter's")

    class Meta:
        model = Presenter
        fields = [
            "display_name",
            "slug",
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
        self.fields["liaison"].label_from_instance = user_label

    def clean_slug(self):
        return _clean_slug(self, Presenter, "presenter")

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


class SessionPresenterForm(forms.ModelForm):
    """Add a presenter to a session with a role and display order."""

    class Meta:
        model = SessionPresenter
        # Display order stays at its default for now; it is not offered in the UI.
        fields = ["presenter", "role", "is_required"]
        widgets = {
            "presenter": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "role": forms.Select(attrs={"class": "form-select form-select-sm"}),
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
        # Only the roles the session's type allows; its default preselected.
        self.fields["role"].queryset = session.kind.roles.filter(is_active=True)
        self.fields["role"].empty_label = None
        self.fields["role"].initial = session.kind.default_role_id
        self.instance.session = session


class SessionPresenterRoleForm(forms.ModelForm):
    """Change a presenter's role, order or required flag on a session.

    The roles offered are the ones the session's type allows, so a panel
    cannot end up with a Performer.
    """

    def __init__(self, *args, session, roles=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].queryset = session.kind.roles.filter(
            is_active=True
        ).order_by("sort_order", "name")
        if roles is not None:
            # A session page builds one of these per presenter. Handing them
            # the roles it already read keeps the page at one query for the
            # lot instead of one each; validation still uses the queryset.
            self.fields["role"].choices = [(role.pk, role.name) for role in roles]

    class Meta:
        model = SessionPresenter
        fields = ["role", "is_required"]
        widgets = {
            "role": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "is_required": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class InviteForm(forms.Form):
    """The personal note that goes into an invitation email."""

    message_md = forms.CharField(
        label="Personal message",
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text=MARKDOWN_HELP,
    )


class SpeakerProfileForm(IdentityLockMixin, forms.ModelForm):
    """What a presenter edits about themselves (design §2.3).

    The display name and the web address are theirs until one of their
    sessions is scheduled (``locked``); then both are dropped from the form
    and shown read-only via ``locked_fields``.
    """

    timezone = forms.ChoiceField(
        choices=timezone_choices,
        help_text="Reminders and your schedule view use this.",
    )
    slug = _slug_field("/speakers/presenters/ada-lovelace/", "name", "your")

    IDENTITY_FIELDS = (("display_name", "Name"), ("slug", "Web address"))

    class Meta:
        model = Presenter
        fields = [
            "display_name",
            "slug",
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

    def clean_slug(self):
        return _clean_slug(self, Presenter, "presenter")


class SpeakerSessionForm(IdentityLockMixin, forms.ModelForm):
    """What a presenter edits about their session. Every content field is
    optional markdown; the duration is set by the organizers.

    The title and the web address are theirs to edit until an organizer
    schedules the session (``locked``); then those two fields are dropped
    from the form, so a stale POST carrying them is ignored rather than
    rejected, and shown read-only by the template via ``locked_fields``.
    """

    slug = _slug_field("/speakers/sessions/django-101/", "title", "this session's")

    class Meta:
        model = Session
        fields = [
            "title",
            "slug",
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

    IDENTITY_FIELDS = (("title", "Title"), ("slug", "Web address"))

    def clean_slug(self):
        return _clean_slug(self, Session, "session")


class SuggestCoPresenterForm(forms.Form):
    """ "Suggest a co-presenter": the organizers get an email and decide."""

    name = forms.CharField(max_length=200)
    email = forms.EmailField()
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Why they would be a great addition (optional).",
    )


def _clean_slug(form, model, noun):
    """Normalise an optional slug and refuse a clash within the edition.

    Blank means "derive from the title or name on save". The unique
    constraint spans ``conference``, which is not a form field, so Django's
    constraint validation skips it here."""
    slug = slugify(unidecode(form.cleaned_data.get("slug", "") or ""))[:SLUG_MAX_LENGTH]
    if not slug:
        # Blank on create derives from the title or name on save; blank on
        # edit keeps the current address rather than rotating it.
        return form.instance.slug or ""
    if slug in RESERVED_SLUGS:
        raise forms.ValidationError(f"“{slug}” is reserved; pick another address.")
    clash = model.objects.filter(conference=form.conference, slug=slug).exclude(
        pk=form.instance.pk
    )
    if clash.exists():
        raise forms.ValidationError(f"Another {noun} already uses this address.")
    return slug


def _unique_code(form, model, noun):
    """Normalise a code and refuse a clash within the edition.

    The model's unique constraint spans ``conference``, which is not a form
    field, so Django's constraint validation skips it here; without this a
    case variant would only fail on the database."""
    code = form.cleaned_data["code"].strip().upper()
    clash = model.objects.filter(conference=form.conference, code=code).exclude(
        pk=form.instance.pk
    )
    if clash.exists():
        raise forms.ValidationError(f"A {noun} with this code already exists.")
    return code


class PresenterRoleForm(forms.ModelForm):
    """A role organizers can put people in (settings page)."""

    class Meta:
        model = PresenterRole
        fields = ["name", "code", "email_word", "sort_order", "is_active"]
        help_texts = {
            "code": "Upper-case key used by seeds and next year's copy; "
            "cannot change once sessions use the role.",
        }

    def __init__(self, *args, conference, **kwargs):
        super().__init__(*args, **kwargs)
        self.conference = conference
        self.instance.conference = conference
        if self.instance.pk and self.instance.session_presenters.exists():
            self.fields["code"].disabled = True

    def clean_code(self):
        return _unique_code(self, PresenterRole, "role")


class SessionTypeForm(forms.ModelForm):
    """A kind of schedule row and who can be on it (settings page). This is
    where "the default role is one of the allowed roles" is enforced: the
    model cannot check it because the admin saves the many-to-many after
    ``full_clean``."""

    class Meta:
        model = SessionType
        fields = [
            "name",
            "code",
            "is_content",
            "default_duration_minutes",
            "default_delivery",
            "spans_all_channels",
            "roles",
            "default_role",
            "sort_order",
            "is_active",
        ]
        widgets = {"roles": forms.CheckboxSelectMultiple}
        help_texts = {
            "code": "Upper-case key used by seeds and next year's copy; "
            "cannot change once sessions use the type.",
            "roles": "Leave every box empty for a row that takes no people, "
            "such as a break.",
        }

    def __init__(self, *args, conference, **kwargs):
        super().__init__(*args, **kwargs)
        self.conference = conference
        self.instance.conference = conference
        keep = Q(is_active=True) | Q(pk=self.instance.default_role_id)
        if self.instance.pk:
            keep |= Q(session_types=self.instance)  # a retired role still on it
        roles = (
            PresenterRole.objects.filter(conference=conference).filter(keep).distinct()
        )
        self.fields["roles"].queryset = roles
        self.fields["default_role"].queryset = roles
        if self.instance.pk and self.instance.sessions.exists():
            self.fields["code"].disabled = True

    def clean_code(self):
        return _unique_code(self, SessionType, "session type")

    def clean(self):
        cleaned = super().clean()
        default = cleaned.get("default_role")
        roles = cleaned.get("roles")
        if default is not None and roles is not None and default not in roles:
            self.add_error(
                "default_role", "The default role must be one of the allowed roles."
            )
        return cleaned


class AdhocItemForm(forms.Form):
    """A one-off checklist item for one presenter (design §9.2)."""

    title = forms.CharField(max_length=200)
    owner = forms.ChoiceField(choices=ItemOwner.choices, initial=ItemOwner.ORGANIZER)
    due_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    assignee = forms.ModelChoiceField(queryset=User.objects.none(), required=False)
    description_md = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text=MARKDOWN_HELP,
    )

    def __init__(self, *args, conference, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignee"].queryset = assignee_candidates(conference)
        self.fields["assignee"].label_from_instance = user_label


class AssignItemForm(forms.Form):
    assignee = forms.ModelChoiceField(queryset=User.objects.none(), required=False)

    def __init__(self, *args, conference, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignee"].queryset = assignee_candidates(conference)


class ChecklistTemplateForm(forms.ModelForm):
    class Meta:
        model = ChecklistTemplate
        fields = ["scope", "name", "kind", "role", "delivery", "is_active"]
        help_texts = {
            "role": "Presenter templates: which role on the session this applies to.",
            "delivery": "Session templates: live or pre-recorded.",
        }

    def __init__(self, *args, conference, **kwargs):
        super().__init__(*args, **kwargs)
        self.conference = conference
        self.instance.conference = conference
        keep_kind = Q(is_active=True) | Q(pk=self.instance.kind_id)
        keep_role = Q(is_active=True) | Q(pk=self.instance.role_id)
        self.fields["kind"].queryset = SessionType.objects.filter(
            conference=conference
        ).filter(keep_kind)
        self.fields["role"].queryset = PresenterRole.objects.filter(
            conference=conference
        ).filter(keep_role)

    def clean(self):
        """Per-edition uniqueness of the key; the model's ``clean()`` (run by
        the ModelForm after this) reports the scope/role/delivery rules."""
        cleaned = super().clean()
        if self.errors:
            return cleaned
        clash = ChecklistTemplate.objects.filter(
            conference=self.conference,
            scope=cleaned.get("scope"),
            kind=cleaned.get("kind"),
            role=cleaned.get("role"),
            delivery=cleaned.get("delivery", ""),
        )
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            self.add_error(
                "kind", "A template with this scope, kind and role/delivery exists."
            )
        return cleaned


class ChecklistTemplateItemForm(forms.ModelForm):
    class Meta:
        model = ChecklistTemplateItem
        fields = [
            "title",
            "owner",
            "description_md",
            "due_anchor",
            "due_offset_days",
            "auto_complete_rule",
            "requires_asset_kind",
            "requires_asset_language",
            "requires_handbook",
            "per_translation_language",
            "is_required",
            "assignee_default",
        ]
        widgets = {"description_md": forms.Textarea(attrs={"rows": 2})}
        help_texts = {
            "description_md": MARKDOWN_HELP
            + " Speakers see this under the title on their to-do list.",
            "auto_complete_rule": "Pick a rule and the portal ticks the item itself.",
        }

    def __init__(self, *args, conference, **kwargs):
        super().__init__(*args, **kwargs)
        # The guide is picked from the edition's guides, not typed.
        choices = [("", f"{DEFAULT_GUIDE_KEY} (default)")] + [
            (key, f"{title} ({key})")
            for key, title in Handbook.keys(conference)
            if key != DEFAULT_GUIDE_KEY
        ]
        self.fields["requires_handbook"] = forms.ChoiceField(
            choices=choices,
            required=False,
            label="Guide",
            help_text='Which guide the "read the guide" rule checks.',
        )


class NewHandbookForm(forms.Form):
    """Start another guide for the edition (workshop, keynote, performer...)."""

    key = forms.SlugField(max_length=40, help_text="Short identifier, e.g. workshop.")
    title = forms.CharField(max_length=200)

    def __init__(self, *args, conference, **kwargs):
        super().__init__(*args, **kwargs)
        self.conference = conference

    def clean_key(self):
        key = self.cleaned_data["key"].lower()
        if Handbook.objects.filter(conference=self.conference, key=key).exists():
            raise forms.ValidationError("A guide with this key already exists.")
        return key


DEFAULT_GUIDE_URL = "https://conference.pyladies.com/docs/"


class HandbookForm(forms.ModelForm):
    class Meta:
        model = Handbook
        fields = ["title", "url", "body_md"]
        widgets = {"body_md": forms.Textarea(attrs={"rows": 6})}
        help_texts = {"body_md": MARKDOWN_HELP + " Optional."}


class PresenterInviteForm(InviteForm):
    """Invite from the presenter page: pick the session (or the conference
    in general) and write the note."""

    session = forms.ChoiceField(required=False, label="Invite to")

    def __init__(self, *args, presenter, **kwargs):
        super().__init__(*args, **kwargs)
        self.presenter = presenter
        self.links = list(
            presenter.session_presenters.select_related("session", "role").order_by(
                "session__title"
            )
        )
        self.fields["session"].choices = [
            (str(link.session_id), f"{link.session.title} ({link.role.name})")
            for link in self.links
        ] + [("", "The conference in general")]
        self.order_fields(["session", "message_md"])

    def clean_session(self):
        """The choices were built from ``self.links``, and ChoiceField has
        already refused anything else, so read the answer off that list
        instead of querying for it again."""
        value = self.cleaned_data["session"]
        if not value:
            return None
        return next(
            link.session for link in self.links if str(link.session_id) == value
        )
