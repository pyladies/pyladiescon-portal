from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import SponsorshipProfileForm


@login_required
def create_sponsorship_profile(request):
    if request.method == 'POST':
        form = SponsorshipProfileForm(request.POST, request.FILES)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.user = request.user
            profile.application_status = 'pending'
            profile.save()
            form.save_m2m()  # Save ManyToMany relationships
            messages.success(request, "Sponsorship profile submitted successfully!")
            form = SponsorshipProfileForm()  # Clear form after submission
    else:
        form = SponsorshipProfileForm()
    return render(request, 'sponsorship/sponsorship_profile_form.html', {'form': form})
