"""A release that migrates before it rolls out must not break the old one.

The release step runs ``migrate`` and only then serves the new code, so for
a few seconds requests are handled by a process that does not know the
columns the migration just added. Django drops the default it used to
backfill an ``AddField``, which turns that window into 500s (seen on
2026-09-22: "null value in column default_team_name").

Every column added since the speaker module went live therefore carries a
``db_default``. These tests read the schema, so they hold however the test
database was built.
"""

import pytest
from django.db import connection

from speakers.models import ChecklistTemplate, ChecklistTemplateItem
from speakers.program_types import presenter_role, session_type

from .factories import make_settings

#: Columns added by migrations 0005 to 0007, with the value an older
#: process leaves the database to fill in.
BACKFILLED = [
    ("speakers_checklisttemplateitem", "requires_handbook", ""),
    ("speakers_checklisttemplateitem", "default_team_name", ""),
    ("speakers_checklistitem", "requires_handbook", ""),
    ("speakers_checklistitem", "pending_notice", ""),
    ("speakers_handbook", "key", "speaker"),
    ("speakers_presenter", "password_reminder_dismissed", False),
]


@pytest.mark.django_db
class TestColumnsAddedSince0005:
    @pytest.mark.parametrize("table, column, _expected", BACKFILLED)
    def test_the_database_can_fill_it_in(self, table, column, _expected):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select is_nullable, column_default
                from information_schema.columns
                where table_name = %s and column_name = %s
                """,
                [table, column],
            )
            row = cursor.fetchone()
        assert row is not None, f"{table}.{column} is gone"
        nullable, default = row
        assert nullable == "YES" or default is not None, (
            f"{table}.{column} is NOT NULL with no database default: a process "
            "from the previous release cannot insert a row during a deploy"
        )

    def test_an_insert_without_the_new_columns_still_works(self, conference):
        """Exactly what the previous release's code does: name the columns it
        knew about and leave the rest to the database."""
        make_settings(conference)
        template = ChecklistTemplate.objects.create(
            conference=conference,
            scope="PRESENTER",
            name="Old release",
            kind=session_type(conference, "TALK"),
            role=presenter_role(conference, "PRESENTER"),
        )
        with connection.cursor() as cursor:
            cursor.execute(
                """
                insert into speakers_checklisttemplateitem
                    (creation_date, modified_date, template_id, "order", owner,
                     title, description_md, due_anchor, due_offset_days,
                     auto_complete_rule, requires_asset_kind,
                     requires_asset_language, per_translation_language,
                     is_required, assignee_default)
                values (now(), now(), %s, 0, 'SPEAKER', 'Update your bio', '',
                        'INVITATION_ACCEPTED', 7, 'bio_and_headshot', '', '',
                        false, false, 'UNASSIGNED')
                """,
                [template.pk],
            )
        line = ChecklistTemplateItem.objects.get(title="Update your bio")
        assert line.default_team_name == "" and line.requires_handbook == ""

    def test_an_unsaved_row_still_reads_the_python_default(self, conference):
        """``db_default`` alone leaves a sentinel on the attribute until the
        row is saved, and ``clean()`` runs before that. Each field keeps its
        Python ``default`` so the two agree."""
        line = ChecklistTemplateItem(
            template=ChecklistTemplate(conference=conference),
            owner="ORGANIZER",
            title="Cut the trailer",
        )
        assert line.default_team_name == ""
        assert line.requires_handbook == ""
