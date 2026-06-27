from allauth.account.forms import SignupForm
from django import forms

from portal.models import Conference


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


class StartNewYearForm(forms.Form):
    """Create a new conference edition and carry over from the previous one."""

    year = forms.IntegerField(min_value=2000, label="Year")
    name = forms.CharField(max_length=100, label="Name")
    slug = forms.SlugField(label="Slug")
    clone_teams = forms.BooleanField(
        required=False, initial=True, label="Clone teams from the previous edition"
    )
    copy_tiers = forms.BooleanField(
        required=False, initial=True, label="Copy sponsorship tiers"
    )
    copy_goals = forms.BooleanField(
        required=False, initial=True, label="Copy goal amounts"
    )
    bring_volunteers = forms.BooleanField(
        required=False, label="Bring forward approved volunteers (as pending)"
    )
    activate = forms.BooleanField(required=False, label="Activate this edition now")

    def clean_year(self):
        year = self.cleaned_data["year"]
        if Conference.objects.filter(year=year).exists():
            raise forms.ValidationError("A conference for that year already exists.")
        return year

    def clean_slug(self):
        slug = self.cleaned_data["slug"]
        if Conference.objects.filter(slug=slug).exists():
            raise forms.ValidationError("A conference with that slug already exists.")
        return slug
