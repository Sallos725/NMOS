"""Recall over the head membership: lexical (pg_trgm, D11) + optional vectors (Phase 3), fused with RRF.

Also assembles the packet sections: state (Phase 1), facts (Phase 2), excerpts.
"""

from __future__ import annotations

import dataclasses
import logging
import math
import re
import threading
import time
from collections.abc import Callable, Collection, Iterable, Mapping
from concurrent.futures import Future
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from .entities import PERSONA, norm
from .facts import _started_before, FIRST_CUE, FIRST_PERSON, FUNCTION_SYLLABLES, HISTORY_CUE, LIVE, STANDING, WHY, claim_entry, excluded_ids, fact_entry, fact_line, fact_text, lexically_related, memory_view, relevant_facts, settled_entry, thread_entry, told_entry
from . import absence, coverage, mentions, overuse, quotes, rerank, scene, spans, statechange, summaries, variants, source_time
from .gone import is_gone_place, is_gone_status, is_gone_vital
from .ids import uuid7
from .ledger import find_conversation
from .llm import Embedder, LLMError
from . import normtext
from .rerank import Reranker
from .packet import (ABOUT_POLICIES, ANCHOR_POLICIES, BEFORE_POLICIES, NAMED_POLICIES, CAST_POLICIES, CAUSE_POLICIES,
                     CHANGE_POLICIES, CONTENTS, COVERAGE_POLICIES, GONE_POLICIES, LABEL_POLICIES, STATE_HISTORY_KEYS,
                     STATE_HISTORY_MAX, STATE_HISTORY_POLICIES, PERSONA_QUESTION_POLICIES, RELATED_FILL_POLICIES,
                     SOURCE_CLOCK_POLICIES, STATUS_CHANGE_POLICIES, KEYWORD_PARTICLE_POLICIES,
                     QUOTE_POLICIES, UNEXTRACTED_POLICIES, REST_POLICIES, RETURN_GAP_POLICIES, SETTLED_POLICIES,
                     PIN_POLICIES, SEM_QUERY_POLICIES, HAPPENED_POLICIES, TOLD_POLICIES, V21_POLICIES, EXCERPT_FLOOR,
                     CUE_GROW_CHARS,
                     DEFAULT_POLICY, FILL_FACTS_MAX, GROW_POLICIES, SPAN_POLICIES, grown_excerpt,
                     MAX_EXCERPT_CHARS, MEMORY_KINDS, REPEATS, STORY_POLICIES, TURN_POLICIES, Compiled, Excerpt, Line,
                     StateItem, anchor_rank, clean_text, compile_lines, coverage_note, cut_lines, excerpt, fill,
                     fits_at, kept_counts, hidden_entry, secret_line,
                     secret_text)
from .state import CARD_SQL, current_state, history as state_history, windows as state_windows
from .threads import relevant_threads, similarity
from .vectors import vector_candidates
from .keywords import keywords, particle_lookup
from . import carry
from .carry import Carried
from .packet import CARRY_POLICIES, CAST_EXTRA
from .predicates import address_slot
from .facts import SITUATIONAL_ADDRESS_MAX, earlier, first as first_version
from xml.sax.saxutils import escape as xml_escape

CANDIDATE_LIMIT = 50
# packet-v17 (PHASE-39 Q3b): a message that asks how a status value changed: the past (HISTORY_CUE), when, how much,
# since, or a word of change.
STATE_CHANGE_CUE = re.compile(HISTORY_CUE.pattern + r"|언제|얼마나|부터|동안|바뀌|바꼈|변화|변했|올랐|올라갔|늘었|늘어났|줄었"
                              r"|줄어들|떨어졌|\bwhen\b|\bsince\b|how much|how many|\bchanged?\b|went (?:up|down)"
                              r"|\brose\b|\bdropped\b|\bgained\b|\blost\b", re.IGNORECASE)


def _turn_of(entry: dict[str, Any], by_turn: bool) -> int | None:
    return entry["turn"] if by_turn else entry["position"]


# Words a status bar and a message use for the same key (PHASE-39 Q3b): a card's bar is often in English while its
# chat is in Korean ("Level", "레벨 언제 올랐어?"). Each group names one thing; a key in a group is asked about by any
# word of it.
STATUS_WORDS = tuple(frozenset(g) for g in (
    ("level", "lv", "lvl", "레벨"), ("exp", "xp", "experience", "경험치"), ("hp", "health", "체력", "생명력"),
    ("mp", "mana", "마나", "마력"), ("sp", "stamina", "스태미나", "기력"),
    ("gold", "money", "coin", "coins", "currency", "currencies", "골드", "재화", "소지금", "코인"),
    ("item", "items", "inventory", "아이템", "인벤토리", "소지품"), ("statpoints", "statpoint", "스탯포인트"),
    ("weapon", "weapons", "무기"), ("armor", "armour", "방어구", "갑옷"), ("skill", "skills", "스킬"),
    ("quest", "quests", "퀘스트"), ("location", "place", "위치", "장소"), ("time", "시간"), ("date", "날짜"),
    ("mood", "기분"), ("weather", "날씨")))


def asked_keys(query: str, keys: list[str], every_window: bool = False) -> list[str]:
    """The status keys a message names (PHASE-39 Q3b), in the order it names them: a key of two characters or more as
    the bar writes it, case and spacing aside, or a word of its STATUS_WORDS group; a word where a word starts ("HP",
    not the "hp" of another word; 마나, not the 마나 of 얼마나), a Korean one with any particle after it; a sim bot's
    "<character>.<key>" when the message names both. With `every_window` (`packet-v21`, PHASE-65), a message that
    names no character any key is prefixed with asks that key of every character ("HP 얼마야?" with two characters'
    windows); earlier policies keep asking none there, so their recorded requests replay as they were."""
    text = query.casefold()

    def at(word: str) -> int:
        word = re.sub(r"\s+", "", word.casefold())
        if len(word) < 2:
            return -1
        spaced = r"\s*".join(map(re.escape, word))  # spacing aside: "stat points", "스탯 포인트"
        m = re.search(rf"(?<![a-z0-9]){spaced}(?![a-z0-9])" if word.isascii() else rf"(?<![가-힣]){spaced}", text)
        return m.start() if m else -1

    def first(name: str) -> int:
        plain = re.sub(r"\s+", "", name.casefold())
        words = {name, *(w for g in STATUS_WORDS if plain in g for w in g)}
        return min((x for x in map(at, words) if x >= 0), default=-1)

    found = []
    for key in keys:
        entity, _, name = key.rpartition(".")
        where = first(name)
        # a character's key ("하나.HP") is asked when the message names that character; with `every_window`, also
        # when it names no character any key is prefixed with (status windows are prefixed only when one reply holds
        # two characters' windows, or by a sim bot's rule)
        if where >= 0 and (not entity or at(entity) >= 0 or (
                every_window and not any(at(k.rpartition(".")[0]) >= 0 for k in keys if "." in k))):
            found.append((where, -len(name), key))
    return [k for _, _, k in sorted(found)]


# A query that matches more head messages than this is too broad to score (a character's name alone,
# a phrase every reply repeats): lexical recall abstains for it instead of scoring most of the chat
# (Track A, A3; docs/perf/scale.md). Vectors, state and facts still run.
BROAD_LIMIT = 200
RRF_K = 60
# The keyword route (PHASE-18, ADR 0052): each keyword of the user's message (keywords.py) is looked up on its own at
# this word_similarity bar, near an exact match of the word. A keyword in more than BROAD_LIMIT head messages, or in
# more than half of them, names what every scene holds (a main character) and is dropped.
KEYWORD_THRESHOLD = 0.8
# Index envelope only: a whole two-syllable keyword before a particle retains
# at least two of its three boundary trigrams. Exact admission is checked below.
PARTICLE_PREFILTER = 0.6
# Each keyword's lookup gets at most this long; a word that takes longer is as common as a dropped one (a two-syllable
# word's three trigrams can leave the index thousands of long messages to recheck), so it is dropped and the other
# keywords still run (measured at 10,000 messages: 2–3 ms for a rare word, 37 ms for one capped at 201 matches).
KEYWORD_SLICE_MS = 25
# A head of at most this many messages and characters is looked up by its own revisions (ADR 0052 amendment 1): the
# trigram index spans every chat's revisions, and rechecking another chat's long messages took a short chat's keyword
# past its slice. Restricted, the planner rechecks every head revision instead, so the cost follows the head's text: on a
# trial install's recorded requests, heads under 100,000 characters went from 72 of 245 word lookups over 25 ms to 0,
# larger ones from 75 of 276 to 257. Past 500 messages the id list itself costs ~1 ms a statement per 500 more.
HEAD_FIRST_MAX = 500
HEAD_FIRST_CHARS = 100_000
QWEN3_QUERY_INSTRUCTION = ("Instruct: Given a question or remark from a role-play chat, retrieve the earlier story "
                           "passage that answers or relates to it\nQuery: ")
# Candidates must match the user's message; the previous AI turn only breaks ties in ranking
# (as a filter it pulled in near-duplicate filler during manual testing).
AI_TIEBREAK_WEIGHT = 0.2
# The query embedding's whole HTTP exchange runs this many times `embed_timeout_ms`: long enough
# to answer while recall reads and for the wait after them (QueryEmbedding), short enough that a call the request has
# given up on ends soon after, instead of holding the embedder for the next request (ADR 0061).
EMBED_CALL_FACTOR = 2
# Bound abandoned calls even when OS resolver/transport cleanup outlives async cancellation. Saturation falls back
# to lexical recall immediately. Prefetch shares the same bound; no waiting work queue accumulates.
QUERY_EMBED_MAX_INFLIGHT = 8
_QUERY_EMBED_SLOTS = threading.BoundedSemaphore(QUERY_EMBED_MAX_INFLIGHT)
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
    HTTP task has a total deadline of EMBED_CALL_FACTOR × the timeout. OS DNS resolution/transport cleanup can
    outlive cancellation; the shared slot cap bounds these outstanding threads too. No thread touches a DB connection."""

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
        if not _QUERY_EMBED_SLOTS.acquire(blocking=False):
            self._future.set_exception(LLMError("query embedding concurrency limit reached"))
            return
        started = time.perf_counter()
        try:
            (vec,) = embedder.embed([text], timeout_s=self.call_timeout_ms / 1000)
        except BaseException as exc:  # noqa: BLE001 — re-raised to the waiter, which classifies it
            self._future.set_exception(exc)
            return
        finally:
            _QUERY_EMBED_SLOTS.release()
        self.call_ms = round((time.perf_counter() - started) * 1000, 2)
        self._future.set_result(vec)

    def failed(self) -> bool:
        """Whether the call has already ended in an error. A prefetched call that failed (the embedder down for the
        moment of the sync) is not given to its request: the request asks again, as one without a prefetch does."""
        return self._future.done() and self._future.exception() is not None

    def result(self) -> list[float]:
        """The vector, waiting at most `timeout_ms` from now. LLMError when it is not there by then (the thread's call
        is cancelled at its HTTP deadline; cleanup can outlast it), or when the call failed; a ValueError (an answer of the
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
    replies_only: bool = False  # this chat remembers the AI's replies only (PHASE-48): no user message is a candidate
    narrator: str | None = None  # this chat is told in this character's first person (ADR 0035)
    summarize_key: str | None = None  # summaries of this generation in <Story> (packet-v8, ADR 0043); None: off
    canon_key: str | None = None  # canon facts of this generation (ADR 0047); None: off
    lexical_keywords: bool = True  # the keyword route (ADR 0052); a trace that did not record it replays with it off
    source_clock: bool = True  # PHASE-42: source-status clock on temporal questions; old traces default off
    keyword_particles: bool = True  # PHASE-41: v18 exact Korean particle hits; old traces default off
    # PHASE-43 S4: under STATUS_CHANGE_POLICIES (packet-v18, -v19), the status as core values and changes, placed
    # even when its bar's message is in context (presets strip status bars from the prompt); old traces default off.
    # `state_pins`: keys always told.
    state_changes: bool = True
    state_pins: tuple[str, ...] = ()
    # PHASE-43 S2: each card's pinned status keys, from the configuration; a request takes its card's as `state_pins`
    # (recorded). Not recorded itself.
    pins_by_card: tuple[tuple[str, tuple[str, ...]], ...] = ()
    first_cue: bool = True  # how it started, when the message asks (ADR 0056); a trace without it replays with it off
    history_marks: bool = True  # earlier versions only under marks that cover them (ADR 0038 amendment 1); same replay rule
    name_variants: bool = True  # a given name, a Hangul spelling of a romanized name (ADR 0058); same replay rule
    # PHASE-60 S8: `@name` pins a character for the request (packet-v20). Not recorded: a request records its pins.
    pin_at_mentions: bool = False
    # PHASE-60 S5 (ADR 0084): the configured reranker, None when off. Never recorded: it holds a credential.
    reranker: Reranker | None = None
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
            "lexical_keywords", "keyword_particles", "state_changes", "state_pins", "source_clock", "first_cue", "history_marks", "name_variants", "excerpt_anchor", "rest_after",
            "replies_only")
CAST_MAX = 4  # scene characters with a <Cast> group (PHASE-12 Q4)
CAST_GOALS, CAST_ITEMS = 2, 3
CAST_PREDICATES = ("located_in", "has_status", "feels_toward", "possesses")
GONE_MAX = 8  # packet-v20: gone characters pinned at most (PHASE-60 S3)
TOLD_MAX = 2  # packet-v20: lines of who told whom at most (PHASE-60 S8, proposal)
PIN_EXTRA = 3  # packet-v20: <Cast> groups for pinned characters beyond the cast's own CAST_MAX (PHASE-60 S8)
REGRESSION_MAX = 6  # packet-v20: lines of a previous timeline in one packet at most (PHASE-60 S6, ADR 0085 item 5)


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


def unrelated_question(query: str, named: set[str], facts: list[dict[str, Any]]) -> bool:
    """A question (it ends with a question mark) that names no one (`named`, the facts its names select) and shares no
    fact's words at the lexical bar (PHASE-46). Narration without a name is not one: measured on the trial install, a
    rule without the question mark changed 14 of 80 real requests."""
    return query.rstrip().endswith(("?", "？")) and not named and not lexically_related(facts, query)


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


SEM_QUERY_MAX_CHARS = 40  # packet-v20 (PHASE-60 S5, ADR 0084): messages shorter than this embed with the previous reply
SEM_QUERY_REPLY_TAIL = 400


def sem_query(query: str, previous_ai: str) -> str | None:
    """Embedding text for a short message under packet-v20 (PHASE-60 S5, ADR 0084): the previous reply's last
    400 characters, a line break, and the message when the stripped message is shorter than 40 characters and
    there is a previous reply; None otherwise. Both inputs are already `clean_text`-normalized."""
    if not query.strip() or len(query.strip()) >= SEM_QUERY_MAX_CHARS or not previous_ai.strip():
        return None
    return f"{previous_ai[-SEM_QUERY_REPLY_TAIL:]}\n{query}"


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
             threshold: float, timeout_ms: int, upto: int | None = None,
             ids: list[UUID] | None = None, replies: bool = False) -> tuple[list[dict[str, Any]], str]:
    """Lexical candidates over the normalized projection (#9) and the trace mode: "on", "too_broad"
    (more than BROAD_LIMIT matches) or "timeout". Recall abstains from lexical candidates in the last two."""
    try:
        with conn.transaction():  # savepoint: a cancelled statement does not abort the request
            previous = conn.execute("SELECT " + ", ".join(f"current_setting('{k}') AS \"{k}\""
                                                          for k in _RESTORED)).fetchone()
            wanted = {"pg_trgm.word_similarity_threshold": str(threshold), "enable_seqscan": "off",
                      "enable_indexscan": "off", "statement_timeout": str(timeout_ms)}
            _apply(conn, wanted)
            matches = _lexical_matches(conn, head, query, cut, BROAD_LIMIT + 1, upto, ids)
            rows = (_lexical_candidates(conn, head, matches, query, previous_ai, replies) if len(matches) <= BROAD_LIMIT
                    else None)
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
# PHASE-48 D3: a chat remembering the AI's replies only has no user message among its candidates, on any route. With
# the flag off the clause is true for every row, so every route returns what it did.
REPLIES_ONLY = "AND NOT (%(replies)s AND coalesce(sr.metadata->>'role', '') = 'user')"
_MATCHES_HEAD = """
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
    """
_MATCHES = """
    WITH hit AS MATERIALIZED (
        SELECT source_revision_id, normalizer FROM revision_text WHERE %(q)s <%% clean_content
    )
    """ + _MATCHES_HEAD + " LIMIT %(limit)s"
# Exact-particle lookup only, after legacy keyword lookups (PHASE-41). The
# coarse trigram envelope covers every word boundary; two cheap LIKE guards
# avoid expensive trigram rechecks for common start/space-prefixed occurrences.
# Both boundaries and the finite particle suffix are checked before counting.
_PARTICLE_MATCHES = """
    WITH hit AS MATERIALIZED (
        SELECT source_revision_id, normalizer, clean_content FROM revision_text
        WHERE clean_content LIKE ANY(%(prefixes)s) OR %(q)s <%% clean_content
    )
    """ + _MATCHES_HEAD + """
      AND hit.clean_content ~ %(particle)s
    LIMIT %(limit)s
    """


def _matches_params(head: UUID, query: str, cut: int, limit: int, upto: int | None = None,
                    ids: list[UUID] | None = None) -> dict[str, Any]:
    return {"head": head, "q": query, "cut": cut, "limit": limit, "norm": normtext.active(),
            "upto": 2**31 - 1 if upto is None else upto, "ids": ids}


