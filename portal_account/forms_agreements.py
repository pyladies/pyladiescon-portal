"""The form behind the agreement gate."""

from django import forms

from .models import PortalProfile


class AgreementsForm(forms.Form):
    """Both agreements, required, for an account that never met signup."""

    coc_agreement = forms.BooleanField(
        label="I agree to the Code of Conduct",
        help_text="You must agree to our Code of Conduct to use this site.",
    )
    tos_agreement = forms.BooleanField(
        label="I agree to the Terms of Service",
        help_text="You must agree to our Terms of Service to use this site.",
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def save(self):
        """Record both on the profile, creating it when there is none."""
        profile, _ = PortalProfile.objects.get_or_create(user=self.user)
        profile.coc_agreement = True
        profile.tos_agreement = True
        profile.save(update_fields=["coc_agreement", "tos_agreement", "modified_date"])
        return profile
