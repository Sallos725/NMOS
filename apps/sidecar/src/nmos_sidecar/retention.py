"""Retention (O5): superseded projections (owner decision 2026-09-23; ADR 0015) and full-manifest host
observations (owner decision 2026-09-24; ADR 0018).

Keep what is costly to recreate, prune what is cheap. Superseded LLM extractions and their assertions
are kept for audit and rollback and are never touched here. Superseded embeddings and older
normalized text are deterministic re-derivations of the ledger, so they are dropped once the current
projection has replaced them:

- vectors of any embedding projection other than the active one (legacy ones included), for the
  revisions the active projection has embedded, in chats where it has restored every revision an
  older projection had covered and has no work pending;
- `revision_text` rows of other normalizers, for revisions that have a current-normalizer row.

Only rows the active projection replaced go. Vectors of revisions it did not embed (abandoned branches,
old edits, disabled messages) stay; everything else on abandoned worldlines is kept (O5, 2026-09-24).

Host observations are evidence and are never dropped. An edit, reroll, swipe or delete observes the whole
manifest (every row); `compact_observations` rewrites such an observation losslessly as the rows that
differ from the chat's previous full observation, and only after checking that they rebuild it exactly.
"""

from __future__ import annotations

import psycopg

from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

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


# --- host observations (ADR 0018) -------------------------------------------------------------------

CHECKPOINT_RATIO = 0.25  # an observation differing from its base in more rows than this stays full


def diff_rows(base: list[Any], rows: list[Any]) -> list[list[Any]]:
    """[index, row] for every row of `rows` that is not the same row at that index of `base`."""
    return [[i, row] for i, row in enumerate(rows) if i >= len(base) or base[i] != row]


def apply_diff(base: list[Any], length: int, changed: list[list[Any]]) -> list[Any]:
    rows = list(base[:length]) + [None] * max(0, length - len(base))
    for i, row in changed:
        rows[i] = row
    return rows


def observed_rows(conn: psycopg.Connection, observation_id: UUID) -> tuple[list[str], list[Any]] | None:
    """(columns, rows) of a full or compacted manifest observation; None for an appended tail (its rows
    are the observation named by `base_manifest_hash` plus `appended`) or an unknown id."""
    row = conn.execute("SELECT raw_manifest FROM host_observation WHERE id = %s", (observation_id,)).fetchone()
    if row is None:
        return None
    raw = row["raw_manifest"]
    if "entries" in raw:
        return raw["columns"], raw["entries"]
    if "base_observation" in raw:
        base = conn.execute("SELECT raw_manifest FROM host_observation WHERE id = %s",
                            (raw["base_observation"],)).fetchone()["raw_manifest"]
        return raw["columns"], apply_diff(base["entries"], raw["length"], raw["changed"])
    return None


def compact_observations(conn: psycopg.Connection, limit: int = 200) -> int:
    """Rewrite full-manifest observations as differences from the chat's base observation. Returns how
    many were rewritten (at most `limit` per call).

    Per chat, in id order, every full observation not yet decided is either kept full as the chat's next
    base (`observation_base`) or rewritten as `{base_observation, length, changed}` against the latest
    base before it. It stays full when it is the chat's first, when its columns differ from the base's,
    when more than CHECKPOINT_RATIO of its rows differ, or when the difference does not rebuild it
    exactly. A base is never rewritten, so rebuilding any observation reads at most two rows.
    """
    done = 0
    pending = conn.execute(
        "SELECT o.conversation_id AS conv, o.id FROM host_observation o"
        " WHERE o.kind = 'manifest' AND o.raw_manifest ? 'entries'"
        " AND NOT EXISTS (SELECT 1 FROM observation_base b WHERE b.observation_id = o.id)"
        " ORDER BY o.conversation_id, o.id").fetchall()
    base_id, base = None, None
    for row in pending:
        if done >= limit:
            break
        with conn.transaction():
            prior = conn.execute(
                "SELECT observation_id FROM observation_base WHERE conversation_id = %s AND observation_id < %s"
                " ORDER BY observation_id DESC LIMIT 1", (row["conv"], row["id"])).fetchone()
            raw = conn.execute("SELECT raw_manifest FROM host_observation WHERE id = %s FOR UPDATE",
                               (row["id"],)).fetchone()["raw_manifest"]
            if prior is None:
                keep = True
            else:
                if base_id != prior["observation_id"]:
                    base_id = prior["observation_id"]
                    base = conn.execute("SELECT raw_manifest FROM host_observation WHERE id = %s",
                                        (base_id,)).fetchone()["raw_manifest"]
                rows = raw["entries"]
                changed = diff_rows(base["entries"], rows)
                keep = (raw["columns"] != base["columns"] or len(changed) > CHECKPOINT_RATIO * max(1, len(rows))
                        or apply_diff(base["entries"], len(rows), changed) != rows)
            if keep:
                conn.execute("INSERT INTO observation_base (observation_id, conversation_id) VALUES (%s, %s)",
                             (row["id"], row["conv"]))
                continue
            compact = {k: v for k, v in raw.items() if k != "entries"}
            compact.update(base_observation=str(base_id), length=len(rows), changed=changed)
            conn.execute("UPDATE host_observation SET raw_manifest = %s WHERE id = %s", (Jsonb(compact), row["id"]))
            done += 1
    return done
