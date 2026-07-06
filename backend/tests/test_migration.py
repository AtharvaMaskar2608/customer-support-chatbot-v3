"""Migration smoke test — idempotency + resulting schema.

Integration test against the configured DATABASE_URL. Skipped when the database
is unreachable (e.g. CI without Postgres).
"""

from __future__ import annotations

import pytest

from backend.db import get_connection, run_migrations


def _column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    return cur.fetchone() is not None


def _index_exists(cur, index: str) -> bool:
    cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s", (index,))
    return cur.fetchone() is not None


@pytest.fixture(scope="module")
def _db_or_skip():
    try:
        conn = get_connection()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"database unavailable: {exc}")
    conn.close()


def test_run_migrations_idempotent_and_schema_present(_db_or_skip):
    # Run twice — the second run must be a clean no-op.
    run_migrations()
    run_migrations()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            assert _column_exists(cur, "qa_chunks", "fts")
            assert _index_exists(cur, "qa_chunks_fts_gin")

            # Every row has a populated fts value (generated column).
            cur.execute("SELECT count(*) FROM qa_chunks")
            total = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM qa_chunks WHERE fts IS NOT NULL")
            populated = cur.fetchone()[0]
            assert populated == total
    finally:
        conn.close()
