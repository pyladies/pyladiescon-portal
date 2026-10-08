"""The presenters' data view and its CSV (the "Data" mode of the Presenters
page): one row per presenter with everything the team looks up about a
speaker, for designers (links, photo) and staff (Discord, timezone).

One column list drives both the table and the download, so the file is
what the screen shows. Everything here is organizer-facing: email and
Discord usernames are never public.
"""

import csv

from .spreadsheet import safe_cell


def _liaison(presenter):
    liaison = presenter.liaison
    if liaison is None:
        return ""
    return liaison.get_full_name() or liaison.username


def _sessions(presenter):
    return "; ".join(
        f"{link.session.title} ({link.role.name})" for link in presenter.session_links
    )


# (header, value of a presenter row loaded with with_listing_data)
DATA_COLUMNS = [
    ("Name", lambda p: p.display_name),
    ("Pronouns", lambda p: p.pronouns),
    ("Email", lambda p: p.email),
    ("Discord", lambda p: p.discord_username),
    ("Timezone", lambda p: p.timezone),
    ("Location", lambda p: p.location),
    ("Website", lambda p: p.website_url),
    ("GitHub", lambda p: p.github_username),
    ("Mastodon", lambda p: p.mastodon_url),
    ("LinkedIn", lambda p: p.linkedin_url),
    ("Bluesky", lambda p: p.bluesky_username),
    ("Photo", lambda p: "yes" if p.headshot else "no"),
    ("Public profile", lambda p: "yes" if p.is_public else "no"),
    ("Sessions", _sessions),
    ("Liaison", _liaison),
]


def write_presenters_csv(presenters, stream):
    """The data view as CSV: the same columns, one row per presenter."""
    writer = csv.writer(stream)
    writer.writerow([safe_cell(header) for header, _ in DATA_COLUMNS])
    for presenter in presenters:
        writer.writerow([safe_cell(value(presenter)) for _, value in DATA_COLUMNS])
    return stream
