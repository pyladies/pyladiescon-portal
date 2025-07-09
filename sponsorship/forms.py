from django import forms

from .models import SponsorshipProfile


class SponsorshipProfileForm(forms.ModelForm):
    class Meta:
        model = SponsorshipProfile
        fields = [
            'main_contact_user',
            'additional_contacts',
            'organization_name',
            'sponsorship_type',
            #'sponsorship_tier',
            'logo',
            'company_description',
        ]
