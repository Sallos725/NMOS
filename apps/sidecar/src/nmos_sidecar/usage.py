"""What one chat's memory cost in model calls (Phase 17 Q4, ADR 0051): the usage kept with each extraction, canon
read, summary and embedded chunk, totalled per generation. Discarded rows count too: their calls were made."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

COUNTS = ("rows", "not_recorded", "calls", "reported", "input", "output", "cached", "reasoning")

# One row per model-work row of the chat: its generation key and its usage (NULL before migration 0027).
_ROWS = """
    SELECT x.extractor_key AS key, x.usage FROM extraction x
    JOIN source_revision sr ON sr.id = x.source_revision_id
    JOIN source_object so ON so.id = sr.source_object_id
    WHERE so.conversation_id = %(conv)s AND x.extractor_key IS NOT NULL
    UNION ALL
    SELECT s.generation, s.usage FROM summary s WHERE s.conversation_id = %(conv)s
    UNION ALL
    SELECT re.projection, re.usage FROM revision_embedding re
    JOIN source_revision sr ON sr.id = re.source_revision_id
    JOIN source_object so ON so.id = sr.source_object_id
    WHERE so.conversation_id = %(conv)s
"""


def totals(conn: psycopg.Connection, conv: UUID, active: set[str] | None = None) -> dict[str, Any]:
    """Per generation (newest first) and in all: rows, rows from before usage was recorded, model calls, calls whose
    provider reported tokens, and the reported input / output / cached input / reasoning tokens."""
    rows = conn.execute(
        f"""
        WITH r AS ({_ROWS})
        SELECT g.kind, g.key, g.model, g.activated_at,
               count(*) AS rows,
               count(*) FILTER (WHERE r.usage IS NULL) AS not_recorded,
               coalesce(sum((r.usage->>'calls')::int), 0) AS calls,
               count(*) FILTER (WHERE r.usage ? 'input' OR r.usage ? 'output') AS reported,
               coalesce(sum((r.usage->>'input')::bigint), 0) AS input,
               coalesce(sum((r.usage->>'output')::bigint), 0) AS output,
               coalesce(sum((r.usage->>'cached')::bigint), 0) AS cached,
               coalesce(sum((r.usage->>'reasoning')::bigint), 0) AS reasoning
        FROM r JOIN projection_generation g ON g.key = r.key
        GROUP BY g.kind, g.key, g.model, g.activated_at
        ORDER BY g.activated_at DESC, g.key
        """, {"conv": conv}).fetchall()
    gens = [{"kind": r["kind"], "key": r["key"], "model": r["model"], "active": r["key"] in (active or set()),
             **{k: int(r[k]) for k in COUNTS}} for r in rows]
    return {"generations": gens, "total": {k: sum(g[k] for g in gens) for k in COUNTS}}


def produced(conn: psycopg.Connection, conv: UUID, extractor: str | None, summarizer: str | None) -> dict[str, int]:
    """How many facts (valid assertions) and summaries the active generations hold for the chat now. The HUD compares
    two of these to say what background work made (PHASE-17 Q6); cheap enough for its polls."""
    facts = conn.execute(
        "SELECT count(*) AS n FROM assertion a JOIN extraction x ON x.id = a.extraction_id"
        " JOIN source_revision sr ON sr.id = x.source_revision_id JOIN source_object so ON so.id = sr.source_object_id"
        " WHERE so.conversation_id = %s AND x.extractor_key = %s AND x.discarded_at IS NULL AND a.status = 'valid'",
        (conv, extractor)).fetchone()["n"] if extractor else 0
    summaries = conn.execute(
        "SELECT count(*) AS n FROM summary WHERE conversation_id = %s AND generation = %s AND discarded_at IS NULL"
        " AND text <> ''", (conv, summarizer)).fetchone()["n"] if summarizer else 0
    return {"facts": int(facts), "summaries": int(summaries)}
