from .models import Conference


def active_conference(request):
    """Expose the active conference to all templates as ``active_conference``."""
    return {"active_conference": Conference.get_active()}
