"""Fact versions over valid assertions whose extraction matches the head window (D8). Each turn is served
by exactly one extractor generation (ADR 0014): the active one if it has the turn, otherwise the most
recently active earlier generation that does. Discarded extractions (per-chat rebuild, D22) and rows
from before generations existed stay stored for audit only. A turn extraction (ADR 0008) matches its
anchor's turn hash, a per-message one (older generations) the message window hash."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from datetime import datetime
from functools import lru_cache
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid5

import psycopg
from xml.sax.saxutils import escape, quoteattr

from .entities import USER_NAMES, Resolution, names_persona, resolve
from .packet import Line
from .keywords import keywords
from .predicates import (EXTENSIONS, HOLDER_PER_ITEM, REGISTRY, address_label,
                         stored_knowledge, takes_value, whereabouts)
from . import canon, canonfacts
from .repairs import (FACT_KINDS, IN_FORCE, READ_REGISTRY, REPAIR_COLUMNS, anchors_needed, apply_facts, apply_locks,
                      apply_told, cardinality, conditional, epistemic, exclusions, fungible, is_v21, legacy_anchors,
                      live, members_of, pins, quoted_turns, read_predicate, rebase, record_anchors, secret_events, slot,
                      slotted, splits_of, thread_events, unedited_quotes, unifies)
from .secrets import secret_text
from .secrets import fold as fold_secrets
from .threads import MATCH_MIN, PREDICATES as THREAD_PREDICATES, fold as fold_threads, similarity

if TYPE_CHECKING:  # carry imports this module: never at run time
    from .carry import Carried

# `unit` is the turn (a message without one counts alone). `live` holds every extraction that still
# matches the head, and `chosen` the one generation that serves its unit: the active one first, then the
# most recently activated. A reveal check of the turn (ADR 0057) is served with it while the extraction it checked
# (`chosen_id`) is the one serving it: the latest made, by `created_at`, never changed by an activation (so a replay
# reads the check it read then; ADR 0057 amendment 1). Rows without a generation (before migration 0008) never
# qualify. A window function, not a self-join: the CTE's row estimate is far too low for a join (a nested loop at 10k).
# The allBefore cut is an uncorrelated scalar subquery, so it runs once (InitPlan). As a joined CTE, a
# head commit without fresh statistics (every edit makes one) let the planner re-run it per row: ≈7 s
# at 10k messages instead of ≈60 ms.
ACTIVE_ASSERTIONS_TEMPLATE = """
WITH m AS (
    SELECT am.position, am.turn, coalesce(am.turn, -1 - am.position) AS unit, am.source_revision_id AS rid,
           sr.persona_name AS turn_persona,
           am.turn_hash, sr.lifecycle, sr.metadata, so.host_logical_id
    FROM active_membership am
    JOIN source_revision sr ON sr.id = am.source_revision_id
    JOIN source_object so ON so.id = sr.source_object_id
    WHERE am.commit_id = %(head)s{upto}
),
live AS (
    SELECT e.id AS eid, e.extractor_key, e.compiler_version, m.position, m.turn, m.host_logical_id, m.turn_hash,
           m.turn_persona,
           e.window_hash <> m.turn_hash AS is_check,
           CASE WHEN e.window_hash <> m.turn_hash THEN e.hints->>'checks' END AS checks,
           first_value(e.extractor_key) OVER w AS chosen, first_value(e.id) OVER w AS chosen_id,
           first_value(e.compiler_version) OVER w AS chosen_compiler,
           e.source_revision_id AS rid, e.window_hash, e.created_at
    FROM extraction e
    JOIN projection_generation g ON g.key = e.extractor_key
    -- the turn hash (ADR 0008, 0031); a reveal check of the turn under its own window (ADR 0057)
    JOIN m ON m.rid = e.source_revision_id AND e.window_hash IN (m.turn_hash, 'reveal:' || m.turn_hash)
    WHERE {known} AND m.lifecycle = 'accepted'
      AND m.position > (SELECT coalesce(max(position), -1) FROM m WHERE metadata->>'disabled' = 'allBefore')
      AND coalesce(m.metadata->>'disabled', '') NOT IN ('true', 'allBefore')
    WINDOW w AS (PARTITION BY m.unit
                 ORDER BY e.window_hash <> m.turn_hash, e.extractor_key = %(key)s DESC, g.activated_at DESC, g.key)
)
SELECT a.id, a.subject, a.subject_type, a.predicate, a.object, a.object_type, a.value, a.epistemic, a.confidence, a.evidence,
       a.knowledge, a.known_by, a.hidden_from, a.polarity, a.modality, a.source, a.asserted_by, a.salience,
       a.participants::text AS participants, a.outcome, a.because, a.feeling::text AS feeling, a.when_happened,
       a.address_condition::text AS address_condition,
       -- extract-v21's own marks (PHASE-66, migration 0041); null on every earlier generation's row
       a.condition::text AS condition, a.guise, a.item_kind, a.knowledge_scope,
       -- a check's rows read as the extraction it checked
       l.position, l.turn, l.host_logical_id, l.turn_persona, l.chosen AS generation, l.chosen_compiler AS compiler,
       -- the turn's hash: a secret's (ADR 0033 amendment 2) and an owner repair's target (ADR 0044); and the hash a
       -- reveal's listed turn had
       l.turn_hash,
       CASE WHEN a.predicate = 'learned' THEN (
           SELECT h->>'turn_hash' FROM extraction x, jsonb_array_elements(x.hints->'secrets') h
           WHERE x.id = l.eid AND '[turn ' || (h->>'turn') || '] ' || (h->>'text') = a.value
           LIMIT 1) END AS listed_hash
FROM live l
JOIN assertion a ON a.extraction_id = l.eid
WHERE (CASE WHEN l.is_check THEN l.checks = l.chosen_id::text AND NOT EXISTS (  -- a check made later (ADR 0057 am. 1)
                 SELECT 1 FROM extraction r
                 WHERE r.source_revision_id = l.rid AND r.window_hash = l.window_hash AND {known_r}
                   AND (r.created_at, r.id) > (l.created_at, l.eid))
            ELSE l.extractor_key = l.chosen END) AND a.status = 'valid'
ORDER BY l.position, l.is_check, a.id
"""


ACTIVE_ASSERTIONS = ACTIVE_ASSERTIONS_TEMPLATE.format(upto="", known="e.discarded_at IS NULL",
                                                      known_r="r.discarded_at IS NULL")
# The same read "as of" an earlier request (ADR 0027): the head up to a position, and only what NMOS had
# extracted by a time (an extraction discarded later still served then). A separate statement, so the
# request path keeps its plan. With no time (a live request reads up to its own message), as of the request's own
# transaction start, now(): the database's clock, never the sidecar's (Python 3.12 on Windows ticks every 15.6 ms), and
# the instant its trace's created_at records, so an extraction committed while the request runs is read by neither
# the request nor its replay.
_KNOWN = ("{t}.created_at <= coalesce(%(known_at)s::timestamptz, now())"
          " AND ({t}.discarded_at IS NULL OR {t}.discarded_at > coalesce(%(known_at)s::timestamptz, now()))")
ACTIVE_ASSERTIONS_AS_OF = ACTIVE_ASSERTIONS_TEMPLATE.format(
    upto=" AND am.position <= %(upto)s", known=_KNOWN.format(t="e"), known_r=_KNOWN.format(t="r"))


def _with_open_turn(template: str) -> str:
    """The same read also serving the open turn (PHASE-67 part 2, owner decision 2026-11-25): the head's last member,
    when it is a provisional reply of a turn (its user has not answered) whose extraction by the active generation
    exists and is not discarded. Its rows are marked `open_turn`. Only the author's note and carry read it; a request
    never does (`memory_view(include_open_turn=...)`)."""
    out = template
    for old, new in (
        ("am.turn_hash, sr.lifecycle, sr.metadata, so.host_logical_id",
         "am.turn_hash, sr.lifecycle, sr.metadata, so.host_logical_id,\n"
         "           (sr.lifecycle = 'provisional' AND am.turn IS NOT NULL AND am.position = (\n"
         "                SELECT max(position) FROM active_membership WHERE commit_id = %(head)s)) AS is_open"),
        ("e.source_revision_id AS rid, e.window_hash, e.created_at",
         "e.source_revision_id AS rid, e.window_hash, e.created_at, m.is_open"),
        ("AND m.lifecycle = 'accepted'", "AND (m.lifecycle = 'accepted' OR (m.is_open AND e.extractor_key = %(key)s))"),
        ("       l.turn_hash,\n", "       l.turn_hash, l.is_open AS open_turn,\n"),
    ):
        assert out.count(old) == 1, old
        out = out.replace(old, new)
    return out


ACTIVE_ASSERTIONS_OPEN = _with_open_turn(ACTIVE_ASSERTIONS)
ACTIVE_ASSERTIONS_AS_OF_OPEN = _with_open_turn(ACTIVE_ASSERTIONS_AS_OF)
# The open turn a read with `include_open_turn` served (provenance for the note and a carry snapshot).
OPEN_TURN = """
SELECT am.turn, am.position, am.source_revision_id AS revision, so.host_logical_id, sr.revision_hash
FROM active_membership am
JOIN source_revision sr ON sr.id = am.source_revision_id
JOIN source_object so ON so.id = sr.source_object_id
WHERE am.commit_id = %(head)s AND am.turn IS NOT NULL AND sr.lifecycle = 'provisional'
  AND coalesce(sr.metadata->>'disabled', '') NOT IN ('true', 'allBefore')
  AND am.position = (SELECT max(position) FROM active_membership WHERE commit_id = %(head)s)
  AND (%(upto)s::int IS NULL OR am.position <= %(upto)s::int)
  AND EXISTS (SELECT 1 FROM extraction e WHERE e.source_revision_id = am.source_revision_id
              AND e.window_hash = am.turn_hash AND e.extractor_key = %(key)s AND e.discarded_at IS NULL)
"""


def served_assertions(conn: psycopg.Connection, head: UUID, extractor_key: str, upto: int | None = None,
                      known_at: datetime | None = None, open_turn: bool = False) -> list[dict[str, Any]]:
    """ACTIVE_ASSERTIONS with participants parsed. They are fetched as text and parsed only where present:
    decoding every jsonb value through the driver cost ≈10 ms per fact read at 10,000 messages
    (docs/perf/phase8-extraction.md). Knowledge marks stored as a {"name", …} repr read as the name
    (stored_knowledge). With `upto` or `known_at`, the read as of an earlier request. With `open_turn`, the open turn's
    finished early extraction too (`_with_open_turn`), its rows marked `open_turn`."""
    if upto is None and known_at is None:
        rows = conn.execute(ACTIVE_ASSERTIONS_OPEN if open_turn else ACTIVE_ASSERTIONS,
                            {"head": head, "key": extractor_key}).fetchall()
    else:
        rows = conn.execute(ACTIVE_ASSERTIONS_AS_OF_OPEN if open_turn else ACTIVE_ASSERTIONS_AS_OF, {
            "head": head, "key": extractor_key, "upto": upto if upto is not None else 2**31 - 1,
            "known_at": known_at}).fetchall()
    for r in rows:
        if r["participants"] is not None:
            r["participants"] = _parse_participants(r["participants"])
        if r["known_by"] or r["hidden_from"]:
            stored_knowledge(r)
        if (detail := r.pop("feeling")) is not None:  # extract-v18 only (PHASE-58): other rows read as before
            r["feeling"] = _parse_feeling(detail)
        if (when := r.pop("when_happened")) is not None:  # extract-v19 only (PHASE-60 S7): other rows read as before
            r["when_happened"] = when
        if (cond := r.pop("address_condition")) is not None:  # extract-v20 only (PHASE-64): other rows read as before
            r["address_condition"] = _parse_address_condition(cond)
        ontology_marks(r)
        if open_turn and r.pop("open_turn"):  # PHASE-67: only the open turn's rows keep the mark
            r["open_turn"] = True
    return rows


ONTOLOGY_MARKS = ("condition", "guise", "item_kind", "knowledge_scope")  # extract-v21's columns (PHASE-66, 0041)


def ontology_marks(row: dict[str, Any]) -> dict[str, Any]:
    """extract-v21's four marks of a stored row (PHASE-66), in place: each kept only when set, `condition` parsed from
    its text, so a row of every earlier generation (all four null) has none of the keys and reads as before."""
    for k in ONTOLOGY_MARKS:
        if k in row and (value := row.pop(k)) is not None:
            row[k] = _parse_address_condition(value) if k == "condition" and isinstance(value, str) else value
    return row


def told_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The `told` rows among served rows whose own compiler has `told` in its extension (PHASE-60 S8: only
    extract-v19 asks for it and only its rows are read), in the order given (served rows: oldest first). A told row
    of another compiler (one forced valid by hand) is left out."""
    return [r for r in rows
            if r["predicate"] == "told" and "told" in EXTENSIONS.get(r.get("compiler") or "", {})]


def served_told(conn: psycopg.Connection, head: UUID, extractor_key: str, upto: int | None = None,
                known_at: datetime | None = None) -> list[dict[str, Any]]:
    """Who told whom in the head (PHASE-60 S8): the served `told` rows, oldest first, read with the same `upto` and
    `known_at` as every served read, so a replay as of a request reads what the request read. The reader packet-v20
    and the Inspector use; the packet's fact read (`memory_view`, whose rows keep `in REGISTRY`) keeps excluding
    `told`, so the facts served to a packet never gain a told row."""
    return told_rows(served_assertions(conn, head, extractor_key, upto, known_at))


@lru_cache(maxsize=65536)
def _parse_participants(text: str) -> tuple[dict[str, str], ...]:
    """A stored participant list (rows never change, so every read after the first hits the cache).
    Shared between reads: read-only."""
    return tuple(json.loads(text))


@lru_cache(maxsize=16384)
def _parse_feeling(text: str) -> dict[str, Any]:
    """A stored feeling's detail (PHASE-58 S2), parsed once per text. Shared between reads: read-only."""
    return json.loads(text)


@lru_cache(maxsize=4096)
def _parse_address_condition(text: str) -> dict[str, Any]:
    """A stored conditional address spec (PHASE-64 S1), parsed once per text. Shared between reads: read-only."""
    return json.loads(text)


def _norm(value: str | None) -> str:
    return " ".join((value or "").lower().split())


def _subject(a: dict[str, Any], r: Resolution | None) -> str:
    return r.key(a.get("subject_type"), a["subject"]) if r else _norm(a["subject"])


def _object(a: dict[str, Any], r: Resolution | None) -> str:
    return r.key(a.get("object_type"), a["object"]) if r and a.get("object") else _norm(a["object"])


def _item(a: dict[str, Any], r: Resolution | None) -> str:  # possesses: the object; located_in, destroyed: the subject
    return _object(a, r) if a["predicate"] in HOLDER_PER_ITEM else _subject(a, r)


def version_key(a: dict[str, Any], r: Resolution | None = None) -> tuple:
    """Subject and object are entity ids where the resolver links them (ADR 0012), text otherwise.

    extract-v21's own predicates (PHASE-66) take their registry entry (`READ_REGISTRY`): `vital_status`, `lives_in`,
    `disguised_as` and `contained_in` one each per subject (apart from `has_status`, `located_in` and `identity`),
    `holds_rank` one per (character, group), `cover_identity` beside `identity`. The key never depends on the row's
    generation: a pair's roles and an item's holders keep one history across an extract-v20 → v21 switch, and the fold
    (`_versions`) reads several roles or a fungible item's holders apart."""
    if a["predicate"] == "relationship":  # one history per pair, both directions (ADR 0038)
        return ("relationship",) + tuple(sorted((_subject(a, r), _object(a, r))))
    if whereabouts(a):  # one current holder per item (ADR 0011), one whereabouts with its place (PHASE-6)
        return ("whereabouts", _item(a, r))
    pred = READ_REGISTRY[a["predicate"]]
    if pred.cardinality == "single":
        return (a["predicate"], _subject(a, r)) + ((_object(a, r),) if pred.per_object else ())
    return (a["predicate"], _subject(a, r), _object(a, r),
            _norm(a["value"]) if takes_value(a["predicate"], READ_REGISTRY) else "")


