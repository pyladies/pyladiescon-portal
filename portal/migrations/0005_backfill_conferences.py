# Phase 3 of the multi-year-conferences work: seed the Conference rows for
# 2023-2026 and point every existing year-bound record at the 2025 edition.
#
# Historical values are copied literally rather than imported from
# portal.constants. A data migration is a historical record and must stay
# replayable on a fresh database; later phases delete HISTORICAL_STATS and
# PROPOSALS_2025_COUNT from portal.constants, which would break this file if
# it imported them. See docs/architecture/multi-year-conferences.md.

from django.db import migrations

# Snapshots of closed-out years (registrations, sponsors, donors, amounts).
# proposals is stored separately on the proposals_count field, mirroring how
# the live years track it. Source:
# https://conference.pyladies.com/2024-pyladiescon-ends/
HISTORICAL = {
    2023: {
        "name": "PyLadiesCon 2023",
        "proposals_count": 164,
        "snapshot": {
            "registrations": 600,
            "sponsors": 8,
            "sponsorship_amount": 10500,
            "donors": 58,
            "donation_amount": 650,
        },
    },
    2024: {
        "name": "PyLadiesCon 2024",
        "proposals_count": 192,
        "snapshot": {
            "registrations": 732,
            "sponsors": 11,
            "sponsorship_amount": 10000,
            "donors": 105,
            "donation_amount": 1520,
        },
    },
}

# The active edition the portal was originally built for. Goal amounts mirror
# SPONSORSHIP_GOAL_AMOUNT / DONATION_GOAL_AMOUNT and PROPOSALS_2025_COUNT.
PRETIX_EVENT_SLUG_2025 = "2025"


def backfill(apps, schema_editor):
    Conference = apps.get_model("portal", "Conference")

    for year, data in HISTORICAL.items():
        Conference.objects.create(
            year=year,
            name=data["name"],
            slug=str(year),
            proposals_count=data["proposals_count"],
            historical_snapshot=data["snapshot"],
        )

    conf_2025 = Conference.objects.create(
        year=2025,
        name="PyLadiesCon 2025",
        slug="2025",
        is_active=True,
        proposals_count=194,
        sponsorship_goal=15000,
        donation_goal=2500,
        pretix_event_slug=PRETIX_EVENT_SLUG_2025,
    )
    Conference.objects.create(year=2026, name="PyLadiesCon 2026", slug="2026")

    # Everything that exists today belongs to the 2025 edition.
    for app_label, model_name in (
        ("volunteer", "VolunteerProfile"),
        ("volunteer", "Team"),
        ("sponsorship", "SponsorshipProfile"),
        ("sponsorship", "SponsorshipTier"),
        ("sponsorship", "IndividualDonation"),
    ):
        apps.get_model(app_label, model_name).objects.update(conference=conf_2025)

    # Pretix orders resolve by event slug rather than a blanket update, so a
    # future year's orders land on the right conference automatically.
    PretixOrder = apps.get_model("attendee", "PretixOrder")
    slug_to_conf = {
        c.pretix_event_slug: c for c in Conference.objects.exclude(pretix_event_slug="")
    }
    for slug, conf in slug_to_conf.items():
        PretixOrder.objects.filter(event_slug=slug).update(conference=conf)


def unbackfill(apps, schema_editor):
    Conference = apps.get_model("portal", "Conference")

    # Detach the FKs first; conference uses on_delete=PROTECT, so the rows
    # cannot be deleted while anything still points at them.
    for app_label, model_name in (
        ("volunteer", "VolunteerProfile"),
        ("volunteer", "Team"),
        ("sponsorship", "SponsorshipProfile"),
        ("sponsorship", "SponsorshipTier"),
        ("sponsorship", "IndividualDonation"),
        ("attendee", "PretixOrder"),
    ):
        apps.get_model(app_label, model_name).objects.update(conference=None)

    Conference.objects.filter(year__in=[2023, 2024, 2025, 2026]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0004_alter_conference_basemodel_ptr"),
        ("volunteer", "0013_team_conference_volunteerprofile_conference"),
        ("sponsorship", "0009_individualdonation_conference_and_more"),
        ("attendee", "0004_pretixorder_conference"),
    ]

    operations = [migrations.RunPython(backfill, unbackfill)]
