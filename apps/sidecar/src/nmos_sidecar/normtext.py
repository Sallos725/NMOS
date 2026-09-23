"""Normalized-text projection (#9): one versioned `clean_text` output per revision.

Lexical recall, embedding, extraction and excerpting read `revision_text.clean_content`, so they share
one normalization. The projection is derived: it can be dropped and rebuilt from the source ledger.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from .packet import clean_text

# Bump whenever clean_text() output can change; embedding and extractor generations include it.
NORMALIZER_VERSION = "clean-v2"


def write(conn: psycopg.Connection, revision_id: UUID, content: str) -> None:
    clean = clean_text(content)
    conn.execute(
        "INSERT INTO revision_text (source_revision_id, normalizer, clean_content, original_chars, clean_chars)"
        " VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
        (revision_id, NORMALIZER_VERSION, clean, len(content), len(clean)),
    )


def get(conn: psycopg.Connection, revision_id: UUID) -> dict[str, Any] | None:
    """The current normalizer's row, written on demand if a backfill has not reached it yet."""
    sql = ("SELECT clean_content, original_chars, clean_chars FROM revision_text"
           " WHERE source_revision_id = %s AND normalizer = %s")
    row = conn.execute(sql, (revision_id, NORMALIZER_VERSION)).fetchone()
    if row is None:
        src = conn.execute("SELECT content FROM source_revision WHERE id = %s", (revision_id,)).fetchone()
        if src is None:
            return None
        write(conn, revision_id, src["content"])
        row = conn.execute(sql, (revision_id, NORMALIZER_VERSION)).fetchone()
    return row


def backfill(conn: psycopg.Connection, batch: int = 500) -> int:
    """Write the current normalizer's rows for every revision that lacks one (no host re-import)."""
    total = 0
    while True:
        with conn.transaction():
            rows = conn.execute(
                "SELECT sr.id, sr.content FROM source_revision sr WHERE NOT EXISTS (SELECT 1 FROM revision_text rt"
                " WHERE rt.source_revision_id = sr.id AND rt.normalizer = %s) LIMIT %s",
                (NORMALIZER_VERSION, batch),
            ).fetchall()
            for row in rows:
                write(conn, row["id"], row["content"])
        total += len(rows)
        if len(rows) < batch:
            return total
