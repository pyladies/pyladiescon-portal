from django import forms
from django.contrib.auth.models import User

from .models import SponsorshipProfile


class SponsorshipProfileForm(forms.ModelForm):

    main_contact_user = forms.ModelChoiceField(
        queryset=User.objects.filter(is_staff=True),
        help_text="Required. Main contact person from PyLadiesCon. Defaults to the person who creates the profile.",
        label="Internal Contact *",
    )

    class Meta:
        model = SponsorshipProfile
        fields = [
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

    def save(self, commit=True):
        if self.user:
            self.instance.user = self.user

        sponsorship_profile = super().save(commit)
        return sponsorship_profile
