"""Default checklists (design §9.1 and §9.7) and how to load or clone them.

Templates are data the organizers edit in the portal; these defaults only
seed an edition that has none. ``seed_checklists`` is idempotent: it keys
templates on (scope, type, role, delivery) and items on their title. Types
and roles are named by ``code`` and resolved to the edition's rows.

The defaults are opinionated starting points for PyLadiesCon (they name
Discord, the speaker guide, the PyJam post-production steps), not fixtures
the code depends on: an edition may rename, drop or add lines freely.

No default line is required. Accepting the invitation is the presenter's
confirmation (review decision, 2026-09-16), so a session confirms as soon
as its required presenters accept. Organizers may mark a line required in
the template editor; from then on it gates the session, so do that only
once the speaker checklist pages exist for the presenter to tick it.
"""

from typing import NamedTuple

from .constants import (
    SESSION_LANGUAGE,
    AssigneeDefault,
    AutoRule,
    ChecklistScope,
    Delivery,
    DueAnchor,
    ItemOwner,
    MediaKind,
)
from .models import ChecklistTemplate, ChecklistTemplateItem, PresenterRole, SessionType
from .program_types import (
    clone_program_types,
    presenter_role,
    seed_program_types,
    session_type,
)

SPK, ORG = ItemOwner.SPEAKER, ItemOwner.ORGANIZER
ACCEPTED, CONF, SESSION = (
    DueAnchor.INVITATION_ACCEPTED,
    DueAnchor.CONFERENCE_START,
    DueAnchor.SESSION_START,
)


def _item(owner, title, anchor="", offset=0, rule="", **extra):
    item = {
        "owner": owner,
        "title": title,
        "due_anchor": anchor,
        "due_offset_days": offset,
        "auto_complete_rule": rule,
    }
    item.update(extra)
    return item


BIO = _item(SPK, "Update your bio and headshot", ACCEPTED, 7, AutoRule.BIO_AND_HEADSHOT)
CONFIRM_TITLE = _item(SPK, "Confirm your session title and summary", ACCEPTED, 7)
GUIDE = _item(SPK, "Read the speaker guide", ACCEPTED, 14, AutoRule.HANDBOOK_READ)
REGISTER = _item(
    SPK, "Register for the conference", CONF, 14, AutoRule.PRETIX_REGISTERED
)
DISCORD = _item(SPK, "Join the PyLadiesCon Discord", ACCEPTED, 14)
CONFIRM_SLOT = _item(SPK, "Confirm your scheduled slot", SESSION, 14)
MATERIALS = _item(SPK, "Share a link to your workshop materials", SESSION, 7)
SLIDES = _item(SPK, "Share a link to your slides", SESSION, 3)
TECH_CHECK = _item(SPK, "Do a tech check", SESSION, 3)

ORGANIZER_ITEMS = [
    _item(ORG, "Invitation sent", ACCEPTED, 0, AutoRule.INVITATION_SENT),
    _item(ORG, "Presenter in portal", ACCEPTED, 0, AutoRule.INVITATION_ACCEPTED),
    _item(
        ORG,
        "Onboarding email sent",
        ACCEPTED,
        3,
        assignee_default=AssigneeDefault.LIAISON,
    ),
    _item(
        ORG,
        "Registration info sent",
        CONF,
        30,
        assignee_default=AssigneeDefault.LIAISON,
    ),
    _item(ORG, "Promo materials prepared", CONF, 21),
    _item(
        ORG,
        "Promo materials shared with presenter",
        CONF,
        14,
        assignee_default=AssigneeDefault.LIAISON,
    ),
    _item(ORG, "Session scheduled", CONF, 21, AutoRule.SESSION_SCHEDULED),
    _item(
        ORG,
        "Schedule confirmation sent",
        CONF,
        14,
        assignee_default=AssigneeDefault.LIAISON,
    ),
    _item(ORG, "Discord channel and speaker role assigned", ACCEPTED, 14),
    _item(
        ORG,
        "Day-of reminder sent",
        SESSION,
        1,
        assignee_default=AssigneeDefault.LIAISON,
    ),
]

