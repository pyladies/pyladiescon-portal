from django import forms
from .models import SponsorshipProfile

class SponsorshipProfileForm(forms.ModelForm):
    class Meta:
        model = SponsorshipProfile
        fields = [
            'main_contact',
            'sponsor_organization_name',
            'sponsorship_type',
            'sponsorship_tier',
            'logo',
            'company_description',
            'application_status',
        ]
        widgets = {
            'company_description': forms.Textarea(attrs={'rows': 4,}),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)  # Expecting current user from the view
        super().__init__(*args, **kwargs)

        if user:
            self.fields["main_contact"].initial = user
            self.fields["main_contact"].disabled = True  # Makes it read-only

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.main_contact = self._user  # Enforce value
        instance.application_status = 'pending'  # Set status manually
        if commit:
            instance.save()
            self.save_m2m()
        return instance