"""The presenters' data view and its CSV (the "Data" mode of the Presenters
page): one row per presenter with everything the team looks up about a
speaker, for designers (links, photo) and staff (Discord, timezone).

One column list drives both the table and the download, so the file is
what the screen shows. Everything here is organizer-facing: email and
Discord usernames are never public.
"""

import csv
import io
import os
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor

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


def _invitation(presenter):
    invitation = presenter.latest_invitation
    return invitation.status.label if invitation else ""


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
    ("Session", _sessions),
    ("Invitation", _invitation),
    ("Liaison", _liaison),
]


def write_presenters_csv(presenters, stream):
    """The data view as CSV: the same columns, one row per presenter."""
    writer = csv.writer(stream)
    writer.writerow([safe_cell(header) for header, _ in DATA_COLUMNS])
    for presenter in presenters:
        writer.writerow([safe_cell(value(presenter)) for _, value in DATA_COLUMNS])
    return stream


PACKAGE_README = """PyLadiesCon speaker package

presenters.csv: one row per presenter, the same columns as the Presenters
page's data view, plus "Photo file", the name of their photo under photos/
(empty when they have none). Email and Discord usernames are for the
team's own use and never go on the public site.

photos/<name>.<ext>: each presenter's headshot as uploaded.
"""


def photo_name(presenter):
    """The photo's name in the package: the presenter's address plus the
    file's own extension; empty without a photo."""
    if not presenter.headshot:
        return ""
    return f"{presenter.slug}{os.path.splitext(presenter.headshot.name)[1].lower()}"


# The zip is built in memory up to this size and on disk beyond it, so a
# hundred phone-sized headshots cost disk, not RAM.
SPOOL_BYTES = 32 * 1024 * 1024
# Photos come from storage (Spaces in production) a few at a time; reads
# are I/O-bound, so this is wall-clock, not CPU.
PHOTO_FETCHERS = 6


def _read_photo(presenter):
    with presenter.headshot.open("rb") as photo:
        return photo.read()


def build_presenters_package(presenters):
    """The data view as a zip: the CSV with a "Photo file" column, the
    photos under photos/, and a README. Returns a file object positioned at
    the start, for a streaming response: the zip lives in a spooled
    temporary file, photos are stored without recompression (they are
    compressed already) and fetched concurrently, and at most a handful
    are in memory at once."""
    presenters = list(presenters)
    spool = tempfile.SpooledTemporaryFile(max_size=SPOOL_BYTES)
    with zipfile.ZipFile(spool, "w") as archive:
        rows = io.StringIO()
        writer = csv.writer(rows)
        writer.writerow([safe_cell(h) for h, _ in DATA_COLUMNS] + ["Photo file"])
        for presenter in presenters:
            writer.writerow(
                [safe_cell(value(presenter)) for _, value in DATA_COLUMNS]
                + [photo_name(presenter)]
            )
        archive.writestr("presenters.csv", rows.getvalue(), zipfile.ZIP_DEFLATED)
        archive.writestr("README.txt", PACKAGE_README, zipfile.ZIP_DEFLATED)
        with_photos = [p for p in presenters if p.headshot]
        with ThreadPoolExecutor(max_workers=PHOTO_FETCHERS) as pool:
            for presenter, data in zip(with_photos, pool.map(_read_photo, with_photos)):
                archive.writestr(
                    f"photos/{photo_name(presenter)}", data, zipfile.ZIP_STORED
                )
    spool.seek(0)
    return spool
