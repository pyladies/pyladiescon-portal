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

from django.db import transaction

from .checklists import collapse_general_duplicates
from .constants import (
    SESSION_LANGUAGE,
    AssigneeDefault,
    AutoRule,
    ChecklistScope,
    Delivery,
    DueAnchor,
    ItemOwner,
    MediaKind,
    ReadyRule,
)
from .models import (
    ChecklistTemplate,
    ChecklistTemplateItem,
    Handbook,
    PresenterRole,
    ReadinessGate,
    SessionType,
    SpeakerSettings,
)
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


# Gates the default lines wait on. Code, name, what the speaker reads
# while it is shut, and what it is for. They start shut: the work behind
# them has not been done when an edition is seeded.
DEFAULT_GATES = [
    (
        "tech-check-open",
        "Tech check booking open",
        "booking opens closer to the conference",
        "Open once the team has the equipment and a way for speakers to book "
        "a slot.",
    ),
    (
        "upload-open",
        "Recording upload open",
        "uploads open closer to the conference",
        "Open once the portal can take recordings and the team is ready to "
        "review them.",
    ),
]


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
    description_md="Fill in a short bio and upload a square photo on your profile; attendees see both next to your session. Ticks itself once both are there.",
)
CONFIRM_TITLE = _item(
    SPK,
    "Check your session title and summary",
    ACCEPTED,
    7,
    description_md="Check that the title and summary on your session page read the way you want them on the schedule, and edit them if not.",
)
GUIDE = _item(
    SPK,
    "Read the speaker guide",
    ACCEPTED,
    14,
    AutoRule.HANDBOOK_READ,
    ready_rule=ReadyRule.GUIDE_PUBLISHED,
    waiting_note="we are still writing it",
    description_md="Everything about the format, timing and what we need from you. Ticks itself when you reach the end of the guide.",
)
WORKSHOP_GUIDE = _item(
    SPK,
    "Read the workshop guide",
    ACCEPTED,
    14,
    AutoRule.HANDBOOK_READ,
    requires_handbook="workshop",
    ready_rule=ReadyRule.GUIDE_PUBLISHED,
    waiting_note="we are still writing it",
    description_md="How a workshop runs at the conference, the setup we need from you and the deadlines. Ticks itself when you reach the end of the guide.",
    once_per_presenter=True,
)
KEYNOTE_GUIDE = _item(
    SPK,
    "Read the keynote guide",
    ACCEPTED,
    14,
    AutoRule.HANDBOOK_READ,
    requires_handbook="keynote",
    ready_rule=ReadyRule.GUIDE_PUBLISHED,
    waiting_note="we are still writing it",
    description_md="What we need from a keynote: timing, format and the deadlines. Ticks itself when you reach the end of the guide.",
    once_per_presenter=True,
)
REGISTER = _item(
    SPK,
    "Register for the conference",
    CONF,
    14,
    AutoRule.PRETIX_REGISTERED,
    ready_rule=ReadyRule.REGISTRATION_OPEN,
    waiting_note="registration is not open yet",
    description_md="Get your (free) ticket so you can join the conference platform. Ticks itself once your registration matches your email.",
)
DISCORD = _item(
    SPK,
    "Join the PyLadiesCon Discord",
    ACCEPTED,
    14,
    description_md="Where the team, the other speakers and the attendees are during the conference; the link is in the speaker guide.",
)
CONFIRM_SLOT = _item(
    SPK,
    "Confirm your scheduled slot",
    SESSION,
    14,
    # There is nothing to confirm until the session has a slot.
    ready_rule=ReadyRule.SESSION_SCHEDULED,
    waiting_note="your slot is not scheduled yet",
    description_md="Once your slot is set you will see it on your schedule page; tick this to confirm the time works for you, or tell your liaison if it does not.",
)
MATERIALS = _item(
    SPK,
    "Share a link to your workshop materials",
    SESSION,
    7,
    description_md="A repository, notebook or setup guide attendees should have before the workshop starts.",
)
SLIDES = _item(
    SPK,
    "Share a link to your slides",
    SESSION,
    3,
    description_md="A link to your slides so we can post them with the recording; a PDF or a public deck both work.",
)
TECH_CHECK = _item(
    SPK,
    "Do a tech check",
    # Once per speaker, a week before the conference: it is about them and
    # their setup, not about one session.
    CONF,
    7,
    # Nothing in the database knows whether the team has the equipment and
    # has opened booking, so this one waits on a gate.
    ready_gate_code="tech-check-open",
    description_md="A short call with the team to test your camera, microphone and screen sharing before the day.",
)

