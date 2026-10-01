"""Recall over the head membership: lexical (pg_trgm, D11) + optional vectors (Phase 3), fused with RRF.

Also assembles the packet sections: state (Phase 1), facts (Phase 2), excerpts.
"""

from __future__ import annotations

import dataclasses
import math
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from .entities import norm
from .facts import FIRST_CUE, LIVE, STANDING, claim_entry, fact_entry, memory_view, relevant_facts, thread_entry
from . import scene, spans, summaries, variants
from .ids import uuid7
from .ledger import find_conversation
from .llm import Embedder, LLMError
from .normtext import NORMALIZER_VERSION
from .packet import (ABOUT_POLICIES, BEFORE_POLICIES, CAST_POLICIES, CAUSE_POLICIES, DEFAULT_POLICY, FILL_FACTS_MAX,
                     GROW_POLICIES, grown_excerpt,
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
    strict: bool = False  # this chat's memory mode (ADR 0035): withhold what only some of the scene know
    narrator: str | None = None  # this chat is told in this character's first person (ADR 0035)
    summarize_key: str | None = None  # summaries of this generation in <Story> (packet-v8, ADR 0043); None: off
    canon_key: str | None = None  # canon facts of this generation (ADR 0047); None: off
    lexical_keywords: bool = True  # the keyword route (ADR 0052); a trace that did not record it replays with it off
    first_cue: bool = True  # how it started, when the message asks (ADR 0056); a trace without it replays with it off
    history_marks: bool = True  # earlier versions only under marks that cover them (ADR 0038 amendment 1); same replay rule
    name_variants: bool = True  # a given name, a Hangul spelling of a romanized name (ADR 0058); same replay rule
    excerpt_chars: int = MAX_EXCERPT_CHARS  # an excerpt's length at most; derived from the budget (`filled`), not recorded
    fill_facts: int = 0  # fact slots the budget adds, for facts kept from no one (`filled`, ADR 0049), not recorded


# What a trace records of its RecallOptions, so a replay compiles with the same ones (ADR 0027).
RECORDED = ("top_k", "threshold", "facts_limit", "events_limit", "threads_limit", "vector_min_sim", "query_prefix",
            "embed_timeout_ms", "lexical_timeout_ms", "strict", "narrator", "summarize_key", "canon_key",
            "lexical_keywords", "first_cue", "history_marks", "name_variants")
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
    vector_note: str = "off"
    cast: dict[str, str] = field(default_factory=dict)  # scene cast, entity key → name (ADR 0034)
    note: str = ""  # added to the packet's Note (a first-person narrator, ADR 0035)
    withheld: int = 0  # lines and excerpts the chat's memory mode left out or replaced (ADR 0035)
    canon_names: str | None = None  # the canon manifest whose names the read used (ADR 0046)
    canon_facts: str | None = None  # the canon manifest whose facts it used; None: none (ADR 0047)
    withheld_lines: list[Line] = field(default_factory=list)
    secret_pairs: set[tuple[frozenset[str], frozenset[str]]] = field(default_factory=set)  # (holders, absent) given a Secret line
    story: list[Line] = field(default_factory=list)  # summaries (packet-v8, ADR 0043)
    cast_lines: list[tuple[str, list[Line]]] = field(default_factory=list)  # each scene character's state (packet-v8)


def gather(conn: psycopg.Connection, head: UUID, query: str, previous_ai: str, in_context: set[str],
           options: RecallOptions, upto: int | None = None, known_at: datetime | None = None,
           canon_manifest: str | None = None, canon_exact: bool = False, canon_held: Iterable[str] = (),
           canon_facts: Any = LIVE, vectors_now: bool = False) -> Gathered:
    """Candidates for one request, already normalized (`clean_text`). `upto` and `known_at` gather them as
    of an earlier request: the head up to that position, and what NMOS had derived by that time. The canon keys the
    prompt held count as in context: the host sent their text, so their facts are not sent again (D3, ADR 0047).
    `vectors_now` searches vectors as they are now whatever `known_at` says (a replay's named projection)."""
    started = time.perf_counter()
    g = Gathered()
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
    if query.strip():
        cut = _cut(conn, head, upto)
        lexical, g.lexical_note = _lexical(conn, head, query, previous_ai, cut, options.threshold,
                                           options.lexical_timeout_ms, upto)
        g.timings["lexical"] = round((time.perf_counter() - started) * 1000, 2)
        if options.lexical_keywords:
            t0 = time.perf_counter()
            keyword, g.keyword_note = _keyword_lexical(conn, head, keywords(query), cut, options.lexical_timeout_ms,
                                                       upto)
            g.timings["keywords"] = round((time.perf_counter() - t0) * 1000, 2)
        if options.embedder is not None:
            t0 = time.perf_counter()
            try:
                (qvec,) = options.embedder.embed([options.query_prefix + query],
                                                 timeout_s=options.embed_timeout_ms / 1000)
                g.timings["embed"] = round((time.perf_counter() - t0) * 1000, 2)
                vector = vector_candidates(conn, head, qvec, options.embed_projection, cut, CANDIDATE_LIMIT,
                                           upto, None if vectors_now else known_at)
                g.timings["vector"] = round((time.perf_counter() - t0) * 1000 - g.timings["embed"], 2)
                g.vector_note = "on"
            except (LLMError, ValueError) as exc:  # fail open to lexical-only
                g.vector_note = f"fallback: {exc}"[:200]
    g.candidates = fuse(lexical, vector, options.threshold, options.vector_min_sim, keyword)
    g.excluded = [c for c in g.candidates if c["host_logical_id"] in in_context]
    eligible = [c for c in g.candidates if c["host_logical_id"] not in in_context][: options.top_k]
    focus = f"{query} {previous_ai}"
    # The turn the packet shows: the message's turn index since packet-v7, as facts have it (ADR 0041).
    by_turn = options.policy in TURN_POLICIES
    words = keywords(query) if options.policy in GROW_POLICIES else []
    for c in eligible:
        # a lexical or keyword hit is the whole message; a vector-only hit is its chunk
        clean = (c["clean"] if c.get("user_score") or c.get("keyword_score")
                 else c["clean"][c["text_start"]:c["text_end"]])
        if options.policy in GROW_POLICIES:  # packet-v10: grown to its length from the best sentence (ADR 0053)
            text, short = grown_excerpt(clean, focus, words, options.excerpt_chars)
        else:
            text = excerpt(clean, focus, max_chars=options.excerpt_chars)
            short = excerpt(clean, focus, window=1, max_chars=options.excerpt_chars)
        g.ranked.append(Excerpt(turn=c["turn"] if by_turn else c["position"],
                                speaker=c["name"] or ("user" if c["role"] == "user" else "character"),
                                text=text, score=float(c["rrf"]), revision_id=str(c["id"]), short=short,
                                position=c["position"]))
    if options.rules_version != "none":
        g.state = [StateItem(key=r["key"], value=r["value"], turn=r["turn"] if by_turn else r["position"])
                   for r in current_state(conn, head, options.rules_version, upto)
                   if r["host_logical_id"] not in in_context]
        # Sim bots track many characters: state of characters mentioned right now gets the budget first.
        g.state.sort(key=lambda i: ("." in i.key and i.key.split(".", 1)[0] in focus), reverse=True)
    view = None
    if options.facts_limit > 0 or options.threads_limit > 0:
        view = memory_view(conn, head, options.extractor_key, upto, known_at, canon_manifest, canon_exact,
                           options.canon_key, canon_facts)
        g.canon_names, g.canon_facts = view.get("canon_names"), view.get("canon_facts_manifest")
        r = view["resolution"]
        persona = r.persona_names if r else frozenset()
        aliases = _aliases(r, query, previous_ai, options, view)
        # Who is in the scene, so facts only some of them know are marked (packet-v3, ADR 0034).
        g.cast = scene.cast(view["facts"] + view["claims"] + view["other"], r, query, previous_ai,
                            _head_turn(conn, head, upto), aliases=aliases)
        if options.threads_limit > 0:
            g.threads = _moded([thread_entry(t, scene.private(t, g.cast, r)) for t in
                                relevant_threads(view["threads"], query, previous_ai, in_context,
                                                 options.threads_limit, persona,
                                                 about=options.policy in ABOUT_POLICIES, aliases=aliases)],
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
                                    len(view["facts"]) if grow else options.facts_limit,
                                    options.events_limit, persona, scene.names(g.cast, r, aliases), causes=causes,
                                    first_cue=first, window_start=start, marks=options.history_marks, aliases=aliases)
            facts = _grown(ranked[:options.facts_limit], ranked, options.fill_facts)
            # Claims after facts, so the budget serves narration first (ADR 0013).
            ranked = relevant_facts(view["claims"], query, previous_ai, in_context,
                                    len(view["claims"]) if grow else claims_limit, persona=persona, causes=causes,
                                    first_cue=first, window_start=start, marks=options.history_marks, aliases=aliases)
            claims = _grown(ranked[:claims_limit], ranked,
                            max(1, (options.facts_limit + options.fill_facts) // 2) - claims_limit)
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
        if g.withheld_lines:
            # An excerpt that says what the mode withheld would give it back word for word.
            kept = [e for e in g.ranked
                    if not any(spans.reuse(line.content, e.text) >= REPEATS for line in g.withheld_lines)]
            g.withheld += len(g.ranked) - len(kept)
            g.ranked = kept
        if options.narrator:
            who = scene.display(r, options.narrator) if r is not None else options.narrator
            g.note = f" The story is told in the first person by {who}: only what they know is listed."
        if options.policy in CAST_POLICIES and r is not None:
            g.cast_lines, used = cast_groups(view, g.cast, r, query, options, in_context, aliases)
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
        aliases = _aliases(r, query, previous_ai, options, view) if view else None
        if view and not g.cast and r is not None:
            g.cast = scene.cast(view["facts"] + view["claims"] + view["other"], r, query, previous_ai,
                                _head_turn(conn, head, upto), aliases=aliases)
        g.story = summaries.packet_lines(conn, head, options.summarize_key, view["secrets"] if view else [], query,
                                         in_context, upto, known_at,
                                         scene.names(g.cast, r, aliases) if r is not None else frozenset())
    # The keyword route adds no raw text that repeats a secret still kept from someone (ADR 0052, owner 2026-09-30):
    # an excerpt only it found is left out when it does, so it places no secret the other routes would not. The same
    # test as a summary's (PHASE-12 Q3), stricter when someone it is kept from is in the scene.
    keyword_only = {str(c["id"]) for c in g.candidates if _keyword_only(c, options)}
    if keyword_only and any(e.revision_id in keyword_only for e in g.ranked) and options.extractor_key:
        if view is None:
            view = memory_view(conn, head, options.extractor_key, upto, known_at, canon_manifest, canon_exact,
                               options.canon_key, canon_facts)
        r = view["resolution"]
        aliases = _aliases(r, query, previous_ai, options, view)
        cast = g.cast
        if not cast and r is not None:  # facts, threads and summaries off: the scene still sets the bar
            cast = scene.cast(view["facts"] + view["claims"] + view["other"], r, query, previous_ai,
                              _head_turn(conn, head, upto), aliases=aliases)
        present = scene.names(cast, r, aliases) if r is not None else frozenset()
        kept = []
        for e in g.ranked:
            if e.revision_id not in keyword_only:
                kept.append(e)
            elif not any(summaries.leaks(form, view["secrets"], present) for form in (e.text, e.short) if form):
                kept.append(dataclasses.replace(e, cut_ok=False))  # the forms checked are the only ones placed
        g.keyword_withheld = len(g.ranked) - len(kept)
        g.ranked = kept
    return g


def _aliases(r: Any, query: str, previous_ai: str, options: RecallOptions,
             view: dict[str, Any]) -> dict[str, frozenset[str]] | None:
    """The other names the characters go by in this request (`name_variants`, ADR 0058), or None."""
    if not options.name_variants or r is None:
        return None
    marked = {n for row in view["facts"] + view["claims"] + view["other"]
              for n in (*(row.get("known_by") or ()), *(row.get("hidden_from") or ()))}
    return variants.aliases(r.entities(), r.persona_names, f"{query} {previous_ai}", marked)


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
                         note=g.note, story=g.story, cast=g.cast_lines)


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
    g = (gather(conn, head, query, previous_ai, in_context, filled(options, request.budget_tokens), upto,
                canon_manifest=getattr(request, "canon_manifest_id", None),
                canon_held=getattr(request, "canon_held", None) or ()) if fresh else Gathered())
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
                   "keyword_withheld": g.keyword_withheld,
                   "vector_mode": g.vector_note,
                   "state_items": len(g.state), "facts": len(g.lead) + len(g.facts), "threads": len(g.threads),
                   "kept_state": kept["state"], "kept_facts": kept["facts"], "kept_threads": kept["threads"],
                   "placed": {k: sum(1 for e in placed if e["kind"] == k)
                              for k in ("state", "thread", "fact", "claim", "secret", "summary", "excerpt")},
                   "cast": sum(1 for e in placed if e.get("section") == "cast"),
                   "scene_cast": sorted(g.cast.values()), "memory_mode_withheld": g.withheld,
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