_HIT_WHERE = re.compile(r"FROM revision_text\s+WHERE ([^\n]*)")


def _head_first(sql: str) -> str:
    """`sql`'s lookup over the head's own revisions (`ids`) instead of the trigram index, the rest of the statement
    unchanged: the head filters after it still decide, so the matches are the same and no other chat's message is
    rechecked. The revisions are read first behind an `OFFSET 0` fence: left to the planner, the index path came back
    with its statistics and rechecked a 10,000-message chat for a 41-message one."""
    return _HIT_WHERE.sub(lambda m: "FROM (SELECT * FROM revision_text WHERE source_revision_id = ANY(%(ids)s::uuid[])"
                                    f" OFFSET 0) AS revision_text WHERE {m[1]}", sql, count=1)


def _head_ids(conn: psycopg.Connection, head: UUID, cut: int, upto: int | None = None) -> list[UUID] | None:
    """The revisions a lookup may find on the head (after the cut, up to `upto`), or None past HEAD_FIRST_MAX messages
    or HEAD_FIRST_CHARS characters: then the index-first lookup is the cheaper one."""
    rows = conn.execute(
        "SELECT am.source_revision_id AS id, coalesce(rt.clean_chars, 0) AS chars FROM active_membership am"
        " LEFT JOIN revision_text rt ON rt.source_revision_id = am.source_revision_id AND rt.normalizer = %s"
        " WHERE am.commit_id = %s AND am.position > %s AND am.position <= %s LIMIT %s",
        (normtext.active(), head, cut, 2**31 - 1 if upto is None else upto, HEAD_FIRST_MAX + 1)).fetchall()
    if len(rows) > HEAD_FIRST_MAX or sum(r["chars"] for r in rows) > HEAD_FIRST_CHARS:
        return None
    return [r["id"] for r in rows]


def _lexical_matches(conn: psycopg.Connection, head: UUID, query: str, cut: int, limit: int,
                     upto: int | None = None, ids: list[UUID] | None = None) -> list[UUID]:
    """Active head revisions the query matches (`<%`), at most `limit`: the statement stops there, after checking the
    trigram index's candidates up to that many head matches (candidates of other chats and earlier revisions are checked
    too, then left out), so a broad query is dropped by its slice or the timeout. Never prepared on the server: after
    five runs Postgres may plan a prepared statement without its parameters, and without the word it cannot tell that
    the trigram index is the narrow way in. Either slow plan took a keyword past its slice, which dropped it as if it
    were too common, and a replay could find what its request had not (ADR 0027)."""
    sql = _MATCHES if ids is None else _head_first(_MATCHES)
    return [r["id"] for r in conn.execute(sql, _matches_params(head, query, cut, limit, upto, ids),
                                          prepare=False).fetchall()]


def _lexical_candidates(conn: psycopg.Connection, head: UUID, ids: list[UUID], query: str,
                        previous_ai: str, replies: bool = False) -> list[dict[str, Any]]:
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
        """ + REPLIES_ONLY + """
        ORDER BY score DESC, am.position DESC
        LIMIT %(limit)s
        """,
        {"head": head, "ids": ids, "q": query, "ai": previous_ai, "w": AI_TIEBREAK_WEIGHT, "limit": CANDIDATE_LIMIT,
         "norm": normtext.active(), "replies": replies},
    ).fetchall()


def _keyword_lexical(conn: psycopg.Connection, head: UUID, words: list[str], cut: int, timeout_ms: int,
                     upto: int | None = None, *, particles: bool = False,
                     head_ids: list[UUID] | None = None, replies: bool = False,
                     v21: bool = False) -> tuple[list[dict[str, Any]], str]:
    """The keyword route (ADR 0052): messages holding the message's keywords, scored by the keywords' rarity
    (log of messages over matches, summed), best first, and the trace mode: "on", "none" (no keyword), "too_broad"
    (every keyword dropped as too common) or "timeout". All keywords share one budget of `timeout_ms`.
    With particles, exact additions spend only each word's unused slice and follow the unchanged legacy list.
    """
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

    def within(most: float | None = None, *, threshold: float | None = None) -> None:
        """This connection's statement timeout: what is left of the route's budget (at most `most` ms)."""
        left = (deadline - time.perf_counter()) * 1000
        if left < 1:
            raise psycopg.errors.QueryCanceled()
        settings = {"statement_timeout": str(max(1, int(left if most is None else min(left, most))))}
        if threshold is not None:
            settings["pg_trgm.word_similarity_threshold"] = str(threshold)
        _apply(conn, settings)

    weights: dict[Any, float] = {}
    additions: dict[Any, float] = {}
    # Only complete, non-broad legacy lookups can supply a trustworthy combined
    # denominator. Each supplemental lookup spends the same word's unused slice.
    supplements: list[tuple[str, set[UUID], float]] = []
    found = dropped = 0
    try:
        with conn.transaction():  # savepoint: a cancelled statement does not abort the request
            previous = conn.execute("SELECT " + ", ".join(f"current_setting('{k}') AS \"{k}\""
                                                          for k in _RESTORED)).fetchone()
            _apply(conn, {"pg_trgm.word_similarity_threshold": str(KEYWORD_THRESHOLD), "enable_seqscan": "off",
                          "enable_indexscan": "off"})
            for word in words:
                started = time.perf_counter() if particles else 0.0
                try:
                    with conn.transaction():  # the original legacy lookup and its original slice
                        within(KEYWORD_SLICE_MS)
                        ids = _lexical_matches(conn, head, word, cut, BROAD_LIMIT + 1, upto, head_ids)
                except psycopg.errors.QueryCanceled:
                    if (deadline - time.perf_counter()) * 1000 < 1:
                        raise  # the route's budget, not the word's slice, ran out
                    found += 1
                    dropped += 1
                    continue
                remaining = KEYWORD_SLICE_MS - (time.perf_counter() - started) * 1000 if particles else 0.0
                if not ids:
                    if particles:
                        supplements.append((word, set(), remaining))
                    continue
                found += 1
                within()
                n = total()
                if len(ids) > BROAD_LIMIT or len(ids) * 2 > n:
                    dropped += 1
                    continue
                weight = math.log(n / len(ids))  # the original rarity and order are preserved
                for i in ids:
                    weights[i] = weights.get(i, 0.0) + weight
                if particles:
                    supplements.append((word, set(ids), remaining))
            if particles and len(weights) < CANDIDATE_LIMIT:
                for word, legacy_ids, remaining in supplements:
                    particle = particle_lookup(word, v21=True) if v21 else particle_lookup(word)
                    if particle is None or remaining < 1:
                        continue
                    prefixes, pattern = particle
                    started = time.perf_counter()
                    try:
                        with conn.transaction():  # losing an addition must not discard a valid legacy hit
                            within(remaining, threshold=PARTICLE_PREFILTER)
                            # Index-first even for a short head: kept to the head's revisions, the planner rechecks
                            # every one of them with the boundary pattern and the word's slice runs out.
                            params = _matches_params(head, word, cut, BROAD_LIMIT + 1, upto)
                            exact_ids = {r["id"] for r in conn.execute(
                                _PARTICLE_MATCHES, params | {"prefixes": prefixes, "particle": pattern},
                                prepare=False).fetchall()}
                            # A backend may deliver a result after its SQL timeout.
                            # Do not admit it beyond this word's remaining allowance.
                            finished = time.perf_counter()
                            if (finished - started) * 1000 >= remaining or (deadline - finished) * 1000 < 1:
                                raise psycopg.errors.QueryCanceled()
                    except psycopg.errors.QueryCanceled:
                        if (deadline - time.perf_counter()) * 1000 < 1:
                            raise
                        found += 1
                        dropped += 1
                        continue
                    if not exact_ids:
                        continue
                    found += 1
                    combined = legacy_ids | exact_ids
                    if len(combined) > BROAD_LIMIT:
                        dropped += 1  # already broad; no full-head count is needed
                        continue
                    within()
                    n = total()
                    if len(combined) * 2 > n:
                        dropped += 1
                        continue
                    weight = math.log(n / len(combined))
                    for i in exact_ids - weights.keys():
                        additions[i] = additions.get(i, 0.0) + weight
            rows = []
            if weights or additions:
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
                    """ + REPLIES_ONLY, {"head": head, "ids": list(weights.keys() | additions.keys()),
                                         "norm": normtext.active(), "replies": replies}).fetchall()
            _apply(conn, dict(previous))
    except psycopg.errors.QueryCanceled:
        return [], "timeout"
    if not weights and not additions:
        return [], "too_broad" if found and dropped == found else "on"
    for r in rows:
        r["keyword_score"] = round((weights if r["id"] in weights else additions)[r["id"]], 4)
    # Keep the original list and weights first, then fill only its unused slots.
    # Within each tier: score, later message, id, independent of index scan order.
    rows.sort(key=lambda r: (r["id"] not in weights, -r["keyword_score"], -r["position"], str(r["id"])))
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


def anchor_words(query: str, words: list[str], tie: tuple[str, ...]) -> tuple[list[str], tuple[str, ...]]:
    """packet-v15 (PHASE-35): the words an excerpt's best sentence is chosen by. A history cue's words (처음, 첫날,
    예전) say when the thing happened, not what it was: they leave the anchor words and only break a tie, as 처음 and
    첫 both do for a first cue (the story says 첫 빵 where the question says 처음). The question's one-syllable words
    break a tie only when they name something (빵, 달), not when they are FUNCTION_SYLLABLES."""
    when = [w for w in words if HISTORY_CUE.search(w)]
    cue_ties = tuple(dict.fromkeys(w for w in (*when, *(("처음", "첫") if FIRST_CUE.search(query) else ()))))
    return ([w for w in words if w not in when],
            tuple(dict.fromkeys((*cue_ties, *(w for w in tie if w not in FUNCTION_SYLLABLES)))))


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
    versions said that the current one does not (quoted, words), and the current version's own (quoted, words).
    For conditional `addresses` (PHASE-64), a quoted form still active in another current condition slot for the same
    pair is not treated as replaced."""
    active_addr: dict[tuple[str, str], str] = {}
    if calls:
        for f in facts:
            if f["predicate"] == "addresses" and f.get("polarity", "positive") != "negative":
                pair = (_flat(str((f.get("subject_entity") or {}).get("id") or f.get("subject") or "")),
                        _flat(str((f.get("object_entity") or {}).get("id") or f.get("object") or "")))
                active_addr[pair] = active_addr.get(pair, "") + " " + _flat(f.get("value"))
    out = []
    for f in facts:
        if f.get("turn") is None:
            continue
        now_q, now_w = _value_marks(f, names, places, calls)
        cur = _flat(" ".join(t for t in (f.get("object"), f.get("value")) if t))
        if calls and f["predicate"] == "addresses":
            pair = (_flat(str((f.get("subject_entity") or {}).get("id") or f.get("subject") or "")),
                    _flat(str((f.get("object_entity") or {}).get("id") or f.get("object") or "")))
            cur = cur + " " + active_addr.get(pair, "")
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
    if options.policy in V21_POLICIES:  # packet-v21: a replaced value counts only in an excerpt about its subject
        aliases = _aliases(r, query, previous_ai, options, view, names_of) if r is not None else None
        judged = [f for f in selected if not asks_about_old(f, query, flat_names)]
        by_subject = [(rv, subject_names(f, r, aliases)) for f in judged if (rv := replaced_values([f]))]

        def stale_v21(text: str, turn: int | None, ignore_now: bool = False) -> bool:
            flat = " ".join(text.casefold().split())
            return (any(states_replaced(text, turn, rv, people, ignore_now) and any(n in flat for n in names)
                        for rv, names in by_subject)
                    or states_marked(text, turn, marks, ignore_now))
        return stale_v21

    def stale(text: str, turn: int | None, ignore_now: bool = False) -> bool:
        return (states_replaced(text, turn, replaced, people, ignore_now)
                or states_marked(text, turn, marks, ignore_now))
    return stale


def subject_names(f: dict[str, Any], r: Any, aliases: dict[str, frozenset[str]] | None) -> set[str]:
    """packet-v21: the normalized names a fact's subject goes by (every name of its entity and its variants; the
    persona's names for the persona), for telling whether an excerpt is about it: a short old value such as 감기 or
    경계 is said of many characters, and an excerpt about someone else does not restate this one's."""
    names = _side_names(f, "subject", r, aliases)
    if r is not None and f.get("subject") and scene.is_persona(r, f["subject"]):
        names |= {" ".join(n.casefold().split()) for n in r.persona_names if len(n) >= 2}
    return names


@dataclass
class Gathered:
    """Everything a request offers the packet, before the budget (ADR 0027)."""
    ranked: list[Excerpt] = field(default_factory=list)
    source_clocks: dict[str, source_time.Clock] = field(default_factory=dict)
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
    hidden_entries: list[dict[str, Any]] = field(default_factory=list)
    secret_pairs: set[tuple[frozenset[str], frozenset[str]]] = field(default_factory=set)  # (holders, absent) given a Secret line
    story: list[Line] = field(default_factory=list)  # summaries (packet-v8, ADR 0043)
    cast_lines: list[tuple[str, list[Line]]] = field(default_factory=list)  # each scene character's state (packet-v8)
    secrets: list[dict[str, Any]] | None = None  # head secrets from view, reused by coverage without a second read
    gone: list[Line] = field(default_factory=list)  # gone characters' status lines not in <Cast> (packet-v20, PHASE-60 S3)
    cast_marks: dict[str, str] = field(default_factory=dict)  # <Cast> name → back_after value (packet-v20, PHASE-60 S4)
    settled: list[Line] = field(default_factory=list)  # threads closed lately, after the open ones (packet-v20, PHASE-60 S4)
    # packet-v20 (PHASE-60 S8): the characters pinned for the request, in pin order (`pinned_characters`); those only a
    # pin put in the scene's cast; and the facts only a pin named (required, but not the message's own: PHASE-46's fill)
    pins: list[dict[str, Any]] = field(default_factory=list)
    pin_only: set[str] = field(default_factory=set)
    pin_named: set[str] = field(default_factory=set)
    sem_query: str | None = None  # packet-v20 (PHASE-60 S5, ADR 0084): reply tail + short message for embedding only
    rerank_used: bool = False  # PHASE-60 S5 (ADR 0084): whether reranking reordered eligible candidates
    regression: list[Line] = field(default_factory=list)  # a previous timeline the named remember (packet-v20, PHASE-60 S6)
    regression_names: tuple[str, ...] = ()  # the characters a regression link names, in its order
    # packet-v21: excerpts fenced in <Private>, excerpts and state items withheld for repeating a secret
    excerpts_fenced: int = 0
    excerpts_withheld: int = 0
    state_withheld: int = 0


# packet-v21: a question about when, or about a time the story dates (3년 전 겨울, last winter): a fact's own
# `when_happened` then counts among its words for relevance
TEMPORAL_CUE_V21 = re.compile(source_time.CUE.pattern + "|" + HISTORY_CUE.pattern
                              + r"|\d+\s*(?:년|달|개월|주일?|일|시간)\s*(?:전|뒤|후)|작년|재작년|지난\s*(?:해|봄|여름|가을|겨울|달|주)"
                              r"|어릴\s*때|어렸을|봄|여름|가을|겨울|\bago\b|\blast (?:year|month|week|winter|summer|spring|autumn|fall)\b",
                              re.IGNORECASE)


def fact_pool_v21(rows: list[dict[str, Any]], query: str, in_context: set[str], history_start: int | None,
                  marks: bool) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    """packet-v21: `rows` as `relevant_facts` should score them, and {id(stand-in): the row} for each one changed. A
    temporal question (TEMPORAL_CUE_V21) scores a row's `when_happened` among its words. A question about the past
    (`history_start`, the window's start, given for HISTORY_CUE without FIRST_CUE) keeps a standing fact whose message
    is in context as a candidate when it started before the window (`_started_before`): its earlier history is not in
    the prompt. The rows themselves are never changed; the caller maps the ranking back."""
    temporal = bool(TEMPORAL_CUE_V21.search(query))
    out: list[dict[str, Any]] = []
    back: dict[int, dict[str, Any]] = {}
    for f in rows:
        row = f
        if temporal and f.get("when_happened"):
            row = {**row, "value": f"{row.get('value') or ''} {f['when_happened']}".strip()}
        if (history_start is not None and f.get("predicate") in STANDING and f.get("host_logical_id") in in_context
                and not f.get("held_off") and _started_before(f, history_start, in_context, marks)):
            row = {**row, "host_logical_id": None}
        if row is not f:
            back[id(row)] = f
        out.append(row)
    return out, back


PERSONA_THREAD_KINDS = ("goal", "question", "threat")


def persona_threads(threads: list[dict[str, Any]], r: Any, query: str, in_context: set[str],
                    picked: list[dict[str, Any]], claimed: Collection[Any]) -> list[dict[str, Any]]:
    """packet-v21: on a first-person message ("내 목표가 뭐였지?", FIRST_PERSON), the persona's own open aims, questions
    and threats, after the threads the message brought (the persona's names are never a mention, ADR 0023, so
    `relevant_threads` never brings them): the most similar to the message first, then the newest."""
    if r is None or not FIRST_PERSON.search(query):
        return []
    taken = {id(t) for t in picked}
    own = [t for t in threads if t.get("status") == "open" and t.get("kind") in PERSONA_THREAD_KINDS
           and t.get("by") and scene.is_persona(r, t["by"]) and id(t) not in taken and t["id"] not in claimed
           and t.get("host_logical_id") not in in_context]
    own.sort(key=lambda t: (similarity(query, t.get("text") or ""), t["position"]), reverse=True)
    return own


