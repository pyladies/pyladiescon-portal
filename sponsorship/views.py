from django.shortcuts import render, redirect
from .forms import SponsorshipProfileForm
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .models import SponsorshipProfile

# Create your views here.

@login_required
def create_sponsorship_profile(request):
    if request.method == 'POST':
        form = SponsorshipProfileForm(request.POST, request.FILES)
        if form.is_valid():
            sponsorship_profile = form.save(commit=False)
            sponsorship_profile.user = request.user  # Assuming the user is logged in
            sponsorship_profile.save()
            sponsorship_profile.application_status = SponsorshipProfile.APPLICATION_PENDING
            form.save_m2m()  # Save many-to-many relationships
            return redirect('sponsorship:success')  # Redirect to a success page or profile page
    else:
        form = SponsorshipProfileForm()
    return render(request, 'portal/sponsorship/create_sponsorship_profile.html', {'form': form})

def success(request):
    return HttpResponse("Sponsorship profile created successfully!")

def sponsorship_success(request):
    return render(request, "sponsorship/success.html")