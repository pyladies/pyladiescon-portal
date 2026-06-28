from django import forms
from django.contrib.auth.models import User

from portal.models import Conference

from .models import SponsorshipProfile, SponsorshipTier


class SponsorshipProfileForm(forms.ModelForm):

    main_contact_user = forms.ModelChoiceField(
        queryset=User.objects.filter(is_staff=True),
        help_text="Required. Main contact person from PyLadiesCon. Defaults to the person who creates the profile.",
        label="Internal Contact *",
    )
    conference = forms.ModelChoiceField(
        queryset=Conference.objects.all(),
        required=False,
        help_text="The conference edition this sponsorship is for. "
        "Defaults to the active conference.",
        label="Conference",
    )

    class Meta:
        model = SponsorshipProfile
        fields = [
            "conference",
            "main_contact_user",
            "organization_name",
            "sponsor_contact_name",
            "sponsors_contact_email",
            "sponsorship_tier",
            "sponsorship_override_amount",
            "po_number",
            "organization_address",
            "logo",
            "company_description",
            "progress_status",
            "github_issue_url",
        ]
        widgets = {
            "company_description": forms.Textarea(
                attrs={
                    "rows": 4,
                }
            ),
        }
        help_texts = {
            "organization_name": "Required",
            "progress_status": "Required",
            "sponsorship_override_amount": "Optional. If set, this amount will override the default sponsorship tier amount."
            " Keep blank to use the default tier amount.",
        }
        labels = {
            "organization_name": "Organization Name *",
            "progress_status": "Progress Status *",
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        # set the main contact user to the currently logged in user
        # for Now only admin users can be the creator of sponsorship profiles
        super().__init__(*args, **kwargs)
        if self.user:
            self.fields["main_contact_user"].initial = self.user.id
        active = Conference.get_active()
        # Pre-select the active conference; admins can switch to another year
        # (e.g. to set up next year's sponsors early).
        if not self.instance.pk:
            self.fields["conference"].initial = active
        # Offer only the relevant edition's tiers (tiers are conference-scoped);
        # when editing, that's the sponsor's own edition, otherwise the active
        # one — instead of listing every year's tiers.
        if self.instance.conference_id:
            tier_conference = self.instance.conference
        else:
            tier_conference = active
        self.fields["sponsorship_tier"].queryset = SponsorshipTier.objects.filter(
            conference=tier_conference
        )

    def clean(self):
        cleaned_data = super().clean()
        tier = cleaned_data.get("sponsorship_tier")
        conference = cleaned_data.get("conference") or Conference.get_active()
        # Guard the (selector vs dropdown) gap: a tier must belong to the same
        # conference the sponsorship is for.
        if tier and conference and tier.conference_id != conference.pk:
            self.add_error(
                "sponsorship_tier",
                "This tier belongs to a different conference edition.",
            )
        return cleaned_data

    def save(self, commit=True):
        if self.user:
            self.instance.user = self.user

        # A new sponsorship belongs to the active conference edition.
        if self.instance.conference_id is None:
            self.instance.conference = Conference.get_active()

        sponsorship_profile = super().save(commit)
        return sponsorship_profile


class SponsorshipTierForm(forms.ModelForm):
    """Create/edit a sponsorship tier through the portal."""

    class Meta:
        model = SponsorshipTier
        fields = ["conference", "name", "amount", "description", "sponsor_limit"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["conference"].initial = Conference.get_active()
