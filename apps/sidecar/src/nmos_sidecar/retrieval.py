"""Recall over the head membership: lexical (pg_trgm, D11) + optional vectors (Phase 3), fused with RRF.

Also assembles the packet sections: state (Phase 1), facts (Phase 2), excerpts.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from .facts import claim_line, fact_line, memory_view, relevant_facts, thread_line
from .ids import uuid7
from .ledger import find_conversation
from .llm import Embedder, LLMError
from .normtext import NORMALIZER_VERSION
from .packet import Excerpt, StateItem, clean_text, compile_packet, excerpt
from .state import current_state
from .threads import relevant_threads
from .vectors import vector_candidates

CANDIDATE_LIMIT = 50
# A query that matches more head messages than this is too broad to score (a character's name alone,
# a phrase every reply repeats): lexical recall abstains for it instead of scoring most of the chat
# (Track A, A3; docs/perf/scale.md). Vectors, state and facts still run.
BROAD_LIMIT = 200
RRF_K = 60
QWEN3_QUERY_INSTRUCTION = ("Instruct: Given a question or remark from a role-play chat, retrieve the earlier story "
                           "passage that answers or relates to it\nQuery: ")
# Candidates must match the user's message; the previous AI turn only breaks ties in ranking
# (as a filter it pulled in near-duplicate filler during manual testing).
AI_TIEBREAK_WEIGHT = 0.2


@dataclass(frozen=True)
class RecallOptions:
    top_k: int = 5
    threshold: float = 0.4
    rules_version: str = "none"
    facts_limit: int = 8
    events_limit: int = 3  # `event` facts among them (PHASE-7 Q4)
    threads_limit: int = 3  # open promises (PHASE-7 Q5)
    embedder: Embedder | None = None
    embed_projection: str = ""  # corpus vectors of this projection only (D20)
    extractor_key: str | None = None  # facts of this extractor generation only (D20)
    embed_timeout_ms: int = 300
    lexical_timeout_ms: int = 300
    vector_min_sim: float = 0.42
    query_prefix: str = ""


def query_prefix(model: str, setting: str) -> str:
    if setting == "auto":
        return QWEN3_QUERY_INSTRUCTION if "qwen3-embedding" in model.lower() else ""
    if setting in ("", "none"):
        return ""
    return f"Instruct: {setting}\nQuery: "


def _cut(conn: psycopg.Connection, head: UUID) -> int:
    """Messages at or before the last 'allBefore' cut are hidden from the model by the host (inv. 7)."""
    return conn.execute(
        "SELECT coalesce(max(am.position), -1) AS position FROM active_membership am"
        " JOIN source_revision sr ON sr.id = am.source_revision_id"
        " WHERE am.commit_id = %s AND sr.metadata->>'disabled' = 'allBefore'",
        (head,),
    ).fetchone()["position"]


# Settings applied to the lexical statement only (restored after it; a cancelled savepoint reverts them).
#  - pg_trgm.word_similarity_threshold: the `<%` bar (D11, D15).
#  - enable_seqscan / enable_indexscan off: the planner cannot estimate `<%` selectivity and otherwise
#    filters every head row with word_similarity instead of asking the trigram index (measured with
#    long messages: 82 ms at 1k and 818 ms at 10k, vs 1 ms / 0.05 ms through the index).
#  - statement_timeout: a safety net. Broad queries are stopped by BROAD_LIMIT first; before that
#    limit a query whose words occur in nearly every message scored every row (6 s at 10k).
_RESTORED = ("enable_seqscan", "enable_indexscan", "statement_timeout")  # the threshold is always set before use


def _lexical(conn: psycopg.Connection, head: UUID, query: str, previous_ai: str, cut: int,
             threshold: float, timeout_ms: int) -> tuple[list[dict[str, Any]], str]:
    """Lexical candidates over the normalized projection (#9) and the trace mode: "on", "too_broad"
    (more than BROAD_LIMIT matches) or "timeout". Recall abstains from lexical candidates in the last two."""
    try:
        with conn.transaction():  # savepoint: a cancelled statement does not abort the request
            previous = conn.execute("SELECT " + ", ".join(f"current_setting('{k}') AS \"{k}\""
                                                          for k in _RESTORED)).fetchone()
            wanted = {"pg_trgm.word_similarity_threshold": str(threshold), "enable_seqscan": "off",
                      "enable_indexscan": "off", "statement_timeout": str(timeout_ms)}
            _apply(conn, wanted)
            matches = _lexical_matches(conn, head, query, cut, BROAD_LIMIT + 1)
            rows = _lexical_candidates(conn, head, matches, query, previous_ai) if len(matches) <= BROAD_LIMIT else None
            _apply(conn, dict(previous))
            return (rows, "on") if rows is not None else ([], "too_broad")
    except psycopg.errors.QueryCanceled:
        return [], "timeout"


def _apply(conn: psycopg.Connection, settings: dict[str, str]) -> None:
    conn.execute("SELECT " + ", ".join("set_config(%s, %s, true)" for _ in settings),
                 [x for kv in settings.items() for x in kv])


def _lexical_matches(conn: psycopg.Connection, head: UUID, query: str, cut: int, limit: int) -> list[UUID]:
    """Active head revisions the query matches (`<%`), at most `limit`: the statement stops there, so a
    broad query costs about `limit` similarity checks instead of one per message."""
    return [r["id"] for r in conn.execute(
        """
        SELECT sr.id
        FROM active_membership am
        JOIN source_revision sr ON sr.id = am.source_revision_id
        JOIN revision_text rt ON rt.source_revision_id = sr.id AND rt.normalizer = %(norm)s
        WHERE am.commit_id = %(head)s
          AND sr.lifecycle = 'accepted'
          AND am.position > %(cut)s
          AND coalesce(sr.metadata->>'disabled', '') NOT IN ('true', 'allBefore')
          AND coalesce(sr.metadata->>'isComment', 'false') <> 'true'
          AND %(q)s <%% rt.clean_content
        LIMIT %(limit)s
        """,
        {"head": head, "q": query, "cut": cut, "limit": limit, "norm": NORMALIZER_VERSION},
    ).fetchall()]


def _lexical_candidates(conn: psycopg.Connection, head: UUID, ids: list[UUID], query: str,
                        previous_ai: str) -> list[dict[str, Any]]:
    """Score the matched revisions: the user's message, with the previous AI turn as a tiebreak."""
    if not ids:
        return []
    return conn.execute(
        """
        SELECT sr.id, am.position, so.host_logical_id, rt.clean_content AS clean, sr.metadata->>'role' AS role,
               sr.metadata->>'name' AS name, s.user_score,
               s.user_score + %(w)s * CASE WHEN %(ai)s = '' THEN 0 ELSE word_similarity(%(ai)s, rt.clean_content) END AS score
        FROM active_membership am
        JOIN source_revision sr ON sr.id = am.source_revision_id
        JOIN source_object so ON so.id = sr.source_object_id
        JOIN revision_text rt ON rt.source_revision_id = sr.id AND rt.normalizer = %(norm)s
        CROSS JOIN LATERAL (SELECT word_similarity(%(q)s, rt.clean_content) AS user_score) s
        WHERE am.commit_id = %(head)s AND sr.id = ANY(%(ids)s)
        ORDER BY score DESC, am.position DESC
        LIMIT %(limit)s
        """,
        {"head": head, "ids": ids, "q": query, "ai": previous_ai, "w": AI_TIEBREAK_WEIGHT, "limit": CANDIDATE_LIMIT,
         "norm": NORMALIZER_VERSION},
    ).fetchall()


def fuse(lexical: list[dict[str, Any]], vector: list[dict[str, Any]], threshold: float,
         min_sim: float) -> list[dict[str, Any]]:
    """Reciprocal-rank fusion with abstention: a candidate needs a lexical or a vector signal above its bar."""
    merged: dict[Any, dict[str, Any]] = {}
    for rank, row in enumerate(lexical):
        item = merged.setdefault(row["id"], {**row, "sim": None, "rrf": 0.0})
        item["rrf"] += 1 / (RRF_K + rank + 1)
    for rank, row in enumerate(vector):
        item = merged.setdefault(row["id"], {**row, "user_score": 0.0, "score": 0.0, "rrf": 0.0})
        item["sim"] = float(row["sim"])
        item["text_start"], item["text_end"] = row["text_start"], row["text_end"]
        item["rrf"] += 1 / (RRF_K + rank + 1)
    kept = [m for m in merged.values()
            if float(m.get("user_score") or 0) >= threshold or (m.get("sim") is not None and m["sim"] >= min_sim)]
    kept.sort(key=lambda m: (m["rrf"], m["position"]), reverse=True)
    return kept


def retrieve(conn: psycopg.Connection, request: Any, options: RecallOptions) -> dict[str, Any]:
    started = time.perf_counter()
    conv = find_conversation(conn, request.host, request.chat_id)
    if conv is None or conv.head_commit_id is None:
        return {"freshness": "unknown_conversation", "trace_id": None, "text": "", "tokens": 0, "count": 0}
    head = conv.head_commit_id
    fresh = (request.active_commit is None or request.active_commit == head) and (
        request.manifest_hash is None or request.manifest_hash == conv.head_manifest_hash
    )
    # The query side is normalized like the corpus: reasoning blocks in the previous AI turn must not
    # steer lexical scores, fact relevance or excerpt focus either.
    query = clean_text(request.query or "")
    previous_ai = clean_text(request.previous_ai or "")
    timings: dict[str, float] = {}
    vector_note = "off"
    lexical_note = "off"
    lexical: list[dict[str, Any]] = []
    vector: list[dict[str, Any]] = []
    if fresh and query.strip():
        cut = _cut(conn, head)
        lexical, lexical_note = _lexical(conn, head, query, previous_ai, cut, options.threshold,
                                         options.lexical_timeout_ms)
        timings["lexical"] = round((time.perf_counter() - started) * 1000, 2)
        if options.embedder is not None:
            t0 = time.perf_counter()
            try:
                (qvec,) = options.embedder.embed([options.query_prefix + query],
                                                 timeout_s=options.embed_timeout_ms / 1000)
                timings["embed"] = round((time.perf_counter() - t0) * 1000, 2)
                vector = vector_candidates(conn, head, qvec, options.embed_projection, cut, CANDIDATE_LIMIT)
                timings["vector"] = round((time.perf_counter() - t0) * 1000 - timings["embed"], 2)
                vector_note = "on"
            except (LLMError, ValueError) as exc:  # fail open to lexical-only
                vector_note = f"fallback: {exc}"[:200]

    in_context = set(request.in_context_ids)
    candidates = fuse(lexical, vector, options.threshold, options.vector_min_sim)
    excluded = [c for c in candidates if c["host_logical_id"] in in_context]
    eligible = [c for c in candidates if c["host_logical_id"] not in in_context][: options.top_k]
    focus = f"{query} {previous_ai}"
    ranked = [
        Excerpt(
            turn=c["position"],
            speaker=c["name"] or ("user" if c["role"] == "user" else "character"),
            text=excerpt(c["clean"] if c.get("user_score") else c["clean"][c["text_start"]:c["text_end"]], focus),
            score=float(c["rrf"]),
            revision_id=str(c["id"]),
        )
        for c in eligible
    ]
    state_items: list[StateItem] = []
    if fresh and options.rules_version != "none":
        state_items = [StateItem(key=r["key"], value=r["value"], turn=r["position"])
                       for r in current_state(conn, head, options.rules_version)
                       if r["host_logical_id"] not in in_context]
        # Sim bots track many characters: state of characters mentioned right now gets the budget first.
        now_text = f"{query} {previous_ai}"
        state_items.sort(key=lambda i: ("." in i.key and i.key.split(".", 1)[0] in now_text), reverse=True)
    fact_lines: list[str] = []
    thread_lines: list[str] = []
    view = memory_view(conn, head, options.extractor_key) if fresh and (options.facts_limit > 0
                                                                        or options.threads_limit > 0) else None
    persona = view["resolution"].persona_names if view is not None and view["resolution"] else frozenset()
    if view is not None and options.threads_limit > 0:
        thread_lines = [thread_line(t) for t in relevant_threads(view["threads"], query, previous_ai, in_context,
                                                                 options.threads_limit, persona)]
    if view is not None and options.facts_limit > 0:
        facts = relevant_facts(view["facts"], query, previous_ai, in_context, options.facts_limit,
                               options.events_limit, persona)
        # Claims after facts, so the budget serves narration first (ADR 0013).
        claims = relevant_facts(view["claims"], query, previous_ai, in_context, max(1, options.facts_limit // 2),
                                persona=persona)
        fact_lines = [fact_line(f) for f in facts] + [claim_line(c) for c in claims]
    text, tokens, chosen = compile_packet(ranked, request.budget_tokens, state=state_items, facts=fact_lines,
                                         threads=thread_lines)
    timings["sidecar_total"] = round((time.perf_counter() - started) * 1000, 2)

    def brief(c: dict[str, Any]) -> dict[str, Any]:
        return {"revision_id": str(c["id"]), "position": c["position"], "host_logical_id": c["host_logical_id"],
                "score": round(float(c.get("score") or 0), 4), "user_score": round(float(c.get("user_score") or 0), 4),
                "sim": None if c.get("sim") is None else round(float(c["sim"]), 4),
                "rrf": round(float(c.get("rrf") or 0), 5)}

    trace_id: UUID = uuid7()
    conn.execute(
        "INSERT INTO retrieval_trace (id, conversation_id, commit_id, query, candidates, selected, excluded_in_context,"
        " token_estimate, latency_ms, freshness) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            trace_id, conv.id, head, query,
            Jsonb([brief(c) for c in candidates]),
            Jsonb([{"revision_id": e.revision_id, "turn": e.turn, "score": round(e.score, 5)} for e in chosen]),
            Jsonb([brief(c) for c in excluded]),
            tokens,
            Jsonb({**timings, "lexical_mode": lexical_note, "vector_mode": vector_note, "state_items": len(state_items), "facts": len(fact_lines), "threads": len(thread_lines),
                   "embedding_projection": options.embed_projection[:20] if options.embedder else None,
                   "extractor": (options.extractor_key or "")[:20] or None,
                   **{f"client_{k}": v for k, v in request.client_timings_ms.items()}}),
            "fresh" if fresh else "stale",
        ),
    )
    return {"freshness": "fresh" if fresh else "stale", "trace_id": trace_id, "text": text, "tokens": tokens,
            "count": len(chosen)}