ORGANIZER_ITEMS_ALL = [
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

# Once per presenter for the whole edition (the general template).
GENERAL_TITLES = {
    "Presenter in portal",
    "Onboarding email sent",
    "Registration info sent",
    "Discord channel and speaker role assigned",
}
# The speaker guide is not here: a workshop or keynote presenter reads the
# guide for their kind instead, and two "read the guide" lines due the same
# day read as a bug rather than as two guides. Kinds without one of their
# own carry the general guide themselves, once per presenter.
GENERAL_SPEAKER = [BIO, REGISTER, DISCORD, TECH_CHECK]
GENERAL_ORGANIZER = [i for i in ORGANIZER_ITEMS_ALL if i["title"] in GENERAL_TITLES]
# Per presenter per session.
ORGANIZER_ITEMS = [i for i in ORGANIZER_ITEMS_ALL if i["title"] not in GENERAL_TITLES]

GUIDE_ONCE = dict(GUIDE, once_per_presenter=True)
WORKSHOP_SPEAKER = [CONFIRM_TITLE, WORKSHOP_GUIDE, CONFIRM_SLOT, MATERIALS]
TALK_SPEAKER = [CONFIRM_TITLE, GUIDE_ONCE, CONFIRM_SLOT, SLIDES]
KEYNOTE_SPEAKER = [CONFIRM_TITLE, KEYNOTE_GUIDE, CONFIRM_SLOT, SLIDES]
PANEL_LIGHT = [GUIDE_ONCE, CONFIRM_SLOT]
PERFORMER = [
    _item(
        SPK,
        "Check your title and description",
        ACCEPTED,
        7,
        description_md="Check that the title and description of your performance read the way you want them on the schedule.",
    ),
    _item(
        SPK,
        "Read the performer guide",
        ACCEPTED,
        14,
        AutoRule.HANDBOOK_READ,
        description_md="How PyJam works, the video format we need and the deadlines. Ticks itself when you reach the end.",
        requires_handbook="performer",
        once_per_presenter=True,
    ),
    _item(
        SPK,
        "Upload your performance video",
        CONF,
        28,
        AutoRule.ASSET_EXISTS,
        description_md="Upload the recording from your dashboard; the page shows its length against the limit. Ticks itself once a video is in.",
        requires_asset_kind=MediaKind.RAW_VIDEO,
    ),
    _item(
        SPK,
        "Approve the final cut",
        CONF,
        7,
        description_md="We will send you the edited video; watch it and tick this when you are happy for it to go out.",
    ),
]
HOST = [
    _item(
        SPK,
        "Confirm you can host this slot",
        ACCEPTED,
        7,
        description_md="Tick this once you have checked the time and can be there to host.",
    ),
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
        ChecklistScope.GENERAL,
        "Every presenter",
        "",
        "",
        "",
        GENERAL_SPEAKER + GENERAL_ORGANIZER,
    ),
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
        KEYNOTE_SPEAKER + ORGANIZER_ITEMS,
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
    described: int = 0  # existing lines whose empty description was filled in


def seed_checklists(conference):
    """Load the default templates into ``conference``. Safe to run again:
    existing templates keep their edits and only missing items are added.

    An edition with no session types yet gets the default types and roles
    first. An edition that has types keeps exactly the ones it has: a
    default template whose type or role the edition lacks (a retired
    keynote, say) is skipped and named in ``skipped``, never conjured up.
    Add the type on the "Types and roles" page and load again if wanted.

    All or nothing: the failure that prompted this (production, 2026-09-22)
    left an edition with some templates seeded and others missing, which
    re-running repairs but nothing announces."""
    with transaction.atomic():
        return _seed_checklists(conference)


def seed_readiness_gates(conference):
    """Create the default gates for an edition, shut. Existing gates keep
    whatever organizers changed, including whether they are open."""
    created = 0
    for code, name, waiting_note, description in DEFAULT_GATES:
        _, made = ReadinessGate.objects.get_or_create(
            conference=conference,
            code=code,
            defaults={
                "name": name,
                "waiting_note": waiting_note,
                "description": description,
            },
        )
        created += made
    return created


def _seed_checklists(conference):
    if not SessionType.objects.filter(conference=conference).exists():
        seed_program_types(conference)
    # Before the lines, so a line naming a gate finds it.
    seed_readiness_gates(conference)
    kinds = {t.code: t for t in SessionType.objects.filter(conference=conference)}
    roles = {r.code: r for r in PresenterRole.objects.filter(conference=conference)}
    templates_created = items_created = described = 0
    skipped = []
    for scope, name, kind, role, delivery, items in DEFAULT_TEMPLATES:
        # The every-presenter template names no kind, role or delivery: its
        # lines are about the person, not about a session.
        if kind and kind not in kinds:
            skipped.append((name, f"no {kind} session type in this edition"))
            continue
        if role and role not in roles:
            skipped.append((name, f"no {role} presenter role in this edition"))
            continue
        template, created = ChecklistTemplate.objects.get_or_create(
            conference=conference,
            scope=scope,
            kind=kinds[kind] if kind else None,
            role=roles[role] if role else None,
            delivery=delivery,
            defaults={"name": name},
        )
        templates_created += created
        existing = {line.title: line for line in template.items.all()}
        next_order = len(existing)
        for spec in items:
            if spec["title"] in existing:
                # An edition seeded before the defaults carried descriptions:
                # fill an empty one in, never overwrite an organizer's text.
                line = existing[spec["title"]]
                if line and not line.description_md and spec.get("description_md"):
                    line.description_md = spec["description_md"]
                    line.save(update_fields=["description_md", "modified_date"])
                    described += 1
                continue
            ChecklistTemplateItem.objects.create(
                template=template, order=next_order, **spec
            )
            existing[spec["title"]] = None
            next_order += 1
            items_created += 1
    # An edition seeded before a line moved to the general template still
    # carries it per session; fold those copies into the general item.
    collapse_general_duplicates(conference)
    return SeedResult(templates_created, items_created, skipped, described)


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
    "requires_handbook",
    "per_translation_language",
    "is_required",
    "assignee_default",
    "default_team_name",
    "once_per_presenter",
    # The wait sources travel by value: the rule is a name, and the gate is
    # a code matched against next year's own gates. ``waits_for`` points at
    # a line of the source edition, so it is remapped after the copy.
    "ready_rule",
    "ready_gate_code",
    "waiting_note",
]