def persona_question_names(r: Any) -> frozenset[str]:
    """Resolved persona spellings, plus an unshared Korean given name, for PHASE-40 questions only."""
    if r is None:
        return frozenset()
    entity = r.entity("character", "{{user}}")
    if not entity:
        return frozenset()
    others = [e for e in r.entities() if e["id"] != entity["id"]]
    held = {norm(n) for e in others for n in e["names"]}
    derived = {g for e in others if e["type"] == "character" for n in e["names"]
               if (g := variants.given(norm(n)))}
    names = {norm(n) for n in r.persona_names if r.status("character", n) == "resolved"} - held
    return frozenset(names | {g for n in names if (g := variants.given(n)) and g not in held | derived})


def gather(conn: psycopg.Connection, head: UUID, query: str, previous_ai: str, in_context: set[str],
           options: RecallOptions, upto: int | None = None, known_at: datetime | None = None,
           canon_manifest: str | None = None, canon_exact: bool = False, canon_held: Iterable[str] = (),
           canon_facts: Any = LIVE, vectors_now: bool = False,
           recent: list[overuse.Recent] | None = None,
           coverage_info: Mapping[str, int | None] | None = None,
           served_turns: frozenset[int] | None = None,
           pins: list[dict[str, Any]] | None = None,
           recorded_sem_query: Any = LIVE,
           rerank_scores: Mapping[str, float] | None = None, carried: Carried | None = None) -> Gathered:
    """Candidates for one request, already normalized (`clean_text`). `upto` and `known_at` gather them as
    of an earlier request: the head up to that position, and what NMOS had derived by that time. The canon keys the
    prompt held count as in context: the host sent their text, so their facts are not sent again (D3, ADR 0047).
    `vectors_now` searches vectors as they are now whatever `known_at` says (a replay's named projection).
    `served_turns`: the turns an extraction serves as of the request, when the caller has read them (packet-v20's
    return gap); otherwise they are read here, as of `upto` and `known_at`, and only when a gap is possible.
    `pins`: a replay's recorded pins (`recall_options.pins`, ADR 0087 item 4), read instead of the message's `@name`s
    and the owner's pins; None for a live request.
    `carried`: what the chat's carry link carries (`carry.target_rows`, PHASE-60 S6, ADR 0085), read into every memory
    view under CARRY_POLICIES only; every other policy reads as if there were none."""
    started = time.perf_counter()
    g = Gathered()
    v21 = options.policy in V21_POLICIES  # packet-v21 (PHASE-65): every addition below is gated on it
    carried = carried if options.policy in CARRY_POLICIES else None
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
    if options.policy in SEM_QUERY_POLICIES:
        g.sem_query = sem_query(query, previous_ai) if recorded_sem_query is LIVE else recorded_sem_query
    if query.strip():
        if options.embedder is not None:  # asked for first, answered while the reads below run (ADR 0061)
            text = options.query_prefix + (g.sem_query if g.sem_query is not None else query)
            # A live request takes the embedding its sync asked for (item 7); a replay compiles from its own reads.
            pending = (prefetched.take(options.embedder, options.embed_projection, text) if known_at is None
                       else None)
            if pending is not None:
                g.timings["embed_lead"] = round((time.perf_counter() - pending.started) * 1000, 2)
            else:
                pending = QueryEmbedding(options.embedder, text, options.embed_timeout_ms)
        cut = _cut(conn, head, upto)
        head_ids = _head_ids(conn, head, cut, upto)  # ADR 0052 amendment 1: a short head is looked up by its revisions
        lexical, g.lexical_note = _lexical(conn, head, query, previous_ai, cut, options.threshold,
                                           options.lexical_timeout_ms, upto, head_ids, options.replies_only)
        g.timings["lexical"] = round((time.perf_counter() - started) * 1000, 2)
        if options.lexical_keywords:
            t0 = time.perf_counter()
            keyword, g.keyword_note = _keyword_lexical(conn, head, keywords(query, v21=True) if v21 else keywords(query), cut,
                                                       options.lexical_timeout_ms,
                                                       upto, particles=options.keyword_particles
                                                       and options.policy in KEYWORD_PARTICLE_POLICIES, head_ids=head_ids,
                                                       replies=options.replies_only, **({"v21": True} if v21 else {}))
            g.timings["keywords"] = round((time.perf_counter() - t0) * 1000, 2)
    # State, facts, threads, the scene and the summaries are read before the excerpts are chosen: none of them depends
    # on the candidates, and the query embedding answers meanwhile (ADR 0061). The excerpts follow, then what the
    # memory mode withheld is taken out of them.
    if options.rules_version != "none":
        held = current_state(conn, head, options.rules_version, upto)
        if options.state_changes and options.policy in STATUS_CHANGE_POLICIES:
            # PHASE-43 S4: what the status is now, told as changes; its bar is often stripped from the prompt, so
            # "in context" (judged by the prose) is no reason to leave it out
            told = statechange.tell(state_windows(conn, head, options.rules_version, upto, statechange.CORE_WINDOWS),
                                    frozenset(options.state_pins),
                                    frozenset(asked_keys(query, [r["key"] for r in held],
                                                         options.policy in V21_POLICIES)), by_turn)
            g.state = [StateItem(key=t.key, value=t.value, turn=t.turn, since_previous=t.since_previous) for t in told]
        else:
            g.state = [StateItem(key=r["key"], value=r["value"], turn=r["turn"] if by_turn else r["position"])
                       for r in held if r["host_logical_id"] not in in_context]
        # Sim bots track many characters: state of characters mentioned right now gets the budget first.
        g.state.sort(key=lambda i: ("." in i.key and i.key.split(".", 1)[0] in focus), reverse=True)
        if options.policy in STATE_HISTORY_POLICIES and held and STATE_CHANGE_CUE.search(query):
            # packet-v17: the history of each key the message asks about, first: it asked for it. Changes whose bar
            # is still in the prompt count too: the line is the sequence, which the prompt shows only scattered.
            asked = asked_keys(query, [r["key"] for r in held],
                               options.policy in V21_POLICIES)[:STATE_HISTORY_KEYS]
            lines = state_history(conn, head, options.rules_version, upto, keys=asked) if asked else {}
            g.state[:0] = [StateItem(key=k, value=lines[k][-1]["value"], turn=_turn_of(lines[k][-1], by_turn),
                                     history=tuple((_turn_of(e, by_turn), e["value"])
                                                   for e in lines[k][-STATE_HISTORY_MAX:]))
                           for k in asked if lines.get(k)]
            if options.state_changes and options.policy in STATUS_CHANGE_POLICIES:  # a key's history line says its value too
                drawn = {k for k in asked if lines.get(k)}
                g.state = [i for i in g.state if i.history or i.key not in drawn]
    view = None
    names_of: dict[int, Any] = {}  # one mapping of name variants per view, whichever path asks first (ADR 0058)
    changes = options.policy in CHANGE_POLICIES and not HISTORY_CUE.search(query)  # packet-v12, PHASE-31 Q1/Q2
    selected: list[dict[str, Any]] = []  # the facts offered (facts, <Cast>), for packet-v12's replaced values
    if options.facts_limit > 0 or options.threads_limit > 0:
        view = memory_view(conn, head, options.extractor_key, upto, known_at, canon_manifest, canon_exact,
                           options.canon_key, canon_facts,
                           told=options.policy in TOLD_POLICIES and options.facts_limit > 0,  # PHASE-60 S8
                           carried=carried)
        g.canon_names, g.canon_facts = view.get("canon_names"), view.get("canon_facts_manifest")
        r = view["resolution"]
        persona = r.persona_names if r else frozenset()
        aliases = _aliases(r, query, previous_ai, options, view, names_of)
        # Who is in the scene, so facts only some of them know are marked (packet-v3, ADR 0034).
        now = _head_turn(conn, head, upto)
        g.cast = _scene_cast(view, r, query, previous_ai, now, aliases, options)
        # packet-v20 (PHASE-60 S8, ADR 0087 item 2): a pinned character is present, before any line is judged private
        if v21:
            _join_pins(g, view, r, query, options, pins, aliases)
        else:
            _join_pins(g, view, r, query, options, pins)
        # packet-v21: how a line is written (feeling detail; no public clause that says a secret), and <Cast> and the gone
        # pins chosen before threads and facts, so the lines they take leave their slots to the next ones
        shown21 = Shown(view.get("secrets") or [], scene.names(g.cast, r, aliases)) if v21 and r is not None else None
        claimed: set[Any] = set()
        early_cast: tuple[list[tuple[str, list[Line]]], set[Any]] | None = None
        if v21 and options.policy in CAST_POLICIES and r is not None:
            early_cast = cast_groups(view, g.cast, r, query, options, in_context, aliases,
                                     pins=[p["key"] for p in g.pins], added=g.pin_only, shown_v21=shown21)
            claimed |= early_cast[1]
        if v21 and options.facts_limit > 0 and r is not None:
            claimed |= {f["id"] for f in gone_rows(view, r, now, v21=True)}
        if options.threads_limit > 0:
            picked = relevant_threads(view["threads"], query, previous_ai, in_context,
                                      len(view["threads"]) if rest or v21 else options.threads_limit, persona,
                                      about=options.policy in ABOUT_POLICIES, aliases=aliases, named=g.named)
            if v21:
                picked = [t for t in picked if t["id"] not in claimed]
                picked += persona_threads(view["threads"], r, query, in_context, picked, claimed)
            picked = (_rested(picked, "thread", rest, g, v21=True) if v21
                      else _rested(picked, "thread", rest, g))[:options.threads_limit]
            g.threads = _moded([thread_entry(t, scene.private(t, g.cast, r), options.policy in HAPPENED_POLICIES)
                                for t in picked],
                               view["threads"], g, r, options)
        if options.facts_limit > 0:
            causes = options.policy in CAUSE_POLICIES
            persona_questions = options.policy in PERSONA_QUESTION_POLICIES
            persona_entity = (r.entity("character", "{{user}}") or {}).get("id") if persona_questions and r else None
            question_names = persona_question_names(r) if persona_questions else frozenset()
            persona_added: set[str] = set()  # one cap across narrated facts and attributed claims
            # packet-v9 ranks every candidate once: the configured limit's share is its head (relevant_facts keeps
            # its order and event cap at any limit), and the added slots go to what no one is kept from (ADR 0049).
            grow = options.fill_facts > 0
            claims_limit = max(1, options.facts_limit // 2)
            # How it started (ADR 0056): where the window starts, read only when the message asks.
            first = options.first_cue and bool(FIRST_CUE.search(query))
            # packet-v21: a question about the past without a first cue also reads where the window starts
            history = v21 and not first and options.first_cue and bool(HISTORY_CUE.search(query))
            start = _window_start(conn, head, in_context, upto) if first or history else None
            fact_pool, pooled = (fact_pool_v21(view["facts"], query, in_context, start if history else None,
                                               options.history_marks) if v21 else (view["facts"], {}))
            # the label policies rank a risky line after the others before the limits choose (PHASE-34 Q1)
            contradicted = (frozenset(str(c["fact"]) for c in view.get("conflicts") or [] if c.get("fact") is not None)
                            if options.policy in LABEL_POLICIES else None)
            # packet-v20 (PHASE-60 S8): a pinned character's names make its now and standing facts named
            pinned = scene.names({p["key"]: p["name"] for p in g.pins}, r, aliases) if g.pins else frozenset()
            ranked = relevant_facts(fact_pool, query, previous_ai, in_context,
                                    len(view["facts"]) if grow or rest or v21 else options.facts_limit,
                                    options.events_limit, persona, scene.names(g.cast, r, aliases), causes=causes,
                                    first_cue=first, window_start=start, marks=options.history_marks, aliases=aliases,
                                    named=g.named, named_by_words=options.policy in NAMED_POLICIES, risky=contradicted,
                                    keep=((lambda f: bool(_rested([f], "fact", rest, g, v21=True))) if v21
                                          else (lambda f: bool(_rested([f], "fact", rest, g)))) if rest else None,
                                    persona_questions=persona_questions, persona_entity=persona_entity,
                                    persona_query_names=question_names, persona_added=persona_added,
                                    pinned=pinned, pin_named=g.pin_named)
            ranked = [pooled.get(id(f), f) for f in ranked] if pooled else ranked
            # packet-v19 (PHASE-46): a question that names no one and shares no fact's words gets no added fact or
            # claim slots; the configured limits still choose (small talk took 30 facts and 8 claims at 4,000 tokens).
            # A pin names no one in the message (PHASE-60 S8): the facts only a pin named do not count.
            fill_facts = 0 if options.fill_facts and options.policy in RELATED_FILL_POLICIES and unrelated_question(
                query, g.named - g.pin_named, view["facts"] + view["claims"]) else options.fill_facts
            if options.policy in LABEL_POLICIES:  # before the limits: a risky fact never takes an ordinary one's slot
                ranked = _risky_last(ranked, view, g.named)
            if claimed:  # packet-v21: a fact <Cast> or a gone pin says is not said again; the next one takes its slot
                ranked = [f for f in ranked if f["id"] not in claimed]
            if changes:  # an ended role answers a question about the past, not about now (PHASE-31 Q2); the facts
                # after it take its slot
                def now_or_kept(f: dict[str, Any]) -> bool:
                    return not _ended_role(f) or ended_role_kept(f, view["facts"], query, r, aliases)
                g.ended = sum(1 for f in _grown(ranked[:options.facts_limit], ranked, fill_facts)
                              if not now_or_kept(f))
                ranked = [f for f in ranked if now_or_kept(f)]
            facts = _grown(ranked[:options.facts_limit], ranked, fill_facts)
            persona_added.intersection_update(str(f["id"]) for f in facts)
            if changes:
                selected = list(facts)
            # Claims after facts, so the budget serves narration first (ADR 0013).
            claim_pool, pooled = (fact_pool_v21(view["claims"], query, in_context, None, options.history_marks)
                                  if v21 else (view["claims"], {}))
            ranked = relevant_facts(claim_pool, query, previous_ai, in_context,
                                    len(view["claims"]) if grow or rest else claims_limit, persona=persona,
                                    causes=causes, first_cue=first, window_start=start, marks=options.history_marks,
                                    aliases=aliases, named=g.named, named_by_words=options.policy in NAMED_POLICIES,
                                    risky=contradicted, persona_questions=persona_questions,
                                    persona_entity=persona_entity, persona_query_names=question_names,
                                    persona_added=persona_added)
            ranked = [pooled.get(id(f), f) for f in ranked] if pooled else ranked
            ranked = _rested(ranked, "claim", rest, g, v21=True) if v21 else _rested(ranked, "claim", rest, g)
            if options.policy in LABEL_POLICIES:
                ranked = _risky_last(ranked, view, g.named)
            claims = _grown(ranked[:claims_limit], ranked,
                            max(1, (options.facts_limit + fill_facts) // 2) - claims_limit)
            g.risky = ({str(f["id"]) for f in facts + claims if f.get("disputed_by")}
                       | {str(c["fact"]) for c in view.get("conflicts") or [] if c.get("fact") is not None})
            # How the cast stand with each other takes the budget before threads (ADR 0026).
            before, cause = options.policy in BEFORE_POLICIES, causes
            marks = options.history_marks
            happened = options.policy in HAPPENED_POLICIES  # packet-v20 (PHASE-60 S7)
            g.lead = _moded([entry_v21(f, scene.private(f, g.cast, r), before, cause, marks, shown21, happened=happened)
                             for f in facts if f["predicate"] in STANDING],
                            facts, g, r, options)
            g.facts = _moded([entry_v21(f, scene.private(f, g.cast, r), before, cause, marks, shown21, happened=happened)
                              for f in facts if f["predicate"] not in STANDING]
                             + [claim_entry(c, scene.private(c, g.cast, r), cause) for c in claims], facts + claims, g, r,
                             options)
            # packet-v20 (PHASE-60 S8): who told whom, after the ordinary facts and claims; chosen after them, so it
            # changes neither their selection nor the fill decision
            g.facts += told_lines(g, view, r, query, previous_ai, in_context, options, aliases, rest)
        if options.narrator:
            who = scene.display(r, options.narrator) if r is not None else options.narrator
            g.note = f" The story is told in the first person by {who}: only what they know is listed."
        if options.policy in CAST_POLICIES and r is not None:
            g.cast_lines, used = early_cast if early_cast is not None else cast_groups(
                view, g.cast, r, query, options, in_context, aliases, pins=[p["key"] for p in g.pins], added=g.pin_only)
            if changes:
                selected += [f for f in view["facts"] if f["id"] in used]
            if used:  # a line in <Cast> is not said again in another section
                g.lead = [line for line in g.lead if line.ref.get("assertion") not in used]
                g.facts = [line for line in g.facts if line.ref.get("assertion") not in used]
                g.threads = [line for line in g.threads if line.ref.get("assertion") not in used]
        if options.policy in GONE_POLICIES and options.facts_limit > 0 and r is not None:
            # packet-v20 (PHASE-60 S3): a gone character's status, whether or not the message names them; like <Cast>,
            # whether or not its message is in the prompt (the mark is what the prompt lacks)
            pin_gone(g, view, r, now, options)
        if options.policy in RETURN_GAP_POLICIES and g.cast_lines and r is not None and now is not None:
            # packet-v20 (PHASE-60 S4): a <Cast> character back after a long absence; which turns an extraction serves
            # is read only when some character's appearances leave room for a gap
            loaded = [served_turns]

            def served(t: int) -> bool:
                if loaded[0] is None:
                    loaded[0] = coverage.extraction_state(conn, head, upto, known_at)[0]
                return t in loaded[0]

            g.cast_marks = return_marks(view, r, g.cast, g.cast_lines, now, served, options.policy)
        if options.policy in SETTLED_POLICIES and options.threads_limit > 0:
            # packet-v20 (PHASE-60 S4): threads the story closed lately, outside threads_limit
            g.settled = settled_lines(g, view, r, query, now, rest, options, aliases)
        if options.policy in CARRY_POLICIES and view.get("regression") and r is not None:
            # packet-v20 (PHASE-60 S6): what the named remember of a previous timeline, apart from everything above
            g.regression = regression_lines(g, view, r, query, previous_ai, in_context, options, aliases)
            g.regression_names = tuple(view["carried"]["names"])
    if options.policy in COVERAGE_POLICIES and coverage_info is not None:
        g.note += coverage_note(coverage_info.get("recorded_through_turn"), coverage_info.get("latest_replied_turn"))
    if options.policy in STORY_POLICIES and options.summarize_key and not options.narrator:  # ADR 0043, PHASE-12 Q3
        if view is None and options.extractor_key:  # facts and threads off: the secrets still decide what may be told
            view = memory_view(conn, head, options.extractor_key, upto, known_at, canon_manifest, canon_exact,
                               options.canon_key, canon_facts, carried=carried)
            g.canon_names, g.canon_facts = view.get("canon_names"), view.get("canon_facts_manifest")
        r = view["resolution"] if view else None
        aliases = _aliases(r, query, previous_ai, options, view, names_of) if view else None
        if view and not g.cast and r is not None:
            g.cast = _scene_cast(view, r, query, previous_ai, _head_turn(conn, head, upto), aliases, options)
            if v21:  # facts and threads off: the summaries' scene (PHASE-60 S8)
                _join_pins(g, view, r, query, options, pins, aliases)
            else:
                _join_pins(g, view, r, query, options, pins)
        g.story = summaries.packet_lines(conn, head, options.summarize_key, view["secrets"] if view else [], query,
                                         in_context, upto, known_at,
                                         scene.names(g.cast, r, aliases) if r is not None else frozenset(),
                                         hidden_entries=g.hidden_entries if options.policy in LABEL_POLICIES else None)
        if rest:  # a scene summary is supportive and rests as the others do (a review); the story so far never rests
            awake = [line for line in g.story
                     if '<Summary kind="story"' in line.xml or overuse.key(line.kind, line.ref) not in rest]
            g.rested += len(g.story) - len(awake)
            g.story = awake
        if options.policy in CARRY_POLICIES and view and (line := carried_story(
                view, view["secrets"], scene.names(g.cast, r, aliases) if r is not None else frozenset(),
                g.hidden_entries if options.policy in LABEL_POLICIES else None)) is not None:
            g.story.append(line)  # offered last: the first one left out when STORY_SHARE is full; emitted first
    if pending is not None:
        t0 = time.perf_counter()
        try:
            qvec = pending.result()
            g.timings["embed_wait"] = round((time.perf_counter() - t0) * 1000, 2)
            g.timings["embed"] = pending.call_ms  # the embedder's own time, mostly spent during the reads
            t0 = time.perf_counter()
            vector = vector_candidates(conn, head, qvec, options.embed_projection, cut, CANDIDATE_LIMIT,
                                       upto, None if vectors_now else known_at, options.replies_only)
            g.timings["vector"] = round((time.perf_counter() - t0) * 1000, 2)
            g.vector_note = "on"
        except (LLMError, ValueError) as exc:  # fail open to lexical-only
            g.timings["embed_wait"] = round((time.perf_counter() - t0) * 1000, 2)
            g.vector_note = f"fallback: {exc}"[:200]
    g.candidates = fuse(lexical, vector, options.threshold, options.vector_min_sim, keyword)
    g.excluded = [c for c in g.candidates if c["host_logical_id"] in in_context]
    eligible = [c for c in g.candidates if c["host_logical_id"] not in in_context]
    if known_at is None and options.reranker is not None:
        t0 = time.perf_counter()
        if query.strip() and eligible:
            top = eligible[:rerank.MAX_CANDIDATES]
            docs = [rerank_doc(c) if v21 else c["clean"][:rerank.MAX_DOC_CHARS] for c in top]
            # RetrieveRequest carries no remaining client deadline, so the call is bounded by the reranker's own
            # timeout (`options.reranker.timeout_ms`); any timeout, error or malformed answer leaves the fused order.
            # packet-v21: the text the query was embedded with (a short message with the reply's tail, ADR 0084)
            scores = rerank.score(options.reranker, (g.sem_query or query) if v21 else query, docs)
            if scores is not None:
                for c, s in zip(top, scores):
                    c["rerank"] = float(s)
                eligible = rerank.reorder(top, scores) + eligible[rerank.MAX_CANDIDATES:]
                it = iter(eligible)
                g.candidates = [c if c["host_logical_id"] in in_context else next(it) for c in g.candidates]
                g.rerank_used = True
        g.timings["rerank"] = round((time.perf_counter() - t0) * 1000, 2)
    elif rerank_scores:
        # Replay (ADR 0084 item 5): never calls a reranker; reapplies recorded scores to the same candidates.
        scored = [c for c in eligible if str(c["id"]) in rerank_scores]
        if scored:
            scores = [float(rerank_scores[str(c["id"])]) for c in scored]
            for c, s in zip(scored, scores):
                c["rerank"] = s
            unscored = [c for c in eligible if str(c["id"]) not in rerank_scores]
            eligible = rerank.reorder(scored, scores) + unscored
            it = iter(eligible)
            g.candidates = [c if c["host_logical_id"] in in_context else next(it) for c in g.candidates]
            g.rerank_used = True
    stale = _replaced_judge(view, selected, query, previous_ai, options, names_of) if changes and view is not None else None
    scan_slots = stale is not None or options.policy in UNEXTRACTED_POLICIES
    if not scan_slots:  # older policies keep the original top-k cut
        eligible = eligible[: options.top_k]
    words = (keywords(query, v21=True) if v21 else keywords(query)) if options.policy in GROW_POLICIES else []
    span = options.policy in SPAN_POLICIES  # packet-v11 (ADR 0063)
    cue = span and bool(WHY.search(query) or CONTENTS.search(query))  # a why or contents question (PHASE-27 Q2)
    # Q1b: the keywords anchor is the question's keywords alone, or the question itself when it has none (the
    # prototype's rule: never the previous reply); every other case anchors on the question and the previous reply
    anchor = (" ".join(words) or query) if span and options.excerpt_anchor == "keywords" else focus
    tie = one_char_words(query) if options.policy in CHANGE_POLICIES else ()  # packet-v12, PHASE-31 Q3
    nouns: tuple[str, ...] = ()  # packet-v15: the question's one-syllable nouns (PHASE-35 Q3)
    if options.policy in ANCHOR_POLICIES:  # packet-v15: the anchor is what the question asks, not when (PHASE-35)
        words, tie = anchor_words(query, words, tie)
        nouns = tuple(w for w in tie if len(w) == 1 and w != "첫")
        anchor = (" ".join(words) or query) if span and options.excerpt_anchor == "keywords" else focus
    # packet-v13 (PHASE-33 Q5): a turn this generation has not extracted yet (a first sight still catching up) has no
    # fact to restate, so its excerpt is raw evidence; one such excerpt may take one more slot than top_k,
    # even before there are facts to build a stale-value judge, or when a history question disables that judge.
    unextracted = (_unextracted(conn, head, [c["id"] for c in eligible], options.extractor_key, known_at)
                   if options.policy in UNEXTRACTED_POLICIES and options.extractor_key and eligible else set())
    def resting(c: dict[str, Any]) -> bool:  # a tired excerpt is left out while it rests (PHASE-34 Q3) ...
        return bool(rest) and ("excerpt", str(c["id"])) in rest and str(c["id"]) not in g.named \
            and not (c.get("user_score") or c.get("keyword_score"))  # ... unless the question's words found it
    floor = (EXCERPT_FLOOR * max((float(c["rrf"]) for c in eligible if not resting(c)), default=0.0)
             if options.policy in REST_POLICIES else 0.0)
    # packet-v21: once the reranker ordered the candidates, its own order decides what clears the bar, not the fused
    # score it replaced: its first never falls under it, nor one it scored at least EXCERPT_FLOOR of its best
    reranked_ok = reranked_above(eligible) if v21 and g.rerank_used else frozenset()
    for c in eligible:
        # A resting excerpt is offered marked, outside the count: the compiler places it only when it holds the reserved
        # first place, which is known only after its repeat check and the filters below (a review's follow-up)
        tired = resting(c)
        # the activation threshold (PHASE-34 Q4) is the compiler's too, at the reserved place's stage (third review)
        low = (bool(floor) and float(c["rrf"]) < floor and not (c.get("user_score") or c.get("keyword_score"))
               and str(c["id"]) not in reranked_ok)
        awake = [e for e in g.ranked if not e.resting and not e.below_floor]
        if scan_slots and len(awake) >= options.top_k + bool(unextracted):
            break
        if scan_slots and not (tired or low) and len(awake) == options.top_k and str(c["id"]) not in unextracted:
            continue  # the one more slot is for an unextracted turn only
        # a lexical or keyword hit is the whole message; a vector-only hit is its chunk; under packet-v11 a word hit
        # whose vector similarity meets the bar excerpts within its chunk too: the chunk is the part of the message
        # the question is about, the words only say the message is relevant (PHASE-27 Q1)
        word_hit = bool(c.get("user_score") or c.get("keyword_score"))
        in_chunk = not word_hit or (span and c.get("sim") is not None and c["sim"] >= options.vector_min_sim
                                    and c.get("text_end") is not None)
        clean = c["clean"][c["text_start"]:c["text_end"]] if in_chunk else c["clean"]
        if (in_chunk and word_hit and nouns
                and anchor_rank(c["clean"], nouns, words) > anchor_rank(clean, nouns, words)):
            clean = c["clean"]  # packet-v15: the whole message says more of what the question names (PHASE-35 Q3)
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
                       position=c["position"], unextracted=str(c["id"]) in unextracted, resting=tired,
                       below_floor=low)
        if stale is not None:  # packet-v12 (PHASE-31 Q1): no form of an excerpt says only a replaced value
            if stale(item.text, item.turn):
                g.replaced += 1
                continue
            if item.short and stale(item.short, item.turn):  # its sentence alone would: placed whole or not at all
                item = dataclasses.replace(item, short="", cut_ok=False)
            elif stale(item.text, item.turn, ignore_now=True):  # a cut could keep the old value and lose the new
                item = dataclasses.replace(item, cut_ok=False)
        g.ranked.append(item)
    if options.policy in QUOTE_POLICIES and query.strip() and (quotes.asks_for_words(query, v21=True) if v21
                                                                    else quotes.asks_for_words(query)):
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
            extra = _turn_messages(conn, head, named - quotes.TURN_SPAN, named + quotes.TURN_SPAN, upto, cut,
                                   options.replies_only)
        met = None
        if first:  # how it started: the opening, and the turns where everyone the question names had appeared
            asked, others = quotes.named(query, names)
            met = _first_met(conn, head, [[k for k, d in names.items() if d == who] for who in asked | others], upto,
                             cut, options.replies_only)
            if met == 0:
                met = None  # all there from the opening: no meeting to anchor on, the earliness bonus decides
            extra = _turn_messages(conn, head, 0, quotes.TURN_SPAN, upto, cut, options.replies_only)
            if met is not None:
                extra += _turn_messages(conn, head, met, met + quotes.TURN_SPAN, upto, cut, options.replies_only)
        searched, rarity, g.quote_note = _quote_messages(conn, head, quotes.query_words(query), upto, cut,
                                                         options.replies_only)
        seen = {str(c["id"]) for c in found}
        g.quote_only = {str(c["id"]) for c in extra + searched} - {str(c["id"]) for c in g.candidates}
        for c in extra + searched:
            if c["host_logical_id"] not in in_context and str(c["id"]) not in seen:
                found.append(c)
                seen.add(str(c["id"]))
        known = (_quote_speakers(conn, [c["id"] for c in found], options.extractor_key, known_at, any_generation=True)
                 if v21 else _quote_speakers(conn, [c["id"] for c in found], options.extractor_key, known_at))  # PHASE-45 S3
        if known and resolution is not None:  # the speaker rule writes the persona's lines as "{{user}}"
            me = next((e for e in resolution.entities() if e.get("persona") and e.get("name")), None)
            if me is not None:
                names = {norm(PERSONA): me["name"], **names}
        picked = quotes.pick(found, query, names, _last_position(conn, head, upto), first, rarity, met, known,
                             **({"v21": True} if v21 else {}))
        g.quotes = len(picked)
        g.ranked = [Excerpt(turn=q.turn if by_turn else q.position, speaker=q.speaker or "", text=q.text,
                            score=q.score, revision_id=q.revision_id, position=q.position, cut_ok=False, quote=True)
                    for q in picked] + g.ranked
        g.timings["quote_route"] = round((time.perf_counter() - t0) * 1000, 2)  # ms; `quotes` is the count placed
    if g.withheld_lines:
        # An excerpt that says what the mode withheld would give it back word for word.
        kept = []
        for e in g.ranked:
            if not any(spans.reuse(line.content, e.text) >= REPEATS for line in g.withheld_lines):
                kept.append(e)
            elif options.policy in LABEL_POLICIES:
                g.hidden_entries.append(hidden_entry("quote" if e.quote else "excerpt",
                                                     {"revision": e.revision_id}, e.turn, "mode_withheld"))
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
                               options.canon_key, canon_facts, carried=carried)
        r = view["resolution"]
        aliases = _aliases(r, query, previous_ai, options, view, names_of)
        cast = g.cast
        if not cast and r is not None:  # facts, threads and summaries off: the scene still sets the bar
            cast = _scene_cast(view, r, query, previous_ai, _head_turn(conn, head, upto), aliases, options)
        present = scene.names(cast, r, aliases) if r is not None else frozenset()
        kept = []
        for e in g.ranked:
            if e.revision_id not in keyword_only:
                kept.append(e)
            elif not any(summaries.leaks(form, view["secrets"], present) for form in (e.text, e.short) if form):
                kept.append(dataclasses.replace(e, cut_ok=False))  # the forms checked are the only ones placed
            elif options.policy in LABEL_POLICIES:
                g.hidden_entries.append(hidden_entry("quote" if e.quote else "excerpt",
                                                     {"revision": e.revision_id}, e.turn, "secret_gate"))
        g.quote_withheld = sum(e.quote for e in g.ranked) - sum(e.quote for e in kept)
        g.keyword_withheld = len(g.ranked) - len(kept) - g.quote_withheld
        g.ranked = kept
    if v21 and (g.ranked or g.state) and options.extractor_key:
        if view is None:
            view = memory_view(conn, head, options.extractor_key, upto, known_at, canon_manifest, canon_exact,
                               options.canon_key, canon_facts, carried=carried)
        if view["secrets"]:
            r = view["resolution"]
            aliases = _aliases(r, query, previous_ai, options, view, names_of)
            cast = g.cast
            if not cast and r is not None:
                cast = _scene_cast(view, r, query, previous_ai, _head_turn(conn, head, upto), aliases, options)
            present = scene.names(cast, r, aliases) if r is not None else frozenset()
            gate_excerpts_v21(g, view["secrets"], present, keyword_only, options)
            gate_state_v21(g, view["secrets"], present, options)
    if (options.policy in SOURCE_CLOCK_POLICIES and options.source_clock and source_time.CUE.search(query)
            and options.rules_version != "none" and g.ranked and not options.strict and not options.narrator):
        started_clock = time.perf_counter()
        clocks = source_time.read(conn, head, options.rules_version,
                                  list(dict.fromkeys(e.revision_id for e in g.ranked)), upto, cut)
        if clocks and options.extractor_key:
            if view is None:
                view = memory_view(conn, head, options.extractor_key, upto, known_at, canon_manifest, canon_exact,
                                   options.canon_key, canon_facts, carried=carried)
            # A clock is additional text from the source. Conservatively withhold any known secret overlap,
            # including a fabricated parser value, regardless of which characters are in this scene.
            protected = frozenset(norm(n) for secret in view["secrets"] for n in secret.get("open", ()))
            clocks = {rid: clock for rid, clock in clocks.items()
                      if not any(summaries.leaks(value, view["secrets"], protected)
                                 for _, value, _ in clock.fields)}
        g.source_clocks = clocks
        g.timings["source_clock"] = round((time.perf_counter() - started_clock) * 1000, 2)
    if view is not None:
        g.secrets = view["secrets"]
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
        found = variants.aliases(r.entities(), r.persona_names, f"{query} {previous_ai}", marked)
        if options.policy in V21_POLICIES:
            found = _with_titles(found, view, r)
        cache[id(view)] = found
    return cache[id(view)]


TITLE_MAX_CHARS = 8  # packet-v21: a title longer than this is a description, not a form of address


def title_aliases(view: dict[str, Any], r: Any) -> dict[str, str]:
    """packet-v21: {normalized title: the character's display name} for each title that points from the persona to
    exactly one character: a quoted form the persona calls them by (`addresses`, persona → them: "반말, '선배'라고
    부름") or the role they hold toward the persona (`role_toward`, them → persona, the value before its colon:
    "선배: …"). A user writes "선배, 아까 그 일 어떻게 됐어?" with no name at all (Korean drops it). Not a title that is
    any entity's name or the persona's, not one two characters share, not of a negated, carried or left-out row."""
    if r is None:
        return {}
    held = {norm(n) for e in r.entities() for n in e["names"]} | {norm(n) for n in r.persona_names}
    left_out = excluded_ids(view)
    targets: dict[str, set[str]] = {}
    names: dict[str, str] = {}
    for f in view.get("facts") or ():
        if f.get("polarity") == "negative" or f.get("carried") or not f.get("object"):
            continue
        if f["predicate"] == "addresses" and scene.is_persona(r, f["subject"]) and not scene.is_persona(r, f["object"]):
            who, forms = f["object"], [q.strip() for q in _QUOTED.findall(f.get("value") or "")]
        elif f["predicate"] == "role_toward" and scene.is_persona(r, f["object"]) and not scene.is_persona(r, f["subject"]):
            who, forms = f["subject"], [(f.get("value") or "").split(":", 1)[0].strip()]
        else:
            continue
        e = r.entity("character", who)
        if e is None or str(e["id"]) in left_out:
            continue
        for form in forms:
            t = norm(form)
            if 2 <= len(t) <= TITLE_MAX_CHARS and t not in held:
                targets.setdefault(t, set()).add(str(e["id"]))
                names[str(e["id"])] = e["name"]
    return {t: names[next(iter(ids))] for t, ids in targets.items() if len(ids) == 1}


def _with_titles(found: dict[str, frozenset[str]], view: dict[str, Any], r: Any) -> dict[str, frozenset[str]]:
    """`found` (`variants.aliases`) with each unique title (`title_aliases`) as one more name of its character, under
    every name that character goes by, so the scene, the facts, the pins and PHASE-46's small-talk test all read it."""
    titles = title_aliases(view, r)
    if not titles:
        return found
    out = dict(found)
    taken = {v for vs in found.values() for v in vs}
    for title, who in titles.items():
        if title in taken:  # already another name's variant: not this character's alone
            continue
        e = r.entity("character", who)
        for n in (e["names"] if e else [who]):
            k = norm(n)
            out[k] = out.get(k, frozenset()) | {title}
    return out


CAST_TURNS_V21 = 4  # packet-v21: the turns before the current one whose rows put a character in the scene


def _scene_cast(view: dict[str, Any], r: Any, query: str, previous_ai: str, now: int | None,
                aliases: dict[str, frozenset[str]] | None, options: RecallOptions) -> dict[str, str]:
    """The scene's cast (`scene.cast`), never with an entity the owner marked not a character (`excluded_ids`), so no
    line is private for one. packet-v21 reads CAST_TURNS_V21 turns instead of `scene.CAST_TURNS`."""
    rows = view["facts"] + view["claims"] + view["other"]
    # every policy: an entity the owner marked not a character is never in the cast (PHASE-47 S2; a bug fix, PHASE-65:
    # the cast was the one reader that still counted one, so a line could be private for it)
    if options.policy in V21_POLICIES:
        return scene.cast(rows, r, query, previous_ai, now, turns=CAST_TURNS_V21, aliases=aliases,
                          marks=_thread_marks(view, aliases), excluded=excluded_ids(view))
    return scene.cast(rows, r, query, previous_ai, now, aliases=aliases, marks=_thread_marks(view, aliases),
                      excluded=excluded_ids(view))


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


def pinned_characters(view: dict[str, Any] | None, r: Any, query: str, options: RecallOptions,
                      recorded: list[dict[str, Any]] | None = None,
                      aliases: dict[str, frozenset[str]] | None = None) -> list[dict[str, Any]]:
    """packet-v20 (PHASE-60 S8, ADR 0087): the characters pinned for this request, in pin order, one entry each
    ({"key": entity key, "name": display name, "source": "at" or "owner"}): first those an `@name` in the message
    names (only with `pin_at_mentions`; `mentions.at_mentions` over every character's normalized names, a name two
    characters share naming neither), then the owner's pins, newest first (`view["pins"]`). Never the persona, never
    a character the owner left out (`entity_exclude` wins, item 5). `recorded`: a replay's `recall_options.pins`,
    resolved by name in its own view; the message and the view's pins are then not read (item 4). Every other policy:
    none."""
    if options.policy not in PIN_POLICIES or r is None or view is None:
        return []
    persona = scene.key(r, scene.PERSONA)
    left_out = excluded_ids(view)
    by_id = {str(e["id"]): e for e in r.entities()}
    out: dict[str, dict[str, Any]] = {}

    def add(e: dict[str, Any] | None, source: str) -> None:
        if (e is None or e.get("type") != "character" or e.get("persona") or e["id"] == persona
                or str(e["id"]) in left_out or str(e["id"]) in out):
            return
        out[str(e["id"])] = {"key": e["id"], "name": e["name"], "source": source}

    if recorded is not None:
        for p in recorded:
            if isinstance(p, dict) and p.get("name"):
                add(r.entity("character", p["name"]), "at" if p.get("source") == "at" else "owner")
        return list(out.values())
    if options.pin_at_mentions and query:
        names: dict[str, str] = {}
        shared: set[str] = set()
        for e in r.entities():
            if e.get("type") != "character":
                continue
            spelled = e["names"]
            if options.policy in V21_POLICIES and aliases:  # packet-v21: `@이안` pins 백이안 (ADR 0058's variants)
                spelled = [*spelled, *(v for n in e["names"] for v in aliases.get(norm(n), ()))]
            for n in spelled:
                k = norm(n)
                if k and names.setdefault(k, str(e["id"])) != str(e["id"]):
                    shared.add(k)
        for k in shared:
            del names[k]
        for i in mentions.at_mentions(query, names, {str(persona), *left_out}):
            add(by_id.get(i), "at")
    for p in view.get("pins") or ():
        add(by_id.get(str(p.get("entity_id"))), "owner")
    return list(out.values())


def _join_pins(g: Gathered, view: dict[str, Any], r: Any, query: str, options: RecallOptions,
               recorded: list[dict[str, Any]] | None, aliases: dict[str, frozenset[str]] | None = None) -> None:
    """The request's pins (`pinned_characters`) join the scene's cast after everyone already in it, so knowledge marks,
    Private, strict and narrator lines treat them as present (ADR 0087 item 2). Every other policy: nothing."""
    g.pins = (pinned_characters(view, r, query, options, recorded, aliases) if options.policy in V21_POLICIES
              else pinned_characters(view, r, query, options, recorded))
    for p in g.pins:
        if p["key"] not in g.cast:
            g.cast[p["key"]] = p["name"]
            g.pin_only.add(p["key"])


def recorded_pins(pins: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """What a request records of its pins (`recall_options.pins`, ADR 0087 item 4): each name it resolved to."""
    return [{"name": p["name"], "entity_type": "character", "source": p["source"]} for p in pins]


FEELING_INTENSITY = ("faint", "clear", "strong")
FEELING_VALENCE = ("positive", "negative")


def feeling_inline(f: dict[str, Any]) -> str:
    """packet-v21: a `feels_toward` fact's feeling detail (extract-v18, PHASE-58) as a short tail on its line, e.g.
    " [strong, positive; under: 원망 (faint, negative)]"; nothing when it has none. Only the stored words are used, and
    an intensity or valence outside the extractor's own words is left out."""
    d = f.get("feeling")
    if f.get("predicate") != "feels_toward" or not isinstance(d, Mapping):
        return ""

    def how(x: Mapping[str, Any]) -> list[str]:
        return [v for v, allowed in ((x.get("intensity"), FEELING_INTENSITY), (x.get("valence"), FEELING_VALENCE))
                if isinstance(v, str) and v in allowed]

    parts = ", ".join(how(d))
    under = d.get("under")
    if isinstance(under, Mapping) and isinstance(under.get("value"), str) and under["value"].strip():
        detail = ", ".join(how(under))
        parts += ("; " if parts else "") + f"under: {under['value'].strip()}" + (f" ({detail})" if detail else "")
    return f" [{parts}]" if parts else ""


def present_leaks(text: str | None, secrets: list[dict[str, Any]] | None,
                  present: frozenset[str]) -> list[dict[str, Any]]:
    """The secrets `text` repeats (`summaries.leaks`) that are kept from someone in the scene (`present`, normalized)."""
    if not text or not secrets:
        return []
    return [s for s in summaries.leaks(text, secrets, present) if any(norm(n) in present for n in s.get("open") or ())]


@dataclass(frozen=True)
class Shown:
    """packet-v21's way of writing a fact line (`entry_v21`): the open secrets and who is in the scene, so a public
    line drops a clause that would say a secret aloud, and whether to write the feeling detail."""
    secrets: list[dict[str, Any]] = field(default_factory=list)
    present: frozenset[str] = frozenset()


def entry_v21(f: dict[str, Any], private: bool, before: bool, cause: bool, marks: bool, shown: Shown | None, *,
              gone: bool = False, happened: bool = False) -> Line:
    """`fact_entry`, under packet-v21 (`shown` set): a line every present character may read (not private) leaves out
    its `because` and its `disputed_by` clause when that clause repeats a secret kept from someone present
    (`present_leaks`), and a `feels_toward` line ends its text with the feeling detail (`feeling_inline`). Its ledger
    text, content and marks stay `fact_entry`'s, so echo, rest and restate keys are unchanged. With `shown` None it is
    `fact_entry` exactly."""
    if shown is None:  # exactly the call v20 makes
        return (fact_entry(f, private, before, cause, marks, gone=True, happened=happened) if gone
                else fact_entry(f, private, before, cause, marks, happened=happened))
    row = f
    if not private:
        drop: dict[str, Any] = {}
        if cause and f.get("because") and present_leaks(f["because"], shown.secrets, shown.present):
            drop["because"] = None
        if (against := f.get("disputed_by")) and present_leaks(fact_text(against), shown.secrets, shown.present):
            drop["disputed_by"] = None
        if drop:
            row = {**f, **drop}
        if before and any(present_leaks(fact_text(h), shown.secrets, shown.present)
                          for h in (earlier(f, marks), first_version(f, marks)) if h):
            before = False  # its `before` and `first` clauses would say the secret: the line names neither
    line = fact_entry(row, private, before, cause, marks, gone=gone, happened=happened)
    if inline := feeling_inline(f):
        line = dataclasses.replace(line, xml=fact_line(row, before, cause, marks, gone, happened,
                                                       body=fact_text(row) + inline))
    return line


CAST_PEERS = 2  # packet-v21: feelings toward and forms of address for other scene characters, per <Cast> group
CAST_PREDICATES_V21 = (*CAST_PREDICATES, "addresses")


def cast_facts_v21(facts: list[dict[str, Any]], to_persona: Callable[[dict[str, Any]], bool],
                   to_cast: Callable[[dict[str, Any]], bool]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """packet-v21's <Cast> group, as (what `cast_facts` picks: the Inspector's rule and packet-v20's group, unchanged;
    the extra lines): the character's newest feeling toward each other scene character (`to_cast`, not the persona), at
    most CAST_PEERS of them, and how they address the persona and each other scene character, at most CAST_PEERS + 1
    of them, newest first. A form of address is one line per condition slot (PHASE-64, `predicates.address_slot`): a
    pair's public and private forms both show, each with its label, and its situational ones at most
    `facts.SITUATIONAL_ADDRESS_MAX`, the newest, as everywhere else."""
    pick = cast_facts(facts, to_persona)
    newest = sorted((f for f in facts if f.get("polarity") != "negative" and f.get("object")
                     and f.get("subject_type") in (None, "character")), key=lambda f: f["position"], reverse=True)
    extra: list[dict[str, Any]] = []
    seen: set[str] = set()
    for f in newest:
        if f["predicate"] == "feels_toward" and to_cast(f) and not to_persona(f) and norm(f["object"]) not in seen \
                and len(seen) < CAST_PEERS:
            seen.add(norm(f["object"]))
            extra.append(f)
    whom: list[str] = []
    slots: dict[str, dict[tuple[str, ...], dict[str, Any]]] = {}
    for f in newest:
        if f["predicate"] != "addresses" or not (to_persona(f) or to_cast(f)):
            continue
        k = norm(f["object"])
        if k not in slots:
            if len(whom) >= CAST_PEERS + 1:
                continue
            whom.append(k)
            slots[k] = {}
        held = slots[k]
        slot = address_slot(f)
        situational = sum(1 for x in held if x[0] == "situational")
        if slot not in held and (slot[0] != "situational" or situational < SITUATIONAL_ADDRESS_MAX):
            held[slot] = f
    extra += [f for k in whom for f in slots[k].values()]
    return pick, extra


def _extra(line: Line, bundle: Any = True) -> Line:
    """packet-v21: a <Cast> line packet-v20's group never had, marked so the compiler places it after the others and
    within its bound (`packet.CAST_EXTRA`); lines of one `bundle` (a pair's forms of address) are placed together."""
    return dataclasses.replace(line, marks={**line.marks, CAST_EXTRA: bundle})


PERSONA_CAST_PREDICATES = ("located_in", "has_status", "possesses")


def persona_cast_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """packet-v21: the persona's own group in <Cast>: where they are, their condition and what they carry (newest, at
    most CAST_ITEMS), so a reply to a message that never names them (Korean drops the subject) still knows the
    persona is hurt, disguised or armed."""
    rows = sorted((f for f in facts if f["predicate"] in PERSONA_CAST_PREDICATES and f.get("polarity") != "negative"),
                  key=lambda f: f["position"], reverse=True)
    return ([f for f in rows if f["predicate"] == "located_in"][:1] + [f for f in rows if f["predicate"] == "has_status"][:1]
            + [f for f in rows if f["predicate"] == "possesses"][:CAST_ITEMS])


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
                in_context: set[str] = frozenset(), aliases: dict[str, frozenset[str]] | None = None,
                pins: Iterable[str] = (), added: Collection[str] = (), shown_v21: Shown | None = None
                ) -> tuple[list[tuple[str, list[Line]]], set[Any]]:
    """Each scene character's current state as the lines it is (PHASE-12 Q4, ADR 0043): place, condition, feeling
    toward the persona, what they carry, and, for a character the message names, their open goals, the one the
    message is about first: an open goal can be long over without a turn saying so (K23), and every request would
    carry it. Up to CAST_MAX characters, the persona left out. A line only some of the scene know stays in its section
    (its Private handling), and a narrator's unknowns are left out (ADR 0035). Returns the groups and the assertions
    they use. A canon fact whose text the prompt held is not said again (D3, ADR 0047). With `aliases`
    (`name_variants`, ADR 0058) the characters the user's message names come first: a given name in the previous
    reply brings more characters into the scene, and the one asked about must keep its group.

    `pins` (packet-v20, PHASE-60 S8, ADR 0087 item 2): the request's pinned characters' keys, in pin order; `added`,
    those in `cast` only because they are pinned. The cast's own groups are chosen as before without them; then each
    pinned character without one of those gets a group of the same shape, at most PIN_EXTRA, in pin order, from its
    own chat's rows only (a row carried from another chat never fills one).

    `shown_v21` (packet-v21): each group also holds the character's feelings toward and forms of address for the other
    scene characters (`cast_facts_v21`), lines are written by `entry_v21` (feeling detail, no public clause that says a
    secret), and the persona has a group of its own after the others (`persona_cast_facts`)."""
    v21 = shown_v21 is not None
    persona = scene.key(r, scene.PERSONA)
    said = norm(query)
    left_out = frozenset(view.get("excluded") or ())  # PHASE-47: not a character, so no <Cast> group
    order = [k for k in cast if k != persona and str(k) not in left_out and k not in added]
    if aliases is not None:
        order.sort(key=lambda k: not any(n in said for n in scene.names({k: cast[k]}, r, aliases)))  # stable
    order = order[:CAST_MAX]
    before, cause = options.policy in BEFORE_POLICIES, options.policy in CAUSE_POLICIES
    happened = options.policy in HAPPENED_POLICIES  # packet-v20 (PHASE-60 S7)

    def shown(row: dict[str, Any]) -> bool:
        if scene.private(row, cast, r) or (row.get("canon") and row["host_logical_id"] in in_context
                                           and not row.get("held_off")):
            return False
        if row.get("carried"):  # an earlier chat's (ADR 0085): not where a character stands in this one's scene
            return False
        return not options.narrator or scene.narrator_knows(row, options.narrator, r)

    mine: dict[str, list[dict[str, Any]]] = {}
    unshown_pairs: set[tuple[str, str]] = set()  # packet-v21: a pair with a form of address the scene may not read
    for f in view["facts"]:
        if f["predicate"] in (CAST_PREDICATES_V21 if v21 else CAST_PREDICATES) and shown(f):
            mine.setdefault(scene.key(r, f["subject"]), []).append(f)
        elif v21 and f["predicate"] == "addresses" and f.get("object"):
            unshown_pairs.add((scene.key(r, f["subject"]), scene.key(r, f["object"])))
    others = {k for k in cast if k != persona and str(k) not in left_out}
    groups: list[tuple[str, list[Line]]] = []
    used: set[Any] = set()

    def lines_of(k: str) -> list[Line]:
        own = mine.get(k, [])
        if k not in order:  # a group only a pin brings: never from rows carried from another chat (PHASE-60 S8)
            own = [f for f in own if not f.get("carried")]
        to_persona = lambda f: scene.key(r, f["object"]) == persona  # noqa: E731
        more: list[dict[str, Any]] = []
        if v21:
            pick, more = cast_facts_v21(own, to_persona, lambda f: scene.key(r, f["object"]) in others - {k})
            # a pair's slots show together or not at all: with one of them private here (or withheld), the pair's
            # forms of address stay in lead and <Private>, as packet-v20 has them
            more = [f for f in more if f["predicate"] != "addresses"
                    or (k, scene.key(r, f["object"])) not in unshown_pairs]
        else:
            pick = cast_facts(own, to_persona)
        named = any(n in said for n in scene.names({k: cast[k]}, r, aliases))
        goals = [t for t in view["threads"] if named and t.get("kind") == "goal" and t["status"] == "open"
                 and scene.key(r, t["by"]) == k and shown(t)]
        goals.sort(key=lambda t: (similarity(query, t.get("text")) if query else 0.0, t["position"]), reverse=True)
        return [entry_v21(f, False, before, cause, options.history_marks, shown_v21, happened=happened)
                for f in pick] + [thread_entry(t, happened=happened) for t in goals[:CAST_GOALS]] + [
            _extra(entry_v21(f, False, before, cause, options.history_marks, shown_v21, happened=happened),
                   f"addresses:{norm(f['object'])}" if f["predicate"] == "addresses" else True)
            for f in more]

    extra = 0
    for k in [*order, *(k for k in pins if k not in order)]:
        if k not in order and (extra >= PIN_EXTRA or k not in cast or k == persona or str(k) in left_out):
            continue
        lines = lines_of(k)
        if lines:
            groups.append((cast[k], lines))
            used |= {line.ref.get("assertion") for line in lines if not line.marks.get(CAST_EXTRA)}
            extra += k not in order
    if v21 and persona in cast:  # packet-v21: the persona's own group, after the others
        own = [f for f in mine.get(persona, []) if not f.get("carried")]
        lines = [_extra(entry_v21(f, False, before, cause, options.history_marks, shown_v21, happened=happened))
                 for f in persona_cast_facts(own)]
        if lines:
            groups.append((cast[persona], lines))
            used |= {line.ref.get("assertion") for line in lines if not line.marks.get(CAST_EXTRA)}
    return groups, used


def _gone_status(f: dict[str, Any], v21: bool = False) -> bool:
    """Whether a current fact says its character is gone (PHASE-60 S3, ADR 0082 item 2): a narrated, positive,
    undisputed `has_status` the word rule calls gone, or a `located_in` whose whole place name is no place. Canon is
    left out: it is how things stood before the story, which the story may have changed without saying so, and a
    character the setting calls dead or missing can be one the story is about (a missed pin is today's behaviour, a
    wrong pin silences a living character). A row carried from another chat is never one either.

    `v21` (packet-v21): `gone.py`'s packet-v21 word lists (`v21=True`), and a row carried by a `continue` link counts:
    a character dead in the chat this one continues stays dead here until this chat's story brings them back."""
    if (f.get("canon") or (f.get("carried") and not v21) or f.get("polarity") != "positive" or f.get("disputed_by")
            or f.get("subject_type") != "character" or f.get("turn") is None):
        return False
    if f["predicate"] == "has_status":
        return is_gone_status(f.get("value"), v21=True) if v21 else is_gone_status(f.get("value"))
    return f["predicate"] == "located_in" and (is_gone_place(f.get("object"), v21=True) if v21
                                               else is_gone_place(f.get("object")))


# packet-v21: what shows a character is there: narrated, actual, said of them as the subject, of their body or of what
# they do (never a claim, a dream, a feeling toward them, nor a flashback the story dates with `when_happened`)
PRESENCE_PREDICATES = frozenset({"located_in", "event", "has_status", "possesses", "destroyed", "vital_status"})


def says_gone(x: dict[str, Any]) -> bool:
    """packet-v21: a row that says its character is (still) dead or gone, never a return: a gone status or place
    (`_gone_status`), a destruction, or a vital status the word rule calls gone (`gone.is_gone_vital`)."""
    if x.get("predicate") == "destroyed":
        return True
    if x.get("predicate") == "vital_status":
        return is_gone_vital(x.get("value"))
    return _gone_status(x, True)


def presence_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """packet-v21: the rows that show their subject present (PRESENCE_PREDICATES), narrated and actual, of this chat."""
    return [x for x in rows if x.get("predicate") in PRESENCE_PREDICATES and x.get("source") == "narration"
            and (x.get("modality") or "actual") == "actual" and x.get("subject_type") == "character"
            and (x.get("polarity") or "positive") == "positive"
            and not x.get("when_happened") and not x.get("canon") and not x.get("carried")
            and x.get("turn") is not None and x.get("subject")]


def gone_rows(view: dict[str, Any], r: Any, now: int | None, *, v21: bool = False) -> list[dict[str, Any]]:
    """The characters who are gone (PHASE-60 S3), each by their newest gone fact, newest first, at most GONE_MAX.

    From the view's current narrated facts only (a later status replaced an earlier one there; a claim is what someone
    said). Not the persona, nor a character the owner left out (PHASE-47). Not a character the story brought back: one
    who is a subject, object or typed participant of a row (fact, claim or other) of a turn after the gone fact's, in
    the scene window `scene.cast` reads (CAST_TURNS turns before `now`). Their own gone rows, canon rows and carried
    rows bring no one back.

    `v21` (packet-v21): `_gone_status(v21=True)`, and only a row that shows the character present (`presence_rows`: a
    mourner's feeling toward them, a dream, a rumour or a flashback does not) brings them back, at any turn after the
    gone fact's up to the one before `now`: a resurrection told more than CAST_TURNS turns ago still holds."""
    if r is None:
        return []
    persona = scene.key(r, scene.PERSONA)
    left_out = frozenset(view.get("excluded") or ())
    newest: dict[str, dict[str, Any]] = {}
    gone_ids: set[int] = set()
    for f in view["facts"]:
        if not (_gone_status(f, True) if v21 else _gone_status(f)):
            continue
        gone_ids.add(id(f))
        k = scene.key(r, f["subject"])
        if scene.is_persona(r, f["subject"]) or k == persona or str(k) in left_out:
            continue
        if k not in newest or (f["turn"], f["position"]) > (newest[k]["turn"], newest[k]["position"]):
            newest[k] = f
    if not newest:
        return []
    rows = view["facts"] + view["claims"] + view["other"]
    until = now - 1 if now is not None else max((x["turn"] for x in rows if x.get("turn") is not None), default=-1)
    if v21:
        back: set[str] = set()
        source = view.get("assertions")
        gone_keys = {(f["id"], f["turn"]) for f in newest.values()}
        for x in presence_rows(source if source is not None else rows):
            if id(x) in gone_ids or (x.get("id"), x["turn"]) in gone_keys or x["turn"] > until:
                continue
            k = scene.key(r, x["subject"])
            if k in newest and x["turn"] > newest[k]["turn"] and not says_gone(x):
                back.add(k)
        kept = [f for k, f in newest.items() if k not in back]
        kept.sort(key=lambda f: (f["turn"], f["position"]), reverse=True)
        return kept[:GONE_MAX]
    since = until - scene.CAST_TURNS + 1
    last_seen: dict[str, int] = {}  # each character's latest turn in the window, by the rows `scene.cast` reads
    for x in rows:
        if (id(x) in gone_ids or x.get("canon") or x.get("carried") or x.get("turn") is None
                or not since <= x["turn"] <= until):
            continue
        names = [x["subject"]] if x.get("subject_type") == "character" else []
        if x.get("object_type") == "character":
            names.append(x.get("object"))
        names += [p["name"] for p in x.get("participants") or () if p.get("type") == "character"]
        for name in names:
            if name:
                k = scene.key(r, name)
                last_seen[k] = max(last_seen.get(k, x["turn"]), x["turn"])
    kept = [f for k, f in newest.items() if last_seen.get(k, f["turn"]) <= f["turn"]]
    kept.sort(key=lambda f: (f["turn"], f["position"]), reverse=True)
    return kept[:GONE_MAX]


def gone_lines(view: dict[str, Any], r: Any, cast: dict[str, str], now: int | None,
               options: RecallOptions) -> list[Line]:
    """packet-v20 (PHASE-60 S3): each gone character's status line, marked gone="true", newest first, private as any
    fact line is in this scene (ADR 0034). Every other policy: none."""
    if options.policy not in GONE_POLICIES:
        return []
    before, cause = options.policy in BEFORE_POLICIES, options.policy in CAUSE_POLICIES
    v21 = options.policy in V21_POLICIES
    if v21:  # packet-v21: a public gone line drops a clause that would say a secret (`entry_v21`)
        shown = Shown(view.get("secrets") or [], scene.names(cast, r))
        return [entry_v21(f, scene.private(f, cast, r), before, cause, options.history_marks, shown, gone=True,
                          happened=options.policy in HAPPENED_POLICIES) for f in gone_rows(view, r, now, v21=True)]
    return [fact_entry(f, scene.private(f, cast, r), before, cause, options.history_marks, gone=True,
                       happened=options.policy in HAPPENED_POLICIES) for f in gone_rows(view, r, now)]


def pin_gone(g: Gathered, view: dict[str, Any], r: Any, now: int | None, options: RecallOptions) -> list[dict[str, Any]]:
    """Put each gone character's status line where it goes (PHASE-60 S3, ADR 0082 item 3), once: first in the
    character's <Cast> group when `cast_groups` gave it the line (it judged privacy, the narrator and D3 there),
    else in `g.gone` (first in <Facts>, or <Private>) through this chat's memory mode (`_moded`). The same assertion
    leaves the lead and facts. A gone fact the memory mode already withheld as a fact stays as the mode left it (a
    strict <Secret> where the fact was), so nothing is withheld twice. Returns the rows pinned."""
    if options.policy not in GONE_POLICIES:
        return []
    withheld = {line.ref.get("assertion") for line in g.withheld_lines}
    lines = {line.ref.get("assertion"): line for line in gone_lines(view, r, g.cast, now, options)
             if line.ref.get("assertion") not in withheld}
    if not lines:
        return []
    in_cast: set[Any] = set()
    groups: list[tuple[str, list[Line]]] = []
    for name, group in g.cast_lines:
        own = [line.ref.get("assertion") for line in group if line.ref.get("assertion") in lines]
        if own:
            in_cast.update(own)
            group = [lines[a] for a in own] + [line for line in group if line.ref.get("assertion") not in lines]
        groups.append((name, group))
    g.cast_lines = groups
    g.lead = [line for line in g.lead if line.ref.get("assertion") not in lines]
    g.facts = [line for line in g.facts if line.ref.get("assertion") not in lines]
    rows = [f for f in view["facts"] if f["id"] in lines]
    rows.sort(key=lambda f: (f["turn"], f["position"]), reverse=True)
    g.gone = _moded([lines[f["id"]] for f in rows if f["id"] not in in_cast], rows, g, r, options)
    return rows


def appearances(view: dict[str, Any], r: Any, *, v21: bool = False) -> dict[str, list[int]]:
    """Each character's turns, by entity key, from every assertion the view read: superseded versions too (a place the
    story replaced was still an appearance), as subject, object or typed participant (PHASE-60 S4). Canon rows are
    before the story, and rows carried from another chat are not this chat's story: neither is an appearance.

    `v21` (packet-v21): only a row that shows the character present as its subject (`presence_rows`): a rumour about
    them, someone's feeling toward them or a dream of them is no appearance, so it never starts a run."""
    rows = view.get("assertions")
    if rows is None:
        rows = view["facts"] + view["claims"] + view["other"]
    if v21:
        found: dict[str, set[int]] = {}
        for x in presence_rows(rows):
            found.setdefault(scene.key(r, x["subject"]), set()).add(x["turn"])
        return {k: sorted(v) for k, v in found.items()}
    out: dict[str, set[int]] = {}
    for x in rows:
        if x.get("canon") or x.get("carried") or x.get("turn") is None:
            continue
        names = [x["subject"]] if x.get("subject_type") == "character" else []
        if x.get("object_type") == "character":
            names.append(x.get("object"))
        names += [p["name"] for p in x.get("participants") or () if p.get("type") == "character"]
        for name in names:
            if name:
                out.setdefault(scene.key(r, name), set()).add(x["turn"])
    return {k: sorted(v) for k, v in out.items()}


def return_marks(view: dict[str, Any], r: Any, cast: dict[str, str], cast_lines: list[tuple[str, list[Line]]],
                 now: int, served: Callable[[int], bool] | Collection[int], policy: str = "packet-v20") -> dict[str, str]:
    """packet-v20 (PHASE-60 S4, ADR 0082 item 4): {<Cast> name: back_after value} for each character with a <Cast>
    group, not the persona, whose current run began at most RUN_START_MAX turns ago after at least GAP_MIN served turns
    away (`absence.return_gap`). `served` is asked only when a gap is possible even if every turn were served. Every
    other policy: none."""
    if policy not in RETURN_GAP_POLICIES or r is None or not cast_lines:
        return {}
    persona = scene.key(r, scene.PERSONA)
    key_of = {name: k for k, name in cast.items()}
    seen = appearances(view, r, v21=True) if policy in V21_POLICIES else appearances(view, r)
    out: dict[str, str] = {}
    for name, _ in cast_lines:
        k = key_of.get(name)
        if k is None or k == persona or scene.is_persona(r, name):
            continue
        turns = seen.get(k, [])
        if absence.return_gap(turns, lambda _t: True, now) is None:  # no gap even if every turn were served
            continue
        if (gap := absence.return_gap(turns, served, now)) is not None:
            out[name] = absence.back_after_label(gap)
    return out


def settled_lines(g: Gathered, view: dict[str, Any], r: Any, query: str, now: int | None,
                  rest: frozenset[tuple[str, str]], options: RecallOptions,
                  aliases: dict[str, frozenset[str]] | None = None) -> list[Line]:
    """packet-v20 (PHASE-60 S4, ADR 0082 item 5): the lines of threads closed within SETTLED_TURNS of `now` whose maker
    or recipient (not the persona) is in the scene or named in the user's message, under any name they go by
    (`aliases`): bad endings first, then newest, at most SETTLED_MAX (`absence.settled`). Supportive: a tired one rests
    as an open thread does and holds no place (`_rested`, the same key as its open line). A thread carried from another
    chat has none. Private as any thread is in this scene, through this chat's memory mode (`_moded`). Every other
    policy: none."""
    if options.policy not in SETTLED_POLICIES or r is None or now is None:
        return []
    persona = scene.key(r, scene.PERSONA)
    present = set(g.cast) - {persona}
    said = norm(query)
    v21 = options.policy in V21_POLICIES

    def involved(t: dict[str, Any]) -> bool:
        if v21 and t.get("by") and scene.is_persona(r, t["by"]):
            return True  # packet-v21: the persona's own aim, question or promise, settled lately
        for name in (t.get("by"), t.get("to")):
            if not name or scene.is_persona(r, name):
                continue
            k = scene.key(r, name)
            if k == persona:
                continue
            if k in present or any(n in said for n in scene.names({k: name}, r, aliases)):
                return True
        return False

    own = [t for t in view["threads"] if not t.get("carried")]
    picked = absence.settled(own, now, lambda t: involved(t) and bool(
        _rested([t], "thread", rest, g, v21=True, settled=True) if v21 else _rested([t], "thread", rest, g)))
    if v21:  # packet-v21: a thread ended in secret is as private as its ending
        picked = [closing_marks(t) for t in picked]
        return _moded([settled_entry(t, scene.private(t, g.cast, r), options.policy in HAPPENED_POLICIES)
                       for t in picked], picked, g, r, options)
    return _moded([settled_entry(t, scene.private(t, g.cast, r), options.policy in HAPPENED_POLICIES) for t in picked],
                  view["threads"], g, r, options)


def closing_marks(t: dict[str, Any]) -> dict[str, Any]:
    """packet-v21: a settled thread under its closing's knowledge marks when they say less people know: a promise made
    openly and broken in secret is known to be broken only by those who saw it. The thread as it is otherwise."""
    closed = t.get("closed_by")
    if not isinstance(closed, Mapping) or closed.get("knowledge") != "limited":
        return t
    hidden_now, known_now = list(t.get("hidden_from") or ()), list(t.get("known_by") or ())
    hidden, known = list(closed.get("hidden_from") or ()), list(closed.get("known_by") or ())
    more_hidden = [n for n in hidden if n not in hidden_now]
    fewer_know = bool(known) and (t.get("knowledge") != "limited" or not known_now
                                  or (set(known) < set(known_now)))
    if t.get("knowledge") == "limited" and not more_hidden and not fewer_know:
        return t
    return {**t, "knowledge": "limited", "known_by": known or known_now or None,
            "hidden_from": (hidden_now + more_hidden) or None}


def told_lines(g: Gathered, view: dict[str, Any], r: Any, query: str, previous_ai: str, in_context: set[str],
               options: RecallOptions, aliases: dict[str, frozenset[str]] | None = None,
               rest: frozenset[tuple[str, str]] = frozenset()) -> list[Line]:
    """packet-v20 (PHASE-60 S8, ADR 0086): at most TOLD_MAX lines of who told whom (`view["told"]`, read only under
    TOLD_POLICIES), as <Fact kind="told">.

    A told row is a candidate when its teller or hearer (not the persona, who is in every scene) is in the scene or
    named in the user's message, under any name they go by (`aliases`), as for a settled thread. The candidates are
    ranked as facts are (`relevant_facts`: what the message names or its words point at first); one only the scene
    brings follows, newest first. Neither is said again while its message is in the prompt (D3), and a tired one rests
    (`_rested`). A line whose value or quote says a secret still kept from someone (`summaries.leaks`, stricter with
    such a someone in the scene) is left out as a keyword-only excerpt is (D62), recorded as a hidden ledger entry
    (`secret_gate`); the next candidate may take its place. The rest is any fact line's: private as such in this scene,
    through this chat's memory mode (`_moded`: strict, narrator). Every other policy: none."""
    if options.policy not in TOLD_POLICIES or r is None or not view.get("told"):
        return []
    persona = scene.key(r, scene.PERSONA)
    present = set(g.cast) - {persona}
    said = norm(query)
    v21 = options.policy in V21_POLICIES

    def involved(t: dict[str, Any]) -> bool:
        about = [p.get("name") for p in t.get("participants") or () if v21 and p.get("type") in (None, "character")]
        for name in (t.get("subject"), t.get("object"), *about):
            if not name or scene.is_persona(r, name):
                continue
            k = scene.key(r, name)
            if k != persona and (k in present or any(n in said for n in scene.names({k: name}, r, aliases))):
                return True
        return False

    candidates = [t for t in view["told"] if not t.get("carried") and involved(t)]
    if not candidates:
        return []
    names = scene.names(g.cast, r, aliases)
    ranked = relevant_facts(candidates, query, previous_ai, in_context, len(candidates), persona=r.persona_names,
                            present=names, aliases=aliases, named=g.named,
                            named_by_words=options.policy in NAMED_POLICIES)
    chosen = {id(t) for t in ranked}
    ranked += sorted((t for t in candidates if id(t) not in chosen and t["host_logical_id"] not in in_context),
                     key=lambda t: t["position"], reverse=True)
    picked: list[dict[str, Any]] = []
    for t in _rested(ranked, "fact", rest, g):
        if len(picked) >= TOLD_MAX:
            break
        # packet-v21: only a secret kept from someone in the scene withholds it: two holders telling each other alone
        # say nothing anyone present must not hear
        leaked = (present_leaks if v21 else summaries.leaks)
        if any(leaked(form, view["secrets"], names) for form in (t.get("value"), t.get("evidence")) if form):
            if options.policy in LABEL_POLICIES:
                g.hidden_entries.append(hidden_entry("fact", {"assertion": t["id"]}, t.get("turn"), "secret_gate"))
            continue
        picked.append(t)
    happened = options.policy in HAPPENED_POLICIES
    return _moded([told_entry(t, scene.private(t, g.cast, r), happened) for t in picked], picked, g, r, options)


def regression_lines(g: Gathered, view: dict[str, Any], r: Any, query: str, previous_ai: str, in_context: set[str],
                     options: RecallOptions, aliases: dict[str, frozenset[str]] | None = None) -> list[Line]:
    """packet-v20 (PHASE-60 S6, ADR 0085 item 5): what the characters a regression link names remember of the previous
    timeline (`view["regression"]`), as the lines of its own <Regression> group. Facts are ranked as facts are
    (`relevant_facts`), threads as threads are (`relevant_threads`: open and mentioned); the two are merged by how the
    message names them (in the user's message, then in the previous reply, then by its words only), then each list's own
    order, the newer source position first on a tie; at most REGRESSION_MAX. Each line says timeline="previous" and its
    rememberers as known_by, and no turn (none of this chat's); private (limited knowledge), through this chat's memory
    mode (`_moded`: strict mode withholds it as a Secret line, a narrator who does not remember it never sees it). Its
    marks name its rememberers (`remembered_by`), a Secret line's too. None of them is a fact, a <Cast> line, a gone pin,
    a thread, a settled line or a return mark. Every other policy: none."""
    if options.policy not in CARRY_POLICIES or r is None or not view.get("regression"):
        return []
    rows = [{**x, "timeline": "previous"} for x in view["regression"]]
    persona = r.persona_names
    facts = relevant_facts([x for x in rows if x["line"] == "fact"], query, previous_ai, in_context, len(rows),
                           options.events_limit, persona, scene.names(g.cast, r, aliases),
                           causes=options.policy in CAUSE_POLICIES, aliases=aliases)
    thread_rows = [x for x in rows if x["line"] == "thread"]
    if options.policy in V21_POLICIES:  # packet-v21: a promise kept or broken in that timeline is remembered too
        threads = carry.regression_threads(thread_rows, query, previous_ai, in_context, len(rows), persona,
                                           about=options.policy in ABOUT_POLICIES, aliases=aliases)
    else:
        threads = relevant_threads(thread_rows, query, previous_ai, in_context, len(rows),
                                   persona, about=options.policy in ABOUT_POLICIES, aliases=aliases)
    said, before = norm(query), norm(previous_ai)

    def mention(x: dict[str, Any]) -> int:
        names = {n for n in variants.widened(x.get("names") or [], aliases) if len(n) >= 2} - persona
        return 2 if any(n in said for n in names) else (1 if any(n in before for n in names) else 0)

    ranked = [(x, i) for i, x in enumerate(facts)] + [(x, i) for i, x in enumerate(threads)]
    ranked.sort(key=lambda p: (-mention(p[0]), p[1], -(p[0].get("position") or 0)))
    picked = [x for x, _ in ranked[:REGRESSION_MAX]]
    cause = options.policy in CAUSE_POLICIES
    lines = []
    for x in picked:
        line = (fact_entry(x, True, False, cause, options.history_marks) if x["line"] == "fact"
                else thread_entry(x, True))
        lines.append(dataclasses.replace(line, turn=None, marks={**line.marks,
                                                                 "remembered_by": list(x.get("known_by") or ())}))
    by_id = {x["id"]: x for x in picked}
    out: list[Line] = []
    for line in _moded(lines, picked, g, r, options):
        row = by_id.get(line.ref.get("assertion"))
        if row is not None and "remembered_by" not in line.marks:  # a strict Secret line still says who remembers
            line = dataclasses.replace(line, marks={**line.marks, "remembered_by": list(row.get("known_by") or ())})
        out.append(line)
    return out


RERANK_DOC_PAD = 200  # packet-v21: characters of the message around the matched chunk the reranker reads


def rerank_doc(c: Mapping[str, Any]) -> str:
    """packet-v21: what the reranker reads of a candidate: the vector chunk it was found by (`text_start`…`text_end`),
    with up to RERANK_DOC_PAD characters around it, at most `rerank.MAX_DOC_CHARS`; the message's start for a candidate
    no chunk found (a lexical or keyword hit)."""
    clean = c.get("clean") or ""
    start, end = c.get("text_start"), c.get("text_end")
    if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end:
        return clean[:rerank.MAX_DOC_CHARS]
    room = max(0, rerank.MAX_DOC_CHARS - (end - start))
    lo = max(0, start - min(RERANK_DOC_PAD, room // 2))
    return clean[lo:lo + rerank.MAX_DOC_CHARS]


def reranked_above(eligible: list[dict[str, Any]]) -> frozenset[str]:
    """packet-v21: the candidates the reranker put first or scored at least EXCERPT_FLOOR of its best (when its scores
    are not negative; a score of any sign keeps only the first)."""
    scored = [c for c in eligible if "rerank" in c]
    if not scored:
        return frozenset()
    best = float(scored[0]["rerank"])
    out = {str(scored[0]["id"])}
    if best > 0 and all(float(c["rerank"]) >= 0 for c in scored):
        out |= {str(c["id"]) for c in scored if float(c["rerank"]) >= EXCERPT_FLOOR * best}
    return frozenset(out)


CUT_RISK = 0.5  # packet-v21: a form this share of a secret's bar or more may cross it once cut shorter


def _leak_margin(text: str | None, secrets: list[dict[str, Any]], present: frozenset[str]) -> float:
    """How close `text` comes to repeating a secret, as the largest share of its `summaries.leaks` bar."""
    if not text:
        return 0.0
    return max((summaries.leak_score(s, text) / (summaries.LEAK_NEAR if any(norm(n) in present for n in s["open"])
                                                 else summaries.LEAK_MIN)
                for s in secrets if s.get("open")), default=0.0)


def gate_excerpts_v21(g: Gathered, secrets: list[dict[str, Any]], present: frozenset[str], gated: Collection[str],
                      options: RecallOptions) -> None:
    """packet-v21: every excerpt and quote against the secrets still kept from someone (`summaries.leaks`), not only the
    ones the keyword and quote routes alone found (`gated`, checked before as they were). A strict or narrator chat
    leaves out one that repeats a secret (`secret_gate`). Otherwise one that repeats a secret kept from someone in the
    scene (`present_leaks`) is fenced in <Private>, with the secret's holders and those present it is kept from as its
    knowledge marks; one that comes close may not be cut (a shorter form can cross the bar)."""
    withhold = options.strict or bool(options.narrator)
    kept: list[Excerpt] = []
    for e in g.ranked:
        if e.revision_id in gated:  # the keyword-only gate checked its forms; they are the only ones placed
            kept.append(e)
            continue
        forms = [f for f in (e.text, e.short) if f]
        if withhold:
            if any(summaries.leaks(f, secrets, present) for f in forms):
                g.excerpts_withheld += 1
                if options.policy in LABEL_POLICIES:
                    g.hidden_entries.append(hidden_entry("quote" if e.quote else "excerpt",
                                                         {"revision": e.revision_id}, e.turn, "secret_gate"))
                continue
        else:
            hits = [s for f in forms for s in present_leaks(f, secrets, present)]
            if hits:
                holders = tuple(dict.fromkeys(n for s in hits for n in s.get("holders") or ()))
                hidden = tuple(dict.fromkeys(n for s in hits for n in s.get("open") or () if norm(n) in present))
                kept.append(dataclasses.replace(e, known_by=holders, hidden_from=hidden))
                g.excerpts_fenced += 1
                continue
        if e.cut_ok and max(_leak_margin(f, secrets, present) for f in forms) >= CUT_RISK:
            e = dataclasses.replace(e, cut_ok=False)
        kept.append(e)
    g.ranked = kept


STATE_GATE_LETTERS = 3  # packet-v21: a status value with fewer letters ("30", "우물") says too little to repeat a secret


def _letters(text: str) -> int:
    """The letters of `text`: no digit, space or sign (a number alone shares a trigram with any secret holding it)."""
    return sum(1 for ch in text if ch.isalpha())


def gate_state_v21(g: Gathered, secrets: list[dict[str, Any]], present: frozenset[str], options: RecallOptions) -> None:
    """packet-v21: a <State> item or <StateHistory> line whose value repeats a secret still kept from someone is left
    out (`secret_gate`), as a recalled excerpt's source clock is: against the scene (`present`), or in a strict or
    narrator chat against everyone any secret is kept from."""
    who = (frozenset(norm(n) for s in secrets for n in s.get("open") or ())
           if options.strict or options.narrator else present)
    kept: list[StateItem] = []
    for item in g.state:
        values = [item.value, item.since_previous or "", *(v for _, v in item.history)]
        if any(_letters(v) >= STATE_GATE_LETTERS and summaries.leaks(v, secrets, who) for v in values if v):
            g.state_withheld += 1
            if options.policy in LABEL_POLICIES:
                g.hidden_entries.append(hidden_entry("state_history" if item.history else "state", {"key": item.key},
                                                     item.turn, "secret_gate"))
            continue
        kept.append(item)
    g.state = kept


def compile_gathered(g: Gathered, budget: int, policy: str) -> Compiled:
    """One request's packet from what `gather` offered (the request and its replay compile alike)."""
    compiled = compile_lines(g.ranked, budget, state=g.state, threads=g.threads, facts=g.facts, policy=policy, lead=g.lead,
                             note=g.note, story=g.story, cast=g.cast_lines, named=frozenset(g.named),
                             risky=frozenset(g.risky), gone=g.gone, cast_marks=g.cast_marks, settled=g.settled,
                             regression=g.regression, regression_names=g.regression_names)
    compiled = source_time.supplement(compiled, g.ranked, g.source_clocks, budget, policy)
    if policy in LABEL_POLICIES:
        # Diagnostics never take part in selection, token fitting or the rest/echo calculation.
        compiled.ledger.extend(dict(e) for e in g.hidden_entries)
    return compiled


def rested(g: Gathered, compiled: Compiled) -> int:
    """Lines left out resting (PHASE-34 Q3): those gather left out, and the excerpts the compiler did (a resting
    excerpt is offered marked and placed only when it holds the reserved first place)."""
    return g.rested + sum(1 for e in compiled.ledger if e.get("why") == "resting")


def below_floor(g: Gathered, compiled: Compiled) -> int:
    """Excerpts under the activation threshold (PHASE-34 Q4), left out by the compiler as resting ones are."""
    return g.below_floor + sum(1 for e in compiled.ledger if e.get("why") == "below_floor")


def quiet_feeling(row: Mapping[str, Any]) -> bool:
    """packet-v21: a feeling its holder keeps to themselves (`feels_toward`, limited, kept from no one by name), not a
    secret the story plots: strict mode leaves it readable in <Private>, since an opaque <Secret> would leave the model
    playing that character without their own feeling. Never a previous timeline's line (a regression row)."""
    return (row.get("predicate") == "feels_toward" and row.get("knowledge") == "limited"
            and not row.get("hidden_from") and not row.get("timeline"))


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
            if options.policy in LABEL_POLICIES:
                g.hidden_entries.append(hidden_entry(line.kind, line.ref, line.turn, "mode_withheld"))
            continue
        if (options.strict and line.private and r is not None and options.policy in V21_POLICIES
                and quiet_feeling(row)):
            out.append(line)  # packet-v21: an unspoken feeling is not a plotted secret; its <Private> line stays
            continue
        if options.strict and line.private and r is not None:
            holders, absent = scene.missing(row, g.cast, r)
            g.withheld += 1
            g.withheld_lines.append(line)
            if options.policy in LABEL_POLICIES:
                g.hidden_entries.append(hidden_entry(line.kind, line.ref, line.turn, "mode_withheld"))
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
                   cut: int, replies: bool = False) -> list[dict[str, Any]]:
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
        """ + REPLIES_ONLY + """
        ORDER BY am.position LIMIT 20
        """,
        {"head": head, "lo": lo, "hi": hi, "norm": normtext.active(), "cut": cut,
         "upto": 2**31 - 1 if upto is None else upto, "replies": replies}, prepare=False).fetchall()


def _first_met(conn: psycopg.Connection, head: UUID, keys: list[list[str]], upto: int | None,
               cut: int, replies: bool = False) -> int | None:
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
                    """ + REPLIES_ONLY).format(named=sql.SQL(" OR ").join(  # strpos, as the route's search
                        sql.SQL("strpos(rt.clean_content, {}) > 0").format(sql.Literal(f)) for f in forms)),
                    {"head": head, "norm": normtext.active(), "cut": cut,
                     "upto": 2**31 - 1 if upto is None else upto, "replies": replies}, prepare=False).fetchone()
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
                    cut: int, replies: bool = False) -> tuple[list[dict[str, Any]], dict[str, float], str]:
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
                """ + REPLIES_ONLY).format(hits=sql.SQL(", ").join(holds(w) for w in words), quoted=quoted),
                {"head": head, "norm": normtext.active(), "cut": cut, "upto": 2**31 - 1 if upto is None else upto,
                 "replies": replies}, prepare=False).fetchall()
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
                """, {"head": head, "norm": normtext.active(), "ids": ids}, prepare=False).fetchall()
            _apply(conn, {"statement_timeout": previous["t"]})
    except psycopg.errors.QueryCanceled:
        return [], {}, "timeout"
    order = {i: n for n, i in enumerate(ids)}
    rows.sort(key=lambda r: order[r["id"]])
    return rows, dict(zip(words, weight)), "on"


