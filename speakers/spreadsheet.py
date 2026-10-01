"""Text that goes into a CSV a spreadsheet will open, or a shell script will
embed: one line, and never a formula.

Presenters type their own display name, session title and file titles;
organizers type notes. Any of them could start with ``=`` and be read as a
formula by Excel or Sheets, and any of them could carry a newline, which a
CSV writer quotes faithfully and a heredoc in a script does not survive.
Every cell of every CSV the speakers app writes goes through ``safe_cell``,
so there is one place to get this right.
"""

FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r", "\n")


def safe_cell(value):
    """``value`` as one line of text a spreadsheet shows rather than runs:
    runs of whitespace, newlines included, folded to a space, and a
    leading apostrophe when it would otherwise read as a formula."""
    text = " ".join(str(value).split())
    if text.startswith(FORMULA_STARTS):
        return "'" + text
    return text
