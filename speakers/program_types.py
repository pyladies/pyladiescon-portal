"""Session types and presenter roles are data, seeded per edition.

What a schedule row is (workshop, panel, break...) and what a person can be
on it (presenter, panelist, host...) used to be enumerations in code. They
are rows now, so an edition can add a "Sprint" or a "Lightning host" without
a deploy, and the code only reads the behaviour flags on the type row.

``seed_program_types`` loads the defaults below for one edition and is
idempotent: it creates what is missing by ``code`` and never overwrites what
organizers changed.
"""

from .constants import Delivery
from .models import PresenterRole, SessionType

# code, name, the word the thank-you preface uses, sort order
DEFAULT_ROLES = [
    ("PRESENTER", "Presenter", "speaker", 10),
    ("PANELIST", "Panelist", "panelist", 20),
    ("MODERATOR", "Moderator", "moderator", 30),
    ("HOST", "Host", "host", 40),
    ("PERFORMER", "Performer", "performer", 50),
]

# code, name, is_content, default duration, default delivery, spans all
# channels, allowed role codes (first one is the default), sort order.
# The two a stranger may propose are opened below, after the table.
DEFAULT_SESSION_TYPES = [
    ("WORKSHOP", "Workshop", True, 90, Delivery.LIVE, False, ["PRESENTER"], 10),
    ("TALK", "Talk", True, 30, Delivery.LIVE, False, ["PRESENTER"], 20),
    ("LIGHTNING", "Lightning talk", True, 5, Delivery.LIVE, False, ["PRESENTER"], 30),
    ("PANEL", "Panel", True, 60, Delivery.LIVE, False, ["PANELIST", "MODERATOR"], 40),
    (
        "PYJAM",
        "PyJam performance",
        True,
        30,
        Delivery.PRE_RECORDED,
        False,
        ["PERFORMER"],
        50,
    ),
    ("KEYNOTE", "Keynote", False, 45, Delivery.LIVE, False, ["PRESENTER", "HOST"], 60),
    ("OPENING", "Opening", False, 15, Delivery.LIVE, True, ["HOST"], 70),
    ("CLOSING", "Closing", False, 15, Delivery.LIVE, True, ["HOST"], 80),
    ("ANNOUNCEMENT", "Announcement", False, 5, Delivery.LIVE, True, ["HOST"], 90),
    ("BREAK", "Break", False, 15, Delivery.LIVE, True, [], 100),
    ("SOCIAL", "Social", False, 60, Delivery.LIVE, True, [], 110),
    ("OTHER", "Other", False, 30, Delivery.LIVE, False, ["PRESENTER", "HOST"], 120),
]


# The types a person may propose, or add for themselves, on a fresh
# edition: the three someone brings to the conference. The rest are the
# program's own furniture (the opening, a break) or an invitation the team
# makes (a keynote). Every edition can change this on the "Types and roles"
# page; the seed only decides where it starts.
PROPOSABLE_CODES = {"TALK", "WORKSHOP", "PYJAM"}


def seed_program_types(conference):
    """Create the default roles and session types for ``conference``.

    Returns ``(types_created, roles_created)``. Existing rows (matched by
    ``code``) are left exactly as they are, mapping included, so rerunning
    after organizers edited a type changes nothing.
    """
    roles_created = 0
    roles = {}
    for code, name, email_word, order in DEFAULT_ROLES:
        role, created = PresenterRole.objects.get_or_create(
            conference=conference,
            code=code,
            defaults={"name": name, "email_word": email_word, "sort_order": order},
        )
        roles[code] = role
        roles_created += created
    types_created = 0
    for (
        code,
        name,
        is_content,
        duration,
        delivery,
        spans,
        role_codes,
        order,
    ) in DEFAULT_SESSION_TYPES:
        session_type, created = SessionType.objects.get_or_create(
            conference=conference,
            code=code,
            defaults={
                "name": name,
                "is_content": is_content,
                "default_duration_minutes": duration,
                "default_delivery": delivery,
                "spans_all_channels": spans,
                "sort_order": order,
                "default_role": roles[role_codes[0]] if role_codes else None,
            },
        )
        if created:
            session_type.roles.set([roles[c] for c in role_codes])
            # What someone may propose, or add for themselves: a talk or a
            # workshop. Nobody proposes a coffee break, and an edition can
            # open more types on the "Types and roles" page.
            if code in PROPOSABLE_CODES:
                session_type.open_for_proposals = True
                session_type.save(update_fields=["open_for_proposals"])
            types_created += 1
    return types_created, roles_created


def session_type(conference, code):
    """The edition's type with this ``code``, seeding the defaults first if
    the edition has none yet (tests and sample data lean on this)."""
    if not SessionType.objects.filter(conference=conference).exists():
        seed_program_types(conference)
    return SessionType.objects.get(conference=conference, code=code)


def presenter_role(conference, code):
    """The edition's role with this ``code``, seeding first if needed."""
    if not PresenterRole.objects.filter(conference=conference).exists():
        seed_program_types(conference)
    return PresenterRole.objects.get(conference=conference, code=code)


def clone_program_types(target, source):
    """Copy ``source``'s roles, types and the mapping into ``target`` by
    code, keeping whatever ``target`` already has. Returns
    ``(types_created, roles_created)``.

    This is the speaker module's "start next year" hook, reached through
    ``seeds.clone_checklists``. The conference creation flow in
    ``portal.views`` (the one that calls ``portal.services.clone_teams``)
    is where it should be wired in when the 2027 edition is set up."""
    roles_created = types_created = 0
    role_map = {}
    for role in PresenterRole.objects.filter(conference=source):
        copy, created = PresenterRole.objects.get_or_create(
            conference=target,
            code=role.code,
            defaults={
                "name": role.name,
                "email_word": role.email_word,
                "sort_order": role.sort_order,
                "is_active": role.is_active,
            },
        )
        role_map[role.pk] = copy
        roles_created += created
    for session_type in SessionType.objects.filter(conference=source).prefetch_related(
        "roles"
    ):
        copy, created = SessionType.objects.get_or_create(
            conference=target,
            code=session_type.code,
            defaults={
                "name": session_type.name,
                "is_content": session_type.is_content,
                "default_duration_minutes": session_type.default_duration_minutes,
                "default_delivery": session_type.default_delivery,
                "spans_all_channels": session_type.spans_all_channels,
                "open_for_proposals": session_type.open_for_proposals,
                "sort_order": session_type.sort_order,
                "is_active": session_type.is_active,
                "default_role": role_map.get(session_type.default_role_id),
            },
        )
        if created:
            copy.roles.set([role_map[r.pk] for r in session_type.roles.all()])
            types_created += 1
    return types_created, roles_created
