"""Which hub the page belongs to, for the top navigation.

The tab a page belongs to used to be inferred in CSS from the rail the page
rendered, because the navbar is written before the rail. That marked the tab
by colour alone: no ``aria-current`` for a screen reader, and a browser
without ``:has()`` lost the mark entirely, since one bad selector drops a
whole comma-separated rule.

The section is decided here instead, from the URL that was matched, and the
navbar writes ``active`` and ``aria-current="page"`` itself. Anything not
named below belongs to Home, which is what a page with no rail always meant.
"""

HOME = "home"
VOLUNTEER = "volunteer"
SPEAKING = "speaking"
ORGANIZE = "organize"

# Whole namespaces. A name in EXCEPTIONS wins over its namespace.
SECTION_BY_NAMESPACE = {
    "volunteer": VOLUNTEER,
    "speakers": ORGANIZE,
    "sponsorship": ORGANIZE,
}

# Pages whose hub is not their namespace's.
EXCEPTIONS = {
    # A person's own work, under "My volunteering" for everyone.
    "speakers:checklist_queue": VOLUNTEER,
    "speakers:item_detail": VOLUNTEER,
    "speakers:item_status": VOLUNTEER,
    "speakers:item_assign": VOLUNTEER,
    "speakers:item_ready": VOLUNTEER,
    # Sponsors, read-only, sit in the personal rail; the manage pages are
    # organizer ones and keep the namespace's section.
    "sponsorship:sponsorship_list": VOLUNTEER,
    "sponsorship:sponsorship_detail": VOLUNTEER,
}

# Names outside those namespaces that belong to a hub.
SECTION_BY_NAME = {
    "organizer_dashboard": ORGANIZE,
    "conference_list": ORGANIZE,
    "conference_new": ORGANIZE,
    "conference_edit": ORGANIZE,
    "conference_delete": ORGANIZE,
    "start_new_year": ORGANIZE,
    "teams": ORGANIZE,
    "team_new": ORGANIZE,
    "team_edit": ORGANIZE,
    "team_delete": ORGANIZE,
    "maintenance_accounts": ORGANIZE,
    "my_teams": VOLUNTEER,
    "team_dashboard": VOLUNTEER,
    "team_detail": VOLUNTEER,
}


def current_section(request):
    """The hub this request belongs to: one of the four names above.

    The speaker side is every ``speakers:my_*`` page, which is how the
    speaker rail is chosen too.
    """
    match = getattr(request, "resolver_match", None)
    if match is None:
        return HOME
    view_name = match.view_name  # "namespace:name", or "name"
    if view_name in EXCEPTIONS:
        return EXCEPTIONS[view_name]
    if view_name.startswith("speakers:my_"):
        return SPEAKING
    namespace = match.namespaces[0] if match.namespaces else ""
    if namespace in SECTION_BY_NAMESPACE:
        return SECTION_BY_NAMESPACE[namespace]
    return SECTION_BY_NAME.get(view_name, HOME)


def navigation(request):
    """Context processor: the hub the current page belongs to."""
    return {"nav_section": current_section(request)}
