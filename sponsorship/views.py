from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from .models import SponsorshipTier, SponsorshipApplication, SponsorshipAsset
from .forms import SponsorshipTierForm, SponsorshipStatusForm, SponsorshipAssetForm


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

#addition of more functionalities via sponsorship review code
@login_required
def review_sponsorship_applications(request):
    """ Allow sponsorship team to review applications. """
    applications = SponsorshipApplication.objects.all()
    return render(request, "sponsorship/review_applications.html", {"applications": applications})

#code for sponsorship progress functionality
@login_required
def sponsorship_progress_overview(request):
    """ Display an overview of sponsorship progress. """
    applications = SponsorshipApplication.objects.all()
    total_applications = applications.count()
    approved = applications.filter(status="Approved").count()
    pending = applications.filter(status="Pending").count()
    rejected = applications.filter(status="Rejected").count()
    contracts_sent = applications.filter(contract_sent=True).count()
    paid_sponsorships = applications.filter(payment_received=True).count()

    context = {
        "total_applications": total_applications,
        "approved": approved,
        "pending": pending,
        "rejected": rejected,
        "contracts_sent": contracts_sent,
        "paid_sponsorships": paid_sponsorships,
    }
    return render(request, "sponsorship/progress_overview.html", context)
