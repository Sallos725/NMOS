"""Normalized-text projection (#9): one versioned `clean_text` output per revision.

Lexical recall, embedding, extraction and excerpting read `revision_text.clean_content`, so they share
one normalization. The projection is derived: it can be dropped and rebuilt from the source ledger.

Which normalizer that is (PHASE-66 part 3) is a startup setting, `NMOS_NORMALIZER`: `clean-v3` (the default,
`packet.clean_text`) or `clean-v4` (`packet.clean_text_v4`). Every reader asks `active()`; nothing binds the name at
import. Rows are keyed by normalizer, so both are kept side by side and a switch back serves the other's rows again.
A replay reads the normalizer its request was served from (`reading`, ADR 0027).
"""

from __future__ import annotations

import contextlib
import contextvars
from typing import Any, Callable, Iterator
from uuid import UUID

import psycopg
from psycopg.rows import tuple_row

from .packet import clean_text, clean_text_v4

# Bump whenever clean_text() output can change; embedding and extractor generations include it. Since PHASE-66 part 3
# the default's name: the normalizer in force is `active()`.
NORMALIZER_VERSION = "clean-v3"
DEFAULT_NORMALIZER = NORMALIZER_VERSION
# Every normalizer NMOS_NORMALIZER may select, with its cleaner. Their rows are kept side by side (`retention.prune_text`
# prunes only other normalizers'), and a switch among them re-derives nothing a model wrote (`generations.classify`:
# `normalizer`).
CLEANERS: dict[str, Callable[[str], str]] = {"clean-v3": clean_text, "clean-v4": clean_text_v4}
NORMALIZERS = tuple(CLEANERS)

_configured = DEFAULT_NORMALIZER  # the process's setting (`use`), as each entry point reads it at startup
_reading: contextvars.ContextVar[str | None] = contextvars.ContextVar("nmos_normalizer_reading", default=None)


def use(normalizer: str) -> None:
    """Make `normalizer` the process's normalizer (an entry point, from `Settings.normalizer`)."""
    global _configured
    if normalizer not in CLEANERS:
        raise ValueError(f"unknown normalizer {normalizer!r}: {', '.join(NORMALIZERS)}")
    _configured = normalizer


def active() -> str:
    """The normalizer every reader and writer uses now: a replay's (`reading`), else the process's."""
    return _reading.get() or _configured


@contextlib.contextmanager
def reading(normalizer: str | None) -> Iterator[str]:
    """Read as `normalizer` within the block (a replay of a request served under it, ADR 0027); None or an unknown
    name reads the default, which is what every request recorded before the setting was served from."""
    token = _reading.set(normalizer if normalizer in CLEANERS else DEFAULT_NORMALIZER)
    try:
        yield _reading.get()  # type: ignore[misc]
    finally:
        _reading.reset(token)


def clean(content: str, normalizer: str | None = None) -> str:
    """`content` as `normalizer` (default: the active one) cleans it."""
    return CLEANERS[normalizer or active()](content)


def write(conn: psycopg.Connection, revision_id: UUID, content: str, normalizer: str | None = None) -> None:
    normalizer = normalizer or active()
    text = clean(content, normalizer)
    conn.execute(
        "INSERT INTO revision_text (source_revision_id, normalizer, clean_content, original_chars, clean_chars)"
        " VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
        (revision_id, normalizer, text, len(content), len(text)),
    )


def get(conn: psycopg.Connection, revision_id: UUID, normalizer: str | None = None) -> dict[str, Any] | None:
    """The current normalizer's row, written on demand if a backfill has not reached it yet."""
    normalizer = normalizer or active()
    sql = ("SELECT clean_content, original_chars, clean_chars FROM revision_text"
           " WHERE source_revision_id = %s AND normalizer = %s")
    row = conn.execute(sql, (revision_id, normalizer)).fetchone()
    if row is None:
        src = conn.execute("SELECT content FROM source_revision WHERE id = %s", (revision_id,)).fetchone()
        if src is None:
            return None
        write(conn, revision_id, src["content"], *([normalizer] if normalizer != active() else []))
        row = conn.execute(sql, (revision_id, normalizer)).fetchone()
    return row


def missing(conn: psycopg.Connection) -> list[UUID]:
    """The message revisions no append has seen: without the current normalizer's text, as rows a restore wrote are
    (the archive carries no derived text, ADR 0050) or rows from before the normalizer. What else an append derives
    (the parser state) is owed to them too (PHASE-39)."""
    with conn.cursor(row_factory=tuple_row) as cur:
        return [r[0] for r in cur.execute(
            "SELECT sr.id FROM source_revision sr JOIN source_object so ON so.id = sr.source_object_id"
            " WHERE so.source_kind = 'message' AND NOT EXISTS (SELECT 1 FROM revision_text rt"
            " WHERE rt.source_revision_id = sr.id AND rt.normalizer = %s)", (active(),)).fetchall()]


def backfill(conn: psycopg.Connection, batch: int = 500) -> int:
    """Write the current normalizer's rows for every revision that lacks one (no host re-import)."""
    normalizer = active()
    total = 0
    while True:
        with conn.transaction():
            rows = conn.execute(
                "SELECT sr.id, sr.content FROM source_revision sr WHERE NOT EXISTS (SELECT 1 FROM revision_text rt"
                " WHERE rt.source_revision_id = sr.id AND rt.normalizer = %s) LIMIT %s",
                (normalizer, batch),
            ).fetchall()
            for row in rows:
                write(conn, row["id"], row["content"])  # the active normalizer's row
        total += len(rows)
        if len(rows) < batch:
            return total