def relation(a: dict[str, Any], r: Resolution | None = None) -> tuple:
    """What a negation must match, beyond the version key, to end a version (ADR 0013, item 4): the same
    holder for an item, the same place for an item's place, the same object and value for other
    single-valued predicates. Multi-valued keys already contain everything."""
    if a["predicate"] in HOLDER_PER_ITEM:
        return (a["predicate"], _subject(a, r))
    if a["predicate"] == "destroyed":
        return (a["predicate"],)
    if whereabouts(a):
        return (a["predicate"], _object(a, r))
    pred = READ_REGISTRY[a["predicate"]]
    if pred.cardinality == "single":
        value = _norm(a["value"]) if takes_value(a["predicate"], READ_REGISTRY) else ""
        return ((value,) if pred.per_object else (_object(a, r), value))
    return ()


# Relationships that hold the same both ways (ADR 0038): the head noun of the value, in Korean last, possibly followed
# by 관계/사이; in English any word of it, unless "of" makes it someone else's ("friend of her brother").
# "적" (enemy) only as a word of its own ("적", "오랜 적") or in "숙적": as a suffix it makes adjectives of anything
# ("일방적", "적대적", "의존적"), most of them one way.
SYMMETRIC_KO = ("친구", "연인", "애인", "커플", "부부", "배우자", "형제", "자매", "남매", "쌍둥이", "동급생", "동기",
                "동창", "동료", "라이벌", "경쟁자", "원수", "숙적", "파트너", "동반자", "룸메이트", "이웃", "약혼자", "사촌",
                "동맹", "팀원", "짝꿍", "단짝", "소꿉친구", "동지")
_ENEMY_KO = re.compile(r"(?:^|\s)적$")
SYMMETRIC_EN = frozenset({"friend", "friends", "lover", "lovers", "couple", "spouse", "spouses", "married", "sibling",
                          "siblings", "twin", "twins", "classmate", "classmates", "colleague", "colleagues", "coworker",
                          "coworkers", "rival", "rivals", "enemy", "enemies", "partner", "partners", "roommate",
                          "roommates", "neighbor", "neighbors", "cousin", "cousins", "fiance", "fiancee", "engaged",
                          "allies", "ally", "teammate", "teammates"})
# Words that make an English relationship one way or not (or no longer) what it says: "ex-girlfriend", "former partner",
# "fake friend", "unrequited lover", "one-sided rival". A possessive ("friend's brother") is someone else's.
ONE_WAY_EN = frozenset({"ex", "former", "fake", "unrequited", "sided"})
_POSSESSIVE = re.compile(r"[a-z]['’]s\b")
_ASIDE = re.compile(r"\([^)]*\)")


def symmetric(value: str | None) -> bool:
    """Whether a relationship value holds the same both ways (ADR 0038)."""
    text = _ASIDE.sub(" ", str(value or "")).strip().casefold()
    words = re.findall(r"[a-z]+", text)
    if words and not re.search(r"[가-힣]", text):
        return ("of" not in words and not _POSSESSIVE.search(text) and not ONE_WAY_EN.intersection(words)
                and any(w in SYMMETRIC_EN for w in words))
    head = re.sub(r"\s*(관계|사이)$", "", text).strip()
    return bool(head) and "의 " not in head and (head.endswith(SYMMETRIC_KO) or bool(_ENEMY_KO.search(head)))


def _pair_versions(history: list[dict[str, Any]], r: Resolution | None = None) -> list[dict[str, Any]]:
    """One pair's relationships in position order (ADR 0038). Each direction keeps its latest, as before. A symmetric
    relationship, stated either way, also replaces the other direction's, and a newer one of the other direction
    replaces it. A denial ends the relationship it denies in its direction, or either way when it is symmetric, and
    is current itself (rendered negated); a denial of anything else stands beside, as for every predicate."""
    slots: dict[str, dict[str, Any] | None] = {}  # direction (the subject's key) -> its current row
    negatives: dict[tuple, dict[str, Any]] = {}
    outcome: dict[int, str] = {}
    closer: dict[int, dict[str, Any]] = {}  # id() of a closed row -> the statement that closed it (PHASE-32)

    def close(row: dict[str, Any] | None, how: str, by: dict[str, Any]) -> None:
        if row is not None and id(row) not in outcome:
            outcome[id(row)] = how
            closer[id(row)] = by

    for a in history:
        d, v = _subject(a, r), _norm(a["value"])
        if a["polarity"] == "negative":
            target = d if slots.get(d) is not None and _norm(slots[d]["value"]) == v else next(
                (o for o, held in slots.items() if o != d and held is not None and _norm(held["value"]) == v
                 and symmetric(held["value"])), None)
            if target is None:
                negatives[(d, v)] = a
                continue
            close(slots[target], "ended", a)
            slots[target] = a
            continue
        for key in [k for k in negatives if k[1] == v and (k[0] == d or symmetric(a["value"]))]:
            close(negatives.pop(key), "superseded", a)
        close(slots.get(d), "superseded", a)
        slots[d] = a
        for o, held in slots.items():
            if o != d and held is not None and (symmetric(a["value"]) or symmetric(held["value"])):
                close(held, "superseded", a)
                slots[o] = None
    current_rows = [s for s in slots.values() if s is not None] + list(negatives.values())
    for row in current_rows:
        outcome[id(row)] = "current"
    entries = [_entry(h, outcome, closer) for h in history]
    return [{**row, "versions": len(history), "history": entries, "claims": []} for row in current_rows]


def _entry(h: dict[str, Any], outcome: dict[int, str], closer: dict[int, dict[str, Any]] | None = None) -> dict[str, Any]:
    """One history entry of a fact version; a canon statement names its canon key (ADR 0047). A closed entry carries
    the turn of the statement that closed it (`closed_turn`, PHASE-32): in a pair's or an item's shared history the next
    entry may belong to the other direction or holder, so it is not where this one ended. Display only."""
    out = {"position": h["position"], "turn": h["turn"], "predicate": h["predicate"], "subject": h["subject"],
           "value": h["value"], "object": h["object"], "polarity": h["polarity"],
           "outcome": outcome.get(id(h), "superseded"), "knowledge": h.get("knowledge"),
           "known_by": h.get("known_by"), "hidden_from": h.get("hidden_from")}
    if h.get("feeling"):  # PHASE-58: how the feeling felt then
        out["feeling"] = h["feeling"]
    if h.get("when_happened"):  # PHASE-60 S7: when it happened, apart from when the turn told it
        out["when_happened"] = h["when_happened"]
    if h.get("address_condition"):  # PHASE-64: the condition this address held under
        out["address_condition"] = h["address_condition"]
    for k in ONTOLOGY_MARKS:  # PHASE-66: extract-v21's marks of the statement, only where it has them
        if h.get(k):
            out[k] = h[k]
    if h.get("canon"):
        out["canon"] = h["canon"]
    if h.get("carried"):  # ADR 0085: a statement an earlier chat made
        out["carried"] = h["carried"]
    by = (closer or {}).get(id(h))
    if by is not None and out["outcome"] != "current":
        out["closed_turn"] = by["turn"] if by.get("turn") is not None else (0 if by.get("canon") else None)
    return out


CAUSE_MIN = 0.35  # trigram overlap of a stated cause with the event it names, names left out (ADR 0040)
CAUSE_MARGIN = 0.1
CAUSE_TURNS = 5  # how far back the event may be: the same scene (on M0 a link 29 turns back named the wrong one)


def _unnamed(text: str, names: set[str]) -> str:
    out = _norm(text)
    for name in sorted((_norm(n) for n in names if n and len(_norm(n)) >= 2), key=len, reverse=True):
        out = out.replace(name, " ")
    return out


def cause_links(rows: list[dict[str, Any]], events: list[dict[str, Any]], r: Resolution | None = None) -> None:
    """For each row with a stated cause, the earlier event it names, when one clearly does (ADR 0040): an event of the
    same subject or object (or with either as a participant), at most CAUSE_TURNS turns before the row, whose value the
    cause repeats (CAUSE_MIN, leading the next by CAUSE_MARGIN). Sets `cause_event` {turn, text}; nothing is stored,
    and no cause is inferred: without a match the stated text stands alone."""
    for row in rows:
        if not row.get("because"):
            continue
        who = {_subject(row, r)} | ({_object(row, r)} if row.get("object") else set())
        names = set(row.get("names") or [row["subject"], row.get("object") or ""])
        scored = []
        for e in events:
            if e["position"] > row["position"] or _unit(row) - _unit(e) > CAUSE_TURNS:
                continue
            around = {_subject(e, r)} | {(r.key(p["type"], p["name"]) if r else _norm(p["name"]))
                                          for p in e.get("participants") or ()}
            if not who & around:
                continue
            # names say who, not what happened: they would make any two sentences about the same people look alike
            drop = names | set(e.get("names") or [e["subject"]])
            grams, named = _grams(_unnamed(row["because"], drop)), _grams(_unnamed(e.get("value") or "", drop))
            scored.append((len(grams & named) / max(1, min(len(grams), len(named))), e))
        scored.sort(key=lambda x: (-x[0], -x[1]["position"]))
        if scored and scored[0][0] >= CAUSE_MIN and (len(scored) == 1 or scored[0][0] - scored[1][0] >= CAUSE_MARGIN):
            e = scored[0][1]
            row["cause_event"] = {"turn": e.get("turn"), "position": e["position"], "text": fact_text(e)}


def _unit(a: dict[str, Any]) -> int:
    """The turn an assertion comes from (a message without one counts alone), as in ACTIVE_ASSERTIONS."""
    return a["turn"] if a.get("turn") is not None else -1 - a["position"]


def _different_source(earlier_row: dict[str, Any], later_row: dict[str, Any]) -> bool:
    """Whether two rows come from different turns or different canon sources."""
    return _unit(earlier_row) != _unit(later_row) or earlier_row.get("canon") != later_row.get("canon")


def _address_versions(history: list[dict[str, Any]], r: Resolution | None = None) -> list[dict[str, Any]]:
    """One direction's `addresses` assertions in position order with conditional slots (PHASE-64, ADR 0091); since
    PHASE-66 also one version key's history of an extract-v21 conditioned predicate other than `relationship`
    (`repairs.slot` and `repairs.unifies` read its `condition` as they read an address's `address_condition`, and are
    `predicates.address_slot` and `is_address_all` for an address).

    Each condition slot (`default`, `public`, `private`, or `("situational", normalized_when)`) keeps its own current
    row and per-slot history so settling a private form does not supersede the public form or pollute its `before:`
    line or `replaced_marks`. Two cross-slot transitions keep the view clean:
    - Split cleanup: once both `public` and `private` are active, an earlier positive `default` from a prior turn or
      canon source is superseded into the matching/new slot's history so no duplicate baseline lingers.
    - Unification (`scope="all"`): closes every earlier active slot (`default`, `public`, `private`, `situational`)
      and open negation from prior turns/canon sources, becoming the sole current unconditional address while retaining
      closed entries in its history.
    """
    order = {id(a): idx for idx, a in enumerate(history)}
    slots: dict[tuple[str, ...], dict[str, Any] | None] = {}
    negatives: dict[tuple[tuple[str, ...], tuple], dict[str, Any]] = {}
    outcome: dict[int, str] = {}
    closer: dict[int, dict[str, Any]] = {}
    slot_history: dict[tuple[str, ...], list[dict[str, Any]]] = {}

    def close(row: dict[str, Any] | None, how: str, by: dict[str, Any]) -> None:
        if row is not None and id(row) not in outcome:
            outcome[id(row)] = how
            closer[id(row)] = by

    def add_hist(key: tuple[str, ...], items: list[dict[str, Any]]) -> None:
        bucket = slot_history.setdefault(key, [])
        seen = {id(x) for x in bucket}
        for x in items:
            if id(x) not in seen:
                bucket.append(x)
                seen.add(id(x))

    for a in history:
        here = slot(a)
        unifying = a["polarity"] == "positive" and unifies(a)
        rel = relation(a, r)
        if a["polarity"] == "negative":
            current = slots.get(here)
            if current is not None and relation(current, r) != rel:
                negatives[(here, rel)] = a
                add_hist(here, [a])
                continue
            close(negatives.pop((here, rel), None), "superseded", a)
            close(current, "ended", a)
            slots[here] = a
            add_hist(here, [a])
            continue
        close(negatives.pop((here, rel), None), "superseded", a)
        if unifying:
            for other, held in list(slots.items()):
                if other != here and held is not None and _different_source(held, a):
                    close(held, "superseded", a)
                    add_hist(here, slot_history.get(other, []))
                    slots[other] = None
            for nkey in [k for k, neg in negatives.items() if _different_source(neg, a)]:
                neg = negatives.pop(nkey)
                close(neg, "superseded", a)
                add_hist(here, [neg])
            close(slots.get(here), "superseded", a)
            slots[here] = a
            add_hist(here, [a])
            continue
        close(slots.get(here), "superseded", a)
        slots[here] = a
        add_hist(here, [a])
        if here in (("public",), ("private",)):
            pub, priv, dflt = slots.get(("public",)), slots.get(("private",)), slots.get(("default",))
            if (pub is not None and pub["polarity"] == "positive"
                    and priv is not None and priv["polarity"] == "positive"
                    and dflt is not None and dflt["polarity"] == "positive"
                    and _different_source(dflt, a)):
                close(dflt, "superseded", a)
                slots[("default",)] = None
                target = here
                if not _different_source(pub, a) and not _different_source(priv, a):
                    dv = _norm(dflt.get("value"))
                    if _norm(pub.get("value")) == dv:
                        target = ("public",)
                    elif _norm(priv.get("value")) == dv:
                        target = ("private",)
                add_hist(target, slot_history.get(("default",), []))

    current_items = [(s, row) for s, row in slots.items() if row is not None] + [
        (k[0], row) for k, row in negatives.items()
    ]
    for _, row in current_items:
        outcome[id(row)] = "current"
    out = []
    for key, row in current_items:
        my_history = sorted(slot_history.get(key, [row]), key=lambda x: order[id(x)])
        entries = [_entry(h, outcome, closer) for h in my_history]
        out.append({**row, "versions": len(entries), "history": entries, "claims": []})
    return out


def _ended_containers(facts: list[dict[str, Any]], r: Resolution | None) -> list[dict[str, Any]]:
    """An item's current `contained_in` (extract-v21) ends with the item: a current end (`destroyed`, positive,
    undisputed) of the same item stated after it closes it (its history entry `ended`, `closed_turn` the end's). A
    fungible item's end is one of many (no container closed)."""
    ended = {_subject(f, r): f for f in facts if f["predicate"] == "destroyed" and f.get("polarity") == "positive"
             and not f.get("disputed_by") and f.get("item_kind") != "fungible"}
    out = []
    for f in facts:
        end = ended.get(_subject(f, r)) if f["predicate"] == "contained_in" and f.get("polarity") == "positive" else None
        if end is None or end["position"] < f["position"]:
            out.append(f)
            continue
        for e in f.get("history") or ():
            if e["position"] == f["position"] and e["outcome"] == "current":
                e["outcome"] = "ended"
                e["closed_turn"] = end.get("turn")
    return out


