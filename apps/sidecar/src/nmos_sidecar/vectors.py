"""Phase 3 vector recall: revision chunk embeddings in pgvector, searched only within head membership.

Vectors belong to an embedding projection (D20): endpoint, model, normalizer, chunker and document
profile. Query vectors are only compared with corpus vectors of the same projection.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

import psycopg

from . import generations, normtext
from .config import Settings
from .extraction import ELIGIBLE, REQUEUE
from .generations import Generation
from .llm import Embedder

CHUNK_CHARS = 700
MAX_CHUNKS = 8
CHUNKER_VERSION = "chunk-v1"  # bump when chunks() can cut differently
DOCUMENT_PROFILE = "plain"  # documents are embedded without an instruction prefix
RECENT_PRIORITY, HISTORY_PRIORITY = 200, 950


def projection(settings: Settings) -> Generation | None:
    """The corpus embedding projection the settings describe (credentials excluded), or None when off."""
    if not (settings.embed_url and settings.embed_model):
        return None
    return generations.make(
        "embed", settings.embed_url, settings.embed_model, normalizer=normtext.NORMALIZER_VERSION,
        chunker=CHUNKER_VERSION, chunk_chars=CHUNK_CHARS, max_chunks=MAX_CHUNKS, document_profile=DOCUMENT_PROFILE,
    )


def chunks(text: str, size: int = CHUNK_CHARS) -> list[tuple[int, int]]:
    """(start, end) spans of at most `size` chars, cut at paragraph/sentence boundaries when possible."""
    spans: list[tuple[int, int]] = []
    start, n = 0, len(text)
    while start < n and len(spans) < MAX_CHUNKS:
        end = min(n, start + size)
        if end < n:
            window = text[start:end]
            cut = max(window.rfind("\n"), max((m.end() for m in re.finditer(r"[.!?。！？…]\s", window)), default=-1))
            if cut > size // 3:
                end = start + cut
        if text[start:end].strip():
            spans.append((start, end))
        start = end
    return spans


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.6g}" for v in values) + "]"


def process_embed(conn: psycopg.Connection, job: dict[str, Any], embedder: Embedder, gen: Generation) -> str:
    if job["payload"].get("generation") != gen.key:
        # claim() never hands a handler another projection's job; refuse rather than mix spaces.
        raise ValueError(f"job generation {job['payload'].get('generation')} is not handler generation {gen.key}")
    revision_id = UUID(job["payload"]["revision_id"])
    with conn.transaction():
        row = normtext.get(conn, revision_id)
        done = conn.execute("SELECT 1 FROM revision_embedding WHERE source_revision_id = %s AND projection = %s LIMIT 1",
                            (revision_id, gen.key)).fetchone()
    if row is None:
        return "obsolete"
    if done:
        return "done"
    text = row["clean_content"]  # spans index into the normalized text (retrieval slices the same way)
    spans = chunks(text)
    if not spans:
        return "done"
    # One chunk per request: Ollama serves embeddings in order, and a large batch here would delay the
    # request-path query embedding past its timeout (measured: 582 ms behind an 8-chunk batch vs ~25 ms).
    vectors = [embedder.embed([text[s:e]], timeout_s=60)[0] for s, e in spans]
    with conn.transaction():
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO revision_embedding (source_revision_id, projection, model, chunk, dim, text_start, text_end,"
                " embedding) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector) ON CONFLICT DO NOTHING",
                [(revision_id, gen.key, gen.model, i, len(v), s, e, vector_literal(v))
                 for i, ((s, e), v) in enumerate(zip(spans, vectors))],
            )
    return "done"


def vector_candidates(conn: psycopg.Connection, head: UUID, query_vec: list[float], projection_key: str, cut: int,
                      limit: int = 50) -> list[dict[str, Any]]:
    """Best chunk per eligible head revision by cosine similarity, most similar first."""
    return conn.execute(
        """
        WITH best AS (
            SELECT DISTINCT ON (sr.id) sr.id, am.position, so.host_logical_id, rt.clean_content AS clean,
                   sr.metadata->>'role' AS role, sr.metadata->>'name' AS name,
                   1 - (re.embedding <=> %(q)s::vector) AS sim, re.text_start, re.text_end
            FROM active_membership am
            JOIN source_revision sr ON sr.id = am.source_revision_id
            JOIN source_object so ON so.id = sr.source_object_id
            JOIN revision_text rt ON rt.source_revision_id = sr.id AND rt.normalizer = %(norm)s
            JOIN revision_embedding re ON re.source_revision_id = sr.id AND re.projection = %(projection)s
                                      AND re.dim = %(dim)s
            WHERE am.commit_id = %(head)s AND sr.lifecycle = 'accepted' AND am.position > %(cut)s
              AND coalesce(sr.metadata->>'disabled', '') NOT IN ('true', 'allBefore')
              AND coalesce(sr.metadata->>'isComment', 'false') <> 'true'
            ORDER BY sr.id, re.embedding <=> %(q)s::vector
        )
        SELECT * FROM best ORDER BY sim DESC LIMIT %(limit)s
        """,
        {"q": vector_literal(query_vec), "projection": projection_key, "dim": len(query_vec), "head": head, "cut": cut,
         "limit": limit, "norm": normtext.NORMALIZER_VERSION},
    ).fetchall()


def schedule_projection(conn: psycopg.Connection, key: str, backfill: int, conv: UUID | None = None,
                        history: bool = False) -> int:
    """Queue what the active projection is missing: the latest `backfill` eligible revisions of each chat,
    then (background priority) every older revision an earlier projection had embedded, or with
    `history` every older revision (per-chat "extract all history", D22). Idempotent."""
    with conn.transaction():
        conn.execute("UPDATE job SET status = 'obsolete', updated_at = now() WHERE kind = 'embed'"
                     " AND status = 'queued' AND payload->>'generation' IS DISTINCT FROM %s", (key,))
        return conn.execute(
            "WITH" + ELIGIBLE + """,
            revs AS (SELECT DISTINCT ON (e.conv, e.rid) e.conv, e.rid, e.position >= e.n - %(n)s AS recent
                     FROM elig e JOIN revision_text t ON t.source_revision_id = e.rid AND t.normalizer = %(norm)s
                     WHERE t.clean_chars > 0  -- nothing to embed
                     ORDER BY e.conv, e.rid, e.position DESC)
            INSERT INTO job (kind, dedupe_key, conversation_id, payload, priority)
            SELECT 'embed', 'embed:' || r.rid || ':' || %(key)s, r.conv,
                   jsonb_build_object('revision_id', r.rid::text, 'generation', %(key)s),
                   CASE WHEN r.recent THEN %(recent)s ELSE %(history)s END
            FROM revs r
            WHERE NOT EXISTS (SELECT 1 FROM revision_embedding x WHERE x.source_revision_id = r.rid
                                AND x.projection = %(key)s)
              AND (r.recent OR %(all)s OR EXISTS (SELECT 1 FROM revision_embedding x WHERE x.source_revision_id = r.rid
                                         AND x.projection <> %(key)s))
            """ + REQUEUE,
            {"conv": conv, "key": key, "n": backfill, "all": history, "recent": RECENT_PRIORITY,
             "history": HISTORY_PRIORITY, "norm": normtext.NORMALIZER_VERSION},
        ).rowcount


def coverage(conn: psycopg.Connection, key: str | None, conv: UUID | None = None) -> dict[UUID, dict[str, Any]]:
    """Per conversation: eligible head revisions embedded by the active projection, and how many of
    those only cover part of their normalized text (MAX_CHUNKS × CHUNK_CHARS, #13)."""
    rows = conn.execute(
        "WITH" + ELIGIBLE + """,
        revs AS (SELECT DISTINCT e.conv, e.rid FROM elig e
                 JOIN revision_text t ON t.source_revision_id = e.rid AND t.normalizer = %(norm)s
                 WHERE t.clean_chars > 0),
        emb AS (SELECT re.source_revision_id AS rid, max(re.text_end) AS covered FROM revision_embedding re
                WHERE re.projection = %(key)s AND re.source_revision_id IN (SELECT rid FROM revs)
                GROUP BY re.source_revision_id)
        SELECT r.conv,
               count(*) AS eligible,
               count(*) FILTER (WHERE emb.rid IS NOT NULL) AS embedded,
               count(*) FILTER (WHERE emb.rid IS NULL AND j.status IN ('queued', 'running')) AS pending,
               count(*) FILTER (WHERE emb.rid IS NULL AND j.status = 'dead') AS failed,
               count(*) FILTER (WHERE emb.covered < rt.clean_chars) AS partial
        FROM revs r
        LEFT JOIN emb ON emb.rid = r.rid
        LEFT JOIN revision_text rt ON rt.source_revision_id = r.rid AND rt.normalizer = %(norm)s
        LEFT JOIN job j ON j.dedupe_key = 'embed:' || r.rid || ':' || %(key)s
        GROUP BY r.conv
        """,
        {"conv": conv, "key": key or "", "norm": normtext.NORMALIZER_VERSION},
    ).fetchall()
    out = {}
    for r in rows:
        stats = {k: r[k] for k in ("eligible", "embedded", "pending", "failed", "partial")}
        stats["percent"] = round(100 * r["embedded"] / r["eligible"], 1) if r["eligible"] else 100.0
        stats["complete"] = r["embedded"] == r["eligible"] and r["partial"] == 0
        out[r["conv"]] = stats
    return out
