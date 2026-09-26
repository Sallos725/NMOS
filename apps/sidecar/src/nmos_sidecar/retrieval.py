"""Recall over the head membership: lexical (pg_trgm, D11) + optional vectors (Phase 3), fused with RRF.

Also assembles the packet sections: state (Phase 1), facts (Phase 2), excerpts.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from .facts import STANDING, claim_entry, fact_entry, memory_view, relevant_facts, thread_entry
from .ids import uuid7
from .ledger import find_conversation
from .llm import Embedder, LLMError
from .normtext import NORMALIZER_VERSION
from .packet import DEFAULT_POLICY, Excerpt, Line, StateItem, clean_text, compile_lines, excerpt, kept_counts
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
    policy: str = DEFAULT_POLICY  # packet compiler (ADR 0027)


# What a trace records of its RecallOptions, so a replay compiles with the same ones (ADR 0027).
RECORDED = ("top_k", "threshold", "facts_limit", "events_limit", "threads_limit", "vector_min_sim", "query_prefix",
            "embed_timeout_ms", "lexical_timeout_ms")


def recorded_options(options: RecallOptions) -> dict[str, Any]:
    return {k: getattr(options, k) for k in RECORDED}


def query_prefix(model: str, setting: str) -> str:
    if setting == "auto":
        return QWEN3_QUERY_INSTRUCTION if "qwen3-embedding" in model.lower() else ""
    if setting in ("", "none"):
        return ""
    return f"Instruct: {setting}\nQuery: "


def _cut(conn: psycopg.Connection, head: UUID, upto: int | None = None) -> int:
    """Messages at or before the last 'allBefore' cut are hidden from the model by the host (inv. 7)."""
    return conn.execute(
        "SELECT coalesce(max(am.position), -1) AS position FROM active_membership am"
        " JOIN source_revision sr ON sr.id = am.source_revision_id"
        " WHERE am.commit_id = %s AND sr.metadata->>'disabled' = 'allBefore' AND am.position <= %s",
        (head, 2**31 - 1 if upto is None else upto),
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
             threshold: float, timeout_ms: int, upto: int | None = None) -> tuple[list[dict[str, Any]], str]:
    """Lexical candidates over the normalized projection (#9) and the trace mode: "on", "too_broad"
    (more than BROAD_LIMIT matches) or "timeout". Recall abstains from lexical candidates in the last two."""
    try:
        with conn.transaction():  # savepoint: a cancelled statement does not abort the request
            previous = conn.execute("SELECT " + ", ".join(f"current_setting('{k}') AS \"{k}\""
                                                          for k in _RESTORED)).fetchone()
            wanted = {"pg_trgm.word_similarity_threshold": str(threshold), "enable_seqscan": "off",
                      "enable_indexscan": "off", "statement_timeout": str(timeout_ms)}
            _apply(conn, wanted)
            matches = _lexical_matches(conn, head, query, cut, BROAD_LIMIT + 1, upto)
            rows = _lexical_candidates(conn, head, matches, query, previous_ai) if len(matches) <= BROAD_LIMIT else None
            _apply(conn, dict(previous))
            return (rows, "on") if rows is not None else ([], "too_broad")
    except psycopg.errors.QueryCanceled:
        return [], "timeout"


def _apply(conn: psycopg.Connection, settings: dict[str, str]) -> None:
    conn.execute("SELECT " + ", ".join("set_config(%s, %s, true)" for _ in settings),
                 [x for kv in settings.items() for x in kv])


def _lexical_matches(conn: psycopg.Connection, head: UUID, query: str, cut: int, limit: int,
                     upto: int | None = None) -> list[UUID]:
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
          AND am.position > %(cut)s AND am.position <= %(upto)s
          AND coalesce(sr.metadata->>'disabled', '') NOT IN ('true', 'allBefore')
          AND coalesce(sr.metadata->>'isComment', 'false') <> 'true'
          AND %(q)s <%% rt.clean_content
        LIMIT %(limit)s
        """,
        {"head": head, "q": query, "cut": cut, "limit": limit, "norm": NORMALIZER_VERSION,
         "upto": 2**31 - 1 if upto is None else upto},
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


@dataclass
class Gathered:
    """Everything a request offers the packet, before the budget (ADR 0027)."""
    ranked: list[Excerpt] = field(default_factory=list)
    state: list[StateItem] = field(default_factory=list)
    threads: list[Line] = field(default_factory=list)
    lead: list[Line] = field(default_factory=list)  # how the cast stand with each other (ADR 0026)
    facts: list[Line] = field(default_factory=list)  # other facts, then claims
    candidates: list[dict[str, Any]] = field(default_factory=list)
    excluded: list[dict[str, Any]] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    lexical_note: str = "off"
    vector_note: str = "off"


def gather(conn: psycopg.Connection, head: UUID, query: str, previous_ai: str, in_context: set[str],
           options: RecallOptions, upto: int | None = None, known_at: datetime | None = None) -> Gathered:
    """Candidates for one request, already normalized (`clean_text`). `upto` and `known_at` gather them as
    of an earlier request: the head up to that position, and what NMOS had derived by that time."""
    started = time.perf_counter()
    g = Gathered()
    # The head's last message is always in the prompt (the host sends the latest message; D13 injects
    # only when it is there), whether or not the plugin could anchor it: it skips messages shorter than
    # 16 characters, so a short first message was recalled as memory of itself (seen in the Phase 9
    # real-host smoke, docs/perf/phase9-packets.md).
    if (last := _head_last(conn, head, upto)) is not None:
        in_context = in_context | {last}
    lexical: list[dict[str, Any]] = []
    vector: list[dict[str, Any]] = []
    if query.strip():
        cut = _cut(conn, head, upto)
        lexical, g.lexical_note = _lexical(conn, head, query, previous_ai, cut, options.threshold,
                                           options.lexical_timeout_ms, upto)
        g.timings["lexical"] = round((time.perf_counter() - started) * 1000, 2)
        if options.embedder is not None:
            t0 = time.perf_counter()
            try:
                (qvec,) = options.embedder.embed([options.query_prefix + query],
                                                 timeout_s=options.embed_timeout_ms / 1000)
                g.timings["embed"] = round((time.perf_counter() - t0) * 1000, 2)
                vector = vector_candidates(conn, head, qvec, options.embed_projection, cut, CANDIDATE_LIMIT,
                                           upto, known_at)
                g.timings["vector"] = round((time.perf_counter() - t0) * 1000 - g.timings["embed"], 2)
                g.vector_note = "on"
            except (LLMError, ValueError) as exc:  # fail open to lexical-only
                g.vector_note = f"fallback: {exc}"[:200]
    g.candidates = fuse(lexical, vector, options.threshold, options.vector_min_sim)
    g.excluded = [c for c in g.candidates if c["host_logical_id"] in in_context]
    eligible = [c for c in g.candidates if c["host_logical_id"] not in in_context][: options.top_k]
    focus = f"{query} {previous_ai}"
    for c in eligible:
        clean = c["clean"] if c.get("user_score") else c["clean"][c["text_start"]:c["text_end"]]
        g.ranked.append(Excerpt(turn=c["position"], speaker=c["name"] or ("user" if c["role"] == "user" else "character"),
                                text=excerpt(clean, focus), score=float(c["rrf"]), revision_id=str(c["id"]),
                                short=excerpt(clean, focus, window=1)))
    if options.rules_version != "none":
        g.state = [StateItem(key=r["key"], value=r["value"], turn=r["position"])
                   for r in current_state(conn, head, options.rules_version, upto)
                   if r["host_logical_id"] not in in_context]
        # Sim bots track many characters: state of characters mentioned right now gets the budget first.
        g.state.sort(key=lambda i: ("." in i.key and i.key.split(".", 1)[0] in focus), reverse=True)
    if options.facts_limit > 0 or options.threads_limit > 0:
        view = memory_view(conn, head, options.extractor_key, upto, known_at)
        persona = view["resolution"].persona_names if view["resolution"] else frozenset()
        if options.threads_limit > 0:
            g.threads = [thread_entry(t) for t in relevant_threads(view["threads"], query, previous_ai, in_context,
                                                                  options.threads_limit, persona)]
        if options.facts_limit > 0:
            facts = relevant_facts(view["facts"], query, previous_ai, in_context, options.facts_limit,
                                   options.events_limit, persona)
            # Claims after facts, so the budget serves narration first (ADR 0013).
            claims = relevant_facts(view["claims"], query, previous_ai, in_context, max(1, options.facts_limit // 2),
                                    persona=persona)
            # How the cast stand with each other takes the budget before threads (ADR 0026).
            g.lead = [fact_entry(f) for f in facts if f["predicate"] in STANDING]
            g.facts = [fact_entry(f) for f in facts if f["predicate"] not in STANDING] + [claim_entry(c) for c in claims]
    return g


def _head_end(conn: psycopg.Connection, head: UUID) -> int | None:
    """The last position of the head: the user's message a request answers."""
    return conn.execute("SELECT max(position) AS p FROM active_membership WHERE commit_id = %s", (head,)).fetchone()["p"]


def _head_last(conn: psycopg.Connection, head: UUID, upto: int | None) -> str | None:
    """Host id of the head's last message (as of `upto`)."""
    row = conn.execute(
        "SELECT so.host_logical_id FROM active_membership am JOIN source_revision sr ON sr.id = am.source_revision_id"
        " JOIN source_object so ON so.id = sr.source_object_id WHERE am.commit_id = %s AND am.position <= %s"
        " ORDER BY am.position DESC LIMIT 1", (head, 2**31 - 1 if upto is None else upto)).fetchone()
    return row["host_logical_id"] if row else None


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
    in_context = set(request.in_context_ids)
    g = gather(conn, head, query, previous_ai, in_context, options) if fresh else Gathered()
    compiled = compile_lines(g.ranked, request.budget_tokens, state=g.state, threads=g.threads, facts=g.facts,
                             policy=options.policy, lead=g.lead)
    kept = kept_counts(compiled.ledger)
    timings = {**g.timings, "sidecar_total": round((time.perf_counter() - started) * 1000, 2)}

    def brief(c: dict[str, Any]) -> dict[str, Any]:
        return {"revision_id": str(c["id"]), "position": c["position"], "host_logical_id": c["host_logical_id"],
                "score": round(float(c.get("score") or 0), 4), "user_score": round(float(c.get("user_score") or 0), 4),
                "sim": None if c.get("sim") is None else round(float(c["sim"]), 4),
                "rrf": round(float(c.get("rrf") or 0), 5)}

    placed = [e for e in compiled.ledger if e["placed"]]
    trace_id: UUID = uuid7()
    conn.execute(
        "INSERT INTO retrieval_trace (id, conversation_id, commit_id, query, candidates, selected, excluded_in_context,"
        " token_estimate, latency_ms, freshness, policy, budget_tokens, upto_position, previous_ai, in_context,"
        " extractor_key, embed_projection, rules_version, recall_options, lines)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            trace_id, conv.id, head, query,
            Jsonb([brief(c) for c in g.candidates]),
            Jsonb([{"revision_id": e.revision_id, "turn": e.turn, "score": round(e.score, 5)} for e in compiled.excerpts]),
            Jsonb([brief(c) for c in g.excluded]),
            compiled.tokens,
            Jsonb({**timings, "lexical_mode": g.lexical_note, "vector_mode": g.vector_note,
                   "state_items": len(g.state), "facts": len(g.lead) + len(g.facts), "threads": len(g.threads),
                   "kept_state": kept["state"], "kept_facts": kept["facts"], "kept_threads": kept["threads"],
                   "placed": {k: sum(1 for e in placed if e["kind"] == k)
                              for k in ("state", "thread", "fact", "claim", "excerpt")},
                   "embedding_projection": options.embed_projection[:20] if options.embedder else None,
                   "extractor": (options.extractor_key or "")[:20] or None,
                   **{f"client_{k}": v for k, v in request.client_timings_ms.items()}}),
            "fresh" if fresh else "stale",
            options.policy, request.budget_tokens, _head_end(conn, head) if fresh else None, previous_ai,
            Jsonb(sorted(in_context)), options.extractor_key,
            options.embed_projection if options.embedder else None, options.rules_version,
            Jsonb(recorded_options(options)), Jsonb(compiled.ledger),
        ),
    )
    return {"freshness": "fresh" if fresh else "stale", "trace_id": trace_id, "text": compiled.text,
            "tokens": compiled.tokens, "count": len(compiled.excerpts)}
