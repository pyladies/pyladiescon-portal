from django.shortcuts import render


def index(request):
    """Display the index page for all users."""
    return render(request, "portal/index.html")