def _risky_last(rows: list[dict[str, Any]], view: dict[str, Any], named: set[str]) -> list[dict[str, Any]]:
    """`rows` with the risky ones last (PHASE-34 Q1: a disputed or contradicted line is offered after the other
    supportive ones), applied before the limits so that it never takes an ordinary line's slot (a review's
    follow-up). A named, private or secret line keeps its place: it is required."""
    contradicted = {str(c["fact"]) for c in view.get("conflicts") or [] if c.get("fact") is not None}

    def risky(r: dict[str, Any]) -> bool:
        return (bool(r.get("disputed_by")) or str(r["id"]) in contradicted) and str(r["id"]) not in named \
            and not (r.get("hidden_from") or r.get("known_by"))
    return [r for r in rows if not risky(r)] + [r for r in rows if risky(r)]


def _rested(rows: list[Any], kind: str, rest: frozenset[tuple[str, str]], g: Gathered,
            ident: Callable[[Any], str] = lambda r: str(r["id"]),
            hit: Callable[[Any], bool] = lambda r: False, *, v21: bool = False, settled: bool = False) -> list[Any]:
    """`rows` without the tired ones (PHASE-34 Q3, amended: a resting line is left out; moved behind the others it was
    placed anyway whenever the budget had room, which on S1 was nearly always). A line the question names (`named`;
    for an excerpt, `hit`: the question's words found it, lexically or by keyword) is required and never rests; one a
    reply used is not tired (`overuse.tired` reads the echo)."""
    if not rest:
        return rows
    def tired(r: Any) -> bool:
        if kind != "excerpt" and (r.get("hidden_from") or r.get("known_by")):
            return False  # a knowledge boundary is required wherever it is placed (Private, Secret): it never rests
        if v21 and kind in ("fact", "thread") and overuse.exempt_from_rest(kind, r.get("predicate"), settled):
            return False  # packet-v21: how two stand, and a thread just settled, hold for every reply
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


