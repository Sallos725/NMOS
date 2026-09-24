"""Retention of superseded projections (O5, owner decision 2026-09-23; ADR 0015).

Keep what is costly to recreate, prune what is cheap. Superseded LLM extractions and their assertions
are kept for audit and rollback and are never touched here. Superseded embeddings and older
normalized text are deterministic re-derivations of the ledger, so they are dropped once the current
projection has replaced them:

- vectors of any embedding projection other than the active one (legacy ones included), for the
  revisions the active projection has embedded, in chats where it has restored every revision an
  older projection had covered and has no work pending;
- `revision_text` rows of other normalizers, for revisions that have a current-normalizer row.

Only rows the active projection replaced go. Vectors of revisions it did not embed (abandoned branches,
old edits, disabled messages) stay: retention of abandoned worldlines is still open (O5).
"""

from __future__ import annotations

import psycopg

from . import generations, normtext
from .extraction import ELIGIBLE

BATCH = 500  # revisions per delete transaction

# Chats the active projection fully covers (ADR 0006 §4 coverage: every eligible revision an older
# projection had embedded now has an active vector, and none of its jobs is queued or running) and
# that still hold superseded vectors of revisions it replaced.
_PRUNABLE_REVISIONS = "WITH" + ELIGIBLE + """,
    missing AS (
        SELECT DISTINCT e.conv FROM elig e
        JOIN revision_text t ON t.source_revision_id = e.rid AND t.normalizer = %(norm)s AND t.clean_chars > 0
        WHERE NOT EXISTS (SELECT 1 FROM revision_embedding x WHERE x.source_revision_id = e.rid
                            AND x.projection = %(key)s)
          AND EXISTS (SELECT 1 FROM revision_embedding x WHERE x.source_revision_id = e.rid
                        AND x.projection <> %(key)s)
    ),
    busy AS (
        SELECT DISTINCT conversation_id AS conv FROM job
        WHERE kind = 'embed' AND status IN ('queued', 'running') AND payload->>'generation' = %(key)s
    ),
    complete AS (
        SELECT h.conv FROM heads h
        WHERE h.conv NOT IN (SELECT conv FROM missing)
          AND h.conv NOT IN (SELECT conv FROM busy)
    )
    SELECT sr.id AS rid
    FROM source_object so
    JOIN source_revision sr ON sr.source_object_id = so.id
    WHERE so.conversation_id IN (SELECT conv FROM complete)
      AND EXISTS (SELECT 1 FROM revision_embedding cur WHERE cur.source_revision_id = sr.id
                    AND cur.projection = %(key)s)
      AND EXISTS (SELECT 1 FROM revision_embedding old WHERE old.source_revision_id = sr.id
                    AND old.projection <> %(key)s)
    LIMIT %(batch)s
"""


def prune_embeddings(conn: psycopg.Connection, batch: int = BATCH) -> int:
    """Delete superseded vectors the active embedding projection replaced. Returns rows deleted.

    Runs under the activation lock, so the active projection cannot change between the coverage check
    and the delete. Idempotent; nothing happens while no projection was ever activated.
    """
    total = 0
    while True:
        with conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(727002)")
            key = generations.active(conn, "embed")
            if key is None:
                return total
            rids = [r["rid"] for r in conn.execute(
                _PRUNABLE_REVISIONS,
                {"conv": None, "key": key, "norm": normtext.NORMALIZER_VERSION, "batch": batch},
            ).fetchall()]
            if rids:
                # The pruned work's finished jobs become obsolete, so switching back to that projection
                # revives them in place (the job key is unique across statuses) instead of skipping them.
                total += conn.execute(
                    "WITH gone AS (DELETE FROM revision_embedding WHERE source_revision_id = ANY(%(rids)s)"
                    "   AND projection <> %(key)s RETURNING source_revision_id, projection),"
                    " revive AS (UPDATE job SET status = 'obsolete', updated_at = now()"
                    "   WHERE kind = 'embed' AND status = 'done' AND dedupe_key IN"
                    "     (SELECT DISTINCT 'embed:' || source_revision_id || ':' || projection FROM gone))"
                    " SELECT count(*) AS n FROM gone",
                    {"rids": rids, "key": key},
                ).fetchone()["n"]
        if len(rids) < batch:
            return total


def prune_text(conn: psycopg.Connection, batch: int = BATCH) -> int:
    """Delete normalized text of other normalizers where the current normalizer's row exists."""
    total = 0
    while True:
        with conn.transaction():
            n = conn.execute(
                "DELETE FROM revision_text WHERE (source_revision_id, normalizer) IN ("
                " SELECT o.source_revision_id, o.normalizer FROM revision_text o"
                " WHERE o.normalizer <> %(norm)s AND EXISTS (SELECT 1 FROM revision_text c"
                "   WHERE c.source_revision_id = o.source_revision_id AND c.normalizer = %(norm)s)"
                " LIMIT %(batch)s)",
                {"norm": normtext.NORMALIZER_VERSION, "batch": batch},
            ).rowcount
        total += n
        if n < batch:
            return total