def _conditional_pairs(history: list[dict[str, Any]], r: Resolution | None = None) -> list[dict[str, Any]]:
    """One pair's relationships when some hold under a condition (extract-v21, PHASE-66), in position order.

    Each condition slot (`repairs.slot`: default, public, private, or situational with its `when`) is folded as a pair
    is (`_pair_versions`: each direction its latest, a symmetric tie both ways), so a private tie and the public one
    coexist, each with its own history. Two cross-slot transitions, as for addresses (`_address_versions`, ADR 0091):
    - unification: a positive `scope="all"` statement (in the default slot) closes every other slot's current tie from
      an earlier turn or canon source, whose history joins its own;
    - split cleanup: a positive default tie is retired, into the history of the slot that says the same (else the
      later one), once a positive public and a positive private tie of its direction (or symmetric) stand after it from
      another turn or source."""
    order = {(a["id"], a["position"]): i for i, a in enumerate(history)}
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for a in history:
        groups.setdefault(slot(a), []).append(a)
    folded = {key: _pair_versions(rows, r) for key, rows in groups.items()}
    unifiers = [a for a in history if a["polarity"] == "positive" and unifies(a)]
    gone: dict[int, dict[str, Any]] = {}  # id() of an output closed across slots -> the statement that closed it
    joins: dict[tuple, list[dict[str, Any]]] = {}  # (id, position) of a closing statement -> the entries it took in

    def retire(f: dict[str, Any], by: dict[str, Any]) -> None:
        for entry in f["history"]:
            if entry["position"] == f["position"] and entry["outcome"] == "current":
                entry["outcome"] = "superseded"
                entry["closed_turn"] = by["turn"] if by.get("turn") is not None else (0 if by.get("canon") else None)
        gone[id(f)] = by
        joins.setdefault((by["id"], by["position"]), []).extend(f["history"])

    for key, outs in folded.items():
        if key == ("default",):
            continue
        for f in outs:
            at = order[(f["id"], f["position"])]
            closer = next((u for u in reversed(unifiers)
                           if order[(u["id"], u["position"])] > at and _different_source(f, u)), None)
            if closer is not None:
                retire(f, closer)
    pub = [f for f in folded.get(("public",), ()) if id(f) not in gone and f["polarity"] == "positive"]
    priv = [f for f in folded.get(("private",), ()) if id(f) not in gone and f["polarity"] == "positive"]
    for f in folded.get(("default",), ()):
        if f["polarity"] != "positive" or unifies(f):
            continue
        d = _subject(f, r)
        mine = lambda x: _subject(x, r) == d or symmetric(x.get("value"))  # noqa: E731
        p = next((x for x in pub if mine(x) and x["position"] > f["position"]), None)
        q = next((x for x in priv if mine(x) and x["position"] > f["position"]), None)
        if p is None or q is None:
            continue
        later = p if p["position"] > q["position"] else q
        if not _different_source(f, later):
            continue
        retire(f, next((x for x in (p, q) if _norm(x.get("value")) == _norm(f.get("value"))), later))
    out = []
    for key, outs in folded.items():
        for f in outs:
            if id(f) in gone:
                continue
            # the entries a closing statement took in join every output whose history holds it (as an address's slot
            # history does), so they stay readable after that statement is itself replaced in its slot
            held = {h["position"] for h in f["history"]}
            extra = [e for (_, at), entries in joins.items() if at in held for e in entries]
            if extra:
                seen = {id(e) for e in f["history"]}
                merged = sorted(f["history"] + [e for e in extra if id(e) not in seen], key=lambda e: e["position"])
                f = {**f, "history": merged, "versions": len(merged)}
            out.append(f)
    return out


def _versions(history: list[dict[str, Any]], r: Resolution | None = None) -> list[dict[str, Any]]:
    """One version key's facts from its narrated, actual assertions in position order.

    A positive assertion becomes current. A negative one ends the current version only if it denies the
    same relation, and is then current itself (rendered negated); otherwise it stands as its own negative
    fact ("not in the harbor" while at home) until a positive assertion of that relation replaces it.

    An item's whereabouts (PHASE-6 Q2, Q3) has three slots, holder, place and end (`destroyed`), each
    folded as above. A new positive statement also closes the other slots unless they come from the same
    turn ("Hana holds the map in the library"): the newer statement says where the item is now. An end
    also closes holder and place of its own turn ("Hana burns the letter she holds").

    A holder or place from a later turn than the item's end contradicts it (PHASE-6 Q4): the newer
    statement is current, marked `disputed` by the end, until a new end or a denial of the end.

    Each history entry gets an outcome: `current`, `superseded` (replaced or moved on), `ended` (closed
    by a negation or an end) or `conflicting` (an end that later statements contradict).
    """
    if history and history[0]["predicate"] == "relationship":
        if any(conditional(a) for a in history):  # extract-v21 (PHASE-66): a pair's ties by condition slot
            return _conditional_pairs(history, r)
        return _pair_versions(history, r)
    if history and history[0]["predicate"] == "role_toward" and any(is_v21(a) for a in history):
        # PHASE-66: once extract-v21 speaks of a pair's roles, each role is its own history (several roles toward one
        # counterpart, each ended by its own denial), earlier generations' statements of the same role among them
        groups: dict[str, list[dict[str, Any]]] = {}
        for a in history:
            groups.setdefault(_norm(a.get("value")), []).append(a)
        return [f for g in groups.values() for f in _one_slot(g, r)]
    if history and whereabouts(history[0]) and any(fungible(a) for a in history):
        # PHASE-66: an item one of many alike (any statement of it says so): each holder's possession its own history,
        # never ending another's; its place and its end fold apart, and end no one's possession
        holders: dict[str, list[dict[str, Any]]] = {}
        rest = []
        for a in history:
            if a["predicate"] in HOLDER_PER_ITEM:
                holders.setdefault(_subject(a, r), []).append(a)
            else:
                rest.append(a)
        # an end of one of them (eaten, spent, broken) ends its holder's only: the holder its turn names (a typed
        # participant, or who held it in that turn), else the one holder there is
        ends = {}
        for d in rest:
            if d["predicate"] != "destroyed" or d.get("polarity") == "negative":
                continue
            named = ({r.key(p["type"], p["name"]) if r else _norm(p["name"]) for p in d.get("participants") or ()
                      if p.get("type") in ("character", "group")}
                     | {k for k, g in holders.items() if any(_unit(x) == _unit(d) for x in g)})
            if not named and len(holders) == 1:
                named = set(holders)
            for k in named & holders.keys():
                g = holders[k]
                if not any(x["position"] > d["position"] and x.get("polarity") != "negative" for x in g):
                    ends[k] = d  # a later possession of one is another one: no end then
        out = []
        for k, g in holders.items():
            folded = _one_slot(sorted(g + [ends[k]], key=lambda x: x["position"]) if k in ends else g, r)
            out += [f for f in folded if f["predicate"] in HOLDER_PER_ITEM]
        return out + (_one_slot(rest, r) if rest else [])
    return _one_slot(history, r)


def _one_slot(history: list[dict[str, Any]], r: Resolution | None = None) -> list[dict[str, Any]]:
    """`_versions` of one history that holds one role or one holder (or any other key): conditional slots when a row
    states a condition (PHASE-64, PHASE-66), else the plain fold below."""
    if history and slotted(history[0]["predicate"]) and any(conditional(a) for a in history):
        return _address_versions(history, r)  # PHASE-64 addresses; PHASE-66 the other conditioned predicates
    slots: dict[str, dict[str, Any] | None] = {}
    negatives: dict[tuple, dict[str, Any]] = {}
    disputed_by: dict[str, Any] | None = None
    outcome: dict[int, str] = {}  # id() of a history row -> outcome, for rows that were closed
    closer: dict[int, dict[str, Any]] = {}  # id() of a closed row -> the statement that closed it (PHASE-32)

    def close(row: dict[str, Any] | None, how: str, by: dict[str, Any]) -> None:
        if row is not None and id(row) not in outcome:
            outcome[id(row)] = how
            closer[id(row)] = by

    for a in history:
        slot = a["predicate"] if whereabouts(a) else ""
        if slot == "destroyed":
            disputed_by = None  # a new end, or a denial of the end, settles the item's existence
        elif slot and a["polarity"] == "positive":
            end = slots.get("destroyed")
            if end is not None and end["polarity"] == "positive" and _unit(end) != _unit(a):
                disputed_by = end
                close(end, "conflicting", a)
        current = slots.get(slot)
        rel = relation(a, r)
        if a["polarity"] == "negative" and current is not None and relation(current, r) != rel:
            negatives[rel] = a
            continue
        close(negatives.pop(rel, None), "superseded", a)
        if slot and a["polarity"] == "positive":
            for other, held in list(slots.items()):
                if other != slot and held is not None and _unit(held) != _unit(a):
                    if other == "possesses" and slot == "located_in" and is_v21(a):
                        continue  # PHASE-66: where a thing is kept is not who owns it (an extract-v21 statement)
                    close(held, "ended" if slot == "destroyed" else "superseded", a)
                    slots[other] = None
        close(current, "ended" if a["polarity"] == "negative" else "superseded", a)
        slots[slot] = a
    ended = slots.get("destroyed")
    if ended is not None and ended["polarity"] == "positive":
        close(slots.get("possesses"), "ended", ended)
        close(slots.get("located_in"), "ended", ended)
        slots["possesses"] = slots["located_in"] = None
    current_rows = [s for s in slots.values() if s is not None] + list(negatives.values())
    for row in current_rows:
        outcome[id(row)] = "current"
    entries = [_entry(h, outcome, closer) for h in history]
    out = []
    for fact in current_rows:
        f = dict(fact)
        if disputed_by is not None and f["polarity"] == "positive":
            f["disputed_by"] = {k: disputed_by[k] for k in ("id", "position", "turn", "subject", "predicate",
                                                            "object", "value")}
        f["versions"] = len(history)
        f["history"] = entries
        f["claims"] = []
        out.append(f)
    return out


_GUISE_NS = UUID("6f1e4f4e-2f6b-5c39-9a51-6e3f2b7a9c10")  # the namespace of a guise alias's stable negative id

LIVE: Any = object()  # `canon_facts` of a live read: decided from the manifest the request names (ADR 0047)


