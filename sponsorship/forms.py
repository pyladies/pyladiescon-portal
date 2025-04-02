from django import forms
from .models import SponsorshipProfile

class SponsorshipProfileForm(forms.ModelForm):
    class Meta:
        model = SponsorshipProfile
        exclude = ['user', 'application_status']
        fields = [
            'main_contact',
            'additional_contacts',
            'sponsor_organization_name',
            'sponsorship_type',
            'sponsorship_tier',
            'logo',
            'company_description',
            'application_status',
        ]
        widgets = {
            'additional_contacts': forms.CheckboxSelectMultiple(attrs={'class': 'form-control'}),
            'company_description': forms.Textarea(attrs={'rows': 4,}),
        }