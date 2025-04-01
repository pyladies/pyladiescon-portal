from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from .models import SponsorshipApplication, VolunteerTask

#views functionality
#sample code for functionalities of various dashboards for various teams
@login_required
def staffteam_dashboard(request):
    """ Redirect users to their respective team dashboards based on group membership. """
    if request.user.groups.filter(name="Sponsorship Team").exists():
        return redirect("sponsorship_dashboard")
    elif request.user.groups.filter(name="Volunteer Team").exists():
        return redirect("volunteer_dashboard")
    elif request.user.groups.filter(name="Staff Team").exists():
        return redirect("staff_dashboard")
    else:
        return render(request, "dashboard/no_access.html")

@login_required
def sponsorship_dashboard(request):
    """ Dashboard for Sponsorship Team. """
    if not request.user.groups.filter(name="Sponsorship Team").exists():
        return render(request, "dashboard/no_access.html")

    total_applications = SponsorshipApplication.objects.count()
    approved = SponsorshipApplication.objects.filter(status="Approved").count()
    pending = SponsorshipApplication.objects.filter(status="Pending").count()
    rejected = SponsorshipApplication.objects.filter(status="Rejected").count()

    context = {
        "total_applications": total_applications,
        "approved": approved,
        "pending": pending,
        "rejected": rejected,
    }
    return render(request, "dashboard/sponsorship_dashboard.html", context)

@login_required
def volunteer_dashboard(request):
    """ Dashboard for Volunteer Management Team. """
    if not request.user.groups.filter(name="Volunteer Team").exists():
        return render(request, "dashboard/no_access.html")

    total_tasks = VolunteerTask.objects.count()
    completed_tasks = VolunteerTask.objects.filter(status="Completed").count()
    pending_tasks = VolunteerTask.objects.filter(status="Pending").count()

    context = {
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "pending_tasks": pending_tasks,
    }
    return render(request, "dashboard/volunteer_dashboard.html", context)
