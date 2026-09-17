from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.utils import timezone

from portal.models import Conference
from portal_account.models import PortalProfile
from speakers.constants import ItemStatus, SessionStatus
from speakers.models import (
    ChecklistItem,
    ChecklistTemplateItem,
    Handbook,
    Invitation,
    Presenter,
    Session,
)
from speakers.program_types import presenter_role, session_type
from speakers.seeds import seed_checklists


@pytest.mark.django_db
class TestGenerateSpeakerSampleData:
    def test_refuses_without_debug(self, conference, settings):
        settings.DEBUG = False
        with pytest.raises(CommandError, match="DEBUG"):
            call_command("generate_speaker_sample_data")

    def test_builds_every_persona_and_is_idempotent(self, conference, settings):
        settings.DEBUG = True
        out = StringIO()
        call_command("generate_speaker_sample_data", stdout=out)
        assert "Speaker sample data ready" in out.getvalue()
        assert User.objects.filter(username="vol_maya").exists()
        assert Session.objects.filter(conference=conference).count() == 7
        presenters = {
            p.display_name: p for p in Presenter.objects.filter(conference=conference)
        }
        assert (
            presenters["Ada Lovelace"].user is not None
            and presenters["Ada Lovelace"].bio_md
        )
        assert PortalProfile.objects.filter(
            user=presenters["Ada Lovelace"].user
        ).exists()
        assert not PortalProfile.objects.filter(
            user=presenters["Nina Host"].user
        ).exists()
        assert presenters["Sam Newcomer"].invitations.count() == 0
        dex = presenters["Dex Panelist"]
        assert dex.invitations.get().accepted_at is None and dex.user is None
        assert (
            Session.objects.get(title="Testing Django applications").status
            == SessionStatus.SCHEDULED
        )
        assert (
            Session.objects.get(title="Live-coded music with Python").status
            == SessionStatus.CONFIRMED
        )
        blocked = ChecklistItem.objects.filter(
            conference=conference, status=ItemStatus.BLOCKED
        )
        assert blocked.exists() and "over the 10-minute limit" in blocked.first().note
        ada_items = ChecklistItem.objects.filter(presenter=presenters["Ada Lovelace"])
        assert ada_items.filter(status=ItemStatus.SKIPPED).exists()
        assert ada_items.filter(team__short_name="Design Team").exists()
        assert ada_items.filter(
            status=ItemStatus.DONE, completed_by__username="vol_kim"
        ).exists()
        assert ada_items.filter(
            title="Register for the conference", due_date__lt=timezone.now().date()
        ).exists()
        grace = presenters["Grace Hopper"]
        assert grace.checklist_items.filter(title="Read the keynote guide").count() == 1
        assert (
            grace.checklist_items.filter(title="Read the workshop guide").count() == 1
        )
        assert Handbook.current(conference, "workshop") is not None
        assert Handbook.current(conference, "performer") is None
        counts = (
            Session.objects.count(),
            Presenter.objects.count(),
            Invitation.objects.count(),
            ChecklistItem.objects.count(),
            User.objects.count(),
        )
        call_command("generate_speaker_sample_data", stdout=StringIO())
        assert counts == (
            Session.objects.count(),
            Presenter.objects.count(),
            Invitation.objects.count(),
            ChecklistItem.objects.count(),
            User.objects.count(),
        )

    def test_ticks_required_lines_so_sessions_still_confirm(self, conference, settings):
        """An edition whose templates mark a manual line required would keep
        every sample session in Draft; the command completes those lines."""
        settings.DEBUG = True
        seed_checklists(conference)
        line = ChecklistTemplateItem.objects.get(
            template__conference=conference,
            template__kind=session_type(conference, "WORKSHOP"),
            template__role=presenter_role(conference, "PRESENTER"),
            title="Check your session title and summary",
        )
        line.is_required = True
        line.save()
        call_command("generate_speaker_sample_data", stdout=StringIO())
        session = Session.objects.get(title="Testing Django applications")
        assert session.status == SessionStatus.SCHEDULED
        assert (
            ChecklistItem.objects.get(
                session=session, presenter__email="ada@example.com", title=line.title
            ).status
            == ItemStatus.DONE
        )

    def test_conference_argument(self, conference, settings):
        settings.DEBUG = True
        other = Conference.objects.create(year=2024, name="Old", slug="old")
        call_command(
            "generate_speaker_sample_data", conference="2024", stdout=StringIO()
        )
        assert Session.objects.filter(conference=other).count() == 7
        with pytest.raises(CommandError, match="No conference matches"):
            call_command("generate_speaker_sample_data", conference="nope")
        conference.is_active = False
        conference.save()
        with pytest.raises(CommandError, match="No active conference"):
            call_command("generate_speaker_sample_data")
