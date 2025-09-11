from django import forms

from .models import SponsorshipProfile


class SponsorshipProfileForm(forms.ModelForm):
    class Meta:
        model = SponsorshipProfile
        fields = [
            "main_contact_user",
            "organization_name",
            "sponsorship_tier",
            "logo",
            "company_description",
            "application_status",
        ]
        widgets = {
            "company_description": forms.Textarea(
                attrs={
                    "rows": 4,
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        self._user = user  # ✅ Save user for later use

        if user:
            self.fields["main_contact_user"].initial = user

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.main_contact_user = self._user  # Enforce value
        instance.application_status = "pending"  # Set status manually
        if commit:
            instance.save()
            self.save_m2m()
        return instance
