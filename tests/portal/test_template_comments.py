"""Every template comment has to be one Django actually hides.

``{# ... #}`` is a single-line comment. Django's lexer only recognises it
when it opens and closes on the same line, so a comment wrapped over two
lines is not a comment at all: it renders, and the reader sees the note we
wrote for ourselves at the top of the page. That has happened more than
once, most recently on every portal page in production, so it is a test
rather than a habit.

Multi-line notes belong in ``{% comment %} ... {% endcomment %}``.
"""

import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SKIP_DIRS = {
    ".git",
    ".state",
    "docs",
    "htmlcov",
    "node_modules",
    "staticroot",
    "venv",
    "venv_local",
}


def template_files():
    for path in sorted(REPO_ROOT.rglob("*.html")):
        if SKIP_DIRS.isdisjoint(path.relative_to(REPO_ROOT).parts):
            yield path


def unbalanced_lines(path):
    """Lines that open a ``{#`` comment they do not close."""
    return [
        (number, line.strip())
        for number, line in enumerate(path.read_text().splitlines(), 1)
        if line.count("{#") and line.count("{#") != line.count("#}")
    ]


def test_there_are_templates_to_check():
    """A guard on the guard: a bad path here would pass silently."""
    assert len(list(template_files())) > 50


@pytest.mark.parametrize("path", list(template_files()), ids=str)
def test_no_multiline_hash_comment(path):
    offenders = unbalanced_lines(path)
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)} opens a {{# #}} comment that does not "
        f"close on the same line, so it renders: {offenders}. "
        "Use {% comment %} ... {% endcomment %} instead."
    )
