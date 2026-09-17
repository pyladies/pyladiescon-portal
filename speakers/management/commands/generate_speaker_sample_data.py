"""Sample data for the speaker portal in local development.

Builds, on the active edition, every persona and state the speaker module
has: organizer and volunteer accounts (some on teams), sessions of each
kind, presenters who are not yet invited, invited, accepted and onboarded,
a performer with a video over the limit, checklists with done, overdue and
upcoming items, team-owned and volunteer-assigned action items, guides and
schedule slots. Idempotent: rerunning updates rather than duplicates.

Refuses to run unless DEBUG is on. All accounts use the password
``password123``.
"""

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from portal.models import Conference
from portal_account.models import PortalProfile
from speakers.checklists import (
    add_adhoc_item,
    assign_item,
    complete_item,
    instantiate_session_checklist,
    skip_item,
)
from speakers.constants import (
    OPEN_ITEM_STATUSES,
    Delivery,
    ItemOwner,
    MediaKind,
    MediaStatus,
    SessionStatus,
)
from speakers.lifecycle import confirm_session_if_ready
from speakers.models import (
    ChecklistItem,
    DiscordChannel,
    Handbook,
    MediaAsset,
    Presenter,
    ScheduleSlot,
    Session,
    SessionPresenter,
    SpeakerSettings,
)
from speakers.program_types import presenter_role, session_type
from speakers.rules import reevaluate_all
from speakers.seeds import seed_checklists
from speakers.services import accept_invitation, send_invitation
from volunteer.constants import ApplicationStatus
from volunteer.models import Team, VolunteerProfile

PASSWORD = "password123"

PEOPLE = [
    # username, first, last, email, staff, superuser, volunteer status, teams
    ("organizer_lena", "Lena", "Organizer", "lena@example.com", True, False, None, []),
    (
        "vol_maya",
        "Maya",
        "Designer",
        "maya@example.com",
        False,
        False,
        ApplicationStatus.APPROVED,
        ["Design Team"],
    ),
    (
        "vol_kim",
        "Kim",
        "Editor",
        "kim@example.com",
        False,
        False,
        ApplicationStatus.APPROVED,
        ["Media Team"],
    ),
    (
        "vol_pending",
        "Pat",
        "Pending",
        "pat@example.com",
        False,
        False,
        ApplicationStatus.PENDING,
        [],
    ),
]

# Session types and presenter roles are rows per edition, so the tables
# below name them by code and the command looks each one up.
SESSIONS = [
    # title, type code, delivery, summary
    (
        "Testing Django applications",
        "WORKSHOP",
        Delivery.LIVE,
        "Hands-on pytest and Django.",
    ),
    (
        "The future of PyLadies",
        "KEYNOTE",
        Delivery.LIVE,
        "Where the community goes next.",
    ),
    (
        "Careers in open source",
        "PANEL",
        Delivery.LIVE,
        "Four paths into open source work.",
    ),
    (
        "Live-coded music with Python",
        "PYJAM",
        Delivery.PRE_RECORDED,
        "A performance.",
    ),
    (
        "Type hints in practice",
        "TALK",
        Delivery.LIVE,
        "Typing a real codebase.",
    ),
    ("Opening", "OPENING", Delivery.LIVE, ""),
    ("Coffee break", "BREAK", Delivery.LIVE, ""),
]

PRESENTERS = [
    # display name, email, timezone, sessions [(title, role)], state, liaison
    (
        "Ada Lovelace",
        "ada@example.com",
        "Europe/London",
        [("Testing Django applications", "PRESENTER")],
        "onboarded",
        "organizer_lena",
    ),
    (
        "Grace Hopper",
        "grace@example.com",
        "America/New_York",
        [
            ("The future of PyLadies", "PRESENTER"),
            ("Testing Django applications", "PRESENTER"),
            ("Careers in open source", "MODERATOR"),
        ],
        "accepted",
        "organizer_lena",
    ),
    (
        "Dex Panelist",
        "dex@example.com",
        "Africa/Lagos",
        [("Careers in open source", "PANELIST")],
        "invited",
        None,
    ),
    (
        "Maria Performer",
        "maria@example.com",
        "America/Sao_Paulo",
        [("Live-coded music with Python", "PERFORMER")],
        "accepted",
        "vol_kim",
    ),
    (
        "Sam Newcomer",
        "sam@example.com",
        "Asia/Tokyo",
        [("Type hints in practice", "PRESENTER")],
        "not_invited",
        None,
    ),
    (
        "Nina Host",
        "nina@example.com",
        "UTC",
        [("Opening", "HOST")],
        "accepted",
        None,
    ),
]


