"""Postgres connection + migration runner.

Connection details come solely from ``settings.database_url``; no module may
hardcode them.
"""

from __future__ import annotations

from pathlib import Path

import psycopg2

from backend.config import get_settings

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def get_connection() -> "psycopg2.extensions.connection":
    """Open a live Postgres connection from ``settings.database_url``."""

    return psycopg2.connect(get_settings().database_url)


def run_migrations() -> None:
    """Apply every ``migrations/*.sql`` file in filename order, idempotently.

    Each migration is written to be safe to re-run, so this whole call is a
    no-op when the schema is already current.
    """

    files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                for path in files:
                    cur.execute(path.read_text(encoding="utf-8"))
    finally:
        conn.close()
