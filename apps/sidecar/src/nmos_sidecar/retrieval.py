"""Recall over the head membership: lexical (pg_trgm, D11) + optional vectors (Phase 3), fused with RRF.

Also assembles the packet sections: state (Phase 1), facts (Phase 2), excerpts.
"""

from __future__ import annotations

import dataclasses
import math
import re
import threading
import time
from collections.abc import Callable, Iterable
from concurrent.futures import Future
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from .entities import norm
from .facts import FIRST_CUE, HISTORY_CUE, LIVE, STANDING, WHY, claim_entry, fact_entry, memory_view, relevant_facts, thread_entry
from . import overuse, quotes, scene, spans, summaries, variants
from .ids import uuid7
from .ledger import find_conversation
from .llm import Embedder, LLMError
from .normtext import NORMALIZER_VERSION
from .packet import (ABOUT_POLICIES, BEFORE_POLICIES, CAST_POLICIES, CAUSE_POLICIES, CHANGE_POLICIES, CONTENTS,
                     QUOTE_POLICIES, UNEXTRACTED_POLICIES, REST_POLICIES, EXCERPT_FLOOR,
                     CUE_GROW_CHARS,
                     DEFAULT_POLICY, FILL_FACTS_MAX, GROW_POLICIES, SPAN_POLICIES, grown_excerpt,
                     MAX_EXCERPT_CHARS, MEMORY_KINDS, REPEATS, STORY_POLICIES, TURN_POLICIES, Compiled, Excerpt, Line,
                     StateItem, clean_text, compile_lines, cut_lines, excerpt, fill, fits_at, kept_counts, secret_line,
                     secret_text)
from .state import current_state
from .threads import relevant_threads, similarity
from .vectors import vector_candidates
from .keywords import keywords

CANDIDATE_LIMIT = 50
# A query that matches more head messages than this is too broad to score (a character's name alone,
# a phrase every reply repeats): lexical recall abstains for it instead of scoring most of the chat
# (Track A, A3; docs/perf/scale.md). Vectors, state and facts still run.
BROAD_LIMIT = 200
RRF_K = 60
# The keyword route (PHASE-18, ADR 0052): each keyword of the user's message (keywords.py) is looked up on its own at
# this word_similarity bar, near an exact match of the word. A keyword in more than BROAD_LIMIT head messages, or in
# more than half of them, names what every scene holds (a main character) and is dropped.
KEYWORD_THRESHOLD = 0.8
# Each keyword's lookup gets at most this long; a word that takes longer is as common as a dropped one (a two-syllable
# word's three trigrams can leave the index thousands of long messages to recheck), so it is dropped and the other
# keywords still run (measured at 10,000 messages: 2–3 ms for a rare word, 37 ms for one capped at 201 matches).
KEYWORD_SLICE_MS = 25
QWEN3_QUERY_INSTRUCTION = ("Instruct: Given a question or remark from a role-play chat, retrieve the earlier story "
                           "passage that answers or relates to it\nQuery: ")
# Candidates must match the user's message; the previous AI turn only breaks ties in ranking
# (as a filter it pulled in near-duplicate filler during manual testing).
AI_TIEBREAK_WEIGHT = 0.2
# The query embedding's own call runs this many times `embed_timeout_ms` (per network phase, as before): long enough
# to answer while recall reads and for the wait after them (QueryEmbedding), short enough that a call the request has
# given up on ends soon after, instead of holding the embedder for the next request (ADR 0061).
EMBED_CALL_FACTOR = 2
# A prefetched embedding (Prefetched, ADR 0061 item 7) is asked for at the sync, before its request exists: its call
# may run at least this long, since the request follows the sync by the sync's own time (0.3–2.5 s on a long chat,
# docs/perf/scale.md), and an entry no request took within PREFETCH_TTL_S is dropped.
PREFETCH_CALL_MIN_MS = 2000
PREFETCH_TTL_S = 60.0


class QueryEmbedding:
    """The query's embedding, asked for when recall starts and collected after its reads (ADR 0061, K34).

    Before, recall waited `embed_timeout_ms` for the embedding alone, after lexical recall and before every other read:
    an embedder slower than that (a remote one, or Ollama behind a proxy: 70 % of the owner's production requests)
    gave no vectors, and the request still paid the wait. Now the call runs on its own thread while lexical recall,
    the facts, threads, scene and summaries are read, and the request waits for it at most `embed_timeout_ms` after
    those reads: it never waits longer for the embedding than before, and the embedder gets the reads' time as well.
    (A request that now has vectors pays the vector search and a fuller packet, as one with vectors always did.) The
    call itself is bounded at EMBED_CALL_FACTOR × the timeout. The thread touches no database connection."""

    def __init__(self, embedder: Embedder, text: str, timeout_ms: int, call_timeout_ms: int | None = None):
        self.timeout_ms = timeout_ms
        self.call_timeout_ms = call_timeout_ms or EMBED_CALL_FACTOR * timeout_ms  # the call's own bound
        self.started = time.perf_counter()
        self.call_ms: float | None = None  # how long the embedder took, once it answered
        self._future: Future[list[float]] = Future()
        self._future.set_running_or_notify_cancel()
        self._thread = threading.Thread(target=self._run, args=(embedder, text), name="nmos-query-embedding",
                                        daemon=True)
        self._thread.start()

    def _run(self, embedder: Embedder, text: str) -> None:
        started = time.perf_counter()
        try:
            (vec,) = embedder.embed([text], timeout_s=self.call_timeout_ms / 1000)
        except BaseException as exc:  # noqa: BLE001 — re-raised to the waiter, which classifies it
            self._future.set_exception(exc)
            return
        self.call_ms = round((time.perf_counter() - started) * 1000, 2)
        self._future.set_result(vec)

    def failed(self) -> bool:
        """Whether the call has already ended in an error. A prefetched call that failed (the embedder down for the
        moment of the sync) is not given to its request: the request asks again, as one without a prefetch does."""
        return self._future.done() and self._future.exception() is not None

    def result(self) -> list[float]:
        """The vector, waiting at most `timeout_ms` from now. LLMError when it is not there by then (the thread's call
        ends on its own soon after; its answer is dropped), or when the call failed; a ValueError (an answer of the
        wrong shape) comes through as it did."""
        try:
            return self._future.result(timeout=self.timeout_ms / 1000)
        except TimeoutError as exc:
            raise LLMError(f"embedding not answered within {self.timeout_ms} ms after recall's reads") from exc