def clone_checklists(target, source):
    """Copy ``source``'s templates and items into ``target``.

    Templates whose key already exists in ``target`` are skipped, so it is
    safe to run more than once. Returns ``(templates_created, items_created)``.
    """
    templates_created = items_created = 0
    # Types and roles come along first, matched by code, then the gates the
    # lines name, shut, so next year starts where this year started.
    clone_program_types(target, source)
    clone_readiness_gates(target, source)
    copied_lines = {}
    for template in source.checklist_templates.select_related(
        "kind", "role"
    ).prefetch_related("items"):
        copy, created = ChecklistTemplate.objects.get_or_create(
            conference=target,
            scope=template.scope,
            kind=(
                session_type(target, template.kind.code) if template.kind_id else None
            ),
            role=presenter_role(target, template.role.code) if template.role else None,
            delivery=template.delivery,
            defaults={"name": template.name, "is_active": template.is_active},
        )
        if not created:
            continue
        templates_created += 1
        for item in template.items.all():
            copied_lines[item.pk] = ChecklistTemplateItem.objects.create(
                template=copy, **{field: getattr(item, field) for field in ITEM_FIELDS}
            )
            items_created += 1
    # Now that every line exists, point each copy at the copy of the line it
    # waits for. A line whose target was not copied (its template already
    # existed in the new edition) waits on nothing rather than on last
    # year's row.
    for source_pk, copy in copied_lines.items():
        waits_for_id = ChecklistTemplateItem.objects.values_list(
            "waits_for_id", flat=True
        ).get(pk=source_pk)
        target_line = copied_lines.get(waits_for_id)
        if target_line is not None:
            copy.waits_for = target_line
            copy.save(update_fields=["waits_for", "modified_date"])
    return templates_created, items_created


def clone_readiness_gates(target, source):
    """Copy the gates by code, shut. Whether last year's gate was open says
    nothing about this year's work."""
    created = 0
    for gate in ReadinessGate.objects.filter(conference=source):
        _, made = ReadinessGate.objects.get_or_create(
            conference=target,
            code=gate.code,
            defaults={
                "name": gate.name,
                "waiting_note": gate.waiting_note,
                "description": gate.description,
            },
        )
        created += made
    return created


# The pretix event, token and secret are deliberately absent: they are
# per edition, and copying an encrypted value this deploy cannot read
# (see speakers/encryption.py) would raise on save.
SETTINGS_TO_COPY = [
    "default_premiere_location",
    "translation_languages",
    "default_video_length_limit_minutes",
    "conference_timezone",
    "organizers_email",
    "pretix_base_url",
    "pretix_organizer",
]


def clone_speaker_setup(target, source, enable=False):
    """Carry the speaker-portal setup into a new edition (Start next year).

    Copies checklist templates, the latest published version of every guide
    (as an unpublished draft), and the per-edition settings except the
    pretix event, token and secret, which are per edition. ``enable``
    switches the module on. Returns a dict of counts.
    """
    templates, items = clone_checklists(target, source)
    guides = 0
    for key, _ in Handbook.keys(source):
        current = Handbook.current(source, key)
        if (
            current is None
            or Handbook.objects.filter(conference=target, key=key).exists()
        ):
            continue
        Handbook.objects.create(
            conference=target,
            key=key,
            version=1,
            title=current.title,
            url=current.url,
            body_md=current.body_md,
        )
        guides += 1
    settings_row, _ = SpeakerSettings.objects.get_or_create(conference=target)
    source_settings = SpeakerSettings.objects.filter(conference=source).first()
    if source_settings is not None:
        for field in SETTINGS_TO_COPY:
            setattr(settings_row, field, getattr(source_settings, field))
    settings_row.speaker_module_enabled = enable
    settings_row.save()
    return {"templates": templates, "items": items, "guides": guides}
