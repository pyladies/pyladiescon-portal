from portal.models import Conference

from .constants import ProposalDecision
from .models import Presenter, Proposal, speaker_module_enabled
from .permissions import can_work_queue, is_speaker_liaison, is_speaker_organizer
from .services import proposals_open


def speaker_module(request):
    """Flags the shared rails need to show the speaker portal entries.

    * ``speaker_module_enabled``: the active edition has opted in.
    * ``is_speaker_liaison``: this user looks after at least one presenter, so
      the personal rail offers their sessions even though they are not an
      organizer.
    * ``can_work_speaker_queue``: this user may open "My volunteering
      tasks" (an organizer, a liaison, or anyone carrying an organizer
      item), so the personal rail offers the page the digest links to.
    * ``is_speaker_presenter``: this user is a presenter in the active
      edition, so the navbar offers "Speaking".
    * ``speaker_proposals_open``: the edition is taking proposals, so the
      Organize rail offers the queue and the hubs offer the form.
    * ``pending_proposal_count``: how many are waiting, for the rail badge.
    * ``has_speaker_proposals``: this user has proposals of their own, or
      could send one, so the personal rail offers "My proposals".
    """
    # A handful of queries per authenticated render: the liaison lookup is
    # skipped for organizers, who already see everything, and the queue
    # predicate answers from the permission alone for them. Left uncached on
    # purpose while it is this small; the moment another flag joins them,
    # cache the result on the request rather than adding one more query to
    # every page.
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        # Proposing is open to anyone, so the one flag a signed-out page
        # needs is whether the edition is taking proposals: that is what
        # puts the invitation on the public landing page. Two queries, and
        # nothing else here is computed for a visitor. The same helper
        # answers for members below, so the button and the form agree.
        return {
            "speaker_module_enabled": False,
            "speaker_proposals_open": proposals_open(Conference.get_active()),
            "pending_proposal_count": None,
            "has_speaker_proposals": False,
            "is_speaker_liaison": False,
            "can_work_speaker_queue": False,
            "is_speaker_presenter": False,
        }
    conference = Conference.get_active()
    enabled = speaker_module_enabled(conference)
    taking_proposals = proposals_open(conference)
    return {
        "speaker_proposals_open": taking_proposals,
        # Organizers see the count; nobody else needs it, and it is one
        # query for the people who do.
        "pending_proposal_count": (
            Proposal.objects.filter(
                conference=conference, decision=ProposalDecision.PENDING
            ).count()
            if taking_proposals and is_speaker_organizer(user)
            else None
        ),
        "has_speaker_proposals": taking_proposals
        or (
            enabled
            and Proposal.objects.filter(
                conference=conference, presenter__user=user
            ).exists()
        ),
        "speaker_module_enabled": enabled,
        "is_speaker_liaison": enabled
        and not is_speaker_organizer(user)
        and is_speaker_liaison(user, conference),
        # Organizers included: the page is a person's own work, and it is
        # their rail entry too now that it has left the Organize rail.
        "can_work_speaker_queue": enabled and can_work_queue(user, conference),
        # Being a presenter is not enough for the Speaking tab: a
        # proposal that has not been answered yet makes a presenter row
        # and no program. The rule lives on the queryset, shared with the
        # gate on the pages the tab opens.
        "is_speaker_presenter": enabled
        and Presenter.objects.filter(conference=conference, user=user)
        .onboarded()
        .exists(),
    }