def memory_view(conn: psycopg.Connection, head: UUID, extractor_key: str | None, upto: int | None = None,
                known_at: datetime | None = None, canon_manifest: str | None = None,
                canon_exact: bool = False, canon_key: str | None = None,
                canon_facts: Any = LIVE, what_if: dict[str, Any] | None = None,
                told: bool = False, carried: Carried | None = None,
                include_open_turn: bool = False) -> dict[str, list[dict[str, Any]]]:
    """The head's assertions by what they may do (ADR 0013).

    - facts: current fact versions from actual narration (legacy rows without a source count as
      narration), each with the characters' claims about the same key;
    - claims: the latest claim per speaker and version key (modality actual or unknown), whether or not
      a narrated fact exists; a claim never supersedes narration;
    - other: hypothetical, dreamed and unknown assertions, stored and inspectable, never in the packet;
    - entities / ambiguous: the read-time entity resolution those keys use (ADR 0012). `also_called`
      assertions feed it and are not facts themselves;
    - conflicts: current facts the story contradicts (PHASE-6 Q4), each with the assertion against it;
    - items: each item's whereabouts history with the outcome of every assertion (PHASE-6);
    - threads / unmatched: promises with their status, and resolutions that closed none (PHASE-7). The
      assertions a thread consumed are not facts, claims or other assertions as well.
    - secrets / unrevealed: what is kept from whom and who found it out, and reveals that matched no open
      secret (PHASE-10). A revealed secret's fact no longer lists that character in hidden_from.

    `upto` and `known_at` read it as of an earlier request (ADR 0027): the head up to that position, the
    extractions and owner links NMOS had by that time.

    `what_if` reads it as it would be after an owner's join, split or undo (PHASE-20 Q3): `add_links` and
    `add_repairs` are rows as they would be stored, `drop_links` and `drop_repairs` ids taken back. Nothing is written.

    With `canon_key` (a canon generation, ADR 0047), the canon facts of the manifest the names come from are facts
    from before turn 0 (turn -1, `canon` set): the story supersedes them from the turn it says something new. A story
    statement of a relationship (CANON_CONFLICTS, ADR 0047 amendment 1) that replaces or denies a canon one is also
    listed in `conflicts` (`kind` "canon"), and the owner's lock (`fact_lock`) keeps a canon fact or a correction current: a later statement
    that would replace it is held off and listed (`kind` "locked"). Canon facts take no part in secrets or threads.
    They come from the manifest a request names only: while the sidecar lacks it (its upload is under way), the read
    has none, as it cannot tell which of the canon in force still holds. `canon_facts` (a replay) names the manifest
    exactly, None for none; the view's `canon_facts_manifest` says which one a read used.

    With `told` (packet-v20 and the pages that draw chains, PHASE-60 S8, ADR 0086), the view also has `told`: who told
    whom (`told_view`), from the same read, a list of its own. It is never a fact, claim, thread or assertion of the
    view and never shapes its resolution, so nothing else in the view changes; without `told` the key is absent.

    With `carried` (PHASE-60 S6, ADR 0085: what the target's link carries, `carry.target_rows`), a `continue` link's
    rows enter the resolution after the target's own rows (so the target's story names its entities) and fold as facts
    from before turn 0, after the canon facts: the
    story supersedes them, the owner's repairs and exclusions apply to them, a carried opening opens its thread (marked
    `carried`) and the story can close it by text; one kept from someone is a secret of the target, which the target's
    story can reveal (Tier 1: kept out of secrets, it was neither revealable nor held by the secret gates). A
    `regression` link's rows are listed apart (`regression`), annotated with the target's resolution, and enter
    neither the resolution nor a fold; the owner's `memory` exclusions leave them out as they leave rows out and take
    the excluded from their rememberers (`_regression_kept`). Either way the view gains `carried` and `regression`;
    without it, neither.

    With `include_open_turn` (PHASE-67, owner decision 2026-11-25: the author's note and carry only, never a request),
    the open turn's finished early extraction is read as if its reply were accepted (`_with_open_turn`): the head's last
    member, a provisional reply whose extraction by the active generation exists and is not discarded. Its rows fold
    with every other turn's (secrets, threads, knowledge marks alike), marked `open_turn`, and the view gains
    `open_turn` {turn, position, revision, host_logical_id, revision_hash}. A reply rerolled, swiped, edited or removed
    is no head member, so it never counts. Without the option, or with no such extraction, nothing changes.
    """
    if extractor_key is None:
        return {"facts": [], "claims": [], "other": [], "entities": [], "ambiguous": [], "conflicts": [],
                "items": [], "threads": [], "unmatched": [], "secrets": [], "unrevealed": [], "repairs": [],
                "assertions": [], "resolution": None, **({"told": []} if told else {})}
    served = served_assertions(conn, head, extractor_key, upto, known_at, open_turn=include_open_turn)
    # PHASE-66: extract-v21's own predicates on its own rows; its beliefs and forgettings as kinds of their own
    rows = [r for r in served if read_predicate(r) or epistemic(r)]
    # The conversation, the owner's repairs as of the read (ADR 0044) and the read's last turn, in one query.
    found = conn.execute(
        "SELECT w.conversation_id, c.host_persona_name, c.canon_manifest_id, r.id, r.kind, r.target, r.value, r.note,"
        " r.created_at, r.anchor, r.anchored_at,"
        " (SELECT max(turn) FROM active_membership WHERE commit_id = %(head)s"
        "  AND (%(upto)s::int IS NULL OR position <= %(upto)s::int)) AS last_turn"
        " FROM worldline_commit w JOIN conversation c ON c.id = w.conversation_id"
        f" LEFT JOIN owner_repair r ON r.conversation_id = w.conversation_id AND {IN_FORCE[known_at is not None]}"
        " WHERE w.id = %(head)s ORDER BY r.created_at, r.id", {"head": head, "upto": upto, "at": known_at}).fetchall()
    conv = found[0]
    repairs = [{k: x[k] for k in REPAIR_COLUMNS} for x in found if x["id"] is not None]
    if what_if:
        repairs = [x for x in repairs if str(x["id"]) not in what_if.get("drop_repairs", ())] + list(
            what_if.get("add_repairs", ()))
    # PHASE-67 part 4 (D7): an anchored repair as made on this head (`rebase`: its message's turn now, or detached and
    # reported); a live read records the anchor of a legacy repair that matches the head, once (`legacy_anchors`).
    live_read = known_at is None and not what_if
    if repairs:
        need_messages, need_turns = anchors_needed(repairs, live_read)
        if need_messages or need_turns:
            members = members_of(conn, head, need_messages, need_turns)
            repairs = rebase(repairs, members, known_at)
            if live_read:
                record_anchors(conn, legacy_anchors(repairs, members))
    last_turn = conv["last_turn"] if repairs else None
    in_force = live([x for x in repairs if not x.get("detached")], last_turn)
    # Names from canon (PHASE-14 Q6): the request's own manifest, else the canon in force at the read.
    canon_names, canon_used = (canon.names(conn, conv["conversation_id"], known_at, canon_manifest, canon_exact)
                               if conv["canon_manifest_id"] or canon_manifest else ([], None))
    links = links_of(conn, conv["conversation_id"], known_at)
    if what_if:
        links = [x for x in links if str(x["id"]) not in what_if.get("drop_links", ())] + list(
            what_if.get("add_links", ()))
    # Audit B4.3: per-turn persona attribution. On a live read (`upto is None`), `conv["host_persona_name"]` is active;
    # on a historical replay (`upto is not None`), the latest recorded `turn_persona` up to `upto` is the persona that
    # was active then (legacy NULL rows fall back to `conv["host_persona_name"]`, preserving replay identity).
    active_persona = conv["host_persona_name"]
    if upto is not None:
        for s in reversed(served):
            if s.get("turn_persona"):
                active_persona = s["turn_persona"]
                break
    personas = attribute_persona(served, active_persona)
    # Carried rows (ADR 0085), copied: a read annotates and folds its rows in place, and the link's rows are reused. The
    # source's persona is this chat's (S6): its stored marker reads as the persona name the host reports here.
    finale = None
    if carried is not None:
        carried = carried.for_persona(active_persona)
        from .carry import finale_left  # carry imports this module: here, not at import time
        carried, finale = finale_left(conn, carried)  # PHASE-67: a source finale replaced since serves nothing
    carried_all = [{**x, "known_by": list(x["known_by"]) if x.get("known_by") else None,
                    "hidden_from": list(x["hidden_from"]) if x.get("hidden_from") else None}
                   for x in carried.rows] if carried is not None and carried.mode == "continue" else []
    # PHASE-66 guise scoping (soft): a guise and the one wearing it are one entity, so recall still finds them and the
    # response model plays them in disguise; what someone unaware holds toward the guise is kept apart below
    guise_aliases = _guise_aliases(rows + carried_all if carried_all else rows)
    r = resolve(conv["conversation_id"], (rows + carried_all if carried_all else rows) + guise_aliases,
                personas, links, splits_of(in_force), canon_names)
    narrated: dict[tuple, list[dict[str, Any]]] = {}
    claimed: dict[tuple, dict[str, Any]] = {}
    other: list[dict[str, Any]] = []
    promises: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    for row in rows:
        if row["predicate"] == "also_called":
            continue
        _annotate(row, r)
        kept.append(row)
        if row["predicate"] in THREAD_PREDICATES:
            promises.append(row)
    # Canon facts (ADR 0047): those of the manifest the request named (a replay: the one it used), before every row of
    # the story.
    if canon_facts is LIVE:
        canon_facts = canon_used if canon_key and (canon_manifest is None or canon_used == canon_manifest) else None
    canon_rows = [c for c in canonfacts.rows(conn, conv["conversation_id"], canon_facts, canon_key, known_at)
                  if c["predicate"] in REGISTRY and c["predicate"] != "also_called"] if canon_key and canon_facts else []
    for row in canon_rows:
        _annotate(row, r)
    # Carried rows (ADR 0085): after the canon, before every row of the story; their openings open threads first.
    carried_rows = [x for x in carried_all if (read_predicate(x) or epistemic(x)) and x["predicate"] != "also_called"]
    for row in carried_rows:
        _annotate(row, r)
    carried_openings = [x for x in carried_rows if x["predicate"] in THREAD_PREDICATES]
    if carried_openings:
        promises = carried_openings + promises
    rows = canon_rows + carried_rows + kept
    # The owner's repairs (ADR 0044): retracted and corrected facts first, then events of their turn in the secret and
    # thread folds, and name splits in the resolution above.
    applied: dict[str, str | None] = {}
    corrected_at = sorted({(rep.get("value") or {}).get("turn") for rep in in_force if rep["kind"] == "fact_correct"
                           and (rep.get("value") or {}).get("turn") != rep["target"].get("turn")} - {None})  # later turns
    turn_positions = {x["turn"]: x["p"] for x in conn.execute(
        "SELECT turn, max(position) AS p FROM active_membership WHERE commit_id = %s AND turn = ANY(%s) GROUP BY turn",
        (head, corrected_at)).fetchall()} if corrected_at else {}
    quoting = quoted_turns(in_force)  # ADR 0044 amendment 2: a quote counts only while its turn reads as it did
    if quoting:
        in_force = unedited_quotes(in_force, {x["turn"]: x["h"] for x in conn.execute(
            "SELECT turn, max(turn_hash) AS h FROM active_membership WHERE commit_id = %s AND turn = ANY(%s)"
            " GROUP BY turn", (head, quoting)).fetchall()})
    restored_at = sorted({rep["target"].get("turn") for rep in in_force if rep["kind"] in ("fact_restore", "fact_add")}
                         - {None})  # PHASE-67 part 4: a statement the owner adds goes where a restore goes
    turn_info = {x["turn"]: (x["p"], x["h"]) for x in conn.execute(  # PHASE-22 Q7: where a restored fact goes
        "SELECT turn, max(position) AS p, max(turn_hash) AS h FROM active_membership WHERE commit_id = %s"
        " AND turn = ANY(%s) AND (%s::int IS NULL OR position <= %s::int) GROUP BY turn",
        (head, restored_at, upto, upto)).fetchall()} if restored_at else {}
    rows, retracted = apply_facts(rows, in_force, r, applied, _annotate, turn_positions, turn_info)
    # PHASE-67 part 4: the told rows the owner took back, from every read (the repairs list reports them applied)
    told_served = apply_told(told_rows(served), in_force, r, applied) if told or any(
        rep["kind"] == "told_retract" for rep in in_force) else None
    if any(rep["kind"] in FACT_KINDS for rep in in_force):
        # The threads fold what the repairs left: a retracted opening opens nothing, a corrected one opens as corrected
        # and a restored one opens (PHASE-22 Q7), in the rows' order (carried openings first, as above; never canon).
        promises = [x for x in rows if x["predicate"] in THREAD_PREDICATES and not x.get("canon")]
    locks = apply_locks(rows, in_force, r, applied)  # PHASE-14 Q7
    # PHASE-47 S2: entities the owner left out. Out of memory, their own facts and the standing they are one end of
    # leave before the folds; a row that names them only as a participant, or as another's object, stays.
    excluded = exclusions(in_force, r)
    if gone := {i for i, x in excluded.items() if x["scope"] == "memory"}:
        def left_out(a: dict[str, Any]) -> str | None:
            """The left-out entity this row belongs to: its subject, or the other end of a standing."""
            s, o = (str((a.get(f"{side}_entity") or {}).get("id")) for side in ("subject", "object"))
            return s if s in gone else o if a["predicate"] in STANDING and o in gone else None

        for a in rows:
            if (who := left_out(a)) is not None:
                excluded[who]["hidden"] = excluded[who].get("hidden", 0) + 1
        rows = [a for a in rows if left_out(a) is None]
        promises = [a for a in promises if left_out(a) is None]
    # Secrets (PHASE-10, ADR 0033): a reveal ends a secret for the character who found it out, from its
    # turn on: its hidden_from drops that name and its known_by gains it (amendment 1: the scene, strict mode
    # and a narrator must count them as knowing it). `learned` is not a fact itself. Before the threads, which copy
    # the marks of the row that opens them: a revealed goal or promise is revealed as a thread too (ADR 0039).
    # A carried row (ADR 0085) is a secret too: what was kept from someone in the earlier chat still is until this story
    # shows them finding it out, and the summary and excerpt gates keep it.
    # PHASE-66: a belief or a forgetting is no secret (the fold reads both as `NOT_SECRETS`); a forgetting reaches it
    # whole, so it reopens a secret revealed to its subject (and a later reveal ends it again)
    believed = [x for x in rows if epistemic(x)]
    secret_rows = [x for x in rows if not x.get("canon")] if canon_rows else rows
    secrets, unrevealed, reveals = fold_secrets(secret_rows, r, secret_events(in_force, r, applied))
    ended = {s["id"]: set(s["ended"]) for s in secrets if s["ended"]}
    by_repair = {s["id"]: s["repair"] for s in secrets if s.get("repair")}
    for row in rows:
        if row["id"] in by_repair:
            row["repair"] = by_repair[row["id"]]
        if row["id"] in ended:
            # by entity: a reveal to "김하나" also ends the secret for "하나" written beside it
            revealed_to = {r.key("character", n) for n in ended[row["id"]]}
            row["hidden_from"] = [n for n in row.get("hidden_from") or () if r.key("character", n) not in revealed_to] or None
            row["known_by"] = list(row.get("known_by") or []) + sorted(ended[row["id"]] - set(row.get("known_by") or []))
            row["revealed"] = [{"to": n, **s["ended"][n]} for s in secrets if s["id"] == row["id"] for n in s["ended"]]
    disguises = _disguises(rows, r) if guise_aliases else []
    if disguises:  # PHASE-66: after the reveals above, so a character who found out holds toward the one beneath
        _hold_toward_guise(rows, disguises, r)

    def vkey(a: dict[str, Any]) -> tuple:
        """The version key, and a guise-held row's own slot (`toward_guise`): never folded into its wearer's."""
        g = (a.get("toward_guise") or {}).get("guise")
        return version_key(a, r) + (("guise", g),) if g else version_key(a, r)
    threads, unmatched, consumed = fold_threads(promises, r, thread_events(in_force, r, applied))
    if carried_openings:
        assert carried is not None
        opened = {x["id"]: x for x in carried_openings}
        for t in threads:
            if t["id"] in opened:
                t["carried"], t["carried_from"] = carried.link, opened[t["id"]].get("carried_from")
    consumed |= reveals
    for row in rows:
        if row["id"] in consumed:
            continue
        if believed and epistemic(row):  # PHASE-66: told apart below (`_epistemic`), or another assertion
            if (row.get("source") or "narration") != "narration" or (row.get("modality") or "actual") != "actual":
                other.append(row)
            continue
        if row["source"] == "character_claim" and row["modality"] in ("actual", "unknown"):
            # A claim's truth is unknown by nature; the model may say so (owner decision 2026-09-24).
            # latest wins, per speaker as an entity: "백이안" and "이안" are one speaker; an address (and an extract-v21
            # conditioned fact) per condition slot
            where = (slot(row),) if slotted(row["predicate"]) else ()
            claimed[vkey(row) + where + (r.key("character", row["asserted_by"]),)] = row
        elif row["modality"] != "actual":
            other.append(row)
        else:
            narrated.setdefault(vkey(row), []).append(row)
    held: list[dict[str, Any]] = []
    if locks:
        for key, history in narrated.items():
            if any(id(a) in locks for a in history):
                for a in history:
                    if id(a) in locks:
                        a["locked"] = locks[id(a)]
                narrated[key], off = _hold(history, r)
                for lock, a in off:
                    lock["held_off"] = lock.get("held_off", 0) + 1
                    held.append({"kind": "locked", "fact": lock["id"], "turn": lock["turn"], "position": lock["position"],
                                 "text": fact_text(lock), "repair": lock["locked"], "against": _brief(a)})
    facts = [f for history in narrated.values() for f in _versions(history, r)]
    if any(f["predicate"] == "contained_in" for f in facts):  # PHASE-66: what is inside a destroyed thing is not
        facts = _ended_containers(facts, r)
    if believed:  # PHASE-66: beliefs, and what a character forgot withdrawn from them
        aside = {id(x) for x in other}
        beliefs, forgotten, facts = _epistemic([x for x in believed if id(x) not in aside], rows, facts, r)
    by_key: dict[tuple, list[dict[str, Any]]] = {}
    for f in facts:
        by_key.setdefault(vkey(f), []).append(f)
    claims = sorted(claimed.values(), key=lambda c: c["position"], reverse=True)
    for c in claims:
        for f in by_key.get(vkey(c), []):
            if slotted(c["predicate"]) and slot(f) != slot(c):
                continue
            f["claims"].append({"by": c["asserted_by"], "turn": c["turn"], "position": c["position"],
                                "object": c["object"], "value": c["value"], "polarity": c["polarity"]})
    facts.sort(key=lambda f: f["position"], reverse=True)
    for rid, gone in retracted.items():  # the version a retraction made current again names it (ADR 0044, Q7)
        for f in by_key.get(version_key(gone, r), []):
            if slotted(gone["predicate"]) and slot(f) != slot(gone):
                continue
            if not f.get("repair"):
                f["repair"] = rid
    other.sort(key=lambda a: a["position"], reverse=True)
    cause_links(facts + claims, [f for f in facts if f["predicate"] == "event" and f.get("polarity") != "negative"], r)
    conflicts = [{"kind": "disputed", "fact": f["id"], "turn": f["turn"], "position": f["position"], "text": fact_text(f),
                  "against": f["disputed_by"]} for f in facts if f.get("disputed_by")]
    if canon_rows:
        conflicts += _canon_conflicts(facts, {a["position"]: a for a in rows if a.get("canon")}, r)
    conflicts += held
    items: dict[tuple, dict[str, Any]] = {}
    for f in facts:  # one timeline per item, newest first (facts are sorted by position)
        if whereabouts(f):
            items.setdefault(version_key(f, r), {
                "item": f["object"] if f["predicate"] in HOLDER_PER_ITEM else f["subject"],
                "position": f["position"], "history": f["history"]})
    entities = [{**e, "excluded": excluded[str(e["id"])]["scope"]} if str(e["id"]) in excluded else e
                for e in r.entities()]
    pinned = pins(in_force, r)  # PHASE-60 S8: the characters the owner pinned, newest first; an exclusion wins
    view = {"facts": facts, "claims": claims, "other": other, "entities": entities, "excluded": excluded,
            "pins": pinned,
            "ambiguous": r.ambiguous_mentions(), "conflicts": conflicts, "items": list(items.values()),
            "threads": threads, "unmatched": unmatched, "secrets": secrets, "unrevealed": unrevealed,
            "repairs": [_report(rep, applied, r, excluded, pinned) for rep in repairs], "assertions": rows,
            "resolution": r,
            "canon_names": canon_used, "canon_facts": len(canon_rows), "canon_facts_manifest": canon_facts}
    if believed:
        view["beliefs"], view["forgotten"] = beliefs, forgotten
    if disguises:  # PHASE-66: each disguise with the facts held toward its guise (absent without one)
        view["disguises"] = _disguise_view(disguises, facts)
    if include_open_turn and (finale := conn.execute(OPEN_TURN, {"head": head, "key": extractor_key,
                                                                  "upto": upto}).fetchone()) is not None:
        view["open_turn"] = dict(finale)  # PHASE-67: the read took the provisional finale; absent otherwise
    if told:
        view["told"] = told_view(told_served if told_served is not None else told_rows(served), r, excluded)
    if carried is not None:
        view["carried"] = {"link": carried.link, "source": carried.source, "mode": carried.mode,
                           "names": carried.names, "rows": len(carried_rows), "story": carried.story}
        if finale is not None:  # PHASE-67: the snapshot took the source's provisional finale; stale once replaced
            view["carried"]["finale"] = finale
        forgotten = {i for i, x in excluded.items() if x["scope"] == "memory"}  # as the rows above leave them out
        view["regression"] = [line for x in carried.regression
                              if (line := _regression_kept(_regression_line(x, r), r, forgotten)) is not None]
    return view


