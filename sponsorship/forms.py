from django import forms

from .models import SponsorshipProfile


class SponsorshipProfileForm(forms.ModelForm):
    class Meta:
        model = SponsorshipProfile
        fields = [
            "main_contact_user",
            "additional_contacts",
            "organization_name",
            "sponsorship_type",
            "logo",
            "company_description",
        ]
