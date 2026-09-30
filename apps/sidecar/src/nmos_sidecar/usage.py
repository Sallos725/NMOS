"""What one chat's memory cost in model calls (Phase 17 Q4, ADR 0051): the usage kept with each extraction, canon
read, summary and embedded chunk, totalled per generation. Discarded rows count too: their calls were made."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

TOKENS = ("input", "output", "cached", "reasoning")
# `<field>_reported`: calls whose provider gave that field, so a missing count is never shown as a reported 0.
COUNTS = ("rows", "not_recorded", "calls", "reported", *TOKENS, *(f"{k}_reported" for k in TOKENS))

# One row per model-work row of the chat: what made it, its generation key and its usage (NULL before migration 0027).
# Rows from before generations (extractor_key NULL; `legacy:<model>` embeddings, which have no generation row) count
# under their kind with the key they have.
_ROWS = """
    SELECT 'extract' AS kind, x.extractor_key AS key, x.usage FROM extraction x
    JOIN source_revision sr ON sr.id = x.source_revision_id
    JOIN source_object so ON so.id = sr.source_object_id
    WHERE so.conversation_id = %(conv)s
    UNION ALL
    SELECT 'summarize', s.generation, s.usage FROM summary s WHERE s.conversation_id = %(conv)s
    UNION ALL
    SELECT 'embed', re.projection, re.usage FROM revision_embedding re
    JOIN source_revision sr ON sr.id = re.source_revision_id
    JOIN source_object so ON so.id = sr.source_object_id
    WHERE so.conversation_id = %(conv)s
"""


def totals(conn: psycopg.Connection, conv: UUID, active: set[str] | None = None) -> dict[str, Any]:
    """Per generation (newest first; rows without a generation last) and in all: rows, rows from before usage was
    recorded, model calls, calls whose provider reported tokens, the reported input / output / cached input / reasoning
    tokens, and for each of those how many calls reported it."""
    rows = conn.execute(
        f"""
        WITH r AS ({_ROWS})
        SELECT coalesce(g.kind, r.kind) AS kind, r.key, g.model, g.activated_at,
               count(*) AS rows,
               count(*) FILTER (WHERE r.usage IS NULL) AS not_recorded,
               coalesce(sum((r.usage->>'calls')::int), 0) AS calls,
               count(*) FILTER (WHERE r.usage ? 'input' OR r.usage ? 'output') AS reported,
               coalesce(sum((r.usage->>'input')::bigint), 0) AS input,
               coalesce(sum((r.usage->>'output')::bigint), 0) AS output,
               coalesce(sum((r.usage->>'cached')::bigint), 0) AS cached,
               coalesce(sum((r.usage->>'reasoning')::bigint), 0) AS reasoning,
               count(*) FILTER (WHERE r.usage ? 'input') AS input_reported,
               count(*) FILTER (WHERE r.usage ? 'output') AS output_reported,
               count(*) FILTER (WHERE r.usage ? 'cached') AS cached_reported,
               count(*) FILTER (WHERE r.usage ? 'reasoning') AS reasoning_reported
        FROM r LEFT JOIN projection_generation g ON g.key = r.key
        GROUP BY 1, r.key, g.model, g.activated_at
        ORDER BY g.activated_at DESC NULLS LAST, r.key NULLS LAST
        """, {"conv": conv}).fetchall()
    gens = [{"kind": r["kind"], "key": r["key"], "model": r["model"], "active": r["key"] in (active or set()),
             **{k: int(r[k]) for k in COUNTS}} for r in rows]
    return {"generations": gens, "total": {k: sum(g[k] for g in gens) for k in COUNTS}}


def produced(conn: psycopg.Connection, conv: UUID, extractor: str | None, summarizer: str | None) -> dict[str, int]:
    """What the chat's current head holds of the active generations' work: facts (valid assertions of extractions that
    match a turn of the head, as recall's facts must) and summaries (the current scene summaries, and the story when it
    covers them all). The HUD compares two of these to say what background work made (PHASE-17 Q6), so an edit that
    only replaces a fact or a summary adds nothing. Cheap enough for its polls."""
    from . import summaries

    head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (conv,)).fetchone()
    head = head["head_commit_id"] if head else None
    if head is None:
        return {"facts": 0, "summaries": 0}
    facts = conn.execute(
        "SELECT count(*) AS n FROM active_membership am"
        " JOIN extraction x ON x.source_revision_id = am.source_revision_id AND x.window_hash = am.turn_hash"
        " JOIN assertion a ON a.extraction_id = x.id"
        " WHERE am.commit_id = %s AND x.extractor_key = %s AND x.discarded_at IS NULL AND a.status = 'valid'",
        (head, extractor)).fetchone()["n"] if extractor else 0
    made = 0
    if summarizer:
        view = summaries.current(conn, conv, head, summarizer)
        made = view["done"] + (1 if view["story_current"] else 0)
    return {"facts": int(facts), "summaries": made}


def summary_jobs(conn: psycopg.Connection, conv: UUID, summarizer: str | None) -> dict[str, int]:
    """The active summarizer's jobs for the chat still to run and dead: the HUD waits for them too (they run after
    extraction and embedding), so a summary written last is counted."""
    if not summarizer:
        return {"pending": 0, "failed": 0}
    row = conn.execute(
        "SELECT count(*) FILTER (WHERE status IN ('queued', 'running')) AS pending,"
        " count(*) FILTER (WHERE status = 'dead') AS failed FROM job"
        " WHERE conversation_id = %s AND kind = 'summarize' AND payload->>'generation' = %s", (conv, summarizer)).fetchone()
    return {"pending": int(row["pending"]), "failed": int(row["failed"])}
