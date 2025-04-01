from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from .models import SponsorshipTier
from .forms import SponsorshipTierForm

"""from the above this is a sample code i am contributing of starting the sponsorship
portal below, we would have to import the form and models which i havent 
written code for yet which is to be implemented in the views here"""

# Creating views here.

#code functionality for sponsorship tier creation 
@login_required
def create_sponsorship_tier(request):
    """ Allow sponsorship team to define sponsorship tiers. """
    if request.method == "POST":
        form = SponsorshipTierForm(request.POST)
        if form.is_valid():
            form.save()
            return JsonResponse({"message": "Sponsorship tier created successfully!"}, status=201)
    else:
        form = SponsorshipTierForm()
    return render(request, "sponsorship/create_tier.html", {"form": form})

#code sample for tier listing
@login_required
def list_sponsorship_tiers(request):
    """ List all sponsorship tiers available. """
    tiers = SponsorshipTier.objects.all()
    return render(request, "sponsorship/list_tiers.html", {"tiers": tiers})