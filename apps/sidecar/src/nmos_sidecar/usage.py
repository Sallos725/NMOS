"""What one chat's memory cost in model calls (Phase 17 Q4, ADR 0051): the usage kept with each extraction, canon
read, summary and embedded chunk, totalled per generation. Discarded rows count too: their calls were made. The
totals are of the rows NMOS still holds: embeddings of a projection another replaced are pruned (retention, O5) and
their usage with them (owner decision 2026-09-30, the Copilot review of #185)."""

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
               count(*) FILTER (WHERE r.usage ?| array['input', 'output', 'cached', 'reasoning']) AS reported,
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


def work(conn: psycopg.Connection, conv: UUID, extractor: str | None, summarizer: str | None) -> dict[str, Any]:
    """For the HUD's polls (PHASE-17 Q6), both about the chat's current head only:

    `produced`: facts (valid assertions of extractions that match a turn of the head, as recall's facts must) and
    summaries (current scene summaries with text, and the story when it covers them all), so an edit that only
    replaces a fact or a summary, or a window too short to summarize, adds nothing.

    `summaries`: the summary jobs of the head's windows and of its story, still to run or dead, first writes and
    rewrites with a secret alike (`schedule_stale`): found by the window keys in their payload, so a job of a window an
    edit replaced is not counted. The chat's open and dead jobs are few (finished ones are pruned after 7 days;
    production held 2,100 jobs in all on 2026-09-30), so no index is needed."""
    from . import summaries

    row = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (conv,)).fetchone()
    head = row["head_commit_id"] if row else None
    none = {"produced": {"facts": 0, "summaries": 0}, "summaries": {"pending": 0, "failed": 0}}
    if head is None:
        return none
    facts = conn.execute(
        "SELECT count(*) AS n FROM active_membership am"
        " JOIN extraction x ON x.source_revision_id = am.source_revision_id AND x.window_hash = am.turn_hash"
        " JOIN assertion a ON a.extraction_id = x.id"
        " WHERE am.commit_id = %s AND x.extractor_key = %s AND x.discarded_at IS NULL AND a.status = 'valid'",
        (head, extractor)).fetchone()["n"] if extractor else 0
    if not summarizer:
        return {**none, "produced": {"facts": int(facts), "summaries": 0}}
    view = summaries.current(conn, conv, head, summarizer)
    written = [x["summary"] for x in view["scenes"] if x["summary"]]
    made = sum(1 for x in written if x["text"]) + (1 if view["story_current"] and view["story"]["text"] else 0)
    keys = [x["window"].key for x in view["scenes"]]  # may be empty: a story job can still be pending
    if written and len(written) == view["due"]:
        keys.append(summaries.members_key([x["id"] for x in written]))  # the story of these scenes
    # Any story job still to run counts as pending, whatever scenes it was queued for: the worker writes the last
    # scene, queues the story and only then marks the scene job done, so a poll that read the scenes before and the
    # jobs after would otherwise see neither (Copilot review of #186). A stale one is obsolete at once when it runs.
    jobs = conn.execute(
        "SELECT count(*) FILTER (WHERE status IN ('queued', 'running')) AS pending,"
        " count(*) FILTER (WHERE status = 'dead' AND payload->>'window_key' = ANY(%s)) AS failed FROM job"
        " WHERE conversation_id = %s AND kind = 'summarize' AND status IN ('queued', 'running', 'dead')"
        " AND payload->>'generation' = %s"
        " AND (payload->>'window_key' = ANY(%s) OR (payload->>'level' = 'story' AND status <> 'dead'))",
        (keys, conv, summarizer, keys)).fetchone()
    return {"produced": {"facts": int(facts), "summaries": made},
            "summaries": {"pending": int(jobs["pending"]), "failed": int(jobs["failed"])}}
