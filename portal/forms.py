from allauth.account.forms import SignupForm
from django import forms


class CustomSignupForm(SignupForm):
    first_name = forms.CharField(
        max_length=200,
        label="First Name",
        widget=forms.TextInput(attrs={"placeholder": "First Name"}),
    )
    last_name = forms.CharField(
        max_length=200,
        label="Last Name",
        widget=forms.TextInput(attrs={"placeholder": "Last Name"}),
    )
    coc_agreement = forms.BooleanField(
        required=True,
        label="I agree to the Code of Conduct",
        help_text="You must agree to our Code of Conduct to use this site.",
    )
    tos_agreement = forms.BooleanField(
        required=True,
        label="I agree to the Terms of Service",
        help_text="You must agree to our Terms of Service to use this site.",
    )

    def save(self, request):
        user = super().save(request)
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.save()

        from portal_account.models import PortalProfile

        portal_profile, created = PortalProfile.objects.get_or_create(user=user)
        portal_profile.coc_agreement = self.cleaned_data.get("coc_agreement", False)
        portal_profile.tos_agreement = self.cleaned_data.get("tos_agreement", False)
        portal_profile.save()

        return user