class Command(BaseCommand):
    help = "Generate speaker-portal sample data on the active edition (DEBUG only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--conference", help="Year or slug; defaults to the active one."
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("This command only runs with DEBUG on.")
        self.conference = self._conference(options.get("conference"))
        self.today = timezone.now().date()
        self._settings_and_seeds()
        self.users = self._people()
        self.sessions = self._sessions()
        self.presenters = self._presenters()
        self._schedule()
        self._checklist_states()
        self._performer_video()
        reevaluate_all(self.conference)
        self.stdout.write(
            self.style.SUCCESS(
                f"Speaker sample data ready on {self.conference}: "
                f"{len(self.users)} people, {len(self.sessions)} sessions, "
                f"{len(self.presenters)} presenters, "
                f"{ChecklistItem.objects.filter(conference=self.conference).count()} "
                "checklist items. Password for every account: password123."
            )
        )

    # -- pieces --------------------------------------------------------------

    def _conference(self, value):
        if value:
            conference = Conference.objects.filter(slug=value).first()
            if conference is None and value.isdigit():
                conference = Conference.objects.filter(year=int(value)).first()
            if conference is None:
                raise CommandError(f"No conference matches {value!r}.")
        else:
            conference = Conference.get_active()
            if conference is None:
                raise CommandError("No active conference; pass --conference.")
        first_weekend = datetime(conference.year, 12, 5).date()
        if not conference.start_date:
            conference.start_date = first_weekend
            conference.end_date = first_weekend + timedelta(days=1)
            conference.save(update_fields=["start_date", "end_date"])
        return conference

    def _settings_and_seeds(self):
        row, _ = SpeakerSettings.objects.get_or_create(conference=self.conference)
        row.speaker_module_enabled = True
        row.conference_timezone = "UTC"
        row.organizers_email = "organizers@example.com"
        row.translation_languages = ["pt-br"]
        row.default_video_length_limit_minutes = 10
        row.save()
        seed_checklists(self.conference)
        for key, title, url in (
            ("speaker", "Speaker guide", "https://conference.pyladies.com/docs/"),
            (
                "workshop",
                "Workshop guide",
                "https://conference.pyladies.com/docs/workshops/",
            ),
            (
                "keynote",
                "Keynote guide",
                "https://conference.pyladies.com/docs/keynotes/",
            ),
        ):
            if Handbook.current(self.conference, key) is None:
                Handbook.objects.create(
                    conference=self.conference,
                    key=key,
                    title=title,
                    url=url,
                    version=Handbook.next_version(self.conference, key),
                ).publish()
        if not Handbook.objects.filter(
            conference=self.conference, key="performer"
        ).exists():
            Handbook.objects.create(
                conference=self.conference,
                key="performer",
                title="Performer guide",
                url="https://conference.pyladies.com/docs/pyjam/",
            )  # left as a draft on purpose
        DiscordChannel.objects.get_or_create(
            conference=self.conference,
            name="main-stage",
            defaults={"url": "https://discord.com/channels/1/2"},
        )
        DiscordChannel.objects.get_or_create(
            conference=self.conference, name="workshop-room"
        )

    def _people(self):
        users = {}
        for username, first, last, email, staff, superuser, status, teams in PEOPLE:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"email": email, "first_name": first, "last_name": last},
            )
            user.is_staff, user.is_superuser = staff, superuser
            if created:
                user.set_password(PASSWORD)
            user.save()
            PortalProfile.objects.get_or_create(
                user=user, defaults={"coc_agreement": True, "tos_agreement": True}
            )
            if status is not None:
                profile, _ = VolunteerProfile.objects.get_or_create(
                    user=user,
                    conference=self.conference,
                    defaults={
                        "application_status": status,
                        "discord_username": username,
                    },
                )
                for name in teams:
                    team, _ = Team.objects.get_or_create(
                        conference=self.conference,
                        short_name=name,
                        defaults={"description": f"{name} (sample)"},
                    )
                    profile.teams.add(team)
            users[username] = user
        return users

    def _sessions(self):
        sessions = {}
        for title, code, delivery, summary in SESSIONS:
            session, _ = Session.objects.get_or_create(
                conference=self.conference,
                title=title,
                defaults={
                    "kind": session_type(self.conference, code),
                    "delivery": delivery,
                    "summary_md": summary,
                    "language": "en",
                },
            )
            # The two nobody has to present are ready as soon as they exist.
            if (
                session.kind.code in ("OPENING", "BREAK")
                and session.status == SessionStatus.DRAFT
            ):
                session.confirm()
            sessions[title] = session
        return sessions

    def _presenters(self):
        presenters = {}
        for name, email, tz, links, state, liaison in PRESENTERS:
            presenter, _ = Presenter.objects.get_or_create(
                conference=self.conference,
                email=email,
                defaults={
                    "display_name": name,
                    "timezone": tz,
                    "liaison": self.users.get(liaison),
                },
            )
            for title, role_code in links:
                SessionPresenter.objects.get_or_create(
                    session=self.sessions[title],
                    presenter=presenter,
                    defaults={"role": presenter_role(self.conference, role_code)},
                )
            self._bring_to_state(presenter, state)
            presenters[name] = presenter
        return presenters

    def _bring_to_state(self, presenter, state):
        if state == "not_invited":
            return
        invitation = presenter.invitations.first()
        if invitation is None:
            invitation = presenter.invitations.create(
                message_md="We'd love to have you!"
            )
            send_invitation(invitation)
        if state == "invited":
            return
        if invitation.accepted_at is None:
            accept_invitation(invitation)
            presenter.refresh_from_db()
        self._clear_required_items(presenter)
        if state == "onboarded":
            presenter.bio_md = "I write programs and talk about it."
            presenter.headshot = "speakers/headshots/sample.png"
            presenter.pronouns = "she/her"
            presenter.save()

    def _clear_required_items(self, presenter):
        """Tick the presenter's manual required items so the session can
        confirm, whatever the edition's templates mark as required."""
        blocking = presenter.checklist_items.filter(
            is_required=True, status__in=OPEN_ITEM_STATUSES, auto_complete_rule=""
        )
        for item in blocking:
            complete_item(item, actor=presenter.user)
        for session in Session.objects.filter(session_presenters__presenter=presenter):
            confirm_session_if_ready(session)

    def _schedule(self):
        stage = DiscordChannel.objects.get(
            conference=self.conference, name="main-stage"
        )
        start = datetime(self.conference.year, 12, 5, 14, 0, tzinfo=dt_timezone.utc)
        for title, offset in (
            ("Opening", 0),
            ("The future of PyLadies", 1),
            ("Testing Django applications", 2),
        ):
            session = self.sessions[title]
            session.refresh_from_db()
            ScheduleSlot.objects.get_or_create(
                session=session,
                defaults={
                    "channel": None if title == "Opening" else stage,
                    "start_utc": start + timedelta(hours=offset),
                },
            )
            if session.status == SessionStatus.CONFIRMED:
                session.schedule()

    def _checklist_states(self):
        ada = self.presenters["Ada Lovelace"]
        maya, kim = self.users["vol_maya"], self.users["vol_kim"]
        design = Team.objects.get(conference=self.conference, short_name="Design Team")
        # Deadlines in every state on Ada's list.
        for title, days in (
            ("Register for the conference", -3),
            ("Confirm your scheduled slot", 2),
        ):
            ChecklistItem.objects.filter(presenter=ada, title=title).update(
                due_date=self.today + timedelta(days=days)
            )
        guide = ChecklistItem.objects.filter(
            presenter=ada, title="Do a tech check"
        ).first()
        if guide and guide.is_open:
            skip_item(
                guide, actor=self.users["organizer_lena"], note="Done it last year"
            )
        for item in ChecklistItem.objects.filter(
            presenter=ada, owner=ItemOwner.ORGANIZER, title="Promo materials prepared"
        ):
            assign_item(item, team=design, actor=self.users["organizer_lena"])
            item.due_date = self.today + timedelta(days=5)
            item.save(update_fields=["due_date"])
        for item in ChecklistItem.objects.filter(
            presenter=ada, owner=ItemOwner.ORGANIZER, title="Onboarding email sent"
        ):
            assign_item(item, assignee=kim, actor=self.users["organizer_lena"])
            if item.is_open:
                complete_item(item, actor=kim)
        if not ChecklistItem.objects.filter(
            presenter=ada, title="Send us a fun fact"
        ).exists():
            add_adhoc_item(
                self.conference,
                "Send us a fun fact",
                ItemOwner.SPEAKER,
                presenter=ada,
                due_date=self.today + timedelta(days=1),
                actor=self.users["organizer_lena"],
            )
        grace = self.presenters["Grace Hopper"]
        if not ChecklistItem.objects.filter(
            presenter=grace, title="Record a 30-second promo clip"
        ).exists():
            add_adhoc_item(
                self.conference,
                "Record a 30-second promo clip",
                ItemOwner.ORGANIZER,
                presenter=grace,
                session=self.sessions["The future of PyLadies"],
                due_date=self.today - timedelta(days=1),
                assignee=maya,
                actor=self.users["organizer_lena"],
            )

    def _performer_video(self):
        jam = self.sessions["Live-coded music with Python"]
        jam.refresh_from_db()
        if jam.status == SessionStatus.CONFIRMED:
            instantiate_session_checklist(jam)
        if not MediaAsset.objects.filter(
            session=jam, kind=MediaKind.RAW_VIDEO
        ).exists():
            MediaAsset.objects.create(
                session=jam,
                kind=MediaKind.RAW_VIDEO,
                status=MediaStatus.READY,
                duration_seconds=12 * 60 + 30,
                uploaded_by=self.presenters["Maria Performer"].user,
            )
