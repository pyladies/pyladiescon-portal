"""Default checklists (design §9.1 and §9.7) and how to load or clone them.

Templates are data the organizers edit in the portal; these defaults only
seed an edition that has none. ``seed_checklists`` is idempotent: it keys
templates on (scope, kind, role, delivery) and items on their title.
"""

from .constants import (
    SESSION_LANGUAGE,
    AssigneeDefault,
    AutoRule,
    ChecklistScope,
    Delivery,
    DueAnchor,
    ItemOwner,
    MediaKind,
    PresenterRole,
    SessionKind,
)
from .models import ChecklistTemplate, ChecklistTemplateItem

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


BIO = _item(
    SPK,
    "Update your bio and headshot",
    ACCEPTED,
    7,
    AutoRule.BIO_AND_HEADSHOT,
    is_required=True,
)
CONFIRM_TITLE = _item(
    SPK, "Confirm your session title and summary", ACCEPTED, 7, is_required=True
)
GUIDE = _item(SPK, "Read the speaker guide", ACCEPTED, 14, AutoRule.HANDBOOK_READ)
REGISTER = _item(
    SPK, "Register for the conference", CONF, 14, AutoRule.PRETIX_REGISTERED
)
DISCORD = _item(SPK, "Join the PyLadiesCon Discord", CONF, 14)
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
        ACCEPTED,
        7,
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
    _item(ORG, "Discord channel and speaker role assigned", CONF, 7),
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
    _item(SPK, "Confirm your title and description", ACCEPTED, 7, is_required=True),
    _item(SPK, "Read the performer guide", ACCEPTED, 14, AutoRule.HANDBOOK_READ),
    _item(
        SPK,
        "Upload your performance video",
        CONF,
        28,
        requires_asset_kind=MediaKind.RAW_VIDEO,
    ),
    _item(SPK, "Approve the final cut", CONF, 7),
    REGISTER,
    DISCORD,
]
HOST = [
    _item(SPK, "Confirm you can host this slot", ACCEPTED, 7, is_required=True),
    DISCORD,
]
HOST_ORGANIZER = [
    _item(ORG, "Invitation sent", ACCEPTED, 0, AutoRule.INVITATION_SENT),
    _item(ORG, "Run-of-show shared with host", SESSION, 3),
]

POST_PRODUCTION = [
    _item(
        ORG, "Record intro video (MC)", CONF, 21, requires_asset_kind=MediaKind.INTRO
    ),
    _item(
        ORG, "Record outro video (MC)", CONF, 21, requires_asset_kind=MediaKind.OUTRO
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
        requires_asset_kind=MediaKind.TRANSCRIPT,
        requires_asset_language=SESSION_LANGUAGE,
    ),
    _item(ORG, "Review transcript", CONF, 14),
    _item(
        ORG,
        "Translate",
        CONF,
        7,
        requires_asset_kind=MediaKind.TRANSLATION,
        per_translation_language=True,
    ),
    _item(
        ORG,
        "Add title card and assemble final video",
        CONF,
        7,
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

# (scope, name, kind, role, delivery, items)
DEFAULT_TEMPLATES = [
    (
        ChecklistScope.PRESENTER,
        "Workshop presenter",
        SessionKind.WORKSHOP,
        PresenterRole.PRESENTER,
        "",
        WORKSHOP_SPEAKER + ORGANIZER_ITEMS,
    ),
    (
        ChecklistScope.PRESENTER,
        "Workshop co-presenter",
        SessionKind.WORKSHOP,
        PresenterRole.CO_PRESENTER,
        "",
        WORKSHOP_SPEAKER + ORGANIZER_ITEMS,
    ),
    (
        ChecklistScope.PRESENTER,
        "Talk presenter",
        SessionKind.TALK,
        PresenterRole.PRESENTER,
        "",
        TALK_SPEAKER + ORGANIZER_ITEMS,
    ),
    (
        ChecklistScope.PRESENTER,
        "Talk co-presenter",
        SessionKind.TALK,
        PresenterRole.CO_PRESENTER,
        "",
        TALK_SPEAKER + ORGANIZER_ITEMS,
    ),
    (
        ChecklistScope.PRESENTER,
        "Lightning talk presenter",
        SessionKind.LIGHTNING,
        PresenterRole.PRESENTER,
        "",
        TALK_SPEAKER + ORGANIZER_ITEMS,
    ),
    (
        ChecklistScope.PRESENTER,
        "Keynote presenter",
        SessionKind.KEYNOTE,
        PresenterRole.PRESENTER,
        "",
        TALK_SPEAKER + ORGANIZER_ITEMS,
    ),
    (
        ChecklistScope.PRESENTER,
        "Panelist",
        SessionKind.PANEL,
        PresenterRole.PANELIST,
        "",
        PANEL_LIGHT + ORGANIZER_ITEMS,
    ),
    (
        ChecklistScope.PRESENTER,
        "Panel moderator",
        SessionKind.PANEL,
        PresenterRole.MODERATOR,
        "",
        PANEL_LIGHT + ORGANIZER_ITEMS,
    ),
    (
        ChecklistScope.PRESENTER,
        "PyJam performer",
        SessionKind.PYJAM,
        PresenterRole.PERFORMER,
        "",
        PERFORMER + ORGANIZER_ITEMS,
    ),
    (
        ChecklistScope.PRESENTER,
        "Opening host",
        SessionKind.OPENING,
        PresenterRole.HOST,
        "",
        HOST + HOST_ORGANIZER,
    ),
    (
        ChecklistScope.PRESENTER,
        "Closing host",
        SessionKind.CLOSING,
        PresenterRole.HOST,
        "",
        HOST + HOST_ORGANIZER,
    ),
    (
        ChecklistScope.PRESENTER,
        "Keynote host",
        SessionKind.KEYNOTE,
        PresenterRole.HOST,
        "",
        HOST + HOST_ORGANIZER,
    ),
    (
        ChecklistScope.SESSION,
        "PyJam post-production",
        SessionKind.PYJAM,
        "",
        Delivery.PRE_RECORDED,
        POST_PRODUCTION,
    ),
]


def seed_checklists(conference):
    """Load the default templates into ``conference``. Safe to run again:
    existing templates keep their edits and only missing items are added.
    Returns ``(templates_created, items_created)``."""
    templates_created = items_created = 0
    for scope, name, kind, role, delivery, items in DEFAULT_TEMPLATES:
        template, created = ChecklistTemplate.objects.get_or_create(
            conference=conference,
            scope=scope,
            kind=kind,
            role=role,
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
    return templates_created, items_created


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
    for template in source.checklist_templates.prefetch_related("items"):
        copy, created = ChecklistTemplate.objects.get_or_create(
            conference=target,
            scope=template.scope,
            kind=template.kind,
            role=template.role,
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