def _quote_speakers(conn: psycopg.Connection, ids: list[Any], extractor_key: str | None,
                    known_at: datetime | None = None, *, any_generation: bool = False) -> dict[str, str]:
    """Normalized quoted words → the speaker an extraction of the generation in use named for them (PHASE-45 S3): live
    then (with `known_at`, a replay: not written since, or discarded since). A line two extractions name differently
    names nobody. Only extract-v17 writes speakers: with another generation in use there are none.

    `any_generation` (packet-v21): a change of model, of `extract_target_chars` or of compiler makes a new generation
    that may write no speakers, and the records the earlier one wrote for the same messages were lost to the quote
    route. Every live extraction serving those messages with speakers counts then, by generation: the one in use
    first, then the newest activated; each line is named by the first generation that names it, and a line that
    generation names differently names nobody."""
    if not ids:
        return {}
    if any_generation:
        return _quote_speakers_any(conn, ids, extractor_key, known_at)
    if not extractor_key:
        return {}
    seen: dict[str, set[str]] = {}
    for row in conn.execute(
            "SELECT speakers FROM extraction WHERE extractor_key = %(key)s AND speakers IS NOT NULL"
            " AND members && %(ids)s::uuid[] AND created_at <= coalesce(%(at)s::timestamptz, now())"
            " AND (discarded_at IS NULL OR discarded_at > coalesce(%(at)s::timestamptz, now()))",
            {"key": extractor_key, "ids": [str(i) for i in ids], "at": known_at}, prepare=False).fetchall():
        for item in row["speakers"] or ():
            if isinstance(item, dict) and item.get("q") and item.get("speaker"):
                seen.setdefault(norm(str(item["q"])), set()).add(str(item["speaker"]))
    return {k: next(iter(v)) for k, v in seen.items() if len(v) == 1}


