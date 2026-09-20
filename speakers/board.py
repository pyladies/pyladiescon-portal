"""The checklist board (design §9.6): presenters down the side, items
across the top, one status per cell, sorted by who most needs a nudge.

Built from two queries (presenters, items) regardless of size.
"""

import csv
from collections import defaultdict

from .clock import today as current_date
from .constants import ItemStatus
from .models import ChecklistItem, Presenter

CELL_CLASSES = {
    ItemStatus.DONE: "cell-done",
    ItemStatus.SKIPPED: "cell-skipped",
    ItemStatus.BLOCKED: "cell-blocked",
    ItemStatus.TODO: "cell-todo",
}


def cell_class(item, today):
    if item is None:
        return "cell-none"
    if item.status == ItemStatus.TODO and item.due_date and item.due_date < today:
        return "cell-overdue"
    return CELL_CLASSES[ItemStatus(item.status)]


def build_board(conference, user, owner, sort="overdue"):
    """Return ``{"columns": [...titles], "rows": [...]}`` for one tab.

    Each row: ``presenter``, ``cells`` (one per column, item or None),
    ``overdue`` (count), ``open`` (count), ``next_due``.
    """
    today = current_date()
    presenters = list(
        Presenter.objects.for_conference(conference)
        .visible_to(user)
        .select_related("liaison")
        .order_by("display_name")
    )
    items = (
        ChecklistItem.objects.filter(
            conference=conference, owner=owner, presenter__in=[p.pk for p in presenters]
        )
        .select_related("assignee")
        .order_by("order", "id")
    )
    by_presenter = defaultdict(dict)
    column_order = {}
    for item in items:
        # Same title on two sessions: keep the most urgent one for the cell.
        current = by_presenter[item.presenter_id].get(item.title)
        if current is None or _more_urgent(item, current, today):
            by_presenter[item.presenter_id][item.title] = item
        column_order.setdefault(item.title, (item.order, item.pk))
    columns = sorted(column_order, key=column_order.get)
    rows = []
    for presenter in presenters:
        cells = [by_presenter[presenter.pk].get(title) for title in columns]
        open_items = [c for c in cells if c is not None and c.is_open]
        overdue = [c for c in open_items if c.due_date and c.due_date < today]
        due_dates = [c.due_date for c in open_items if c.due_date]
        rows.append(
            {
                "presenter": presenter,
                "cells": [(cell, cell_class(cell, today)) for cell in cells],
                "overdue": len(overdue),
                "open": len(open_items),
                "next_due": min(due_dates) if due_dates else None,
            }
        )
    if sort == "name":
        rows.sort(key=lambda row: row["presenter"].display_name.lower())
    else:
        rows.sort(
            key=lambda row: (
                -row["overdue"],
                row["next_due"] or today.replace(year=today.year + 10),
                -row["open"],
                row["presenter"].display_name.lower(),
            )
        )
    return {"columns": columns, "rows": rows, "today": today}


def _more_urgent(candidate, current, today):
    def rank(item):
        overdue = item.is_open and item.due_date is not None and item.due_date < today
        return (
            not item.is_open,
            not overdue,
            item.due_date or today.replace(year=9999),
        )

    return rank(candidate) < rank(current)


FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")

CSV_NOTE = (
    "One column per item title. A presenter on two sessions shows the more "
    "urgent copy of a same-titled item, so open the presenter page for the "
    "full list."
)


def _safe_cell(value):
    """Text a spreadsheet will show, not run.

    Presenters type their own display name and titles come from templates
    organizers edit; either could start with ``=`` and be read as a formula
    by Excel or Sheets. A leading apostrophe makes the cell literal text."""
    text = str(value)
    if text.startswith(FORMULA_STARTS):
        return "'" + text
    return text


def write_board_csv(board, stream):
    """Write the board as CSV: a note row, then presenter, email, liaison,
    overdue count and one column per item title."""
    writer = csv.writer(stream)
    writer.writerow([CSV_NOTE])
    writer.writerow(
        [_safe_cell(c) for c in ["Presenter", "Email", "Liaison", "Overdue"]]
        + [_safe_cell(title) for title in board["columns"]]
    )
    for row in board["rows"]:
        presenter = row["presenter"]
        liaison = presenter.liaison
        writer.writerow(
            [
                _safe_cell(presenter.display_name),
                _safe_cell(presenter.email),
                _safe_cell(
                    (liaison.get_full_name() or liaison.username) if liaison else ""
                ),
                row["overdue"],
            ]
            + [
                _safe_cell(cell.get_status_display() if cell else "")
                for cell, _ in row["cells"]
            ]
        )
    return stream