# PHASE-66 guise scoping (soft; plan 3C): while a `disguised_as` (X passes as the guise G) holds, a form of address, a
# feeling or a tie that a character who does not know (in its `hidden_from`, not yet revealed to) holds toward G, or a
# row whose `condition.as_guise` is G, stays the guise's: its own slot, marked `toward_guise`. X's body (status, place,
# belongings, life) is one with the guise: one entity. Nothing is hidden beyond the knowledge marks (AGENTS.md §2).
GUISE_HELD = frozenset({"addresses", "feels_toward", "relationship"})


def _is_disguise(x: Mapping[str, Any]) -> bool:
    return (x.get("predicate") == "disguised_as" and bool(x.get("object")) and x.get("polarity") != "negative"
            and (x.get("source") or "narration") == "narration" and (x.get("modality") or "actual") == "actual"
            and read_predicate(x))


def _guise_aliases(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """For each extract-v21 disguise, an `also_called` row joining the guise's name to its wearer for the resolution
    only (never a fact, never stored; `guise_alias` marks it, its id negative): the owner's split still separates
    them."""
    out = []
    for d in rows:
        if _is_disguise(d):
            out.append({"id": -(uuid5(_GUISE_NS, f"{d['id']}:{d['object']}").int % 2**61) - 2**61,
                        "predicate": "also_called", "subject": d["subject"], "subject_type": d.get("subject_type"),
                        "object": None, "object_type": None, "value": d["object"], "modality": "actual",
                        "source": "narration", "polarity": "positive", "participants": None, "turn": d.get("turn"),
                        "position": d["position"], "compiler": d.get("compiler"), "guise_alias": True})
    return out


def _disguises(rows: list[dict[str, Any]], r: Resolution) -> list[dict[str, Any]]:
    """Each disguise's span: from its turn until its wearer's next `disguised_as` statement (a new guise, or the
    disguise denied), oldest first."""
    stated = [x for x in rows if x["predicate"] == "disguised_as"]
    out = []
    for d in stated:
        if not _is_disguise(d):
            continue
        k = _subject(d, r)
        nxt = next((x for x in stated if x["position"] > d["position"] and _subject(x, r) == k), None)
        out.append({"row": d, "of": k, "guise": _norm(d["object"]), "start": _unit(d),
                    "end": _unit(nxt) if nxt is not None else None})
    return out


def _unaware(d: Mapping[str, Any], who: str, turn: int, r: Resolution) -> bool:
    """Whether `who` (an entity key) does not know the disguise at `turn`: kept from them, and not revealed to them by
    then (a reveal's turn on, they know; `revealed` as the secret fold set it)."""
    told = {r.key("character", x["to"]): x.get("turn") for x in d.get("revealed") or ()}
    if who in told:
        return told[who] is not None and turn < told[who]
    return who in {r.key("character", n) for n in d.get("hidden_from") or ()}


def _hold_toward_guise(rows: list[dict[str, Any]], disguises: list[dict[str, Any]], r: Resolution) -> None:
    """Mark, in place, the rows held toward a guise (`toward_guise`: {guise, of, disguise})."""
    for x in rows:
        if x["predicate"] not in GUISE_HELD:
            continue
        as_guise = _norm((x.get("condition") or {}).get("as_guise")) if isinstance(x.get("condition"), Mapping) else ""
        t = _unit(x)
        for d in disguises:
            explicit = as_guise == d["guise"]
            if not explicit and _norm(x.get("object")) != d["guise"]:
                continue
            if t < d["start"] or (d["end"] is not None and t >= d["end"]):
                continue
            who = r.key("character", x["subject"])
            if who == d["of"] or not (explicit or _unaware(d["row"], who, t, r)):
                continue
            x["toward_guise"] = {"guise": d["row"]["object"], "of": d["row"]["subject"], "disguise": d["row"]["id"]}
            break


def _disguise_view(disguises: list[dict[str, Any]], facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """`view["disguises"]`: each disguise, newest first, with who it is kept from now, who found it out, whether it
    still holds, and the current facts held toward its guise (`held`, their ids)."""
    current = {f["id"] for f in facts if f["predicate"] == "disguised_as"}
    out = []
    for d in sorted(disguises, key=lambda x: x["row"]["position"], reverse=True):
        row = d["row"]
        out.append({"id": row["id"], "subject": row["subject"], "subject_entity": row.get("subject_entity"),
                    "guise": row["object"], "turn": row.get("turn"), "position": row["position"],
                    "kept_from": list(row.get("hidden_from") or []), "revealed": list(row.get("revealed") or []),
                    "current": row["id"] in current,
                    "held": [f["id"] for f in facts if (f.get("toward_guise") or {}).get("disguise") == row["id"]]})
    return out


_SINCE = re.compile(r"since\s+turn\s+(\d+)", re.IGNORECASE)
_LISTED = re.compile(r"^\[turn -?\d+\]\s*")  # a reveal's value names its listed secret's turn (ADR 0033)
FORGOT_ALL = frozenset({"all", "everything", "전부", "모두", "전부 다", "모든 것", "모든 기억"})


def forgot_scope(value: str | None) -> tuple[str, int | None]:
    """What a `forgot` value withdraws (extract-v21: "the memory, \"all\", or \"since turn N\""): ("all", None),
    ("since", N), or ("matter", None) for a memory named by its text."""
    text = " ".join(str(value or "").split())
    if text.casefold() in FORGOT_ALL:
        return "all", None
    if m := _SINCE.search(text):
        return "since", int(m.group(1))
    return "matter", None


def _about(value: str | None, f: Mapping[str, Any]) -> bool:
    """Whether a named matter (a belief's, a forgetting's) is this row's: its value, or its line, at least MATCH_MIN
    alike (the bar a thread's close or a reveal's text needs, ADR 0019)."""
    matter = _LISTED.sub("", str(value or ""))
    return bool(matter) and max(similarity(matter, _LISTED.sub("", str(f.get("value") or ""))),
                                similarity(matter, secret_text(f))) >= MATCH_MIN


def _epistemic(believed: list[dict[str, Any]], rows: list[dict[str, Any]], facts: list[dict[str, Any]],
               r: Resolution) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """extract-v21's `believes` and `forgot` (PHASE-66), narrated and actual, oldest first: (beliefs, forgotten, facts).

    A belief is what its subject takes to be true, which may be false. It is never a fact about the world: it folds
    apart (the latest per character and matter, a denial current as "no longer believes"), opens no conflict and no
    `disputed` mark against the fact it contradicts, and is `held` until the same character later knows or learns the
    matter (a `knows` or `learned` row, `_about`) or forgets it; then `ended`, with `ended_by`.

    A forgetting withdraws, from its turn on, its character's knowledge of the matter (`forgot_scope`: one named
    matter, "all", or "since turn N"): a current `knows` fact of theirs stated at or before it leaves `facts`, and their
    name leaves the `known_by` of a fact they knew by then (a reveal's turn, else the fact's). Nothing is added to
    `hidden_from`: nothing is hidden beyond what the marks already did. Each forgetting lists what it `withdrew`; a
    later `knows` (or reveal) after it stands."""
    order = {id(x): i for i, x in enumerate(rows)}
    learners = [x for x in rows if x["predicate"] in ("knows", "learned") and x.get("polarity") != "negative"
                and (x.get("source") or "narration") == "narration" and (x.get("modality") or "actual") == "actual"]
    forgets = [g for g in believed if g["predicate"] == "forgot" and g.get("polarity") != "negative"]
    who = lambda x: r.key("character", x["subject"])  # noqa: E731

    def forgets_it(g: dict[str, Any], start: int | None, f: Mapping[str, Any]) -> bool:
        scope, since = forgot_scope(g.get("value"))
        if start is not None and g.get("turn") is not None and start > g["turn"]:
            return False  # learned after the forgetting
        if scope == "all":
            return True
        if scope == "since":
            return start is not None and since is not None and start >= since
        return _about(g.get("value"), f)

    latest: dict[tuple, dict[str, Any]] = {}
    for b in believed:
        if b["predicate"] == "believes":
            latest[(who(b), _norm(b.get("value")))] = b
    beliefs = []
    for b in sorted(latest.values(), key=lambda x: x["position"], reverse=True):
        out = {**b, "status": "held"}
        ender = next((x for x in sorted(learners + forgets, key=lambda x: order.get(id(x), 0))
                      if order.get(id(x), -1) > order.get(id(b), -1) and who(x) == who(b)
                      and (forgets_it(x, b.get("turn"), b) if x["predicate"] == "forgot" else _about(b.get("value"), x))),
                     None)
        if ender is not None:
            out["status"] = "ended"
            out["ended_by"] = _brief(ender)
        beliefs.append(out)
    forgotten = []
    kept_facts = facts
    for g in forgets:
        withdrew: list[dict[str, Any]] = []
        name = g["subject"]
        k = who(g)
        next_facts = []
        for f in kept_facts:
            if f["predicate"] == "knows" and who(f) == k and f["position"] <= g["position"] \
                    and forgets_it(g, f.get("turn"), f):
                withdrew.append({"id": f["id"], "turn": f.get("turn"), "predicate": f["predicate"],
                                 "text": fact_text(f), "how": "fact"})
                continue
            knew = [n for n in f.get("known_by") or () if r.key("character", n) == k]
            if knew and f["position"] <= g["position"]:
                start = next((x.get("turn") for x in f.get("revealed") or () if r.key("character", x["to"]) == k),
                             f.get("turn"))
                if forgets_it(g, start, f):
                    f["known_by"] = [n for n in f["known_by"] if n not in knew] or None
                    f["forgotten_by"] = list(f.get("forgotten_by") or []) + knew
                    withdrew.append({"id": f["id"], "turn": f.get("turn"), "predicate": f["predicate"],
                                     "text": fact_text(f), "how": "known_by"})
            next_facts.append(f)
        kept_facts = next_facts
        scope, since = forgot_scope(g.get("value"))
        forgotten.append({**g, "scope": scope, "since": since, "who": name, "withdrew": withdrew})
    forgotten.sort(key=lambda x: x["position"], reverse=True)
    return beliefs, forgotten, kept_facts


TOLD_SHOWN = ("id", "turn", "position", "subject", "object", "value", "knowledge", "known_by", "hidden_from",
              "subject_entity", "object_entity", "evidence")


def told_chain(rows: list[dict[str, Any]], entity_id: str | None = None) -> list[dict[str, Any]]:
    """What the pages that draw chains get of `view["told"]` (PHASE-60 S8), oldest first: each row's teller, hearer,
    what, turn, participants and knowledge marks (and `when_happened` when it has one). With `entity_id`, only the rows
    whose teller or hearer is that entity. The view already left out what the pages leave out (`told_view`)."""
    out = []
    for t in rows:
        if entity_id is not None and entity_id not in {
                str((t.get(f"{side}_entity") or {}).get("id")) for side in ("subject", "object")}:
            continue
        shown = {k: t.get(k) for k in TOLD_SHOWN}
        shown["participants"] = [dict(p) for p in t.get("participants") or ()]
        if t.get("when_happened"):
            shown["when_happened"] = t["when_happened"]
        out.append(shown)
    return out


def told_view(rows: list[dict[str, Any]], r: Resolution, excluded: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Who told whom (PHASE-60 S8), oldest first: the served told rows (`told_rows`) taken as facts are (narrated,
    actual, positive), each annotated with the view's entities (`_annotate`). A tie between two characters, as a pair
    is: a row whose teller or hearer the owner left out, either scope (PHASE-47 S2, `excluded_ids`), is left out. The
    knowledge marks are the row's own: a told row is no secret and infers no knowledge (ADR 0086 item 4)."""
    out = []
    for row in rows:
        if ((row.get("source") or "narration") != "narration" or (row.get("modality") or "actual") != "actual"
                or row.get("polarity") == "negative"):
            continue
        _annotate(row, r)
        if any(str((row.get(f"{side}_entity") or {}).get("id")) in excluded for side in ("subject", "object")):
            continue
        out.append(row)
    return out


def _regression_line(stored: dict[str, Any], r: Resolution) -> dict[str, Any]:
    """A copy of a regression row (ADR 0085 item 5) annotated with the target's resolution like a fact: a thread by
    its opening (else its maker and recipient as characters), so a later slice can rank and name it."""
    line = dict(stored)
    if line.get("line") != "thread":
        _annotate(line, r)
        return line
    opening = line.get("opening")
    basis: dict[str, Any] = dict(opening) if opening else {
        "subject": line.get("by"), "subject_type": "character", "object": line.get("to"),
        "object_type": "character" if line.get("to") else None, "participants": None}
    _annotate(basis, r)
    for k in ("subject_entity", "object_entity", "names"):
        if k in basis:
            line[k] = basis[k]
    return line


def _regression_kept(line: dict[str, Any], r: Resolution, out: set[str]) -> dict[str, Any] | None:
    """An annotated regression line (`_regression_line`) under the target's `memory` exclusions (PHASE-47 S2, the
    entity ids in `out`), as a target row is: None when its subject (a thread's maker) is left out, or the other end
    of a standing; else the line with the left-out characters gone from its rememberers (`known_by`), None when no one
    is left to remember it. A `cast` exclusion changes no line."""
    if not out:
        return line
    s, o = (str((line.get(f"{side}_entity") or {}).get("id")) for side in ("subject", "object"))
    if s in out or (line.get("predicate") in STANDING and o in out):
        return None
    known = line.get("known_by") or []
    kept = [n for n in known if str((r.entity("character", n) or {}).get("id")) not in out]
    if known and not kept:
        return None
    if len(kept) != len(known):
        line["known_by"] = kept
    return line


# Predicates whose story statement, replacing a canon one, is listed as a conflict (PHASE-14 Q4, ADR 0047 amendment 1):
# how two stand is rarely a change the story tells without saying so. `identity` is not listed: on the measured chats a
# canon identity in another language, or a second true description, read as "something else" (PHASE-14 step 6). A
# place, a condition, a feeling, a form of address or who someone is now: the story supersedes canon without a listing.
CANON_CONFLICTS = frozenset({"relationship"})


def _brief(a: dict[str, Any]) -> dict[str, Any]:
    out = {k: a.get(k) for k in ("id", "position", "turn", "subject", "predicate", "object", "value", "polarity")}
    if a.get("canon"):
        out["canon"] = a["canon"]
    return out


def _canon_conflicts(facts: list[dict[str, Any]], canon_at: dict[int, dict[str, Any]],
                     r: Resolution | None) -> list[dict[str, Any]]:
    """A current story fact of CANON_CONFLICTS that replaced or ended a canon statement saying something else."""
    out = []
    for f in facts:
        if f["predicate"] not in CANON_CONFLICTS or f.get("canon") or f.get("owner"):
            continue
        for h in f.get("history") or ():
            c = canon_at.get(h["position"]) if h.get("canon") else None
            if c is None or h["outcome"] not in ("superseded", "ended") or _restates(c, f, r):
                continue
            out.append({"kind": "canon", "fact": f["id"], "turn": f["turn"], "position": f["position"],
                        "text": fact_text(f), "against": _brief(c)})
    return out


def _changes(locked: dict[str, Any], a: dict[str, Any], r: Resolution | None) -> bool:
    """Whether a statement of the locked fact's version key would replace or end it: for a relationship, one of the same
    direction or a symmetric one (ADR 0038); for `addresses`, the same condition slot or a unifying `scope="all"`
    (PHASE-64, ADR 0091), and so for an extract-v21 conditioned fact (PHASE-66: a relationship needs both); for every
    other key, any."""
    same_slot = (not (slotted(locked["predicate"]) and slotted(a["predicate"]))
                 or unifies(a) or unifies(locked) or slot(a) == slot(locked))
    if locked["predicate"] == "relationship" and a["predicate"] == "relationship":
        return same_slot and (_subject(a, r) == _subject(locked, r) or symmetric(a["value"])
                              or symmetric(locked["value"]))
    return same_slot


def _restates(a: dict[str, Any], b: dict[str, Any], r: Resolution | None) -> bool:
    """Whether two statements say the same: predicate, polarity, value, subject and object (as entities). A
    relationship said either way round is the same when it holds both ways (ADR 0038). Conditional `addresses` also
    match their condition slot (PHASE-64)."""
    if a["predicate"] != b["predicate"] or a.get("polarity") != b.get("polarity") \
            or _norm(a.get("value")) != _norm(b.get("value")):
        return False
    if slotted(a["predicate"]) and slot(a) != slot(b):
        return False
    ends = lambda x: (_subject(x, r), _object(x, r) if x.get("object") else None)  # noqa: E731
    if ends(a) == ends(b):
        return True
    return a["predicate"] == "relationship" and symmetric(a.get("value")) and ends(a) == ends(b)[::-1]


def _hold(history: list[dict[str, Any]],
          r: Resolution | None) -> tuple[list[dict[str, Any]], list[tuple[dict[str, Any], dict[str, Any]]]]:
    """A version key's history under the owner's locks (PHASE-14 Q7), rows marked `locked`: a statement after a locked
    one that would replace or end it is held off, so each locked version stays current (a relationship's two
    directions each, ADR 0038). Returns (the history the fold reads, (lock, statement) for each statement held off,
    against the latest lock it would change); a later statement that says the same as that lock is left out of
    both."""
    kept: list[dict[str, Any]] = []
    off: list[tuple[dict[str, Any], dict[str, Any]]] = []
    locked: list[dict[str, Any]] = []
    for a in history:
        if a.get("locked"):
            locked.append(a)
            kept.append(a)
            continue
        against = next((x for x in reversed(locked) if _changes(x, a, r)), None)
        if against is None:
            kept.append(a)
        elif not _restates(against, a, r):
            off.append((against, a))
    return kept, off


def _report(rep: dict[str, Any], applied: dict[str, str | None], r: Resolution,
            excluded: dict[str, dict[str, Any]] | None = None,
            pinned: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """A repair with what it applies to now (ADR 0044); a name split, the entity it left and the names that still
    join the two when it could not separate them; an exclusion, the entity it leaves out and how many rows (PHASE-47);
    a pin, the character it pins (PHASE-60 S8), or None when its name is no character now or the owner left it out."""
    if rep["kind"] == "entity_pin":
        t = rep.get("target") or {}
        e = r.entity(t.get("entity_type") or "character", t.get("name")) if r is not None else None
        on = e is not None and any(str(p["entity_id"]) == str(e["id"]) for p in pinned or ())
        return {**rep, "applied": e["id"] if on else None}
    if rep["kind"] == "entity_exclude":
        hit = next(((i, x) for i, x in (excluded or {}).items() if str(x["repair"]) == str(rep["id"])), None)
        return {**rep, "applied": hit[0] if hit else None, "hidden": hit[1].get("hidden", 0) if hit else 0}
    if rep["kind"] != "name_split":
        return {**rep, "applied": applied.get(str(rep["id"]))}
    t = rep["target"]
    via = r.split_via.get(str(rep["id"]))
    done = via is None and any(str(s["id"]) == str(rep["id"]) for _, _, s in r.splits)
    entity = r.entity(t["entity_type"], t["name"]) if done else None
    return {**rep, "applied": entity["id"] if entity else None, "via": via}


def links_of(conn: psycopg.Connection, conversation: UUID, known_at: datetime | None = None) -> list[dict[str, Any]]:
    """The owner's current entity links of a conversation, oldest first (ADR 0025); with `known_at`, the
    links in force at that time (ADR 0027)."""
    if known_at is None:
        return conn.execute("SELECT id, entity_type, name, same_as, created_at FROM entity_link"
                            " WHERE conversation_id = %s AND removed_at IS NULL ORDER BY created_at, id",
                            (conversation,)).fetchall()
    return conn.execute("SELECT id, entity_type, name, same_as, created_at FROM entity_link"
                        " WHERE conversation_id = %s AND created_at <= %s AND (removed_at IS NULL OR removed_at > %s)"
                        " ORDER BY created_at, id", (conversation, known_at, known_at)).fetchall()


def persona_of(host_persona_name: str | None) -> list[str]:
    """The persona names the host reported for a conversation (ADR 0023): none, or its current one."""
    return [host_persona_name] if host_persona_name else []


def _same_persona_name(a: str, b: str) -> bool:
    """Whether two host persona names name the same person (exact match, or one is a piece/given/full-name variant of
    the other via `entities.names_persona`: e.g. '카일' <-> '아오키 카일', '기현' <-> '윤기현',
    'Ronan Voss' <-> 'Ronan Voss/ 윤기현'). Distinct names ('타쿠미' vs '레이') return False."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb or na == nb:
        return True
    return names_persona("character", a, (b,)) or names_persona("character", b, (a,))


def attribute_persona(rows: list[dict[str, Any]], current_persona: str | None) -> list[str]:
    """Per-turn persona attribution (Tier 4, audit B4.3), applied in place on `rows`.

    Returns the persona names for `entities.resolve(...)`: `current_persona` plus any earlier turn persona that is a
    name variant/rename of it. Rows from turns synced under a distinct earlier persona have their `USER_NAMES`
    references (`subject`, `object`, `asserted_by`, `also_called` value, `known_by`, `hidden_from`, `participants`)
    rewritten to that turn's recorded `turn_persona`, preventing retroactive reassignment to the new persona while
    keeping the earlier persona's `{{user}}` and named rows unified as one character. Legacy rows (`turn_persona` None)
    and single-persona chats are untouched. Idempotent.
    """
    personas = persona_of(current_persona)
    if not current_persona or not current_persona.strip():
        return personas
    seen_same: set[str] = {_norm(current_persona)}
    for row in rows:
        tp = row.get("turn_persona")
        if not tp or not isinstance(tp, str):
            continue
        tp = tp.strip()
        if not tp:
            continue
        ntp = _norm(tp)
        if ntp in seen_same:
            continue
        if _same_persona_name(tp, current_persona):
            seen_same.add(ntp)
            personas.append(tp)
            continue
        if row.get("subject_type") == "character" and _norm(row.get("subject")) in USER_NAMES:
            row["subject"] = tp
        if row.get("object") and row.get("object_type") == "character" and _norm(row.get("object")) in USER_NAMES:
            row["object"] = tp
        if row.get("predicate") == "also_called" and row.get("subject_type") == "character" and _norm(row.get("value")) in USER_NAMES:
            row["value"] = tp
        if row.get("asserted_by") and _norm(row.get("asserted_by")) in USER_NAMES:
            row["asserted_by"] = tp
        if kb := row.get("known_by"):
            if any(_norm(x) in USER_NAMES for x in kb):
                row["known_by"] = [tp if _norm(x) in USER_NAMES else x for x in kb]
        if hf := row.get("hidden_from"):
            if any(_norm(x) in USER_NAMES for x in hf):
                row["hidden_from"] = [tp if _norm(x) in USER_NAMES else x for x in hf]
        if parts := row.get("participants"):
            if any(p.get("type") == "character" and _norm(p.get("name")) in USER_NAMES for p in parts):
                row["participants"] = tuple(
                    {**p, "name": tp} if p.get("type") == "character" and _norm(p.get("name")) in USER_NAMES else p
                    for p in parts
                )
    return personas


def _annotate(row: dict[str, Any], r: Resolution) -> None:
    """Entity of subject and object, and every name they go by (recall matches any of them).

    Typed participants (PHASE-8) resolve the same way and add their names too, except the persona: it is
    in every chat, so it is never a mention (Q4). They change no knowledge mark and no version key.
    """
    names: list[str] = []
    for role, kind, name in (("subject", row.get("subject_type"), row["subject"]),
                             ("object", row.get("object_type"), row.get("object"))):
        if not name:
            continue
        e = r.entity(kind, name)
        if e:
            row[f"{role}_entity"] = {"id": e["id"], "name": e["name"]}
            names += e["names"]
        else:
            row[f"{role}_entity"] = {"status": r.status(kind, name), "candidates": r.candidates(kind, name)}
            names.append(name)
    row["names"] = names
    for p in row.get("participants") or ():
        if r.is_persona(p["type"], p["name"]):
            continue
        e = r.entity(p["type"], p["name"])
        names += e["names"] if e else [p["name"]]


def participant_entities(row: dict[str, Any], r: Resolution) -> list[dict[str, Any]]:
    """Each participant with its entity, or its resolution status when it has none (the Inspector's
    view; recall only needs the names `_annotate` adds)."""
    out = []
    for p in row.get("participants") or ():
        e = r.entity(p["type"], p["name"])
        out.append({**p, "entity": {"id": e["id"], "name": e["name"]} if e else
                    {"status": r.status(p["type"], p["name"]), "candidates": r.candidates(p["type"], p["name"])}})
    return out


def fact_versions(conn: psycopg.Connection, head: UUID, extractor_key: str | None) -> list[dict[str, Any]]:
    """Current narrated fact versions (see `memory_view`), newest first."""
    return memory_view(conn, head, extractor_key)["facts"]


def _grams(text: str) -> set[str]:
    padded = f"  {_norm(text)} "
    return {padded[i: i + 3] for i in range(len(padded) - 2)}


def fact_text(f: dict[str, Any]) -> str:
    parts = [f["subject"], f["predicate"].replace("_", " ")]
    if f.get("object"):
        parts.append(f["object"])
    text = " ".join(parts)
    cond = f.get("condition")  # PHASE-66: only a conditioned predicate's own mark; a stray one is ignored, never raised on
    if label := address_label(f) or (address_label({"predicate": "addresses", "address_condition": cond})
                                     if isinstance(cond, Mapping) and slotted(f.get("predicate"))
                                     and f.get("predicate") != "addresses" else None):
        text = f"{text} [{label}]"  # PHASE-64; PHASE-66: a conditioned fact names its condition the same way
    return f"{text}: {f['value']}" if f.get("value") else text


SITUATIONAL_ADDRESS_MAX = 3  # max situational `addresses` lines per direction in one packet (PHASE-64, ADR 0091)


FIRST_PERSON = re.compile(r"(^|\s)(내|나는|나를|나한테|나에게|나의|저는|제가|저를|제|i|my|me|mine)(\s|$|[?,.!])", re.IGNORECASE)
LEXICAL_BAR = 0.35  # trigram overlap with the query that makes an unmentioned fact relevant
# How two characters stand with each other (ADR 0026): one current value per pair, so a scene's cast has
# few of them, and the reply goes wrong without them (a speech level or a form of address forgotten, ADR
# 0028), or a role one holds toward the other (ADR 0059). Read side only, like HOLDER_PER_ITEM: outside REGISTRY, so
# changing it needs no new generation.
STANDING = frozenset({"relationship", "role_toward", "feels_toward", "addresses"})


def excluded_ids(view: dict[str, Any] | None) -> frozenset[str]:
    """The entities the owner left out of the cast, either scope (PHASE-47 S2): not people, pair ends or <Cast>."""
    return frozenset((view or {}).get("excluded") or ())
# How a character stands now (the Cast's predicates, PHASE-12 Q4): with STANDING, what a message naming the character
# needs whatever it asks (PHASE-36 Q1).
NOW = frozenset({"located_in", "has_status", "feels_toward", "possesses"})
# What kind of fact a question asks for, by its own words (PHASE-36 Q1, amended on the replay: "하나는 무슨 일을 해?"
# asks for an identity in words the fact does not share). A fact of the kind asked for is named by a name alone.
# "무슨 일을 해" asks for a job, "무슨 일이 있었어" and "무슨 일을 했어" for an event.
ASKS: tuple[tuple[re.Pattern[str], frozenset[str]], ...] = (
    (re.compile(r"무슨\s?일을?\s?(해|하는|하니|하지)|하는\s?일|직업|정체|뭐\s?하는\s?(사람|분|애)|\bjob\b|\bfor a living\b"
                r"|\bwhat does \w+ do\b|\bwho is\b", re.IGNORECASE), frozenset({"identity", "role_toward"})),
    (re.compile(r"소속|길드|출신|\bguild\b|\bmember of\b", re.IGNORECASE), frozenset({"member_of"})),
    (re.compile(r"성격|어떤\s?사람|생김새|외모|어떻게\s?생겼|특징|\blook like\b|\bpersonality\b", re.IGNORECASE),
     frozenset({"has_trait"})),
    (re.compile(r"무슨\s?일이?\s?있|무슨\s?일을\s?했|뭘\s?했|뭐\s?했|무엇을\s?했|\bwhat happened\b", re.IGNORECASE), frozenset({"event"})),
    (re.compile(r"알고\s?있|아는\s?(것|거|게)|\bknows?\b", re.IGNORECASE), frozenset({"knows"})),
)


# One-syllable words that say how or when, not what (PHASE-35 Q2): a verb's or an ending's piece (온, 준, 한), a
# dependent noun (지, 때, 것, 게), a negation or an adverb (안, 못, 더), a pronoun or a determiner (그, 이, 제).
FUNCTION_SYLLABLES = frozenset(
    "온 간 갈 올 본 볼 한 할 된 될 준 줄 난 넌 날 때 적 지 수 것 거 게 걸 데 뿐 듯 안 못 잘 더 또 좀 다 왜 뭐 "
    "그 이 저 제 내 네 너 나 걔 얘 쟤 두 세 첫 건 곳 쪽 번".split())


def lexically_related(facts: list[dict[str, Any]], query: str) -> bool:
    """Whether a fact shares the message's words at LEXICAL_BAR, the bar that makes an unmentioned fact relevant."""
    q_grams = _grams(query)
    return any(len(_grams(fact_text(f)) & q_grams) / max(1, len(q_grams)) >= LEXICAL_BAR for f in facts)


def asked_nouns(query: str) -> tuple[str, ...]:
    """The question's one-syllable Hangul words that can name something (빵, 달): what a short question asks about
    (PHASE-35 Q2; PHASE-36 Q1, amended: a fact holding one is named by its character's name)."""
    return tuple(dict.fromkeys(w for w in re.findall(r"[가-힣]+", query)
                               if len(w) == 1 and w not in FUNCTION_SYLLABLES))


def asked_predicates(query: str, ontology: bool = False) -> frozenset[str]:
    """The predicates the question's own words ask for (ASKS); with `ontology` (packet-v21 over extract-v21's rows,
    PHASE-66) ASKS_V21 too."""
    return frozenset(p for pattern, preds in (ASKS + ASKS_V21 if ontology else ASKS) if pattern.search(query)
                     for p in preds)


# PHASE-66 (`relevant_facts(ontology=True)`, packet-v21 only): extract-v21's own predicates. How a character stands now
# also holds a death or a life, a home, what an item is in and a rank; a question asks for them in its own words.
NOW_V21 = frozenset({"vital_status", "lives_in", "contained_in", "holds_rank"})
ASKS_V21: tuple[tuple[re.Pattern[str], frozenset[str]], ...] = (
    (re.compile(r"살아\s?있|죽었|죽은|생사|행방|\balive\b|\bdead\b|\bmissing\b", re.IGNORECASE), frozenset({"vital_status"})),
    (re.compile(r"어디\s?살|사는\s?곳|집이\s?어디|거처|\blives?\b|\bhome\b", re.IGNORECASE), frozenset({"lives_in"})),
    (re.compile(r"직위|계급|직책|지위|\brank\b|\btitle\b", re.IGNORECASE), frozenset({"holds_rank"})),
    (re.compile(r"정체|위장|신분|\bcover\b|\bwho is\b", re.IGNORECASE), frozenset({"cover_identity"})),
    (re.compile(r"안에|어디에\s?(넣|두)|\binside\b|\bin which\b", re.IGNORECASE), frozenset({"contained_in"})),
)
# Added to the score of a mentioned fact (ADR 0026). Below the gap between a mention in the user's message
# and one in the previous reply (1.0), so they order facts of equal mention only.
PRIOR_STANDING = 0.5
PRIOR_MAJOR_EVENT = 0.3
# Added to a mentioned fact hidden from someone in the scene (ADR 0034): above how the cast stand (0.5), below
# a mention in the user's message rather than the previous reply (1.0) and the hidden character addressed (2.5).
PRIOR_HIDDEN_PRESENT = 0.8


def prior(f: dict[str, Any]) -> float:
    if f["predicate"] in STANDING:
        return PRIOR_STANDING
    if f["predicate"] == "event" and f.get("salience") == "major":
        return PRIOR_MAJOR_EVENT
    return 0.0


WHY = re.compile(r"(왜|어째서|무슨 이유|이유가|이유는|\bwhy\b|how come)", re.IGNORECASE)
PRIOR_CAUSE = 1.0  # packet-v6: a fact with a stated cause, when the message asks why (ADR 0040)
# The message asks how it started (ADR 0056): 처음 (맨 처음), 최초, 예전, 옛날, 원래, 초반, and 첫 before a space, 번 or 째
# (첫 만남, 첫번째, 첫째; not 첫눈). From the message only, like WHY.
FIRST_CUE = re.compile(r"(처음|최초|예전|옛날|원래|초반|첫(\s|번|째)|\bat first\b|\bfirst time\b|\boriginally\b"
                       r"|\bin the beginning\b)", re.IGNORECASE)
# The message asks about the past (PHASE-31 Q4): FIRST_CUE, and 전에, 이전, 첫날 (FIRST_CUE leaves it out with 첫눈; owner
# 2026-10-05 on the replay), before, used to, previously. Under packet-v12
# it keeps the excerpts that state a replaced value and prints ended roles; from the message only, like FIRST_CUE.
HISTORY_CUE = re.compile(FIRST_CUE.pattern + r"|전에|이전|첫\s?날|\bbefore\b|\bused to\b|\bpreviously\b", re.IGNORECASE)


# PHASE-40: a question must identify its subject, not merely mention the persona somewhere.
# Keep this deliberately narrower than a natural-language parser: uncertain clauses abstain.
_PERSONA_WH = re.compile(r"(?:^|\s)(?:무슨|무엇|어떤|누구|뭐|어디)(?!론가)|\b(?:what|where|who|which)\b", re.I)
_PERSONA_GENERIC = frozenset({"처음", "최초", "예전", "이전", "원래", "초반", "이름", "혼자", "before", "first",
                               "time", "originally", "previously", "job", "identity", "일을", "일이", "하는", "다니는"})


def _persona_questions(query: str, names: set[str], other_names: set[str]) -> list[tuple[frozenset[str], tuple[str, ...]]]:
    """Explicit same-clause subject questions, with predicate and content cues (read side only)."""
    questions = []
    for part in re.finditer(r"([^.!?;\n。！？]+)([.!?;\n。！？]|$)", _norm(query)):
        clause = part.group(1).strip(" \"'“”‘’")
        if not _PERSONA_WH.search(clause):
            continue
        if any(re.search(r"(?<!\w)" + re.escape(n) + r"(?=$|\W|[은는이가의])", clause)
               for n in other_names if len(n) >= 2):
            continue
        for name in sorted(names, key=len, reverse=True):
            n = re.escape(name)
            korean = re.match(r"^" + n + r"(?P<particle>은|는|이|가|의)\s+(?P<body>.*)$", clause)
            english = re.fullmatch(
                r"(?:where (?:is|was) " + n + r"(?: (?:now|before|previously|originally))?"
                r"|where (?:does|did) " + n + r" (?:live|stay)"
                r"|who (?:is|was) " + n + r"|what (?:does|did) " + n + r" (?:do(?: for a living)?|have|own|possess|know)"
                r"|what (?:is|was) " + n + r"['’]s (?:job|identity|personality|guild)"
                r"|what happened to " + n + r")", clause)
            if not korean and not english:
                continue
            body = korean.group("body") if korean else clause.replace(name, " ")
            if korean and re.search(r"(?:인지|는지|냐고|라고)\s", body):
                continue  # an indirect/reported question can have a different, unnamed subject
            if korean and part.group(2) not in ("?", "？") and not re.search(r"(?:까|니|냐|지|어|해|야|더라|요)$", body):
                continue
            if korean and korean.group("particle") == "의" and not re.match(
                    r"^(?:직업|정체|성격|외모|소속|길드|출신|특징)(?:은|는|이|가)?\s", body):
                continue  # "the persona's friend" is another subject, not the persona.
            if korean and re.search(r"(?:친구|동료|아내|남편|선생|딸|아들|그녀)(?:은|는|이|가)\s", body):
                continue
            # Narration followed by a question about somebody else is not a persona question.
            if korean and re.search(r"(?:지만|면서|그리고|그러고|(?:[가-힣]+고))\s", body.replace("가지고", "").replace("갖고", "")):
                continue
            predicates = set(asked_predicates(clause))
            if re.search(r"어디|\bwhere\b", body):
                predicates.add("located_in")
            if re.search(r"가지고|갖고|소유|\b(?:have|own|possess)\b", body):
                predicates.add("possesses")
            if re.search(r"회사|\bcompany\b", body):
                predicates.update(("member_of", "identity"))
            words = tuple(w for w in keywords(body) if w not in _PERSONA_GENERIC and w not in names)
            questions.append((frozenset(predicates), words))
            break
    return questions


def relevant_facts(facts: list[dict[str, Any]], query: str, previous_ai: str, in_context: set[str],
                   limit: int, events_limit: int | None = None,
                   persona: frozenset[str] = frozenset(), present: frozenset[str] = frozenset(),
                   causes: bool = False, first_cue: bool = False,
                   window_start: int | None = None, marks: bool = False,
                   aliases: Mapping[str, frozenset[str]] | None = None,
                   named: set[str] | None = None, named_by_words: bool = False,
                   risky: frozenset[str] | None = None,
                   keep: Callable[[dict[str, Any]], bool] | None = None, *,
                   persona_questions: bool = False, persona_entity: str | None = None,
                   persona_query_names: frozenset[str] | None = None,
                   persona_added: set[str] | None = None,
                   pinned: frozenset[str] = frozenset(), pin_named: set[str] | None = None,
                   _question_facts: frozenset[str] = frozenset(), ontology: bool = False) -> list[dict[str, Any]]:
    """Facts about entities mentioned now, then lexically related ones; never from in-context sources.

    A fact hidden from a character who is being addressed counts as a strong mention: it is the one the
    model most needs to see (so it does not leak), and "내/my" questions concern the user's facts. A fact
    hidden from someone in the scene (`present`, normalized names; ADR 0034) gains less, and only when it is
    mentioned or related: the scene is where it can leak, and where its holder may need it. Among
    facts of equal mention, how two characters stand (`STANDING`) comes first, then major events (ADR
    0026). Being in `known_by` adds nothing: a long list named most of a scene's cast and put trivia first.

    At most `events_limit` of them are `event` facts (PHASE-7 Q4): events are the most frequent predicate
    and all stay current, so a main character's newest events would otherwise take every slot. Among
    events a `major` one comes before any `minor` or unlabeled one with the same mention score, and a
    `minor` one needs the lexical bar: a name mention alone does not bring it (ADR 0020). Unlabeled
    events (older generations) rank as before.

    With `persona_questions` (packet-v18, PHASE-40), an explicit same-clause question about the resolved
    `persona_entity` can offer at most two matching subject facts at mention score 1.5, between a name in
    the current question (2) and the previous reply (1). `persona_query_names` is a caller-validated,
    unambiguous name set, separate from ordinary mentions. `persona_added` shares the cap across fact/claim
    selections. The normal fact/event quotas, history ordering and token budget still apply.

    The persona's names (`USER_NAMES` and `persona`, the resolver's `persona_names`; ADR 0023) are never
    an ordinary mention: the persona is in every chat, and a user who narrates it by name writes that name in every
    message. A first-person question still brings the persona's own facts.

    With `causes` (packet-v6, ADR 0040) a stated cause counts as part of the fact's words, and when the message asks
    why, a fact that has one gains PRIOR_CAUSE.

    With `first_cue` (ADR 0056), when the message asks how it started (FIRST_CUE): events are capped mentioned first
    (whether, not how strongly: a secret's or the persona's bonus would put a newer one first), then oldest first,
    before salience and score; a `minor` event needs no lexical bar; equal scores go to the older fact;
    and a standing fact whose source is in context stays a candidate when it started before the window
    (`_started_before`).

    `aliases` (`name_variants`, ADR 0058): the other names a character goes by in this request (`variants.aliases`, a
    given name or a Hangul spelling of a romanized name); they count as its names, for a mention and for a secret's
    holder addressed.

    `named` collects the facts the question names (PHASE-34 Q1: required, never resting): one whose names the message
    holds. With `named_by_words` (packet-v16, PHASE-36 Q1) a name alone names only how its character stands now or
    with another (NOW, STANDING), a knowledge boundary and a fact of the kind the question asks for (`asked_predicates`);
    any other fact also needs the message's words (overlap at least LEXICAL_BAR). Ranking is unchanged.

    `risky` (the label policies, PHASE-34 Q1): the ids of contradicted facts; with it, a disputed or contradicted fact
    that is not named, private or secret ranks after the others, before `limit` and `events_limit` choose.

    `pinned` (packet-v20, PHASE-60 S8, ADR 0087 item 2): the normalized names of the characters pinned for the request.
    A fact of theirs about how they stand now or with another (NOW, STANDING) is mentioned and named as if the message
    held the name; their other facts are ranked as before. A row carried from another chat (`carried`) is never one.
    `pin_named` collects the facts only a pin named.
    """
    q = _norm(query)
    ai = _norm(previous_ai)
    q_grams = _grams(query)
    first_person = bool(FIRST_PERSON.search(query))
    why = causes and bool(WHY.search(query))
    oldest = first_cue and bool(FIRST_CUE.search(query))
    asked = asked_predicates(query, ontology) if named_by_words else frozenset()
    now = NOW | NOW_V21 if ontology else NOW  # PHASE-66: off, every other policy and chat reads as before
    nouns = asked_nouns(query) if named_by_words else ()
    user = USER_NAMES | persona
    matches: list[dict[str, Any]] = []
    if persona_questions and persona_entity:
        # Classify explicit answers before risk ordering and rest, including already lexical candidates.
        persona_names = ({_norm(n) for n in persona_query_names} if persona_query_names is not None
                         else _widened(list(persona), aliases)) - USER_NAMES
        other_names = {_norm(f[role]) for f in facts for role in ("subject", "object")
                       if f.get(role) and f.get(role + "_type") == "character"
                       and f.get(role + "_entity", {}).get("id") != persona_entity}
        persona_names -= other_names
        questions = _persona_questions(query, persona_names, other_names)
        matches = [f for f in facts if f.get("subject_entity", {}).get("id") == persona_entity
                   and any(f["predicate"] in predicates or any(
                       w in _norm((f.get("object") or "") + " " + (f.get("value") or "")) for w in words)
                           for predicates, words in questions)]
        if named is not None:
            named.update(str(f["id"]) for f in matches)
        extra_limit = max(0, 2 - len(persona_added or ()))
        if matches and extra_limit:
            # Resolve the small question set with the same history, context, rest and event rules.
            # The recursive pass cannot open another persona route. Only its winners gain a mention
            # in the full selection, so a chat with many matching persona facts never gains every slot.
            targets = relevant_facts(matches, query, previous_ai, in_context, min(extra_limit, limit),
                                     events_limit, persona=persona, present=present, causes=causes,
                                     first_cue=first_cue, window_start=window_start, marks=marks, aliases=aliases,
                                     named=named, named_by_words=named_by_words, risky=risky, keep=keep,
                                     _question_facts=frozenset(str(f["id"]) for f in matches), ontology=ontology)
            _question_facts = frozenset(str(f["id"]) for f in targets)
    scored = []
    for f in facts:
        if f["host_logical_id"] in in_context and not f.get("held_off"):  # a lock holds against the story (ADR 0047)
            if not (oldest and window_start is not None and _started_before(f, window_start, in_context, marks)):
                continue
        names = [n for n in _widened(f.get("names") or [f["subject"], f.get("object")], aliases)
                 if len(n) >= 2 and n not in user]
        mention = 2.0 if any(n in q for n in names) else (1.0 if any(n in ai for n in names) else 0.0)
        if _question_facts and str(f["id"]) in _question_facts:
            mention = max(mention, 1.5)
        pin = (bool(pinned) and f["predicate"] in now | STANDING and not f.get("carried")  # another chat's: never
               and any(n in pinned for n in names))
        if pin:  # a pinned character's now and standing facts, as a name in the message brings them
            mention = max(mention, 2.0)
        hidden = [n for n in _widened(f.get("hidden_from") or [], aliases) if len(n) >= 2 and n not in user]
        grams = _grams(fact_text(f) + (f" {f['because']}" if causes and f.get("because") else ""))
        lexical = len(grams & q_grams) / max(1, len(q_grams))
        if named is not None and any(n in q for n in names + hidden) and (  # the question names it (PHASE-34 Q1)
                not named_by_words or f["predicate"] in now | STANDING | asked or f.get("known_by")
                or f.get("hidden_from") or lexical >= LEXICAL_BAR or any(n in fact_text(f) for n in nouns)):
            named.add(str(f["id"]))
        elif pin and named is not None:
            named.add(str(f["id"]))
            if pin_named is not None:
                pin_named.add(str(f["id"]))
        if any(n in q for n in hidden):
            mention += 2.5
        elif mention and any(n in present for n in hidden):
            mention += PRIOR_HIDDEN_PRESENT
        if first_person and (_norm(f["subject"]) in user or _norm(f.get("value")).startswith(tuple(user))):
            mention += 1.0
        score = mention + lexical + (prior(f) if mention else 0.0) + (PRIOR_CAUSE if why and f.get("because") else 0.0)
        if not oldest and f["predicate"] == "event" and f.get("salience") == "minor" and (
                len(_grams(f.get("value") or "") & q_grams) / max(1, len(q_grams)) < LEXICAL_BAR):
            continue  # the query must be about the event itself, not just name its subject
        if mention or lexical >= LEXICAL_BAR:
            scored.append((score, f["position"], f, mention))
    age = (lambda x: -x[1]) if oldest else (lambda x: x[1])  # equal scores: the newer, or the older with the cue

    def plain(f: dict[str, Any]) -> bool:  # not risky (PHASE-34 Q1): a disputed or contradicted line comes after the
        # others, before the limit and the event quota choose (a review's follow-ups); named, private and secret lines
        # keep their place
        return risky is None or not (f.get("disputed_by") or str(f["id"]) in risky) \
            or str(f["id"]) in (named or set()) or bool(f.get("hidden_from") or f.get("known_by"))
    scored.sort(key=lambda x: (plain(x[2]), x[0], age(x)), reverse=True)
    # Rest is decided after `named` is complete, but before the event quota chooses its winners.
    # Preserve the event-specific ordering below (especially the history cue's oldest-first rule).
    if keep is not None:
        scored = [x for x in scored if keep(x[2])]
    if oldest:
        events = sorted((x for x in scored if x[2]["predicate"] == "event"),
                        key=lambda x: (plain(x[2]), x[3] > 0, -x[1], x[2].get("salience") == "major", x[0]),
                        reverse=True)
    else:
        events = sorted((x for x in scored if x[2]["predicate"] == "event"),
                        key=lambda x: (plain(x[2]), x[3], x[2].get("salience") == "major", x[0], x[1]), reverse=True)
    kept_events = {id(x[2]) for x in events[:events_limit]} if events_limit is not None else None
    sit_seen: dict[tuple[str, str], int] = {}
    out: list[dict[str, Any]] = []
    for _, _, f, _ in scored:
        if len(out) >= limit:
            break
        if f["predicate"] == "event" and kept_events is not None and id(f) not in kept_events:
            continue
        if slotted(f["predicate"]) and slot(f)[0] == "situational":  # PHASE-64; PHASE-66 every conditioned predicate
            pair = ((f.get("subject_entity") or {}).get("id") or _norm(f["subject"]),
                    (f.get("object_entity") or {}).get("id") or _norm(f.get("object")))
            if f["predicate"] != "addresses":
                pair = (f["predicate"],) + pair  # addresses keep their PHASE-64 key
            if sit_seen.get(pair, 0) >= SITUATIONAL_ADDRESS_MAX:
                continue
            sit_seen[pair] = sit_seen.get(pair, 0) + 1
        out.append(f)
    if persona_questions and persona_added is not None:
        persona_added.update(str(f["id"]) for f in out if str(f["id"]) in _question_facts)
    return out


def _widened(names: list[Any], aliases: Mapping[str, frozenset[str]] | None) -> set[str]:
    out = {_norm(x) for x in names if x}
    return out | {v for n in out for v in aliases.get(n, ())} if aliases else out


def _scope(f: dict[str, Any]) -> tuple:
    return f.get("knowledge"), sorted(f.get("known_by") or []), sorted(f.get("hidden_from") or [])


def _shown_under(h: dict[str, Any], f: dict[str, Any]) -> bool:
    """Whether an earlier version may be printed in the current version's line, under its knowledge marks (ADR 0038
    amendment 1, K42): not when it was kept from someone (`limited`) and its marks are not the current version's. A
    public or unmarked version under a limited line is treated more narrowly than it was, which leaks nothing."""
    return h.get("knowledge") != "limited" or _scope(h) == _scope(f)


def _started_before(f: dict[str, Any], window_start: int, in_context: set[str], marks: bool = False) -> bool:
    """A standing fact with an earlier version (`_prior`) the prompt does not hold (ADR 0056): one the story stated
    before the window (a position lower than `window_start`, the lowest in context), or a canon statement whose key
    the prompt did not hold (its synthetic position is below every turn; a held one is in the prompt, ADR 0047). The
    packet prints earlier versions under the current row's knowledge marks: with `marks` (ADR 0038 amendment 1) one of
    them must be printed there (`_shown_under`); without, every one of them must have the same marks. Otherwise the
    fact stays out as it would without the cue."""
    before = [h for h in _prior(f) if ("canon:" + h["canon"] not in in_context if h.get("canon")
                                       else h["position"] < window_start)]
    if marks:
        return any(_shown_under(h, f) for h in before)
    return bool(before) and all(_scope(h) == _scope(f) for h in before)


def _prior(f: dict[str, Any]) -> list[dict[str, Any]]:
    """A standing fact's earlier statements of the same predicate with another value, not denials, oldest first."""
    if f["predicate"] not in STANDING:
        return []
    return [h for h in f.get("history") or () if h["position"] < f["position"] and h["predicate"] == f["predicate"]
            and h["polarity"] == "positive" and _norm(h["value"]) != _norm(f.get("value"))]


def _printed(f: dict[str, Any], marks: bool) -> list[dict[str, Any]]:
    prior = _prior(f)
    return [h for h in prior if _shown_under(h, f)] if marks else prior


def earlier(f: dict[str, Any], marks: bool = False) -> dict[str, Any] | None:
    """The version a standing fact replaced (ADR 0038): the latest earlier statement in its history, of the same
    predicate, with another value and not a denial. For a relationship that may be the other direction. With `marks`,
    of those the line may print under its own marks (`_shown_under`, amendment 1)."""
    prior = _printed(f, marks)
    return prior[-1] if prior else None


def first(f: dict[str, Any], marks: bool = False) -> dict[str, Any] | None:
    """How it started, when that differs from what it replaced: the earliest such statement (ADR 0038). "What did she
    call him at first" was answered only by accident before the fold was fixed (M0). `marks` as for `earlier`."""
    prior = _printed(f, marks)
    return prior[0] if len(prior) > 1 and _norm(prior[0]["value"]) != _norm(prior[-1]["value"]) else None


def happened_attr(a: dict[str, Any]) -> str:
    """packet-v20 (PHASE-60 S7, ADR 0086): ` happened="…"` for an assertion that says when it happened, else nothing.
    Always in double quotes (the Note's mark), the value escaped as attribute text."""
    when = a.get("when_happened")
    return f' happened="{escape(when, {chr(34): "&quot;"})}"' if when else ""


def fact_line(f: dict[str, Any], before: bool = False, cause: bool = False, marks: bool = False,
              gone: bool = False, happened: bool = False, body: str | None = None) -> str:
    """One <Fact> with its knowledge marks exactly as stored (D19): knowledge="public", or known_by /
    hidden_from for limited facts, or no mark at all when who knows is unknown. A negated fact is
    explicitly not (or no longer) true (ADR 0013). A disputed fact carries what contradicts it in the same
    line, and neither side is presented as certain (PHASE-6 Q1). With `before` (packet-v5), a standing fact that
    replaced another names it and its turn (ADR 0038); with `cause` (packet-v6), the cause the story states (ADR 0040).
    A canon fact says so in place of a turn, and a fact the owner locked says that (ADR 0047). With `gone` (packet-v20,
    PHASE-60 S3), the status line of a character who is dead or gone is marked so (ADR 0082 item 3). With `happened`
    (packet-v20, PHASE-60 S7), a fact that says when it happened carries it right after its turn. `body`: the line's
    text in place of `fact_text` (a told line, `told_entry`). A carried row (ADR 0085) says where it comes from in
    place of its turn (`_from_attr`)."""
    attrs = f" kind={quoteattr(f['predicate'])}" + _from_attr(f)
    if happened:
        attrs += happened_attr(f)
    if f.get("locked"):
        attrs += ' locked="true"'
    if gone:
        attrs += ' gone="true"'
    if f.get("polarity") == "negative":
        attrs += ' negated="true"'
    if f.get("disputed_by"):
        attrs += ' disputed="true"'
    if f.get("epistemic") == "implied":
        attrs += ' certainty="implied"'
    attrs += _knowledge_attrs(f)
    text = fact_text(f) if body is None else body
    if against := f.get("disputed_by"):
        when = against["turn"] if against.get("turn") is not None else against["position"]
        text += f"; but turn {when}: {fact_text(against)}"
    if cause and f.get("because"):
        text += f"; because: {f['because']}"
    if before and (was := earlier(f, marks)):
        text += f"; before, {_when(was)}: {fact_text(was)}"
        if start := first(f, marks):
            text += f"; first, {_when(start)}: {fact_text(start)}"
    return f"    <Fact{attrs}>{escape(text)}</Fact>"


def _from_attr(f: dict[str, Any]) -> str:
    """Where a fact or thread line comes from, as its attribute: its turn, canon (ADR 0047), a previous timeline (a
    regression line, ADR 0085 item 5), or a chat this one continues (`carried`, item 4). Only packet-v20 reads rows
    carried by a link (PHASE-60 S6)."""
    if f.get("canon"):
        return ' source="canon"'
    if f.get("timeline"):  # a regression line (ADR 0085 item 5): a previous timeline's, which nobody here knows
        return f" timeline={quoteattr(f['timeline'])}"
    if f.get("carried"):
        return ' source="carried"'
    return f" turn=\"{f['turn'] if f.get('turn') is not None else f['position']}\""


def _when(h: dict[str, Any]) -> str:
    """Where a history entry comes from, for a packet line: its turn, canon (ADR 0047), or an earlier chat this one
    continues (ADR 0085)."""
    if h.get("canon"):
        return "in canon"
    if h.get("carried"):
        return "in an earlier chat"
    return f"turn {h['turn'] if h.get('turn') is not None else h['position']}"


def _knowledge_attrs(f: dict[str, Any]) -> str:
    if f.get("knowledge") == "public":
        return ' knowledge="public"'
    attrs = ""
    if f.get("knowledge") == "limited":
        if f.get("known_by"):
            attrs += f" known_by={quoteattr(', '.join(f['known_by']))}"
        if f.get("hidden_from"):
            attrs += f" hidden_from={quoteattr(', '.join(f['hidden_from']))}"
    return attrs


def thread_line(t: dict[str, Any], happened: bool = False) -> str:
    """An open promise (PHASE-7 Q5), with the knowledge marks of the turn that made it; a carried one says so in place
    of its turn (ADR 0085 item 4). With `happened` (packet-v20, PHASE-60 S7), when the assertion that opened it says
    it happens, right after its turn."""
    attrs = f" kind={quoteattr(t['kind'])} by={quoteattr(t['by'])}"
    if t.get("to"):
        attrs += f" to={quoteattr(t['to'])}"
    attrs += _from_attr(t) + (happened_attr(t) if happened else "") + _knowledge_attrs(t)
    return f"    <Thread{attrs}>{escape(t.get('text') or '')}</Thread>"


def settled_line(t: dict[str, Any], happened: bool = False) -> str:
    """packet-v20 (PHASE-60 S4): a thread the story closed, as its open line with how it ended first (`status`, so the
    open kinds' Note marks never match it) and the closing turn after its own; `happened` as for `thread_line`."""
    turn = t["turn"] if t.get("turn") is not None else t["position"]
    attrs = f" status={quoteattr(t['status'])} kind={quoteattr(t['kind'])} by={quoteattr(t['by'])}"
    if t.get("to"):
        attrs += f" to={quoteattr(t['to'])}"
    attrs += (f" turn=\"{turn}\"" + (happened_attr(t) if happened else "")
              + f" closed_turn=\"{t['closed_by']['turn']}\"" + _knowledge_attrs(t))
    return f"    <Thread{attrs}>{escape(t.get('text') or '')}</Thread>"


def claim_line(c: dict[str, Any], marked: bool = False, cause: bool = False) -> str:
    """What a character said (ADR 0013): never a fact, whatever the narration says. `marked` adds who
    knows it (the Private section, ADR 0035); `cause` the cause they give (packet-v6, ADR 0040)."""
    turn = c["turn"] if c.get("turn") is not None else c["position"]
    attrs = f" by={quoteattr(c.get('asserted_by') or '?')} kind={quoteattr(c['predicate'])} turn=\"{turn}\""
    if c.get("polarity") == "negative":
        attrs += ' negated="true"'
    if marked:
        attrs += _knowledge_attrs(c)
    text = fact_text(c) + (f"; because: {c['because']}" if cause and c.get("because") else "")
    return f"    <Claim{attrs}>{escape(text)}</Claim>"


def _marks(f: dict[str, Any]) -> dict[str, Any]:
    """Knowledge marks worth keeping on a ledger line: who a placed secret is kept from (an echo of it in
    the reply may be a leak, K11)."""
    return {"hidden_from": list(f["hidden_from"])} if f.get("knowledge") == "limited" and f.get("hidden_from") else {}


def fact_entry(f: dict[str, Any], private: bool = False, before: bool = False, cause: bool = False,
               marks: bool = False, gone: bool = False, happened: bool = False) -> Line:
    """A fact as a packet line with its provenance (ADR 0027): the assertion, and the words a reply can
    echo (its value, else its object). `private`: only some characters in the scene know it (ADR 0034).
    `before`: name the version a standing fact replaced (packet-v5, ADR 0038); `cause`: the stated cause (ADR 0040);
    `marks`: only versions the line's knowledge marks cover (ADR 0038 amendment 1); `gone`: a gone character's status
    line (packet-v20), marked in its XML and its ledger marks; `happened`: when it happened, in its XML only (packet-v20,
    PHASE-60 S7)."""
    return Line("fact", fact_line(f, before, cause, marks, gone, happened), _ref(f), f.get("turn"), fact_text(f),
                f.get("value") or f.get("object") or "", {**_marks(f), "gone": True} if gone else _marks(f), private)


def told_text(t: dict[str, Any]) -> str:
    """A told row as a line says it (PHASE-60 S8): teller told hearer: what, and whom it is about when it names them."""
    about = [p["name"] for p in t.get("participants") or () if p.get("name")]
    return fact_text(t) + (f"; about: {', '.join(about)}" if about else "")


def told_entry(t: dict[str, Any], private: bool = False, happened: bool = False) -> Line:
    """packet-v20 (PHASE-60 S8, ADR 0086): who told whom as a <Fact kind="told"> line, its knowledge marks as stored, the
    words a reply can echo its value. Ledger kind `fact`, like any fact line."""
    text = told_text(t)
    return Line("fact", fact_line(t, happened=happened, body=text), _ref(t), t.get("turn"), text,
                t.get("value") or "", _marks(t), private)


def claim_entry(c: dict[str, Any], private: bool = False, cause: bool = False) -> Line:
    """A claim as a packet line. It shows no knowledge marks (ADR 0013), except in the Private section
    (packet-v3), where who knows it is the point (ADR 0035). `cause`: the cause they give (packet-v6, ADR 0040)."""
    marks = {"by": c["asserted_by"]} if c.get("asserted_by") else {}
    return Line("claim", claim_line(c, cause=cause), _ref(c), c.get("turn"), fact_text(c),
                c.get("value") or c.get("object") or "", {**marks, **_marks(c)}, private,
                claim_line(c, marked=True, cause=cause) if private else "")


def _ref(a: dict[str, Any]) -> dict[str, Any]:
    """A line's provenance (ADR 0027): its assertion, and the owner's repair that changed it (ADR 0044); a carried
    row's also names its link and the source chat's assertion it was read from (ADR 0085)."""
    ref = {"assertion": a["id"], "repair": a["repair"]} if a.get("repair") else {"assertion": a["id"]}
    if a.get("carried"):
        ref.update(carried=a["carried"], source_assertion=(a.get("carried_from") or {}).get("assertion"))
    return ref


def thread_entry(t: dict[str, Any], private: bool = False, happened: bool = False) -> Line:
    """An open thread's line; `happened` (packet-v20, PHASE-60 S7) changes its XML only."""
    return Line("thread", thread_line(t, happened), _ref(t), t.get("turn"),
                f"{t['by']} → {t.get('to') or '?'}: {t.get('text') or ''}", t.get("text") or "", _marks(t), private)


def settled_entry(t: dict[str, Any], private: bool = False, happened: bool = False) -> Line:
    """A closed thread's line (packet-v20, PHASE-60 S4): ledger kind `thread`, the same assertion as its open line (one
    thread is one line across requests, `overuse.key`), `marks["settled"]` its status. The status is in the text's
    head, so the line never restates a similar promise opened afresh (`packet.restated`). `happened` as for
    `thread_entry`."""
    return Line("thread", settled_line(t, happened), _ref(t), t.get("turn"),
                f"{t['by']} → {t.get('to') or '?'} ({t['status']}): {t.get('text') or ''}", t.get("text") or "",
                {**_marks(t), "settled": t["status"]}, private)
