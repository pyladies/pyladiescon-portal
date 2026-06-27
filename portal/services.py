"""Conference lifecycle operations that span apps.

These touch the ``sponsorship`` and ``volunteer`` apps, which import from
``portal.models``. Putting this logic on the ``Conference`` model would force
module-level imports of those apps back into ``portal.models`` — a circular
import. This module is not imported by any models module, so it can import
everything it needs at the top.
"""

from portal.common import (
    get_attendee_count_cache,
    get_donors_count_cache,
    get_sponsorship_committed_amount_stats_cache,
    get_sponsorship_committed_count_stats_cache,
    get_total_donations_amount_cache,
)
from sponsorship.models import SponsorshipTier
from volunteer.constants import ApplicationStatus
from volunteer.models import Team


def clone_teams(target, source):
    """Copy ``source``'s team structure into ``target``.

    Copies each team's name, description, and open-to-new-members flag but not
    its team leads (those are per-edition volunteers). Teams whose name already
    exists in ``target`` are skipped, so it is safe to run more than once.
    Returns the number of teams created.
    """
    existing = set(target.teams.values_list("short_name", flat=True))
    created = 0
    for team in source.teams.all():
        if team.short_name in existing:
            continue
        Team.objects.create(
            conference=target,
            short_name=team.short_name,
            description=team.description,
            open_to_new_members=team.open_to_new_members,
        )
        created += 1
    return created


def clone_sponsorship_tiers(target, source):
    """Copy ``source``'s sponsorship tiers (name, amount, description) into
    ``target``, skipping tiers whose name already exists. Returns the count
    created.
    """
    existing = set(target.sponsorship_tiers.values_list("name", flat=True))
    created = 0
    for tier in source.sponsorship_tiers.all():
        if tier.name in existing:
            continue
        SponsorshipTier.objects.create(
            conference=target,
            name=tier.name,
            amount=tier.amount,
            description=tier.description,
        )
        created += 1
    return created


def bring_forward_volunteers(target, source):
    """Bring every APPROVED volunteer from ``source`` into ``target``.

    Each becomes a PENDING profile (see ``VolunteerProfile.bring_forward_to``);
    volunteers who already have a profile in ``target`` are skipped. Returns the
    number of profiles created.
    """
    created = 0
    approved = source.volunteer_profiles.filter(
        application_status=ApplicationStatus.APPROVED
    )
    for profile in approved:
        if profile.bring_forward_to(target) is not None:
            created += 1
    return created


def freeze_stats(conference):
    """Snapshot ``conference``'s live metrics into ``historical_snapshot``.

    Once frozen, the comparison and historical-fallback views read these fixed
    numbers instead of recomputing them, so a closed edition's stats stay final.
    Amounts are stored as floats so the dict is JSON-safe. Returns the snapshot.
    """
    conference.historical_snapshot = {
        "registrations": get_attendee_count_cache(conference),
        "sponsors": get_sponsorship_committed_count_stats_cache(conference),
        "sponsorship_amount": float(
            get_sponsorship_committed_amount_stats_cache(conference)
        ),
        "donors": get_donors_count_cache(conference),
        "donation_amount": float(get_total_donations_amount_cache(conference)),
    }
    conference.save()
    return conference.historical_snapshot