def _quote_speakers_any(conn: psycopg.Connection, ids: list[Any], extractor_key: str | None,
                        known_at: datetime | None) -> dict[str, str]:
    """`_quote_speakers` over every generation (packet-v21), the one in use first, then the newest activated."""
    by_generation: dict[str, dict[str, set[str]]] = {}
    order: list[str] = []
    for row in conn.execute(
            "SELECT x.extractor_key AS key, x.speakers FROM extraction x"
            " LEFT JOIN projection_generation pg ON pg.key = x.extractor_key"
            " WHERE x.speakers IS NOT NULL AND x.extractor_key IS NOT NULL AND x.members && %(ids)s::uuid[]"
            " AND x.created_at <= coalesce(%(at)s::timestamptz, now())"
            " AND (x.discarded_at IS NULL OR x.discarded_at > coalesce(%(at)s::timestamptz, now()))"
            " ORDER BY (x.extractor_key IS NOT DISTINCT FROM %(key)s) DESC, pg.activated_at DESC NULLS LAST,"
            " x.extractor_key, x.created_at DESC",
            {"key": extractor_key, "ids": [str(i) for i in ids], "at": known_at}, prepare=False).fetchall():
        if row["key"] not in by_generation:
            by_generation[row["key"]] = {}
            order.append(row["key"])
        seen = by_generation[row["key"]]
        for item in row["speakers"] or ():
            if isinstance(item, dict) and item.get("q") and item.get("speaker"):
                seen.setdefault(norm(str(item["q"])), set()).add(str(item["speaker"]))
    out: dict[str, str] = {}
    decided: set[str] = set()
    for key in order:
        for q, who in by_generation[key].items():
            if q in decided:
                continue
            decided.add(q)
            if len(who) == 1:
                out[q] = next(iter(who))
    return out


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