WORKSHOP_SPEAKER = [
    BIO,
    CONFIRM_TITLE,
    GUIDE,
    REGISTER,
    DISCORD,
    CONFIRM_SLOT,
    MATERIALS,
    TECH_CHECK,
]
TALK_SPEAKER = [
    BIO,
    CONFIRM_TITLE,
    GUIDE,
    REGISTER,
    DISCORD,
    CONFIRM_SLOT,
    SLIDES,
    TECH_CHECK,
]
PANEL_LIGHT = [BIO, GUIDE, REGISTER, DISCORD, CONFIRM_SLOT, TECH_CHECK]
PERFORMER = [
    BIO,
    _item(SPK, "Confirm your title and description", ACCEPTED, 7),
    _item(SPK, "Read the performer guide", ACCEPTED, 14, AutoRule.HANDBOOK_READ),
    _item(
        SPK,
        "Upload your performance video",
        CONF,
        28,
        AutoRule.ASSET_EXISTS,
        requires_asset_kind=MediaKind.RAW_VIDEO,
    ),
    _item(SPK, "Approve the final cut", CONF, 7),
    REGISTER,
    DISCORD,
]
HOST = [
    _item(SPK, "Confirm you can host this slot", ACCEPTED, 7),
    DISCORD,
]
HOST_ORGANIZER = [
    _item(ORG, "Invitation sent", ACCEPTED, 0, AutoRule.INVITATION_SENT),
    _item(ORG, "Run-of-show shared with host", SESSION, 3),
]

POST_PRODUCTION = [
    _item(
        ORG,
        "Record intro video (MC)",
        CONF,
        21,
        AutoRule.ASSET_EXISTS,
        requires_asset_kind=MediaKind.INTRO,
    ),
    _item(
        ORG,
        "Record outro video (MC)",
        CONF,
        21,
        AutoRule.ASSET_EXISTS,
        requires_asset_kind=MediaKind.OUTRO,
    ),
    _item(ORG, "Review audio and video quality", CONF, 21),
    _item(
        ORG, "Check video length is within limit", CONF, 21, AutoRule.VIDEO_LENGTH_OK
    ),
    _item(
        ORG,
        "Transcribe",
        CONF,
        14,
        AutoRule.ASSET_EXISTS,
        requires_asset_kind=MediaKind.TRANSCRIPT,
        requires_asset_language=SESSION_LANGUAGE,
    ),
    _item(ORG, "Review transcript", CONF, 14),
    _item(
        ORG,
        "Translate",
        CONF,
        7,
        AutoRule.ASSET_EXISTS,
        requires_asset_kind=MediaKind.TRANSLATION,
        per_translation_language=True,
    ),
    _item(
        ORG,
        "Add title card and assemble final video",
        CONF,
        7,
        AutoRule.ASSET_EXISTS,
        requires_asset_kind=MediaKind.PROCESSED_VIDEO,
    ),
    _item(
        ORG,
        "Publish to YouTube with schedule and transcript",
        CONF,
        2,
        AutoRule.YOUTUBE_PUBLISHED,
    ),
]

# (scope, name, type code, role code, delivery, items)
DEFAULT_TEMPLATES = [
    (
        ChecklistScope.PRESENTER,
        "Workshop presenter",
        "WORKSHOP",
        "PRESENTER",
        "",
        WORKSHOP_SPEAKER + ORGANIZER_ITEMS,
    ),
    (
        ChecklistScope.PRESENTER,
        "Talk presenter",
        "TALK",
        "PRESENTER",
        "",
        TALK_SPEAKER + ORGANIZER_ITEMS,
    ),
    (
        ChecklistScope.PRESENTER,
        "Lightning talk presenter",
        "LIGHTNING",
        "PRESENTER",
        "",
        TALK_SPEAKER + ORGANIZER_ITEMS,
    ),
    (
        ChecklistScope.PRESENTER,
        "Keynote presenter",
        "KEYNOTE",
        "PRESENTER",
        "",
        TALK_SPEAKER + ORGANIZER_ITEMS,
    ),
    (
        ChecklistScope.PRESENTER,
        "Panelist",
        "PANEL",
        "PANELIST",
        "",
        PANEL_LIGHT + ORGANIZER_ITEMS,
    ),
    (
        ChecklistScope.PRESENTER,
        "Panel moderator",
        "PANEL",
        "MODERATOR",
        "",
        PANEL_LIGHT + ORGANIZER_ITEMS,
    ),
    (
        ChecklistScope.PRESENTER,
        "PyJam performer",
        "PYJAM",
        "PERFORMER",
        "",
        PERFORMER + ORGANIZER_ITEMS,
    ),
    (
        ChecklistScope.PRESENTER,
        "Opening host",
        "OPENING",
        "HOST",
        "",
        HOST + HOST_ORGANIZER,
    ),
    (
        ChecklistScope.PRESENTER,
        "Closing host",
        "CLOSING",
        "HOST",
        "",
        HOST + HOST_ORGANIZER,
    ),
    (
        ChecklistScope.PRESENTER,
        "Keynote host",
        "KEYNOTE",
        "HOST",
        "",
        HOST + HOST_ORGANIZER,
    ),
    (
        ChecklistScope.SESSION,
        "PyJam post-production",
        "PYJAM",
        "",
        Delivery.PRE_RECORDED,
        POST_PRODUCTION,
    ),
]


