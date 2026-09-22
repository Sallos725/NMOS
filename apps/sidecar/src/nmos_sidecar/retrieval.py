"""Raw lexical recall over the head membership (Phase 0: pg_trgm only, D11)."""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from .ids import uuid7
from .ledger import find_conversation
from .packet import Excerpt, StateItem, compile_packet, excerpt
from .state import current_state

CANDIDATE_LIMIT = 50
# Candidates must match the user's message; the previous AI turn only breaks ties in ranking
# (as a filter it pulled in near-duplicate filler during manual testing).
AI_TIEBREAK_WEIGHT = 0.2


def retrieve(conn: psycopg.Connection, request: Any, top_k: int, threshold: float,
             rules_version: str = "none") -> dict[str, Any]:
    started = time.perf_counter()
    conv = find_conversation(conn, request.host, request.chat_id)
    if conv is None or conv.head_commit_id is None:
        return {"freshness": "unknown_conversation", "trace_id": None, "text": "", "tokens": 0, "count": 0}

    fresh = (request.active_commit is None or request.active_commit == conv.head_commit_id) and (
        request.manifest_hash is None or request.manifest_hash == conv.head_manifest_hash
    )
    query = request.query or ""
    previous_ai = request.previous_ai or ""
    rows: list[dict[str, Any]] = []
    if fresh and query.strip():
        # Messages at or before the last 'allBefore' cut are hidden from the model by the host (inv. 7).
        cut = conn.execute(
            "SELECT coalesce(max(am.position), -1) AS position FROM active_membership am"
            " JOIN source_revision sr ON sr.id = am.source_revision_id"
            " WHERE am.commit_id = %s AND sr.metadata->>'disabled' = 'allBefore'",
            (conv.head_commit_id,),
        ).fetchone()["position"]
        # `<%` applies pg_trgm.word_similarity_threshold and can use the trigram GIN index (D11).
        conn.execute("SELECT set_config('pg_trgm.word_similarity_threshold', %s, true)", (str(threshold),))
        rows = conn.execute(
            """
            SELECT sr.id, am.position, so.host_logical_id, sr.content, sr.metadata->>'role' AS role,
                   sr.metadata->>'name' AS name, s.user_score,
                   s.user_score + %(w)s * CASE WHEN %(ai)s = '' THEN 0 ELSE word_similarity(%(ai)s, sr.content) END AS score
            FROM active_membership am
            JOIN source_revision sr ON sr.id = am.source_revision_id
            JOIN source_object so ON so.id = sr.source_object_id
            CROSS JOIN LATERAL (SELECT word_similarity(%(q)s, sr.content) AS user_score) s
            WHERE am.commit_id = %(head)s
              AND sr.lifecycle = 'accepted'
              AND am.position > %(cut)s
              AND coalesce(sr.metadata->>'disabled', '') NOT IN ('true', 'allBefore')
              AND coalesce(sr.metadata->>'isComment', 'false') <> 'true'
              AND %(q)s <%% sr.content
            ORDER BY score DESC, am.position DESC
            LIMIT %(limit)s
            """,
            {"head": conv.head_commit_id, "q": query, "ai": previous_ai, "w": AI_TIEBREAK_WEIGHT,
             "cut": cut, "limit": CANDIDATE_LIMIT},
        ).fetchall()
    db_ms = (time.perf_counter() - started) * 1000

    in_context = set(request.in_context_ids)
    candidates = [r for r in rows if r["user_score"] >= threshold]
    excluded = [r for r in candidates if r["host_logical_id"] in in_context]
    eligible = [r for r in candidates if r["host_logical_id"] not in in_context][:top_k]
    ranked = [
        Excerpt(
            turn=r["position"],
            speaker=r["name"] or ("user" if r["role"] == "user" else "character"),
            text=excerpt(r["content"], f"{query} {previous_ai}"),
            score=float(r["score"]),
            revision_id=str(r["id"]),
        )
        for r in eligible
    ]
    state_items: list[StateItem] = []
    if fresh and rules_version != "none":
        state_items = [StateItem(key=r["key"], value=r["value"], turn=r["position"])
                       for r in current_state(conn, conv.head_commit_id, rules_version)
                       if r["host_logical_id"] not in in_context]
    text, tokens, chosen = compile_packet(ranked, request.budget_tokens, state=state_items)
    total_ms = (time.perf_counter() - started) * 1000

    trace_id: UUID = uuid7()
    brief = lambda r: {"revision_id": str(r["id"]), "position": r["position"], "host_logical_id": r["host_logical_id"],  # noqa: E731
                       "score": round(float(r["score"]), 4), "user_score": round(float(r["user_score"]), 4)}
    conn.execute(
        "INSERT INTO retrieval_trace (id, conversation_id, commit_id, query, candidates, selected, excluded_in_context,"
        " token_estimate, latency_ms, freshness) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            trace_id, conv.id, conv.head_commit_id, query,
            Jsonb([brief(r) for r in rows]),
            Jsonb([{"revision_id": e.revision_id, "turn": e.turn, "score": round(e.score, 4)} for e in chosen]),
            Jsonb([brief(r) for r in excluded]),
            tokens,
            Jsonb({"sidecar_db": round(db_ms, 2), "sidecar_total": round(total_ms, 2),
                   **{f"client_{k}": v for k, v in request.client_timings_ms.items()}}),
            "fresh" if fresh else "stale",
        ),
    )
    return {"freshness": "fresh" if fresh else "stale", "trace_id": trace_id, "text": text, "tokens": tokens, "count": len(chosen)}
