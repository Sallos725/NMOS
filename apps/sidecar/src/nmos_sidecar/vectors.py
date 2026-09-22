"""Phase 3 vector recall: revision chunk embeddings in pgvector, searched only within head membership."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

import psycopg

from .llm import Embedder

CHUNK_CHARS = 700
MAX_CHUNKS = 8


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


def process_embed(conn: psycopg.Connection, job: dict[str, Any], embedder: Embedder, model: str) -> str:
    revision_id = UUID(job["payload"]["revision_id"])
    with conn.transaction():
        row = conn.execute("SELECT content FROM source_revision WHERE id = %s", (revision_id,)).fetchone()
        done = conn.execute("SELECT 1 FROM revision_embedding WHERE source_revision_id = %s AND model = %s LIMIT 1",
                            (revision_id, model)).fetchone()
    if row is None:
        return "obsolete"
    if done:
        return "done"
    spans = chunks(row["content"])
    if not spans:
        return "done"
    vectors = embedder.embed([row["content"][s:e] for s, e in spans], timeout_s=60)
    with conn.transaction():
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO revision_embedding (source_revision_id, model, chunk, dim, text_start, text_end, embedding)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s::vector) ON CONFLICT DO NOTHING",
                [(revision_id, model, i, len(v), s, e, vector_literal(v)) for i, ((s, e), v) in enumerate(zip(spans, vectors))],
            )
    return "done"


def vector_candidates(conn: psycopg.Connection, head: UUID, query_vec: list[float], model: str, cut: int,
                      limit: int = 50) -> list[dict[str, Any]]:
    """Best chunk per eligible head revision by cosine similarity, most similar first."""
    return conn.execute(
        """
        WITH best AS (
            SELECT DISTINCT ON (sr.id) sr.id, am.position, so.host_logical_id, sr.content,
                   sr.metadata->>'role' AS role, sr.metadata->>'name' AS name,
                   1 - (re.embedding <=> %(q)s::vector) AS sim, re.text_start, re.text_end
            FROM active_membership am
            JOIN source_revision sr ON sr.id = am.source_revision_id
            JOIN source_object so ON so.id = sr.source_object_id
            JOIN revision_embedding re ON re.source_revision_id = sr.id AND re.model = %(model)s AND re.dim = %(dim)s
            WHERE am.commit_id = %(head)s AND sr.lifecycle = 'accepted' AND am.position > %(cut)s
              AND coalesce(sr.metadata->>'disabled', '') NOT IN ('true', 'allBefore')
              AND coalesce(sr.metadata->>'isComment', 'false') <> 'true'
            ORDER BY sr.id, re.embedding <=> %(q)s::vector
        )
        SELECT * FROM best ORDER BY sim DESC LIMIT %(limit)s
        """,
        {"q": vector_literal(query_vec), "model": model, "dim": len(query_vec), "head": head, "cut": cut,
         "limit": limit},
    ).fetchall()