class Prefetched:
    """Query embeddings asked for before their request (ADR 0061 item 7). A sync whose bodies carry the chat's newest
    user message starts that message's embedding (`api.bodies`); the retrieve that follows the sync — the plugin sends
    the same text as its query — takes it instead of asking again, so the embedder has had the sync's time as well.
    Keyed by the projection (D20) and the exact text (prefix included); an entry keeps the embedder it was asked of and
    is given only to a request whose embedder is that object, since a settings save rebuilds the embedder
    (`api.rebuild`) and an entry asked of the old one is not the new one's (the old object's `id()` can be reused by
    the new one, so an id is no identity; Codex on #242). An entry whose call already failed is not given either (the
    request asks again; Codex on #244). An entry is taken once, and one no request took within PREFETCH_TTL_S is
    dropped. A replay never takes one (`gather`: `known_at` is set)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[tuple[str, str], tuple[QueryEmbedding, Embedder, float]] = {}

    def start(self, embedder: Embedder, projection: str, text: str, timeout_ms: int) -> QueryEmbedding:
        key = (projection, text)
        with self._lock:
            self._sweep()
            entry = self._entries.get(key)
            if entry is not None and entry[1] is embedder:  # the same text synced twice (a retry): one call
                return entry[0]
            pending = QueryEmbedding(embedder, text, timeout_ms,
                                     call_timeout_ms=max(EMBED_CALL_FACTOR * timeout_ms, PREFETCH_CALL_MIN_MS))
            self._entries[key] = (pending, embedder, time.monotonic())
            return pending

    def take(self, embedder: Embedder, projection: str, text: str) -> QueryEmbedding | None:
        with self._lock:
            self._sweep()
            entry = self._entries.pop((projection, text), None)
        if entry is None or entry[1] is not embedder:  # none, or asked of an embedder a settings save replaced
            return None
        if entry[0].failed():  # the sync's call failed: the request asks again rather than inherit the failure
            return None
        return entry[0]

    def _sweep(self) -> None:
        now = time.monotonic()
        for key in [k for k, (_, _, at) in self._entries.items() if now - at > PREFETCH_TTL_S]:
            del self._entries[key]
        while len(self._entries) > 64:  # requests that never came: the oldest go first
            del self._entries[min(self._entries, key=lambda k: self._entries[k][2])]


prefetched = Prefetched()


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
    rest_after: int = 2  # packet-v14: a supportive line rests after this many placements in a row (PHASE-34 Q2)
    vector_min_sim: float = 0.42
    query_prefix: str = ""
    policy: str = DEFAULT_POLICY  # packet compiler (ADR 0027)
    strict: bool = False  # this chat's memory mode (ADR 0035): withhold what only some of the scene know
    narrator: str | None = None  # this chat is told in this character's first person (ADR 0035)
    summarize_key: str | None = None  # summaries of this generation in <Story> (packet-v8, ADR 0043); None: off
    canon_key: str | None = None  # canon facts of this generation (ADR 0047); None: off
    lexical_keywords: bool = True  # the keyword route (ADR 0052); a trace that did not record it replays with it off
    first_cue: bool = True  # how it started, when the message asks (ADR 0056); a trace without it replays with it off
    history_marks: bool = True  # earlier versions only under marks that cover them (ADR 0038 amendment 1); same replay rule
    name_variants: bool = True  # a given name, a Hangul spelling of a romanized name (ADR 0058); same replay rule
    # packet-v11's tie-break anchor for the excerpt's best sentence (PHASE-27 Q1b, ADR 0063): "keywords", the question's
    # keywords alone — the question itself when it has none — (the prototype's; the default since step 3, measured: with
    # "focus" the forbidden total rose 93 → 96 over twelve sets, with "keywords" it fell to 87), or "focus", the question
    # and the previous reply (`packet-v10`'s, which ignores this option; `tools/eval_rp.py --anchor focus` for an
    # evaluation). Recorded; a trace without it replays with "focus", the anchor every request had before.
    excerpt_anchor: str = "keywords"
    excerpt_chars: int = MAX_EXCERPT_CHARS  # an excerpt's length at most; derived from the budget (`filled`), not recorded
    fill_facts: int = 0  # fact slots the budget adds, for facts kept from no one (`filled`, ADR 0049), not recorded


# What a trace records of its RecallOptions, so a replay compiles with the same ones (ADR 0027).
RECORDED = ("top_k", "threshold", "facts_limit", "events_limit", "threads_limit", "vector_min_sim", "query_prefix",
            "embed_timeout_ms", "lexical_timeout_ms", "strict", "narrator", "summarize_key", "canon_key",
            "lexical_keywords", "first_cue", "history_marks", "name_variants", "excerpt_anchor", "rest_after")
CAST_MAX = 4  # scene characters with a <Cast> group (PHASE-12 Q4)
CAST_GOALS, CAST_ITEMS = 2, 3
CAST_PREDICATES = ("located_in", "has_status", "feels_toward", "possesses")


def recorded_options(options: RecallOptions) -> dict[str, Any]:
    return {k: getattr(options, k) for k in RECORDED}


def filled(options: RecallOptions, budget: int) -> RecallOptions:
    """The recall a budget buys under the options' policy (packet-v9, ADR 0049): the configured excerpt count and each
    excerpt's length times `packet.fill`, and fact slots up to the fact limit times that factor (at most FILL_FACTS_MAX)
    in `fill_facts`: `gather` gives them only to facts kept from no one, so secrets and <Private> do not grow. A limit of
    0 stays 0. Every other limit, and every policy before packet-v9, is left as it is. A request records its configured
    limits, so its replay grows them again from the budget it compiles at."""
    f = fill(budget, options.policy)
    if f == 1.0:
        return options
    return dataclasses.replace(options, top_k=math.floor(options.top_k * f),
                               fill_facts=math.floor(options.facts_limit * min(f, FILL_FACTS_MAX)) - options.facts_limit,
                               excerpt_chars=math.floor(MAX_EXCERPT_CHARS * f))


def _grown(base: list[dict[str, Any]], ranked: list[dict[str, Any]], extra: int) -> list[dict[str, Any]]:
    """`base` (what the configured limit selects) and up to `extra` more from `ranked` (every candidate, best first):
    facts kept from no one and not events (packet-v9, ADR 0049): secrets, <Private> and events keep their limits.
    In ranked order."""
    if extra <= 0:
        return base
    chosen = {id(f) for f in base}
    more = [f for f in ranked if id(f) not in chosen and f.get("knowledge") != "limited" and not f.get("hidden_from")
            and f["predicate"] != "event"][:extra]
    order = {id(f): i for i, f in enumerate(ranked)}
    return sorted(base + more, key=lambda f: order.get(id(f), -1))


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


# The active head revisions a word or message matches (`<%`), at most `limit` (`_lexical_matches`). The matches are
# found through the trigram index first (`hit`, materialized), then kept if they are on the head: planned from the
# membership instead, the lookup checks every head message with word_similarity (40 ms instead of 5 at 146 messages,
# linear in the chat), and the planner chose that whenever its statistics did not hold the head yet: after a reroll,
# an edit or a deletion makes a new head commit (D4), until the next autoanalyze. It could also plan a known head
# through revision_text's primary key, checking every revision. `hit` has no other condition (the normalizer is checked
# after it), so the trigram index is its only way in with sequential scans off.
_MATCHES = """
    WITH hit AS MATERIALIZED (
        SELECT source_revision_id, normalizer FROM revision_text WHERE %(q)s <%% clean_content
    )
    SELECT sr.id
    FROM hit
    JOIN active_membership am ON am.source_revision_id = hit.source_revision_id
    JOIN source_revision sr ON sr.id = am.source_revision_id
    WHERE am.commit_id = %(head)s
      AND sr.lifecycle = 'accepted'
      AND am.position > %(cut)s AND am.position <= %(upto)s
      AND coalesce(sr.metadata->>'disabled', '') NOT IN ('true', 'allBefore')
      AND coalesce(sr.metadata->>'isComment', 'false') <> 'true'
      AND hit.normalizer = %(norm)s
    LIMIT %(limit)s
    """


def _matches_params(head: UUID, query: str, cut: int, limit: int, upto: int | None = None) -> dict[str, Any]:
    return {"head": head, "q": query, "cut": cut, "limit": limit, "norm": NORMALIZER_VERSION,
            "upto": 2**31 - 1 if upto is None else upto}


def _lexical_matches(conn: psycopg.Connection, head: UUID, query: str, cut: int, limit: int,
                     upto: int | None = None) -> list[UUID]:
    """Active head revisions the query matches (`<%`), at most `limit`: the statement stops there, after checking the
    trigram index's candidates up to that many head matches (candidates of other chats and earlier revisions are checked
    too, then left out), so a broad query is dropped by its slice or the timeout. Never prepared on the server: after
    five runs Postgres may plan a prepared statement without its parameters, and without the word it cannot tell that
    the trigram index is the narrow way in. Either slow plan took a keyword past its slice, which dropped it as if it
    were too common, and a replay could find what its request had not (ADR 0027)."""
    return [r["id"] for r in conn.execute(_MATCHES, _matches_params(head, query, cut, limit, upto),
                                          prepare=False).fetchall()]


def _lexical_candidates(conn: psycopg.Connection, head: UUID, ids: list[UUID], query: str,
                        previous_ai: str) -> list[dict[str, Any]]:
    """Score the matched revisions: the user's message, with the previous AI turn as a tiebreak."""
    if not ids:
        return []
    return conn.execute(
        """
        SELECT sr.id, am.position, am.turn, so.host_logical_id, rt.clean_content AS clean, sr.metadata->>'role' AS role,
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


def _keyword_lexical(conn: psycopg.Connection, head: UUID, words: list[str], cut: int, timeout_ms: int,
                     upto: int | None = None) -> tuple[list[dict[str, Any]], str]:
    """The keyword route (ADR 0052): messages holding the message's keywords, scored by the keywords' rarity
    (log of messages over matches, summed), best first, and the trace mode: "on", "none" (no keyword), "too_broad"
    (every keyword dropped as too common) or "timeout". All keywords share one budget of `timeout_ms`."""
    if not words:
        return [], "none"
    counted: list[int] = []

    def total() -> int:
        """The messages a keyword may be found in, counted as _lexical_matches filters them, once and only when a
        keyword matched (every revision has its normalized text, so that join is left out: 5–9 ms at 10,000)."""
        if not counted:
            counted.append(conn.execute(
                """
                SELECT count(*) AS n
                FROM active_membership am
                JOIN source_revision sr ON sr.id = am.source_revision_id
                WHERE am.commit_id = %(head)s AND sr.lifecycle = 'accepted'
                  AND am.position > %(cut)s AND am.position <= %(upto)s
                  AND coalesce(sr.metadata->>'disabled', '') NOT IN ('true', 'allBefore')
                  AND coalesce(sr.metadata->>'isComment', 'false') <> 'true'
                """, {"head": head, "cut": cut, "upto": 2**31 - 1 if upto is None else upto}).fetchone()["n"])
        return counted[0]

    deadline = time.perf_counter() + timeout_ms / 1000  # every statement of the route runs before it

    def within(most: float | None = None) -> None:
        """This connection's statement timeout: what is left of the route's budget (at most `most` ms)."""
        left = (deadline - time.perf_counter()) * 1000
        if left < 1:
            raise psycopg.errors.QueryCanceled()
        _apply(conn, {"statement_timeout": str(max(1, int(left if most is None else min(left, most))))})

    weights: dict[Any, float] = {}
    found = dropped = 0
    try:
        with conn.transaction():  # savepoint: a cancelled statement does not abort the request
            previous = conn.execute("SELECT " + ", ".join(f"current_setting('{k}') AS \"{k}\""
                                                          for k in _RESTORED)).fetchone()
            _apply(conn, {"pg_trgm.word_similarity_threshold": str(KEYWORD_THRESHOLD), "enable_seqscan": "off",
                          "enable_indexscan": "off"})
            for word in words:
                try:
                    with conn.transaction():  # a word past its slice is dropped; the others still run
                        within(KEYWORD_SLICE_MS)
                        ids = _lexical_matches(conn, head, word, cut, BROAD_LIMIT + 1, upto)
                except psycopg.errors.QueryCanceled:
                    if (deadline - time.perf_counter()) * 1000 < 1:
                        raise  # the route's budget, not the word's slice, ran out
                    found += 1
                    dropped += 1
                    continue
                if not ids:
                    continue
                found += 1
                within()
                n = total()
                if len(ids) > BROAD_LIMIT or len(ids) * 2 > n:
                    dropped += 1
                    continue
                weight = math.log(n / len(ids))  # at least log 2: a keyword in more than half is dropped above
                for i in ids:
                    weights[i] = weights.get(i, 0.0) + weight
            rows = []
            if weights:
                within()
                rows = conn.execute(
                    """
                    SELECT sr.id, am.position, am.turn, so.host_logical_id, rt.clean_content AS clean,
                           sr.metadata->>'role' AS role, sr.metadata->>'name' AS name
                    FROM active_membership am
                    JOIN source_revision sr ON sr.id = am.source_revision_id
                    JOIN source_object so ON so.id = sr.source_object_id
                    JOIN revision_text rt ON rt.source_revision_id = sr.id AND rt.normalizer = %(norm)s
                    WHERE am.commit_id = %(head)s AND sr.id = ANY(%(ids)s)
                    """, {"head": head, "ids": list(weights), "norm": NORMALIZER_VERSION}).fetchall()
            _apply(conn, dict(previous))
    except psycopg.errors.QueryCanceled:
        return [], "timeout"
    if not weights:
        return [], "too_broad" if found and dropped == found else "on"
    for r in rows:
        r["keyword_score"] = round(weights[r["id"]], 4)
    # deterministic whatever order the index returned matches in: score, then the later message, then the id
    rows.sort(key=lambda r: (-r["keyword_score"], -r["position"], str(r["id"])))
    return rows[:CANDIDATE_LIMIT], "on"


def fuse(lexical: list[dict[str, Any]], vector: list[dict[str, Any]], threshold: float,
         min_sim: float, keyword: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Reciprocal-rank fusion with abstention: a candidate needs a lexical or a vector signal above its bar, or a
    keyword hit (ADR 0052: the keyword route has its own bar, so a keyword-only hit is kept with vectors off)."""
    merged: dict[Any, dict[str, Any]] = {}
    for rank, row in enumerate(lexical):
        item = merged.setdefault(row["id"], {**row, "sim": None, "rrf": 0.0})
        item["rrf"] += 1 / (RRF_K + rank + 1)
    for rank, row in enumerate(keyword or []):
        item = merged.setdefault(row["id"], {**row, "sim": None, "user_score": 0.0, "score": 0.0, "rrf": 0.0})
        item["keyword_score"] = row["keyword_score"]
        item["rrf"] += 1 / (RRF_K + rank + 1)
    for rank, row in enumerate(vector):
        item = merged.setdefault(row["id"], {**row, "user_score": 0.0, "score": 0.0, "rrf": 0.0})
        item["sim"] = float(row["sim"])
        item["text_start"], item["text_end"] = row["text_start"], row["text_end"]
        item["rrf"] += 1 / (RRF_K + rank + 1)
    kept = [m for m in merged.values()
            if float(m.get("user_score") or 0) >= threshold or (m.get("sim") is not None and m["sim"] >= min_sim)
            or float(m.get("keyword_score") or 0) > 0]
    kept.sort(key=lambda m: (m["rrf"], m["position"]), reverse=True)
    return kept


def one_char_words(query: str) -> tuple[str, ...]:
    """The question's one-character words (책, 집, 돈, 3), which `keywords` drops; a lone Latin letter is no word here.
    packet-v12 breaks a tie of the excerpt's anchor sentence on them (PHASE-31 Q3)."""
    return tuple(dict.fromkeys(w for w in re.findall(r"\w+", query)
                               if len(w) == 1 and not (w.isascii() and not w.isdigit())))


def _said(fact: dict[str, Any]) -> tuple[str, ...]:
    return tuple(t for t in (fact.get("object"), fact.get("value")) if t)


def replaced_values(facts: list[dict[str, Any]]) -> list[tuple[int, tuple[str, ...], tuple[str, ...]]]:
    """For each selected fact with an earlier version of its own predicate: its current turn, what its earlier versions
    said (object, value) and what it says now (PHASE-31 Q1)."""
    out = []
    for f in facts:
        if f.get("turn") is None:
            continue
        old = tuple(t for h in f.get("history") or ()
                    if h.get("outcome") == "superseded" and h["position"] < f["position"]
                    and h["predicate"] == f["predicate"] for t in _said(h))
        if old:
            out.append((f["turn"], old, _said(f)))
    return out


def states_replaced(text: str, turn: int | None, replaced: list[tuple[int, tuple[str, ...], tuple[str, ...]]],
                    names: tuple[str, ...] = (), ignore_now: bool = False) -> bool:
    """An excerpt from before a fact's current version that repeats what that version replaced and not what it says
    now, by the measure that drops an excerpt restating a withheld line (`spans.reuse`, PHASE-31 Q1). Spans of the
    current value and of characters' names are not the old value's."""
    if turn is None:
        return False
    for cur_turn, old, now in replaced:
        if turn >= cur_turn or (not ignore_now and any(spans.reuse(t, text) >= REPEATS for t in now)):
            continue
        if any(spans.reuse(t, text, (*now, *names)) >= REPEATS for t in old):
            return True
    return False


_QUOTED = re.compile(r"['\"‘’“”「」『』](.+?)['\"‘’“”「」『』]")
PLACE_MARKS = frozenset({"located_in"})  # a replaced place: its name's words are marks too (PHASE-31 Q1, amended)
MARKED = STANDING | PLACE_MARKS  # facts the question names that judge what changed although the packet leaves them out
# A place's words are marks only when the question asks where (measured: M0 main lost two answers whose excerpts named
# rooms the characters had passed through, on questions not about where anyone is)
WHERE = re.compile(r"어디|\bwhere\b", re.IGNORECASE)
# A form of address's quoted forms are marks only when the question asks what someone is called (measured: an old
# '도윤 씨' is in the dialogue of most excerpts, and questions about a promise or a key lost them)
CALLED = re.compile(r"부르|불러|부름|호칭|\bcalls?\b|\bcalled\b", re.IGNORECASE)


def _flat(text: str | None) -> str:
    return "".join((text or "").casefold().split())


def _value_marks(fact: dict[str, Any], names: frozenset[str], places: bool = True,
                 calls: bool = True) -> tuple[set[str], set[str]]:
    """What sets one version apart (PHASE-31 Q1, amended 2026-10-05): its quoted forms ('서 선생', '도윤 씨'; not one
    that is only a character's name; for a form of address only when the question asks what someone is called,
    `calls`), and for a place (`located_in`), when the question asks where (`places`), the words of the place's name
    (갈매기, 여관; no character's name). Prose words (친구, 말투) are none: an older excerpt says them about anything.
    Returns (quoted forms, spaces squashed; words)."""
    text = " ".join(t for t in (fact.get("object"), fact.get("value")) if t)
    quoted = {_flat(q) for q in _QUOTED.findall(text)} if calls or fact.get("predicate") != "addresses" else set()
    words: set[str] = set()
    if places and fact.get("predicate") in PLACE_MARKS:
        words = {w.casefold() for w in re.findall(r"\w+", fact.get("object") or "") if len(w) >= 2}
    return ({q for q in quoted if len(q) >= 2 and q not in names},
            {w for w in words if not any(w in n or n in w for n in names)})


def replaced_marks(facts: list[dict[str, Any]], names: frozenset[str], places: bool = True,
                   calls: bool = True) -> list[tuple[int, set[str], set[str], set[str], set[str]]]:
    """For each fact with an earlier version of its own predicate: its current turn, the marks of what its earlier
    versions said that the current one does not (quoted, words), and the current version's own (quoted, words)."""
    out = []
    for f in facts:
        if f.get("turn") is None:
            continue
        now_q, now_w = _value_marks(f, names, places, calls)
        cur = _flat(" ".join(t for t in (f.get("object"), f.get("value")) if t))
        old_q: set[str] = set()
        old_w: set[str] = set()
        for h in f.get("history") or ():
            if h.get("outcome") == "superseded" and h["position"] < f["position"] and h["predicate"] == f["predicate"]:
                q, w = _value_marks(h, names, places, calls)
                old_q |= {m for m in q if m not in cur}
                old_w |= {m for m in w if m not in cur}
        if old_q or old_w:
            out.append((f["turn"], old_q, old_w, now_q, now_w))
    return out


def _has(text: str, quoted: set[str], words: set[str]) -> bool:
    """A quoted form anywhere (spaces ignored), or a word at the start of one of the text's words (a particle after it:
    여관이)."""
    flat = _flat(text)
    return any(q in flat for q in quoted) or any(t.startswith(w) for t in re.findall(r"\w+", text.casefold())
                                                for w in words)


def states_marked(text: str, turn: int | None, marks: list[tuple[int, set[str], set[str], set[str], set[str]]],
                  ignore_now: bool = False) -> bool:
    """An excerpt from before a fact's current version that holds a mark of what that version replaced and none of the
    current version's (PHASE-31 Q1, amended). `ignore_now`: whether it holds an old mark at all."""
    if turn is None:
        return False
    return any(turn < cur_turn and _has(text, old_q, old_w) and (ignore_now or not _has(text, now_q, now_w))
               for cur_turn, old_q, old_w, now_q, now_w in marks)


def asks_about_old(fact: dict[str, Any], query: str, names: frozenset[str]) -> bool:
    """The question names what a fact's earlier version said and its current one does not ("왜 여관에서 나왔어?"): it
    asks about the change, so that fact leaves the old excerpts in (PHASE-31 Q1, amended; measured on the synthetic cut
    at turn 120). A word of two or more characters at the start of a word of the question; no character's name."""
    cur = _flat(" ".join(t for t in (fact.get("object"), fact.get("value")) if t))
    olds = {w.casefold() for h in fact.get("history") or ()
            if h.get("outcome") == "superseded" and h["predicate"] == fact["predicate"]
            for w in re.findall(r"\w+", " ".join(t for t in (h.get("object"), h.get("value")) if t))}
    olds = {w for w in olds if len(w) >= 2 and w not in cur and not any(w in n or n in w for n in names)}
    return any(t.startswith(w) for t in re.findall(r"\w+", query.casefold()) for w in olds)


def named_facts(facts: list[dict[str, Any]], query: str, r: Any,
                aliases: dict[str, frozenset[str]] | None) -> list[dict[str, Any]]:
    """Standing facts and places the question names (both of a pair; a place's subject), whether or not the packet
    holds them: the prompt may hold the current version, and the excerpt of the replaced one would contradict it
    (PHASE-31 Q1, amended). The persona's names count here."""
    q = " ".join(query.casefold().split())
    persona = {" ".join(n.casefold().split()) for n in (r.persona_names if r is not None else ())}

    def named(f: dict[str, Any], role: str) -> bool:
        side = _side_names(f, role, r, aliases)
        if r is not None and f.get(role) and r.is_persona(f.get(f"{role}_type"), f.get(role)):
            side |= {n for n in persona if len(n) >= 2}
        return any(n in q for n in side)

    return [f for f in facts if f["predicate"] in MARKED and f.get("history") and named(f, "subject")
            and (f["predicate"] in PLACE_MARKS or named(f, "object"))]


def _ended_role(f: dict[str, Any]) -> bool:
    return f.get("predicate") == "role_toward" and f.get("polarity") == "negative"


def _side(f: dict[str, Any], role: str) -> str:
    e = f.get(f"{role}_entity") or {}
    return e.get("id") or " ".join(str(f.get(role) or "").casefold().split())


def _side_names(f: dict[str, Any], role: str, r: Any, aliases: dict[str, frozenset[str]] | None) -> set[str]:
    name = f.get(role)
    e = r.entity(f.get(f"{role}_type"), name) if r is not None and name else None
    out = {" ".join(n.casefold().split()) for n in (e["names"] if e else [name] if name else [])}
    return {n for n in out | {v for n in out for v in (aliases or {}).get(n, ())} if len(n) >= 2}


def ended_role_kept(f: dict[str, Any], facts: list[dict[str, Any]], query: str, r: Any = None,
                    aliases: dict[str, frozenset[str]] | None = None) -> bool:
    """An ended role a question about now still gets (PHASE-31 Q2): no fact about the same two is current, and the
    question names both. Then the ended role is all there is to say about them."""
    pair = {_side(f, "subject"), _side(f, "object")}
    if any(g is not f and g.get("polarity") != "negative" and {_side(g, "subject"), _side(g, "object")} == pair
           for g in facts):
        return False
    q = " ".join(query.casefold().split())
    return all(any(n in q for n in _side_names(f, role, r, aliases)) for role in ("subject", "object"))


def _replaced_judge(view: dict[str, Any], selected: list[dict[str, Any]], query: str, previous_ai: str,
                    options: RecallOptions, names_of: dict[int, Any]) -> Callable[..., bool] | None:
    """packet-v12's test for an excerpt that says a value a fact's current version replaced (PHASE-31 Q1, amended), or
    None when no fact gives one: the selected facts by reused spans, the facts the question names by marks (a place's
    words only when it asks where, a form of address's quoted forms only when it asks what someone is called); a fact
    whose old value the question itself names is not judged."""
    r = view["resolution"]  # characters' names are never an old value's spans or marks
    people = (*r.persona_names, *(n for e in r.entities() if e.get("type") == "character"
                                  for n in (e["name"], *e.get("names", ())))) if r is not None else ()
    flat_names = frozenset(_flat(n) for n in people if len(_flat(n)) >= 2)
    replaced = replaced_values([f for f in selected if not asks_about_old(f, query, flat_names)])
    named = named_facts(view["facts"], query, r, _aliases(r, query, previous_ai, options, view, names_of)
                        if r is not None else None)
    marks = replaced_marks([f for f in named if not asks_about_old(f, query, flat_names)], flat_names,
                           bool(WHERE.search(query)), bool(CALLED.search(query)))
    if not replaced and not marks:
        return None

    def stale(text: str, turn: int | None, ignore_now: bool = False) -> bool:
        return (states_replaced(text, turn, replaced, people, ignore_now)
                or states_marked(text, turn, marks, ignore_now))
    return stale


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
    keyword_note: str = "off"  # the keyword route (ADR 0052): "on", "none", "too_broad", "timeout" or "off"
    keyword_withheld: int = 0  # excerpts only the keyword route found, left out for repeating a secret (ADR 0052)
    quote_only: set[str] = dataclasses.field(default_factory=set)  # messages only the quote route found (ADR 0067)
    named: set[str] = dataclasses.field(default_factory=set)  # assertions the question names: required (PHASE-34 Q1)
    rested: int = 0  # candidates left out while they rest (PHASE-34 Q3)
    below_floor: int = 0  # supportive excerpts under EXCERPT_FLOOR (PHASE-34 Q4)
    risky: set[str] = dataclasses.field(default_factory=set)  # disputed or contradicted assertions (PHASE-34 Q1)
    quote_withheld: int = 0  # quotes from them left out for repeating a secret, as the keyword route's (ADR 0067)
    vector_note: str = "off"
    cast: dict[str, str] = field(default_factory=dict)  # scene cast, entity key → name (ADR 0034)
    note: str = ""  # added to the packet's Note (a first-person narrator, ADR 0035)
    withheld: int = 0  # lines and excerpts the chat's memory mode left out or replaced (ADR 0035)
    replaced: int = 0  # excerpts left out for stating a value a selected fact's current version replaced (packet-v12)
    ended: int = 0  # ended roles left out of a question about now (packet-v12, PHASE-31 Q2)
    path: str = "normal"  # "forensic" when the message asked what was said (packet-v13, PHASE-33 Q4)
    quote_note: str = "off"  # the quote route's own search: "on", "none" or "timeout"
    quotes: int = 0  # <Quote> lines offered (packet-v13)
    canon_names: str | None = None  # the canon manifest whose names the read used (ADR 0046)
    canon_facts: str | None = None  # the canon manifest whose facts it used; None: none (ADR 0047)
    withheld_lines: list[Line] = field(default_factory=list)
    secret_pairs: set[tuple[frozenset[str], frozenset[str]]] = field(default_factory=set)  # (holders, absent) given a Secret line
    story: list[Line] = field(default_factory=list)  # summaries (packet-v8, ADR 0043)
    cast_lines: list[tuple[str, list[Line]]] = field(default_factory=list)  # each scene character's state (packet-v8)


def gather(conn: psycopg.Connection, head: UUID, query: str, previous_ai: str, in_context: set[str],
           options: RecallOptions, upto: int | None = None, known_at: datetime | None = None,
           canon_manifest: str | None = None, canon_exact: bool = False, canon_held: Iterable[str] = (),
           canon_facts: Any = LIVE, vectors_now: bool = False,
           recent: list[overuse.Recent] | None = None) -> Gathered:
    """Candidates for one request, already normalized (`clean_text`). `upto` and `known_at` gather them as
    of an earlier request: the head up to that position, and what NMOS had derived by that time. The canon keys the
    prompt held count as in context: the host sent their text, so their facts are not sent again (D3, ADR 0047).
    `vectors_now` searches vectors as they are now whatever `known_at` says (a replay's named projection)."""
    started = time.perf_counter()
    g = Gathered()
    # packet-v14 (PHASE-34 Q2, Q3): the supportive lines overused in the requests before this one rest
    # A question about the past or how it started asks for old memory: nothing rests then
    rest = (overuse.tired(recent or [], options.rest_after)
            if options.policy in REST_POLICIES and not HISTORY_CUE.search(query) else frozenset())
    if canon_held:
        in_context = in_context | {"canon:" + k for k in canon_held}
    # The head's last message is always in the prompt (the host sends the latest message; D13 injects
    # only when it is there), whether or not the plugin could anchor it: it skips messages shorter than
    # 16 characters, so a short first message was recalled as memory of itself (seen in the Phase 9
    # real-host smoke, docs/perf/phase9-packets.md).
    if (last := _head_last(conn, head, upto)) is not None:
        in_context = in_context | {last}
    lexical: list[dict[str, Any]] = []
    keyword: list[dict[str, Any]] = []
    vector: list[dict[str, Any]] = []
    pending: QueryEmbedding | None = None
    cut = 0
    focus = f"{query} {previous_ai}"
    # The turn the packet shows: the message's turn index since packet-v7, as facts have it (ADR 0041).
    by_turn = options.policy in TURN_POLICIES
    if query.strip():
        if options.embedder is not None:  # asked for first, answered while the reads below run (ADR 0061)
            text = options.query_prefix + query
            # A live request takes the embedding its sync asked for (item 7); a replay compiles from its own reads.
            pending = (prefetched.take(options.embedder, options.embed_projection, text) if known_at is None
                       else None)
            if pending is not None:
                g.timings["embed_lead"] = round((time.perf_counter() - pending.started) * 1000, 2)
            else:
                pending = QueryEmbedding(options.embedder, text, options.embed_timeout_ms)
        cut = _cut(conn, head, upto)
        lexical, g.lexical_note = _lexical(conn, head, query, previous_ai, cut, options.threshold,
                                           options.lexical_timeout_ms, upto)
        g.timings["lexical"] = round((time.perf_counter() - started) * 1000, 2)
        if options.lexical_keywords:
            t0 = time.perf_counter()
            keyword, g.keyword_note = _keyword_lexical(conn, head, keywords(query), cut, options.lexical_timeout_ms,
                                                       upto)
            g.timings["keywords"] = round((time.perf_counter() - t0) * 1000, 2)
    # State, facts, threads, the scene and the summaries are read before the excerpts are chosen: none of them depends
    # on the candidates, and the query embedding answers meanwhile (ADR 0061). The excerpts follow, then what the
    # memory mode withheld is taken out of them.
    if options.rules_version != "none":
        g.state = [StateItem(key=r["key"], value=r["value"], turn=r["turn"] if by_turn else r["position"])
                   for r in current_state(conn, head, options.rules_version, upto)
                   if r["host_logical_id"] not in in_context]
        # Sim bots track many characters: state of characters mentioned right now gets the budget first.
        g.state.sort(key=lambda i: ("." in i.key and i.key.split(".", 1)[0] in focus), reverse=True)
    view = None
    names_of: dict[int, Any] = {}  # one mapping of name variants per view, whichever path asks first (ADR 0058)
    changes = options.policy in CHANGE_POLICIES and not HISTORY_CUE.search(query)  # packet-v12, PHASE-31 Q1/Q2
    selected: list[dict[str, Any]] = []  # the facts offered (facts, <Cast>), for packet-v12's replaced values
    if options.facts_limit > 0 or options.threads_limit > 0:
        view = memory_view(conn, head, options.extractor_key, upto, known_at, canon_manifest, canon_exact,
                           options.canon_key, canon_facts)
        g.canon_names, g.canon_facts = view.get("canon_names"), view.get("canon_facts_manifest")
        r = view["resolution"]
        persona = r.persona_names if r else frozenset()
        aliases = _aliases(r, query, previous_ai, options, view, names_of)
        # Who is in the scene, so facts only some of them know are marked (packet-v3, ADR 0034).
        g.cast = scene.cast(view["facts"] + view["claims"] + view["other"], r, query, previous_ai,
                            _head_turn(conn, head, upto), aliases=aliases,
                            marks=_thread_marks(view, aliases))
        if options.threads_limit > 0:
            picked = relevant_threads(view["threads"], query, previous_ai, in_context,
                                      len(view["threads"]) if rest else options.threads_limit, persona,
                                      about=options.policy in ABOUT_POLICIES, aliases=aliases, named=g.named)
            picked = _rested(picked, "thread", rest, g)[:options.threads_limit]
            g.threads = _moded([thread_entry(t, scene.private(t, g.cast, r)) for t in picked],
                               view["threads"], g, r, options)
        if options.facts_limit > 0:
            causes = options.policy in CAUSE_POLICIES
            # packet-v9 ranks every candidate once: the configured limit's share is its head (relevant_facts keeps
            # its order and event cap at any limit), and the added slots go to what no one is kept from (ADR 0049).
            grow = options.fill_facts > 0
            claims_limit = max(1, options.facts_limit // 2)
            # How it started (ADR 0056): where the window starts, read only when the message asks.
            first = options.first_cue and bool(FIRST_CUE.search(query))
            start = _window_start(conn, head, in_context, upto) if first else None
            ranked = relevant_facts(view["facts"], query, previous_ai, in_context,
                                    len(view["facts"]) if grow or rest else options.facts_limit,
                                    options.events_limit, persona, scene.names(g.cast, r, aliases), causes=causes,
                                    first_cue=first, window_start=start, marks=options.history_marks, aliases=aliases,
                                    named=g.named)
            ranked = _rested(ranked, "fact", rest, g)
            if changes:  # an ended role answers a question about the past, not about now (PHASE-31 Q2); the facts
                # after it take its slot
                def now_or_kept(f: dict[str, Any]) -> bool:
                    return not _ended_role(f) or ended_role_kept(f, view["facts"], query, r, aliases)
                g.ended = sum(1 for f in _grown(ranked[:options.facts_limit], ranked, options.fill_facts)
                              if not now_or_kept(f))
                ranked = [f for f in ranked if now_or_kept(f)]
            facts = _grown(ranked[:options.facts_limit], ranked, options.fill_facts)
            if changes:
                selected = list(facts)
            # Claims after facts, so the budget serves narration first (ADR 0013).
            ranked = relevant_facts(view["claims"], query, previous_ai, in_context,
                                    len(view["claims"]) if grow or rest else claims_limit, persona=persona,
                                    causes=causes, first_cue=first, window_start=start, marks=options.history_marks,
                                    aliases=aliases, named=g.named)
            ranked = _rested(ranked, "claim", rest, g)
            claims = _grown(ranked[:claims_limit], ranked,
                            max(1, (options.facts_limit + options.fill_facts) // 2) - claims_limit)
            g.risky = ({str(f["id"]) for f in facts + claims if f.get("disputed_by")}
                       | {str(c["fact"]) for c in view.get("conflicts") or [] if c.get("fact") is not None})
            # How the cast stand with each other takes the budget before threads (ADR 0026).
            before, cause = options.policy in BEFORE_POLICIES, causes
            marks = options.history_marks
            g.lead = _moded([fact_entry(f, scene.private(f, g.cast, r), before, cause, marks) for f in facts
                             if f["predicate"] in STANDING],
                            facts, g, r, options)
            g.facts = _moded([fact_entry(f, scene.private(f, g.cast, r), before, cause, marks) for f in facts
                              if f["predicate"] not in STANDING]
                             + [claim_entry(c, scene.private(c, g.cast, r), cause) for c in claims], facts + claims, g, r,
                             options)
        if options.narrator:
            who = scene.display(r, options.narrator) if r is not None else options.narrator
            g.note = f" The story is told in the first person by {who}: only what they know is listed."
        if options.policy in CAST_POLICIES and r is not None:
            g.cast_lines, used = cast_groups(view, g.cast, r, query, options, in_context, aliases)
            if changes:
                selected += [f for f in view["facts"] if f["id"] in used]
            if used:  # a line in <Cast> is not said again in another section
                g.lead = [line for line in g.lead if line.ref.get("assertion") not in used]
                g.facts = [line for line in g.facts if line.ref.get("assertion") not in used]
                g.threads = [line for line in g.threads if line.ref.get("assertion") not in used]
    if options.policy in STORY_POLICIES and options.summarize_key and not options.narrator:  # ADR 0043, PHASE-12 Q3
        if view is None and options.extractor_key:  # facts and threads off: the secrets still decide what may be told
            view = memory_view(conn, head, options.extractor_key, upto, known_at, canon_manifest, canon_exact,
                               options.canon_key, canon_facts)
            g.canon_names, g.canon_facts = view.get("canon_names"), view.get("canon_facts_manifest")
        r = view["resolution"] if view else None
        aliases = _aliases(r, query, previous_ai, options, view, names_of) if view else None
        if view and not g.cast and r is not None:
            g.cast = scene.cast(view["facts"] + view["claims"] + view["other"], r, query, previous_ai,
                                _head_turn(conn, head, upto), aliases=aliases,
                                marks=_thread_marks(view, aliases))
        g.story = summaries.packet_lines(conn, head, options.summarize_key, view["secrets"] if view else [], query,
                                         in_context, upto, known_at,
                                         scene.names(g.cast, r, aliases) if r is not None else frozenset())
        if rest:  # a scene summary is supportive and rests as the others do (a review); the story so far never rests
            awake = [line for line in g.story
                     if '<Summary kind="story"' in line.xml or overuse.key(line.kind, line.ref) not in rest]
            g.rested += len(g.story) - len(awake)
            g.story = awake
    if pending is not None:
        t0 = time.perf_counter()
        try:
            qvec = pending.result()
            g.timings["embed_wait"] = round((time.perf_counter() - t0) * 1000, 2)
            g.timings["embed"] = pending.call_ms  # the embedder's own time, mostly spent during the reads
            t0 = time.perf_counter()
            vector = vector_candidates(conn, head, qvec, options.embed_projection, cut, CANDIDATE_LIMIT,
                                       upto, None if vectors_now else known_at)
            g.timings["vector"] = round((time.perf_counter() - t0) * 1000, 2)
            g.vector_note = "on"
        except (LLMError, ValueError) as exc:  # fail open to lexical-only
            g.timings["embed_wait"] = round((time.perf_counter() - t0) * 1000, 2)
            g.vector_note = f"fallback: {exc}"[:200]
    g.candidates = fuse(lexical, vector, options.threshold, options.vector_min_sim, keyword)
    g.excluded = [c for c in g.candidates if c["host_logical_id"] in in_context]
    eligible = [c for c in g.candidates if c["host_logical_id"] not in in_context]
    stale = _replaced_judge(view, selected, query, previous_ai, options, names_of) if changes and view is not None else None
    if stale is None:  # packet-v12 judges each excerpt as it is made and fills a dropped one's slot (PHASE-31 Q1)
        eligible = eligible[: options.top_k]
    words = keywords(query) if options.policy in GROW_POLICIES else []
    span = options.policy in SPAN_POLICIES  # packet-v11 (ADR 0063)
    cue = span and bool(WHY.search(query) or CONTENTS.search(query))  # a why or contents question (PHASE-27 Q2)
    # Q1b: the keywords anchor is the question's keywords alone, or the question itself when it has none (the
    # prototype's rule: never the previous reply); every other case anchors on the question and the previous reply
    anchor = (" ".join(words) or query) if span and options.excerpt_anchor == "keywords" else focus
    tie = one_char_words(query) if options.policy in CHANGE_POLICIES else ()  # packet-v12, PHASE-31 Q3
    # packet-v13 (PHASE-33 Q5): a turn this generation has not extracted yet (a first sight still catching up) has no
    # fact to restate, so its excerpt is raw evidence; one such excerpt may take one more slot than top_k (packet-v13
    # judges excerpts as packet-v12 does: `stale` is set whenever there is an extractor to ask)
    unextracted = (_unextracted(conn, head, [c["id"] for c in eligible], options.extractor_key, known_at)
                   if options.policy in UNEXTRACTED_POLICIES and options.extractor_key and eligible else set())
    def resting(c: dict[str, Any]) -> bool:  # a tired excerpt is left out while it rests (PHASE-34 Q3) ...
        return bool(rest) and ("excerpt", str(c["id"])) in rest and str(c["id"]) not in g.named \
            and not (c.get("user_score") or c.get("keyword_score"))  # ... unless the question's words found it
    floor = (EXCERPT_FLOOR * max((float(c["rrf"]) for c in eligible if not resting(c)), default=0.0)
             if options.policy in REST_POLICIES else 0.0)
    for c in eligible:
        if g.ranked and resting(c):  # the first excerpt is the reserved, required one: it never rests (a review)
            g.rested += 1
            continue
        if floor and g.ranked and float(c["rrf"]) < floor and not (c.get("user_score") or c.get("keyword_score")):
            g.below_floor += 1  # supportive memory's activation threshold (PHASE-34 Q4): the first excerpt is required
            continue
        extra = any(e.unextracted for e in g.ranked)
        if stale is not None and len(g.ranked) >= options.top_k + extra:
            break
        if stale is not None and len(g.ranked) == options.top_k and str(c["id"]) not in unextracted:
            continue  # the one more slot is for an unextracted turn only
        # a lexical or keyword hit is the whole message; a vector-only hit is its chunk; under packet-v11 a word hit
        # whose vector similarity meets the bar excerpts within its chunk too: the chunk is the part of the message
        # the question is about, the words only say the message is relevant (PHASE-27 Q1)
        word_hit = bool(c.get("user_score") or c.get("keyword_score"))
        in_chunk = not word_hit or (span and c.get("sim") is not None and c["sim"] >= options.vector_min_sim
                                    and c.get("text_end") is not None)
        clean = c["clean"][c["text_start"]:c["text_end"]] if in_chunk else c["clean"]
        if cue:  # packet-v11: by whole sentences up to CUE_GROW_CHARS, no sentence cap (PHASE-27 Q2)
            text, short = grown_excerpt(clean, anchor, words, min(options.excerpt_chars, CUE_GROW_CHARS),
                                        max_sentences=None, tie_words=tie)
        elif options.policy in GROW_POLICIES:  # packet-v10: grown to its length from the best sentence (ADR 0053)
            text, short = grown_excerpt(clean, anchor, words, options.excerpt_chars, tie_words=tie)
        else:
            text = excerpt(clean, focus, max_chars=options.excerpt_chars)
            short = excerpt(clean, focus, window=1, max_chars=options.excerpt_chars)
        item = Excerpt(turn=c["turn"] if by_turn else c["position"],
                       speaker=c["name"] or ("user" if c["role"] == "user" else "character"),
                       text=text, score=float(c["rrf"]), revision_id=str(c["id"]), short=short,
                       position=c["position"], unextracted=str(c["id"]) in unextracted)
        if stale is not None:  # packet-v12 (PHASE-31 Q1): no form of an excerpt says only a replaced value
            if stale(item.text, item.turn):
                g.replaced += 1
                continue
            if item.short and stale(item.short, item.turn):  # its sentence alone would: placed whole or not at all
                item = dataclasses.replace(item, short="", cut_ok=False)
            elif stale(item.text, item.turn, ignore_now=True):  # a cut could keep the old value and lose the new
                item = dataclasses.replace(item, cut_ok=False)
        g.ranked.append(item)
    if options.policy in QUOTE_POLICIES and query.strip() and quotes.asks_for_words(query):
        # The forensic path (PHASE-33, ADR 0067): the words said, from the messages recall found and the turns a turn
        # number names; placed before the excerpts, never cut. The filters below apply to them as to any excerpt.
        t0 = time.perf_counter()
        g.path = "forensic"
        resolution = (view or {}).get("resolution")
        names = quotes.character_names(resolution.entities()) if resolution is not None else {}
        first = bool(quotes.FIRST_QUOTE.search(query)) and quotes.named_turn(query) is None
        found = [c for c in g.candidates if c["host_logical_id"] not in in_context][:quotes.CANDIDATES]
        extra: list[dict[str, Any]] = []
        if (named := quotes.named_turn(query)) is not None:
            extra = _turn_messages(conn, head, named - quotes.TURN_SPAN, named + quotes.TURN_SPAN, upto, cut)
        met = None
        if first:  # how it started: the opening, and the turns where everyone the question names had appeared
            asked, others = quotes.named(query, names)
            met = _first_met(conn, head, [[k for k, d in names.items() if d == who] for who in asked | others], upto,
                             cut)
            if met == 0:
                met = None  # all there from the opening: no meeting to anchor on, the earliness bonus decides
            extra = _turn_messages(conn, head, 0, quotes.TURN_SPAN, upto, cut)
            if met is not None:
                extra += _turn_messages(conn, head, met, met + quotes.TURN_SPAN, upto, cut)
        searched, rarity, g.quote_note = _quote_messages(conn, head, quotes.query_words(query), upto, cut)
        seen = {str(c["id"]) for c in found}
        g.quote_only = {str(c["id"]) for c in extra + searched} - {str(c["id"]) for c in g.candidates}
        for c in extra + searched:
            if c["host_logical_id"] not in in_context and str(c["id"]) not in seen:
                found.append(c)
                seen.add(str(c["id"]))
        picked = quotes.pick(found, query, names, _last_position(conn, head, upto), first, rarity, met)
        g.quotes = len(picked)
        g.ranked = [Excerpt(turn=q.turn if by_turn else q.position, speaker=q.speaker or "", text=q.text,
                            score=q.score, revision_id=q.revision_id, position=q.position, cut_ok=False, quote=True)
                    for q in picked] + g.ranked
        g.timings["quote_route"] = round((time.perf_counter() - t0) * 1000, 2)  # ms; `quotes` is the count placed
    if g.withheld_lines:
        # An excerpt that says what the mode withheld would give it back word for word.
        kept = [e for e in g.ranked
                if not any(spans.reuse(line.content, e.text) >= REPEATS for line in g.withheld_lines)]
        g.withheld += len(g.ranked) - len(kept)
        g.ranked = kept
    # The keyword route adds no raw text that repeats a secret still kept from someone (ADR 0052, owner 2026-09-30):
    # an excerpt only it found is left out when it does, so it places no secret the other routes would not. The same
    # test as a summary's (PHASE-12 Q3), stricter when someone it is kept from is in the scene.
    # The same for a quote from a message only the quote route found (the named turn's, its own search): raw text no
    # other route would place (ADR 0067).
    keyword_only = {str(c["id"]) for c in g.candidates if _keyword_only(c, options)} | g.quote_only
    if keyword_only and any(e.revision_id in keyword_only for e in g.ranked) and options.extractor_key:
        if view is None:
            view = memory_view(conn, head, options.extractor_key, upto, known_at, canon_manifest, canon_exact,
                               options.canon_key, canon_facts)
        r = view["resolution"]
        aliases = _aliases(r, query, previous_ai, options, view, names_of)
        cast = g.cast
        if not cast and r is not None:  # facts, threads and summaries off: the scene still sets the bar
            cast = scene.cast(view["facts"] + view["claims"] + view["other"], r, query, previous_ai,
                              _head_turn(conn, head, upto), aliases=aliases,
                              marks=_thread_marks(view, aliases))
        present = scene.names(cast, r, aliases) if r is not None else frozenset()
        kept = []
        for e in g.ranked:
            if e.revision_id not in keyword_only:
                kept.append(e)
            elif not any(summaries.leaks(form, view["secrets"], present) for form in (e.text, e.short) if form):
                kept.append(dataclasses.replace(e, cut_ok=False))  # the forms checked are the only ones placed
        g.quote_withheld = sum(e.quote for e in g.ranked) - sum(e.quote for e in kept)
        g.keyword_withheld = len(g.ranked) - len(kept) - g.quote_withheld
        g.ranked = kept
    return g


def _aliases(r: Any, query: str, previous_ai: str, options: RecallOptions, view: dict[str, Any],
             cache: dict[int, Any]) -> dict[str, frozenset[str]] | None:
    """The other names the characters go by in this request (`name_variants`, ADR 0058), or None when the option is
    off; computed once per view (`cache`). The names in knowledge marks include an open thread's: a thread keeps the
    marks of the assertion that opened it (`threads.fold`)."""
    if not options.name_variants or r is None:
        return None
    if id(view) not in cache:
        marked = {n for row in view["facts"] + view["claims"] + view["other"] + view["threads"]
                  for n in (*(row.get("known_by") or ()), *(row.get("hidden_from") or ()))}
        cache[id(view)] = variants.aliases(r.entities(), r.persona_names, f"{query} {previous_ai}", marked)
    return cache[id(view)]


def _thread_marks(view: dict[str, Any], aliases: dict[str, frozenset[str]] | None) -> list[str]:
    """With `name_variants`, the names in open threads' knowledge marks, for the scene's cast: someone a thread is kept
    from may be named only there (ADR 0058). Without it, none, as recorded requests had it."""
    if aliases is None:
        return []
    return [n for t in view["threads"] for n in (*(t.get("known_by") or ()), *(t.get("hidden_from") or ()))]


def _keyword_only(c: dict[str, Any], options: RecallOptions) -> bool:
    """A candidate that only the keyword route admitted (fuse's other two bars not met)."""
    return (float(c.get("keyword_score") or 0) > 0 and float(c.get("user_score") or 0) < options.threshold
            and not (c.get("sim") is not None and c["sim"] >= options.vector_min_sim))


def cast_facts(facts: list[dict[str, Any]], to_persona: Callable[[dict[str, Any]], bool]) -> list[dict[str, Any]]:
    """What <Cast> says of one character (ADR 0043), from their current facts: the newest place and condition, the
    newest feeling toward the persona, and up to CAST_ITEMS things they carry, newest first. The Inspector's state
    block uses the same rule (PHASE-12 step 6)."""
    facts = sorted((f for f in facts if f["predicate"] in CAST_PREDICATES and f.get("polarity") != "negative"
                    and f.get("subject_type") in (None, "character")), key=lambda f: f["position"], reverse=True)
    pick = [f for f in facts if f["predicate"] == "located_in"][:1]
    pick += [f for f in facts if f["predicate"] == "has_status"][:1]
    pick += [f for f in facts if f["predicate"] == "feels_toward" and f.get("object") and to_persona(f)][:1]
    return pick + [f for f in facts if f["predicate"] == "possesses"][:CAST_ITEMS]


def cast_groups(view: dict[str, Any], cast: dict[str, str], r: Any, query: str, options: RecallOptions,
                in_context: set[str] = frozenset(), aliases: dict[str, frozenset[str]] | None = None
                ) -> tuple[list[tuple[str, list[Line]]], set[Any]]:
    """Each scene character's current state as the lines it is (PHASE-12 Q4, ADR 0043): place, condition, feeling
    toward the persona, what they carry, and, for a character the message names, their open goals, the one the
    message is about first: an open goal can be long over without a turn saying so (K23), and every request would
    carry it. Up to CAST_MAX characters, the persona left out. A line only some of the scene know stays in its section
    (its Private handling), and a narrator's unknowns are left out (ADR 0035). Returns the groups and the assertions
    they use. A canon fact whose text the prompt held is not said again (D3, ADR 0047). With `aliases`
    (`name_variants`, ADR 0058) the characters the user's message names come first: a given name in the previous
    reply brings more characters into the scene, and the one asked about must keep its group."""
    persona = scene.key(r, scene.PERSONA)
    said = norm(query)
    order = [k for k in cast if k != persona]
    if aliases is not None:
        order.sort(key=lambda k: not any(n in said for n in scene.names({k: cast[k]}, r, aliases)))  # stable
    order = order[:CAST_MAX]
    before, cause = options.policy in BEFORE_POLICIES, options.policy in CAUSE_POLICIES

    def shown(row: dict[str, Any]) -> bool:
        if scene.private(row, cast, r) or (row.get("canon") and row["host_logical_id"] in in_context
                                           and not row.get("held_off")):
            return False
        return not options.narrator or scene.narrator_knows(row, options.narrator, r)

    mine: dict[str, list[dict[str, Any]]] = {}
    for f in view["facts"]:
        if f["predicate"] in CAST_PREDICATES and shown(f):
            mine.setdefault(scene.key(r, f["subject"]), []).append(f)
    groups: list[tuple[str, list[Line]]] = []
    used: set[Any] = set()
    for k in order:
        pick = cast_facts(mine.get(k, []), lambda f: scene.key(r, f["object"]) == persona)
        named = any(n in said for n in scene.names({k: cast[k]}, r, aliases))
        goals = [t for t in view["threads"] if named and t.get("kind") == "goal" and t["status"] == "open"
                 and scene.key(r, t["by"]) == k and shown(t)]
        goals.sort(key=lambda t: (similarity(query, t.get("text")) if query else 0.0, t["position"]), reverse=True)
        lines = [fact_entry(f, False, before, cause, options.history_marks) for f in pick] + [
            thread_entry(t) for t in goals[:CAST_GOALS]]
        if lines:
            groups.append((cast[k], lines))
            used |= {line.ref.get("assertion") for line in lines}
    return groups, used


def compile_gathered(g: Gathered, budget: int, policy: str) -> Compiled:
    """One request's packet from what `gather` offered (the request and its replay compile alike)."""
    return compile_lines(g.ranked, budget, state=g.state, threads=g.threads, facts=g.facts, policy=policy, lead=g.lead,
                         note=g.note, story=g.story, cast=g.cast_lines, named=frozenset(g.named),
                         risky=frozenset(g.risky))


def _moded(lines: list[Line], rows: list[dict[str, Any]], g: Gathered, r: Any, options: RecallOptions) -> list[Line]:
    """This chat's memory mode applied to offered lines (ADR 0035). A first-person narrator drops what the
    narrator is not shown to know. Strict mode replaces a private line with a Secret line naming its holders
    and the characters present who are not shown to know it, one per such pair."""
    if not options.narrator and not options.strict:
        return lines
    by_id = {row["id"]: row for row in rows}
    out: list[Line] = []
    seen = g.secret_pairs
    for line in lines:
        row = by_id.get(line.ref.get("assertion"))
        if row is None:
            out.append(line)
            continue
        if options.narrator and not scene.narrator_knows(row, options.narrator, r):
            g.withheld += 1
            g.withheld_lines.append(line)
            continue
        if options.strict and line.private and r is not None:
            holders, absent = scene.missing(row, g.cast, r)
            g.withheld += 1
            g.withheld_lines.append(line)
            pair = (frozenset(holders), frozenset(absent))
            if pair in seen:
                continue
            seen.add(pair)
            # Not private itself: its content is withheld, so it needs no Private rule (and no room for one).
            out.append(Line("secret", secret_line(holders, absent, line.turn), line.ref, line.turn,
                            secret_text(holders, absent), "", {"not_known_by": absent}))
            continue
        out.append(line)
    return out


def _turn_messages(conn: psycopg.Connection, head: UUID, lo: int, hi: int, upto: int | None,
                   cut: int) -> list[dict[str, Any]]:
    """The messages of turns lo…hi on the head (PHASE-33 Q3), as candidates are shaped; none at or before the
    `allBefore` cut (invariant 7), as lexical and vector recall."""
    return conn.execute(
        """
        SELECT sr.id, am.position, am.turn, so.host_logical_id, rt.clean_content AS clean,
               sr.metadata->>'role' AS role, sr.metadata->>'name' AS name
        FROM active_membership am
        JOIN source_revision sr ON sr.id = am.source_revision_id
        JOIN source_object so ON so.id = sr.source_object_id
        JOIN revision_text rt ON rt.source_revision_id = sr.id AND rt.normalizer = %(norm)s
        WHERE am.commit_id = %(head)s AND am.turn BETWEEN %(lo)s AND %(hi)s
          AND am.position > %(cut)s AND am.position <= %(upto)s
          AND sr.lifecycle = 'accepted'
          AND coalesce(sr.metadata->>'disabled', '') NOT IN ('true', 'allBefore')
          AND coalesce(sr.metadata->>'isComment', 'false') <> 'true'
        ORDER BY am.position LIMIT 20
        """,
        {"head": head, "lo": lo, "hi": hi, "norm": NORMALIZER_VERSION, "cut": cut,
         "upto": 2**31 - 1 if upto is None else upto}, prepare=False).fetchall()


def _first_met(conn: psycopg.Connection, head: UUID, keys: list[list[str]], upto: int | None,
               cut: int) -> int | None:
    """The turn by which every one of these characters (each a list of its normalized names) had been named in the
    chat: where they met. None when one of them never was, when there is nobody, or past the route's time slice."""
    keys = [k for k in keys if k]
    if not keys:
        return None
    turns = []
    try:
        with conn.transaction():
            previous = conn.execute("SELECT current_setting('statement_timeout') AS t").fetchone()
            _apply(conn, {"statement_timeout": str(quotes.TIMEOUT_MS)})
            for names in keys:
                forms = sorted({f for n in names for f in ((n, n[:1].upper() + n[1:]) if n.isascii() else (n,))})
                row = conn.execute(sql.SQL(
                    """
                    SELECT min(am.turn) AS t FROM active_membership am
                    JOIN source_revision sr ON sr.id = am.source_revision_id
                    JOIN revision_text rt ON rt.source_revision_id = sr.id AND rt.normalizer = %(norm)s
                    WHERE am.commit_id = %(head)s AND am.position > %(cut)s AND am.position <= %(upto)s
                      AND sr.lifecycle = 'accepted'
                      AND coalesce(sr.metadata->>'disabled', '') NOT IN ('true', 'allBefore')
                      AND ({named})
                    """).format(named=sql.SQL(" OR ").join(  # strpos, as the route's search (no case in Korean)
                        sql.SQL("strpos(rt.clean_content, {}) > 0").format(sql.Literal(f)) for f in forms)),
                    {"head": head, "norm": NORMALIZER_VERSION, "cut": cut,
                     "upto": 2**31 - 1 if upto is None else upto}, prepare=False).fetchone()
                if row["t"] is None:
                    turns = []
                    break
                turns.append(row["t"])
            _apply(conn, {"statement_timeout": previous["t"]})
    except psycopg.errors.QueryCanceled:
        return None
    return max(turns) if turns else None


_QUOTE_MARKS = ('"', "“", "「", "『")


def _quote_messages(conn: psycopg.Connection, head: UUID, words: list[str], upto: int | None,
                    cut: int) -> tuple[list[dict[str, Any]], dict[str, float], str]:
    """The quote route's own search (PHASE-33 Q2): messages on the head that hold a quote and the question's words,
    rarest words first, lexically (quotes prefer lexical to embeddings, original §78), and each word's rarity on the
    head: ln(1 + N/df) / ln(1 + N), 1 for a word one message holds, 0 for one none does. Abstains on its time slice.

    Two passes: which words each message holds (`strpos`, no text returned: ILIKE and carrying the text cost three
    times as much at 10,000 messages), then the text of the best SEARCHED. A Latin word is matched as written and
    capitalized; Korean has no case."""
    if not words:
        return [], {}, "none"
    words = words[:8]

    def holds(w: str) -> sql.Composable:
        forms = {w, w[:1].upper() + w[1:]} if w.isascii() else {w}
        return sql.SQL("({})").format(sql.SQL(" OR ").join(
            sql.SQL("strpos(rt.clean_content, {}) > 0").format(sql.Literal(f)) for f in sorted(forms)))

    quoted = sql.SQL(" OR ").join(sql.SQL("strpos(rt.clean_content, {}) > 0").format(sql.Literal(m))
                                  for m in _QUOTE_MARKS)
    try:
        with conn.transaction():
            previous = conn.execute("SELECT current_setting('statement_timeout') AS t").fetchone()
            _apply(conn, {"statement_timeout": str(quotes.TIMEOUT_MS)})
            marks = conn.execute(sql.SQL(
                """
                SELECT sr.id, am.position, ARRAY[{hits}] AS hit, ({quoted}) AS quoted
                FROM active_membership am
                JOIN source_revision sr ON sr.id = am.source_revision_id
                JOIN revision_text rt ON rt.source_revision_id = sr.id AND rt.normalizer = %(norm)s
                WHERE am.commit_id = %(head)s AND am.position > %(cut)s AND am.position <= %(upto)s
                  AND sr.lifecycle = 'accepted'
                  AND coalesce(sr.metadata->>'disabled', '') NOT IN ('true', 'allBefore')
                  AND coalesce(sr.metadata->>'isComment', 'false') <> 'true'
                """).format(hits=sql.SQL(", ").join(holds(w) for w in words), quoted=quoted),
                {"head": head, "norm": NORMALIZER_VERSION, "cut": cut, "upto": 2**31 - 1 if upto is None else upto},
                prepare=False).fetchall()
            total = len(marks)
            df = [sum(1 for m in marks if m["hit"][i]) for i in range(len(words))]
            weight = [0.0 if not n else math.log(1 + total / n) / math.log(1 + max(total, 1)) for n in df]
            best = sorted((m for m in marks if m["quoted"] and any(m["hit"])),
                          key=lambda m: (-sum(w for w, h in zip(weight, m["hit"]) if h), m["position"]))
            ids = [m["id"] for m in best[:quotes.SEARCHED]]
            rows = conn.execute(
                """
                SELECT sr.id, am.position, am.turn, so.host_logical_id, rt.clean_content AS clean,
                       sr.metadata->>'role' AS role, sr.metadata->>'name' AS name
                FROM active_membership am
                JOIN source_revision sr ON sr.id = am.source_revision_id
                JOIN source_object so ON so.id = sr.source_object_id
                JOIN revision_text rt ON rt.source_revision_id = sr.id AND rt.normalizer = %(norm)s
                WHERE am.commit_id = %(head)s AND sr.id = ANY(%(ids)s)
                """, {"head": head, "norm": NORMALIZER_VERSION, "ids": ids}, prepare=False).fetchall()
            _apply(conn, {"statement_timeout": previous["t"]})
    except psycopg.errors.QueryCanceled:
        return [], {}, "timeout"
    order = {i: n for n, i in enumerate(ids)}
    rows.sort(key=lambda r: order[r["id"]])
    return rows, dict(zip(words, weight)), "on"


def _rested(rows: list[Any], kind: str, rest: frozenset[tuple[str, str]], g: Gathered,
            ident: Callable[[Any], str] = lambda r: str(r["id"]),
            hit: Callable[[Any], bool] = lambda r: False) -> list[Any]:
    """`rows` without the tired ones (PHASE-34 Q3, amended: a resting line is left out; moved behind the others it was
    placed anyway whenever the budget had room, which on S1 was nearly always). A line the question names (`named`;
    for an excerpt, `hit`: the question's words found it, lexically or by keyword) is required and never rests; one a
    reply used is not tired (`overuse.tired` reads the echo)."""
    if not rest:
        return rows
    def tired(r: Any) -> bool:
        if kind != "excerpt" and (r.get("hidden_from") or r.get("known_by")):
            return False  # a knowledge boundary is required wherever it is placed (Private, Secret): it never rests
        return (kind, ident(r)) in rest and ident(r) not in g.named and not hit(r)
    awake = [r for r in rows if not tired(r)]
    g.rested += len(rows) - len(awake)
    return awake


def _unextracted(conn: psycopg.Connection, head: UUID, ids: list[Any], extractor_key: str,
                 known_at: datetime | None = None) -> set[str]:
    """The revisions among `ids` whose turn on the head the generation has not extracted (PHASE-33 Q5). A turn is
    extracted once, on its last message, for every message of it; an extraction of the turn as it was before an edit
    (another window, ADR 0008) does not count, as `readmodel.membership` counts it. With `known_at`, as of an earlier
    request (a replay): an extraction written since does not count, one discarded since still does."""
    return {str(r["id"]) for r in conn.execute(
        """
        SELECT am.source_revision_id AS id FROM active_membership am
        WHERE am.commit_id = %(head)s AND am.source_revision_id = ANY(%(ids)s)
          AND NOT EXISTS (SELECT 1 FROM active_membership t JOIN extraction x ON x.source_revision_id = t.source_revision_id
                           AND x.window_hash = t.turn_hash
                          WHERE t.commit_id = %(head)s AND t.turn = am.turn AND t.turn_hash IS NOT NULL
                            AND x.extractor_key = %(key)s
                            AND x.created_at <= coalesce(%(at)s::timestamptz, now())
                            AND (x.discarded_at IS NULL OR x.discarded_at > coalesce(%(at)s::timestamptz, now())))
        """, {"head": head, "ids": ids, "key": extractor_key, "at": known_at}, prepare=False).fetchall()}


def _last_position(conn: psycopg.Connection, head: UUID, upto: int | None) -> int | None:
    row = conn.execute("SELECT max(position) AS p FROM active_membership WHERE commit_id = %s AND position <= %s",
                       (head, 2**31 - 1 if upto is None else upto)).fetchone()
    return row["p"] if row else None


def _head_turn(conn: psycopg.Connection, head: UUID, upto: int | None = None) -> int | None:
    """The turn of the head's last message (as of `upto`): the turn a request answers."""
    return conn.execute("SELECT max(turn) AS t FROM active_membership WHERE commit_id = %s AND position <= %s",
                        (head, 2**31 - 1 if upto is None else upto)).fetchone()["t"]


def _window_start(conn: psycopg.Connection, head: UUID, in_context: set[str], upto: int | None) -> int | None:
    """The lowest head position (as of `upto`) of a message in context: where the chat window starts (ADR 0056)."""
    return conn.execute(
        "SELECT min(am.position) AS p FROM active_membership am JOIN source_revision sr ON sr.id = am.source_revision_id"
        " JOIN source_object so ON so.id = sr.source_object_id WHERE am.commit_id = %s AND am.position <= %s"
        " AND so.host_logical_id = ANY(%s)", (head, 2**31 - 1 if upto is None else upto, sorted(in_context))).fetchone()["p"]


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
    # The head, its manifest hash and its end in one statement, and every read below bounded by that end: recall
    # takes no conversation lock, and a concurrent sync's append extends the head commit in place (D4).
    snap = conn.execute(
        "SELECT head_commit_id, head_manifest_hash, (SELECT max(position) FROM active_membership am"
        " WHERE am.commit_id = c.head_commit_id) AS head_end FROM conversation c WHERE c.id = %s", (conv.id,)).fetchone()
    head, upto = snap["head_commit_id"], snap["head_end"]
    fresh = (request.active_commit is None or request.active_commit == head) and (
        request.manifest_hash is None or request.manifest_hash == snap["head_manifest_hash"]
    )
    # The query side is normalized like the corpus: reasoning blocks in the previous AI turn must not
    # steer lexical scores, fact relevance or excerpt focus either.
    query = clean_text(request.query or "")
    previous_ai = clean_text(request.previous_ai or "")
    options = dataclasses.replace(options, strict=conv.memory_strict, narrator=conv.memory_narrator)
    in_context = set(request.in_context_ids)
    history = (overuse.recent(conn, conv.id, head, n=options.rest_after + 1)
               if options.policy in REST_POLICIES and fresh else None)
    g = (gather(conn, head, query, previous_ai, in_context, filled(options, request.budget_tokens), upto,
                canon_manifest=getattr(request, "canon_manifest_id", None),
                canon_held=getattr(request, "canon_held", None) or (), recent=history) if fresh else Gathered())
    def compile_at(budget: int) -> Compiled:
        return compile_gathered(g, budget, options.policy)

    compiled = compile_at(request.budget_tokens)
    kept = kept_counts(compiled.ledger)
    # Memory the budget left out, and the budget that would hold it all: the panel suggests it (ADR 0036).
    fit_started = time.perf_counter()
    cut = cut_lines(compiled.ledger)
    fit = fits_at(compile_at, request.budget_tokens) if cut else None
    memory = {"offered": sum(1 for e in compiled.ledger if e["kind"] in MEMORY_KINDS and e["why"] != "restates"),
              "cut": cut, "fits_at": fit}
    timings = {**g.timings, "fit": round((time.perf_counter() - fit_started) * 1000, 2),
               "sidecar_total": round((time.perf_counter() - started) * 1000, 2)}

    def brief(c: dict[str, Any]) -> dict[str, Any]:
        return {"revision_id": str(c["id"]), "position": c["position"], "host_logical_id": c["host_logical_id"],
                "score": round(float(c.get("score") or 0), 4), "user_score": round(float(c.get("user_score") or 0), 4),
                "sim": None if c.get("sim") is None else round(float(c["sim"]), 4),
                "keyword_score": round(float(c.get("keyword_score") or 0), 4), "rrf": round(float(c.get("rrf") or 0), 5)}

    placed = [e for e in compiled.ledger if e["placed"]]
    trace_id: UUID = uuid7()
    conn.execute(
        "INSERT INTO retrieval_trace (id, conversation_id, commit_id, query, candidates, selected, excluded_in_context,"
        " token_estimate, latency_ms, freshness, policy, budget_tokens, upto_position, previous_ai, in_context,"
        " extractor_key, embed_projection, rules_version, recall_options, lines, canon_manifest_id, canon_held)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            trace_id, conv.id, head, query,
            Jsonb([brief(c) for c in g.candidates]),
            Jsonb([{"revision_id": e.revision_id, "turn": e.turn, "score": round(e.score, 5)} for e in compiled.excerpts]),
            Jsonb([brief(c) for c in g.excluded]),
            compiled.tokens,
            Jsonb({**timings, "lexical_mode": g.lexical_note, "keyword_mode": g.keyword_note,
                   "keyword_withheld": g.keyword_withheld, "quote_withheld": g.quote_withheld,
                   "rested": g.rested, "below_floor": g.below_floor,
                   "vector_mode": g.vector_note,
                   "state_items": len(g.state), "facts": len(g.lead) + len(g.facts), "threads": len(g.threads),
                   "kept_state": kept["state"], "kept_facts": kept["facts"], "kept_threads": kept["threads"],
                   "placed": {k: sum(1 for e in placed if e["kind"] == k)
                              for k in ("state", "thread", "fact", "claim", "secret", "summary", "excerpt", "quote")},
                   "path": g.path, "quotes": g.quotes, "quote_mode": g.quote_note,  # the forensic path (PHASE-33 Q4)
                   "cast": sum(1 for e in placed if e.get("section") == "cast"),
                   "scene_cast": sorted(g.cast.values()), "memory_mode_withheld": g.withheld,
                   "replaced_left_out": g.replaced, "ended_left_out": g.ended,  # packet-v12 (PHASE-31 Q1, Q2)
                   "memory_cut": cut, "fits_at": fit,
                   "embedding_projection": options.embed_projection[:20] if options.embedder else None,
                   "extractor": (options.extractor_key or "")[:20] or None,
                   **{f"client_{k}": v for k, v in request.client_timings_ms.items()}}),
            "fresh" if fresh else "stale",
            options.policy, request.budget_tokens, upto if fresh else None, previous_ai,
            Jsonb(sorted(in_context)), options.extractor_key,
            options.embed_projection if options.embedder else None, options.rules_version,
            Jsonb({**recorded_options(options), "canon_names": g.canon_names, "canon_facts": g.canon_facts,
                   "fill": fill(request.budget_tokens, options.policy)}),  # the growth its budget bought (ADR 0049)
            Jsonb(compiled.ledger),
            getattr(request, "canon_manifest_id", None),  # ADR 0045
            Jsonb(sorted(set(getattr(request, "canon_held", None) or []))),
        ),
    )
    return {"freshness": "fresh" if fresh else "stale", "trace_id": trace_id, "text": compiled.text,
            "tokens": compiled.tokens, "count": len(compiled.excerpts), "memory": memory, "conversation_id": conv.id,
            "vectors": ("fallback" if g.vector_note.startswith("fallback") else g.vector_note) if fresh else None}
