"""A release that migrates before it rolls out must not break the old one.

The release step runs ``migrate`` and only then serves the new code, so for
a few seconds requests are handled by a process that does not know the
columns the migration just added. Django backfills a column it adds and then
**drops** the default, which turns that window into 500s (production,
2026-09-22: "null value in column default_team_name").

So every column added to a table that already existed must be reachable
without naming it: nullable, or carrying a database default. Nullable counts
on purpose, and a later column that happens to be nullable passes for a
reason of its own; the rule is about what the old code can write, not about
how the new column is declared.

The list is read from the migrations rather than written here, so a column
added tomorrow is audited tomorrow. A column added by the same migration
that creates its table is not in scope: no earlier release ever wrote to
that table.
"""

import ast
from pathlib import Path

import pytest
from django.apps import apps
from django.db import connection

APP = "speakers"
MIGRATIONS = Path(apps.get_app_config(APP).path) / "migrations"


def _operations(tree):
    """Every ``migrations.X(...)`` call in a migration's operations list."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            yield node.func.attr, {
                keyword.arg: keyword.value
                for keyword in node.keywords
                if isinstance(keyword.value, ast.Constant)
            }


def _added_after_creation():
    """``(table, column)`` for every column an ``AddField`` put on a model an
    earlier migration had already created.

    Read from the migration files rather than through Django's loader, which
    imports them: importing a migration makes coverage measure a module the
    suite never runs, since the tests run with ``--no-migrations``.
    """
    created = {}
    added = []
    for path in sorted(MIGRATIONS.glob("[0-9]*.py")):
        tree = ast.parse(path.read_text())
        for name, kwargs in _operations(tree):
            if name == "CreateModel" and "name" in kwargs:
                created.setdefault(kwargs["name"].value.lower(), path.name)
            elif name == "AddField" and {"model_name", "name"} <= kwargs.keys():
                model = kwargs["model_name"].value.lower()
                if created.get(model) in (None, path.name):
                    continue  # the table arrived in this same migration
                added.append((model, kwargs["name"].value))
    return added


def _columns(pairs=None):
    """The audited columns, as ``(table, column)``, skipping fields since
    removed and relations that live in a table of their own."""
    rows = []
    for model_name, field_name in _added_after_creation() if pairs is None else pairs:
        model = apps.get_model(APP, model_name)
        field = next(
            (f for f in model._meta.get_fields() if f.name == field_name), None
        )
        if field is None or field.many_to_many:
            continue
        row = (model._meta.db_table, field.column)
        if row not in rows:
            rows.append(row)
    return rows


ADDED_LATER = _columns()


@pytest.mark.django_db
class TestEveryColumnAddedLater:
    def test_a_field_with_no_column_here_is_not_audited(self):
        """Two ways an ``AddField`` has nothing to check: the field was
        removed again later, or it is a many-to-many, whose rows live in a
        table of their own that no older release wrote to."""
        assert _columns([("session", "presenters"), ("session", "long_gone")]) == []

    def test_the_audit_finds_the_columns_it_should(self):
        """A guard on the guard: if this ever comes back empty, the walk
        above has stopped working and everything below passes vacuously."""
        columns = set(ADDED_LATER)
        assert ("speakers_checklisttemplateitem", "default_team_name") in columns
        assert ("speakers_speakersettings", "conference_timezone") in columns
        assert len(columns) > 10

    @pytest.mark.parametrize(
        "table, column", ADDED_LATER, ids=[f"{t}.{c}" for t, c in ADDED_LATER]
    )
    def test_the_previous_release_can_still_insert(self, table, column):
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
            f"{table}.{column} is NOT NULL with no database default, so a "
            "process from the previous release cannot insert a row while a "
            "deploy rolls out. Give the field a db_default and keep its "
            "Python default; a foreign key, which has no default to give, "
            "goes in nullable and is tightened a release later. See "
            "docs/developer/deployment.md."
        )
