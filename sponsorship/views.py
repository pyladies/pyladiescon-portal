from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .forms import SponsorshipProfileForm


@login_required
def create_sponsorship_profile(request):
    if request.method == "POST":
        form = SponsorshipProfileForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.user = request.user  # Set the user field
            profile.save()
            form.save_m2m()  # Save ManyToMany relationships
            messages.success(request, "Sponsorship profile submitted successfully!")
            form = SponsorshipProfileForm(user=request.user)  # Fresh form for next use
    else:
        form = SponsorshipProfileForm(user=request.user)
    return render(request, "sponsorship/sponsorship_profile_form.html", {"form": form})


@login_required
def sponsorship_success(request):
    print("Not implemented", request)
    pass