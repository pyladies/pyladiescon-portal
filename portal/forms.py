from allauth.account.forms import SignupForm
from django import forms
from django.utils.safestring import mark_safe


class CustomSignupForm(SignupForm):
    first_name = forms.CharField(
        max_length=200,
        label='First Name',
        widget=forms.TextInput(
            attrs={'placeholder': 'First Name'}
        )
    )
    
    last_name = forms.CharField(
        max_length=200,
        label='Last Name',
        widget=forms.TextInput(
            attrs={'placeholder': 'Last Name'}
        )
    )
    
    tos_agreement = forms.BooleanField(
        required=True,
        label=mark_safe('I agree to the <a href="https://policies.python.org/pypi.org/Terms-of-Service/" target="_blank">Terms of Service</a>'),
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    coc_agreement = forms.BooleanField(
        required=True,
        label=mark_safe('I agree to the <a href="https://conference.pyladies.com/about/#code-of-conduct" target="_blank">Code of Conduct</a>'),
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    field_order = ['email', 'username', 'first_name', 'last_name', 'password1', 'password2', 'tos_agreement', 'coc_agreement']

    def save(self, request):
        user = super().save(request)
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.save()
        
        from portal_account.models import PortalProfile
        profile, _ = PortalProfile.objects.get_or_create(user=user)
        profile.coc_agreement = self.cleaned_data.get('coc_agreement')
        profile.tos_agreement = self.cleaned_data.get('tos_agreement')
        profile.save()
        
        return user 