def carried_story(view: Mapping[str, Any], secrets: list[dict[str, Any]], present: frozenset[str],
                  hidden_entries: list[dict[str, Any]] | None = None) -> Line | None:
    """packet-v20 (PHASE-60 S6, ADR 0085 item 4): the story so far of the earlier chat a `continue` link carries, as one
    <Summary scope="earlier chat"> line (its provenance the link and the source's summary). Like this chat's own
    summaries, none when it repeats a secret this chat still keeps from someone (`summaries.leaks`, PHASE-12 Q3)."""
    held = (view.get("carried") or {})
    story = held.get("story")
    if not story or not story.get("text"):
        return None
    text = str(story["text"])
    ref = {"carried": held["link"], "summary": (story.get("from") or {}).get("summary")}
    if summaries.leaks(text, secrets, present):
        if hidden_entries is not None:
            hidden_entries.append(hidden_entry("summary", ref, None, "secret_gate"))
        return None
    return Line("summary", f'    <Summary scope="earlier chat">{xml_escape(text)}</Summary>', ref, None,
                f"earlier chat: {text}", text)


def carry_record(link: Mapping[str, Any]) -> dict[str, Any]:
    """What a trace records of the carry link its request read (PHASE-60 S6, ADR 0085 item 7): ids as strings, the
    cutoff its reading was taken at, its mode and the characters who remember."""
    return {"link": str(link["id"]), "source": str(link["source_conversation_id"]),
            "commit": str(link["cutoff_commit_id"]), "position": link["cutoff_position"], "mode": link["mode"],
            "names": [str(n) for n in link.get("entity_names") or ()]}