class SeedResult(NamedTuple):
    """What ``seed_checklists`` did: counts, plus the templates it left out
    because the edition has no type or role of that code."""

    templates: int
    items: int
    skipped: list  # of (template name, reason) pairs


def seed_checklists(conference):
    """Load the default templates into ``conference``. Safe to run again:
    existing templates keep their edits and only missing items are added.

    An edition with no session types yet gets the default types and roles
    first. An edition that has types keeps exactly the ones it has: a
    default template whose type or role the edition lacks (a retired
    keynote, say) is skipped and named in ``skipped``, never conjured up.
    Add the type on the "Types and roles" page and load again if wanted."""
    if not SessionType.objects.filter(conference=conference).exists():
        seed_program_types(conference)
    kinds = {t.code: t for t in SessionType.objects.filter(conference=conference)}
    roles = {r.code: r for r in PresenterRole.objects.filter(conference=conference)}
    templates_created = items_created = 0
    skipped = []
    for scope, name, kind, role, delivery, items in DEFAULT_TEMPLATES:
        if kind not in kinds:
            skipped.append((name, f"no {kind} session type in this edition"))
            continue
        if role and role not in roles:
            skipped.append((name, f"no {role} presenter role in this edition"))
            continue
        template, created = ChecklistTemplate.objects.get_or_create(
            conference=conference,
            scope=scope,
            kind=kinds[kind],
            role=roles[role] if role else None,
            delivery=delivery,
            defaults={"name": name},
        )
        templates_created += created
        existing = set(template.items.values_list("title", flat=True))
        next_order = template.items.count()
        for spec in items:
            if spec["title"] in existing:
                continue
            ChecklistTemplateItem.objects.create(
                template=template, order=next_order, **spec
            )
            existing.add(spec["title"])
            next_order += 1
            items_created += 1
    return SeedResult(templates_created, items_created, skipped)


ITEM_FIELDS = [
    "order",
    "owner",
    "title",
    "description_md",
    "due_anchor",
    "due_offset_days",
    "auto_complete_rule",
    "requires_asset_kind",
    "requires_asset_language",
    "per_translation_language",
    "is_required",
    "assignee_default",
]


def clone_checklists(target, source):
    """Copy ``source``'s templates and items into ``target``.

    Templates whose key already exists in ``target`` are skipped, so it is
    safe to run more than once. Returns ``(templates_created, items_created)``.
    """
    templates_created = items_created = 0
    # Types and roles come along first, matched by code.
    clone_program_types(target, source)
    for template in source.checklist_templates.select_related(
        "kind", "role"
    ).prefetch_related("items"):
        copy, created = ChecklistTemplate.objects.get_or_create(
            conference=target,
            scope=template.scope,
            kind=session_type(target, template.kind.code),
            role=presenter_role(target, template.role.code) if template.role else None,
            delivery=template.delivery,
            defaults={"name": template.name, "is_active": template.is_active},
        )
        if not created:
            continue
        templates_created += 1
        for item in template.items.all():
            ChecklistTemplateItem.objects.create(
                template=copy, **{field: getattr(item, field) for field in ITEM_FIELDS}
            )
            items_created += 1
    return templates_created, items_created
