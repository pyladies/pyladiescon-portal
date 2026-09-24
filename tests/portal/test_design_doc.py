"""The design document is cited by the code, so the citations must land.

Twenty-one distinct ``design §N`` references live in docstrings, help text
and READMEs. They are only useful while they resolve to a heading on
``docs/architecture/speaker-portal.md``: a deleted or renumbered section
turns them into dead ends, quietly.

What this catches is a citation that lands on nothing. A citation that
lands on the *wrong* section still passes, because the number exists:
§7.1 was cited for per-language names while §7.1 was about permissions,
and no test can tell. Reading the section a number points at is still a
person's job.

The nav check is here for the same reason: an architecture page missing
from ``mkdocs.yml`` is reachable only by guessing its URL, and mkdocs
reports it as INFO, which nothing fails on.
"""

import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DESIGN_DOC = REPO_ROOT / "docs" / "architecture" / "speaker-portal.md"
SKIP_DIRS = {
    ".git",
    ".state",
    "htmlcov",
    "node_modules",
    "site",
    "staticroot",
    "venv",
    "venv_local",
}
CITATION = re.compile(r"design §([0-9]+(?:\.[0-9a-z]+)*)")
HEADING = re.compile(r"^#+\s+([0-9]+(?:\.[0-9a-z]+)*)\.?\s", re.M)


def headings():
    return set(HEADING.findall(DESIGN_DOC.read_text()))


def citations():
    """Every ``design §N`` in the repository, with where it was found."""
    found = []
    for suffix in ("*.py", "*.md", "*.html"):
        for path in REPO_ROOT.rglob(suffix):
            if not SKIP_DIRS.isdisjoint(path.relative_to(REPO_ROOT).parts):
                continue
            if path == DESIGN_DOC:
                continue
            for section in CITATION.findall(path.read_text(errors="ignore")):
                found.append((section, str(path.relative_to(REPO_ROOT))))
    return found


def test_there_are_citations_to_check():
    """A guard on the guard: a broken walk would pass silently."""
    assert len({section for section, _ in citations()}) > 10


def test_every_design_citation_resolves():
    known = headings()
    dead = sorted(
        {(section, where) for section, where in citations() if section not in known}
    )
    assert dead == [], (
        "these point at a section the design document does not have: "
        f"{dead}. Renumbering a section means updating what cites it."
    )


STAGE = re.compile(r"Stage (\d+(?:\.\d+)?b?)")


def stages_cited():
    """Every ``Stage N`` in the code and the app READMEs."""
    found = {}
    for suffix in ("*.py", "*.md"):
        for path in REPO_ROOT.rglob(suffix):
            if not SKIP_DIRS.isdisjoint(path.relative_to(REPO_ROOT).parts):
                continue
            if path == DESIGN_DOC:
                continue
            for stage in STAGE.findall(path.read_text(errors="ignore")):
                found.setdefault(stage, str(path.relative_to(REPO_ROOT)))
    return found


def mapped_stages():
    """The stage numbers the build order's mapping table translates.

    Read from the table's own column rather than from the page, and
    matched whole: "Stage 3b" contains "Stage 3", so a substring search
    would accept a mapping that names neither.
    """
    doc = DESIGN_DOC.read_text()
    start = doc.index("| Here | In the code |")
    end = doc.index("\n\n", start)
    mapped = set()
    for row in doc[start:end].splitlines():
        cells = [cell.strip() for cell in row.split("|")]
        if len(cells) > 2:
            match = re.fullmatch(r"Stage (\d+(?:\.\d+)?b?)", cells[2])
            if match:
                mapped.add(match.group(1))
    return mapped


def tasks_explained():
    """The decimal numbers the paragraph under the table accounts for."""
    doc = DESIGN_DOC.read_text()
    start = doc.index("A number with a decimal")
    end = doc.index("\n\n", start)
    return set(STAGE.findall(doc[start:end]))


def test_the_stage_mapping_covers_what_the_code_says():
    """The build order translates between the page's milestones and the
    stage numbers the code uses. A stage the code cites and the mapping
    does not name sends a reader to the wrong section, which is worse than
    sending them nowhere: that is what happened when the mapping was
    written from a planning file instead of from the repository.

    Read only the mapping, not the whole page: the numbers appear in the
    prose too, and matching there would pass a mapping that says anything.
    A decimal is a task rather than a stage, and the paragraph under the
    table accounts for those.
    """
    mapped = mapped_stages() | tasks_explained()
    missing = sorted(
        (stage, where) for stage, where in stages_cited().items() if stage not in mapped
    )
    assert missing == [], (
        "the build order does not translate these, which the code cites: " f"{missing}"
    )


def test_the_page_names_a_stage_number_only_where_it_maps_them():
    """One place, or they drift.

    The build-order table used to repeat the stage in every row, and when
    the mapping was corrected the rows kept the old numbers, so the
    section contradicted itself twelve lines apart. The mapping table and
    the paragraph under it are the only place a stage number belongs.
    """
    doc = DESIGN_DOC.read_text()
    start = doc.index("| Here | In the code |")
    end = doc.index("\n\n", doc.index("A number with a decimal", start))
    outside = doc[:start] + doc[end:]
    assert STAGE.findall(outside) == [], (
        "stage numbers appear outside the mapping: "
        f"{sorted(set(STAGE.findall(outside)))}. The mapping is the one "
        "place they belong, so the two cannot disagree."
    )


def test_every_architecture_page_is_in_the_nav():
    nav = (REPO_ROOT / "mkdocs.yml").read_text()
    missing = sorted(
        path.name
        for path in (REPO_ROOT / "docs" / "architecture").glob("*.md")
        if f"architecture/{path.name}" not in nav
    )
    assert missing == [], f"add these to the nav in mkdocs.yml: {missing}"