def read_carry(conn: psycopg.Connection, conversation: UUID, policy: str) -> tuple[Carried | None, dict[str, Any] | None]:
    """The chat's carry link in force, as (what it carries, its record), under CARRY_POLICIES only; (None, None)
    otherwise or without a link: nothing read, nothing recorded."""
    if policy not in CARRY_POLICIES:
        return None, None
    link = carry.in_force(conn, conversation)
    return (carry.target_rows(link), carry_record(link)) if link is not None else (None, None)


_log = logging.getLogger("nmos.retrieval")
NULL_COVERAGE = {"recorded_through_turn": None, "covered_through_turn": None}


def retrieve(conn: psycopg.Connection, request: Any, options: RecallOptions) -> dict[str, Any]:
    started = time.perf_counter()
    trim_req = getattr(request, "trim", None)
    conv = find_conversation(conn, request.host, request.chat_id)
    if conv is None or conv.head_commit_id is None:
        out: dict[str, Any] = {
            "freshness": "unknown_conversation", "trace_id": None, "text": "", "tokens": 0, "count": 0,
            "coverage": {"recorded_through_turn": None, "covered_through_turn": None},
        }
        if trim_req is not None:
            out["trim"] = {"keep_from_id": None, "keep_from_turn": None, "reason": "stale"}
        return out
    # The head, its manifest hash and its end in one statement, and every read below bounded by that end: recall
    # takes no conversation lock, and a concurrent sync's append extends the head commit in place (D4).
    snap = conn.execute(
        f"SELECT head_commit_id, head_manifest_hash, {CARD_SQL} AS card, (SELECT max(position) FROM active_membership am"
        " WHERE am.commit_id = c.head_commit_id) AS head_end FROM conversation c WHERE c.id = %s", (conv.id,)).fetchone()
    head, upto = snap["head_commit_id"], snap["head_end"]
    fresh = (request.active_commit is None or request.active_commit == head) and (
        request.manifest_hash is None or request.manifest_hash == snap["head_manifest_hash"]
    )
    # The query side is normalized like the corpus: reasoning blocks in the previous AI turn must not
    # steer lexical scores, fact relevance or excerpt focus either.
    query = clean_text(request.query or "")
    previous_ai = clean_text(request.previous_ai or "")
    options = dataclasses.replace(options, strict=conv.memory_strict, narrator=conv.memory_narrator,
                                  replies_only=conv.replies_only,
                                  state_pins=dict(options.pins_by_card).get(snap["card"] or "", ()))
    original_in_context = set(request.in_context_ids)
    in_context = original_in_context
    cov: coverage.Coverage | None = None
    served: frozenset[int] | None = None
    latest_replied: int | None = None
    cov_for_gather: dict[str, int | None] | None = None
    trim_out: dict[str, Any] | None = None
    trim_trace: dict[str, Any] | None = None
    # Coverage reads fail open (PHASE-60 S1 review): any error leaves the request its packet, with null coverage and,
    # for a trim request, no boundary. Each read runs in a savepoint so a database error cannot spoil the trace
    # insert, and its time is counted (`latency_ms.coverage`).
    cov_ms = 0.0
    cov_error: str | None = None

    def guarded(read: Callable[[], Any]) -> Any:
        nonlocal cov_ms, cov_error
        t0 = time.perf_counter()
        try:
            with conn.transaction():
                return read()
        except Exception as exc:  # noqa: BLE001  (fail open)
            cov_error = cov_error or type(exc).__name__
            return None
        finally:
            cov_ms += (time.perf_counter() - t0) * 1000

    if trim_req is not None:
        now_turn = _head_turn(conn, head, upto)
        if not fresh:
            trim_out = {"keep_from_id": None, "keep_from_turn": None, "reason": "stale"}
            trim_trace = {"keep_recent_turns": trim_req.keep_recent_turns, "step": trim_req.step,
                          "now": now_turn, "cut": None, "keep_from_id": None, "reason": "stale"}
        else:
            def decide() -> tuple[coverage.Coverage, str | None, int | None, str | None, set[str]]:
                # the trim decision tells held summaries apart, so it reads the memory view (secrets) it needs
                c = coverage.read(conn, conv.id, head, options.summarize_key,
                                  extractor_key=options.extractor_key, upto=upto)
                last_id = _head_last(conn, head, upto)
                window_ids = original_in_context | ({last_id} if last_id is not None else set())
                w_turns = coverage.window_turns(conn, head, window_ids, upto)
                decision = coverage.decide_trim(
                    now_turn, trim_req.keep_recent_turns, trim_req.step,
                    [(t, t in c.covered_turns) for t in w_turns],
                    # a narrator chat's packet carries no <Story> (gather), so no summary stands in for cut dialogue
                    bool(options.summarize_key) and not options.narrator,
                )
                kid: str | None = None
                kturn: int | None = None
                why: str | None = decision.reason
                before: set[str] = set()
                if decision.cut is not None:
                    kid, before = coverage.trim_boundary(conn, head, decision.cut, upto)
                    if kid is not None:
                        kturn = decision.cut
                    else:
                        why, before = "short", set()
                return c, kid, kturn, why, before

            decided = guarded(decide)
            if decided is not None:
                cov, keep_from_id, keep_from_turn, reason, before_ids = decided
                in_context = original_in_context - before_ids
                if options.policy in COVERAGE_POLICIES:
                    cov_for_gather = cov.recorded_dict()
            else:  # coverage unknown: nothing is known covered, so no boundary and nothing left out
                keep_from_id, keep_from_turn, reason = None, None, "uncovered"
            trim_out = {"keep_from_id": keep_from_id, "keep_from_turn": keep_from_turn, "reason": reason}
            trim_trace = {"keep_recent_turns": trim_req.keep_recent_turns, "step": trim_req.step,
                          "now": now_turn, "cut": keep_from_turn, "keep_from_id": keep_from_id, "reason": reason}
    elif fresh and options.policy in COVERAGE_POLICIES:
        state = guarded(lambda: coverage.extraction_state(conn, head, upto))
        if state is not None:
            served, latest_replied = state
            cov_for_gather = {
                "recorded_through_turn": max(served) if served else None,
                "latest_replied_turn": latest_replied,
            }
    served_now = cov.served_turns if cov is not None else served  # read once; the return gap reuses it (PHASE-60 S4)
    v21 = options.policy in V21_POLICIES
    history = ((overuse.recent(conn, conv.id, head, n=options.rest_after + 1, dedupe_positions=True,
                               exclude_position=upto) if v21
                else overuse.recent(conn, conv.id, head, n=options.rest_after + 1))
               if options.policy in REST_POLICIES and fresh else None)
    carried, carry_record = read_carry(conn, conv.id, options.policy) if fresh else (None, None)
    g = (gather(conn, head, query, previous_ai, in_context, filled(options, request.budget_tokens), upto,
                canon_manifest=getattr(request, "canon_manifest_id", None),
                canon_held=getattr(request, "canon_held", None) or (), recent=history,
                coverage_info=cov_for_gather, served_turns=served_now, carried=carried) if fresh else Gathered())
    def compile_at(budget: int) -> Compiled:
        return compile_gathered(g, budget, options.policy)

    compiled = compile_at(request.budget_tokens)
    if fresh and trim_out is not None and trim_out["keep_from_id"] is not None and not compiled.text:
        # Empty packet cannot safely drop dialogue (PHASE-60 S1): revert to the unmodified in-context set so the
        # returned packet and trace match what the request without trimming would have produced.
        in_context = original_in_context
        trim_out = {"keep_from_id": None, "keep_from_turn": None, "reason": "empty_packet"}
        trim_trace = {**trim_trace, "cut": None, "keep_from_id": None, "reason": "empty_packet"}
        g = gather(conn, head, query, previous_ai, in_context,
                   dataclasses.replace(filled(options, request.budget_tokens), reranker=None), upto,
                   canon_manifest=getattr(request, "canon_manifest_id", None),
                   canon_held=getattr(request, "canon_held", None) or (), recent=history,
                   coverage_info=cov_for_gather, served_turns=served_now, carried=carried)
        compiled = compile_at(request.budget_tokens)
    kept = kept_counts(compiled.ledger)
    # Memory the budget left out, and the budget that would hold it all: the panel suggests it (ADR 0036).
    fit_started = time.perf_counter()
    cut = cut_lines(compiled.ledger)
    fit = fits_at(compile_at, request.budget_tokens) if cut else None
    memory = {"offered": sum(1 for e in compiled.ledger if e["kind"] in MEMORY_KINDS
                            and e["why"] != "restates" and e.get("label") != "hidden"),
              "cut": cut, "fits_at": fit}
    fit_ms = round((time.perf_counter() - fit_started) * 1000, 2)
    if cov is None and fresh and cov_error is None:
        # Read only, after the packet: never a memory view of its own (no view at hand -> summaries not counted, so
        # coverage is under-reported, never over). A stale request reads nothing and answers null coverage.
        cov = guarded(lambda: coverage.read(conn, conv.id, head, options.summarize_key,
                                            extractor_key=options.extractor_key, secrets=g.secrets, upto=upto,
                                            served=served, latest_replied=latest_replied, read_view=False))
    timings = {**g.timings, "fit": fit_ms, "coverage": round(cov_ms, 2),
               "sidecar_total": round((time.perf_counter() - started) * 1000, 2)}

    def brief(c: dict[str, Any]) -> dict[str, Any]:
        out = {"revision_id": str(c["id"]), "position": c["position"], "host_logical_id": c["host_logical_id"],
               "score": round(float(c.get("score") or 0), 4), "user_score": round(float(c.get("user_score") or 0), 4),
               "sim": None if c.get("sim") is None else round(float(c["sim"]), 4),
               "keyword_score": round(float(c.get("keyword_score") or 0), 4), "rrf": round(float(c.get("rrf") or 0), 5)}
        if "rerank" in c:
            out["rerank"] = float(c["rerank"])
        return out

    trace_options: dict[str, Any] = {
        **recorded_options(options), "canon_names": g.canon_names, "canon_facts": g.canon_facts,
        "fill": fill(request.budget_tokens, options.policy),  # the growth its budget bought (ADR 0049)
    }
    if fresh and options.policy in COVERAGE_POLICIES and cov_for_gather is not None:
        # what gather was fed (its Note sentence), so the replay compiles the same packet whatever the tail read did
        trace_options["coverage"] = {**cov_for_gather,
                                     "covered_through_turn": cov.covered_through_turn if cov is not None else None}
    if fresh and options.policy in PIN_POLICIES and g.pins:  # the names its pins resolved to (ADR 0087 item 4)
        trace_options["pins"] = recorded_pins(g.pins)
    if fresh and options.policy in SEM_QUERY_POLICIES:  # ADR 0084 item 1: recorded only under SEM_QUERY_POLICIES
        trace_options["sem_query"] = g.sem_query
    if fresh and options.reranker is not None:  # ADR 0084 item 5: absent when unconfigured
        trace_options["rerank_used"] = g.rerank_used
        trace_options["rerank_ms"] = g.timings.get("rerank", 0.0)
    if trim_trace is not None:
        trace_options["trim"] = trim_trace
    if carry_record is not None:  # PHASE-60 S6: the link it read, for its replay (ADR 0085 item 7)
        trace_options["carry"] = carry_record
    if normtext.active() != normtext.DEFAULT_NORMALIZER:  # PHASE-66 part 3: the text its replay reads (ADR 0027)
        trace_options["normalizer"] = normtext.active()
    if fresh and options.policy in V21_POLICIES:  # packet-v21: what the secret gates did
        trace_options["secret_gate"] = {"excerpts_fenced": g.excerpts_fenced, "excerpts_withheld": g.excerpts_withheld,
                                        "state_withheld": g.state_withheld}
    placed = [e for e in compiled.ledger if e["placed"]]
    trace_id: UUID = uuid7()
    if cov_error is not None:  # the type only: a database message may quote chat text
        _log.warning("coverage read failed trace=%s error=%s; answered null coverage", trace_id, cov_error)
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
                   "rested": rested(g, compiled), "below_floor": below_floor(g, compiled),
                   "vector_mode": g.vector_note,
                   "state_items": len(g.state), "facts": len(g.lead) + len(g.facts), "threads": len(g.threads),
                   "kept_state": kept["state"], "kept_facts": kept["facts"], "kept_threads": kept["threads"],
                   "placed": {k: sum(1 for e in placed if e["kind"] == k)
                              for k in ("state", "state_history", "thread", "fact", "claim", "secret", "summary",
                                        "excerpt", "quote", "source_time")},
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
            Jsonb(trace_options),
            Jsonb(compiled.ledger),
            getattr(request, "canon_manifest_id", None),  # ADR 0045
            Jsonb(sorted(set(getattr(request, "canon_held", None) or []))),
        ),
    )
    result: dict[str, Any] = {
        "freshness": "fresh" if fresh else "stale", "trace_id": trace_id, "text": compiled.text,
        "tokens": compiled.tokens, "count": len(compiled.excerpts), "memory": memory, "conversation_id": conv.id,
        "vectors": ("fallback" if g.vector_note.startswith("fallback") else g.vector_note) if fresh else None,
        "coverage": cov.response_dict() if cov is not None else dict(NULL_COVERAGE),
    }
    if trim_out is not None:
        result["trim"] = trim_out
    return result
