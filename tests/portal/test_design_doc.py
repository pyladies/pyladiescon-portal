"""The design document is cited by the code, so the citations must land.

Twenty-one distinct ``design §N`` references live in docstrings, help text
and READMEs. They are only useful while they resolve to a heading on
``docs/architecture/speaker-portal.md``: a renumbered section turns every
one of them into a dead end, quietly.

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


def test_every_architecture_page_is_in_the_nav():
    nav = (REPO_ROOT / "mkdocs.yml").read_text()
    missing = sorted(
        path.name
        for path in (REPO_ROOT / "docs" / "architecture").glob("*.md")
        if f"architecture/{path.name}" not in nav
    )
    assert missing == [], f"add these to the nav in mkdocs.yml: {missing}"
