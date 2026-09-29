"""Create, snapshot and restore the throwaway database the screencasts use.

Every take starts from the same seeded state, so a take that consumes
something (an invitation link, a proposal) can be re-run. The snapshot is a
Postgres template database, restored with ``CREATE DATABASE ... TEMPLATE``.

Usage: ``python db.py snapshot|restore|drop`` with ``DATABASE_URL`` pointing at
the working database. The snapshot is named ``<database>_base``.
"""

import os
import sys
from urllib.parse import urlparse

import psycopg2
from psycopg2 import sql


def connect():
    url = urlparse(os.environ["DATABASE_URL"])
    connection = psycopg2.connect(
        dbname="postgres",
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port,
    )
    connection.autocommit = True
    return connection, url.path.lstrip("/")


def run(*statements):
    connection, name = connect()
    names = {"db": sql.Identifier(name), "base": sql.Identifier(f"{name}_base")}
    with connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement.format(**names))
    connection.close()


def disconnect_others():
    """A template database must have no other sessions; drop any left over."""
    connection, name = connect()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            [name],
        )
    connection.close()


def main(action):
    drop = sql.SQL("DROP DATABASE IF EXISTS {db} WITH (FORCE)")
    drop_base = sql.SQL("DROP DATABASE IF EXISTS {base} WITH (FORCE)")
    if action == "snapshot":
        disconnect_others()
        run(drop_base, sql.SQL("CREATE DATABASE {base} TEMPLATE {db}"))
    elif action == "restore":
        run(drop, sql.SQL("CREATE DATABASE {db} TEMPLATE {base}"))
    elif action == "create":
        run(drop, sql.SQL("CREATE DATABASE {db}"))
    elif action == "drop":
        run(drop, drop_base)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
