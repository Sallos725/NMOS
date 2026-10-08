"""Fact versions over valid assertions whose extraction matches the head window (D8). Each turn is served
by exactly one extractor generation (ADR 0014): the active one if it has the turn, otherwise the most
recently active earlier generation that does. Discarded extractions (per-chat rebuild, D22) and rows
from before generations existed stay stored for audit only. A turn extraction (ADR 0008) matches its
anchor's turn hash, a per-message one (older generations) the message window hash."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime
from functools import lru_cache
from typing import Any
from uuid import UUID

import psycopg
from xml.sax.saxutils import escape, quoteattr

from .entities import USER_NAMES, Resolution, resolve
from .packet import Line
from .predicates import HOLDER_PER_ITEM, REGISTRY, stored_knowledge, whereabouts
from . import canon, canonfacts
from .repairs import (IN_FORCE, REPAIR_COLUMNS, apply_facts, apply_locks, live, quoted_turns, secret_events,
                      splits_of, thread_events, unedited_quotes)
from .secrets import fold as fold_secrets
from .threads import PREDICATES as THREAD_PREDICATES, fold as fold_threads

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
           am.turn_hash, sr.lifecycle, sr.metadata, so.host_logical_id
    FROM active_membership am
    JOIN source_revision sr ON sr.id = am.source_revision_id
    JOIN source_object so ON so.id = sr.source_object_id
    WHERE am.commit_id = %(head)s{upto}
),
live AS (
    SELECT e.id AS eid, e.extractor_key, e.compiler_version, m.position, m.turn, m.host_logical_id, m.turn_hash,
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
       a.participants::text AS participants, a.outcome, a.because,
       -- a check's rows read as the extraction it checked
       l.position, l.turn, l.host_logical_id, l.chosen AS generation, l.chosen_compiler AS compiler,
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


def served_assertions(conn: psycopg.Connection, head: UUID, extractor_key: str, upto: int | None = None,
                      known_at: datetime | None = None) -> list[dict[str, Any]]:
    """ACTIVE_ASSERTIONS with participants parsed. They are fetched as text and parsed only where present:
    decoding every jsonb value through the driver cost ≈10 ms per fact read at 10,000 messages
    (docs/perf/phase8-extraction.md). Knowledge marks stored as a {"name", …} repr read as the name
    (stored_knowledge). With `upto` or `known_at`, the read as of an earlier request."""
    if upto is None and known_at is None:
        rows = conn.execute(ACTIVE_ASSERTIONS, {"head": head, "key": extractor_key}).fetchall()
    else:
        rows = conn.execute(ACTIVE_ASSERTIONS_AS_OF, {
            "head": head, "key": extractor_key, "upto": upto if upto is not None else 2**31 - 1,
            "known_at": known_at}).fetchall()
    for r in rows:
        if r["participants"] is not None:
            r["participants"] = _parse_participants(r["participants"])
        if r["known_by"] or r["hidden_from"]:
            stored_knowledge(r)
    return rows


@lru_cache(maxsize=65536)
def _parse_participants(text: str) -> tuple[dict[str, str], ...]:
    """A stored participant list (rows never change, so every read after the first hits the cache).
    Shared between reads: read-only."""
    return tuple(json.loads(text))


def _norm(value: str | None) -> str:
    return " ".join((value or "").lower().split())


def _subject(a: dict[str, Any], r: Resolution | None) -> str:
    return r.key(a.get("subject_type"), a["subject"]) if r else _norm(a["subject"])


def _object(a: dict[str, Any], r: Resolution | None) -> str:
    return r.key(a.get("object_type"), a["object"]) if r and a.get("object") else _norm(a["object"])


def _item(a: dict[str, Any], r: Resolution | None) -> str:  # possesses: the object; located_in, destroyed: the subject
    return _object(a, r) if a["predicate"] in HOLDER_PER_ITEM else _subject(a, r)


def version_key(a: dict[str, Any], r: Resolution | None = None) -> tuple:
    """Subject and object are entity ids where the resolver links them (ADR 0012), text otherwise."""
    if a["predicate"] == "relationship":  # one history per pair, both directions (ADR 0038)
        return ("relationship",) + tuple(sorted((_subject(a, r), _object(a, r))))
    if whereabouts(a):  # one current holder per item (ADR 0011), one whereabouts with its place (PHASE-6)
        return ("whereabouts", _item(a, r))
    pred = REGISTRY[a["predicate"]]
    if pred.cardinality == "single":
        return (a["predicate"], _subject(a, r)) + ((_object(a, r),) if pred.per_object else ())
    return (a["predicate"], _subject(a, r), _object(a, r), _norm(a["value"]))


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
    pred = REGISTRY[a["predicate"]]
    if pred.cardinality == "single":
        return ((_norm(a["value"]),) if pred.per_object else (_object(a, r), _norm(a["value"])))
    return ()


# Relationships that hold the same both ways (ADR 0038): the head noun of the value, in Korean last, possibly followed
# by 관계/사이; in English any word of it, unless "of" makes it someone else's ("friend of her brother").
SYMMETRIC_KO = ("친구", "연인", "애인", "커플", "부부", "배우자", "형제", "자매", "남매", "쌍둥이", "동급생", "동기",
                "동창", "동료", "라이벌", "경쟁자", "원수", "적", "파트너", "동반자", "룸메이트", "이웃", "약혼자", "사촌",
                "동맹", "팀원", "짝꿍", "단짝", "소꿉친구", "동지")
SYMMETRIC_EN = frozenset({"friend", "friends", "lover", "lovers", "couple", "spouse", "spouses", "married", "sibling",
                          "siblings", "twin", "twins", "classmate", "classmates", "colleague", "colleagues", "coworker",
                          "coworkers", "rival", "rivals", "enemy", "enemies", "partner", "partners", "roommate",
                          "roommates", "neighbor", "neighbors", "cousin", "cousins", "fiance", "fiancee", "engaged",
                          "allies", "ally", "teammate", "teammates"})
_ASIDE = re.compile(r"\([^)]*\)")


def symmetric(value: str | None) -> bool:
    """Whether a relationship value holds the same both ways (ADR 0038)."""
    text = _ASIDE.sub(" ", str(value or "")).strip().casefold()
    words = re.findall(r"[a-z]+", text)
    if words and not re.search(r"[가-힣]", text):
        return "of" not in words and any(w in SYMMETRIC_EN for w in words)
    head = re.sub(r"\s*(관계|사이)$", "", text).strip()
    return bool(head) and "의 " not in head and head.endswith(SYMMETRIC_KO)


def _pair_versions(history: list[dict[str, Any]], r: Resolution | None = None) -> list[dict[str, Any]]:
    """One pair's relationships in position order (ADR 0038). Each direction keeps its latest, as before. A symmetric
    relationship, stated either way, also replaces the other direction's, and a newer one of the other direction
    replaces it. A denial ends the relationship it denies in its direction, or either way when it is symmetric, and
    is current itself (rendered negated); a denial of anything else stands beside, as for every predicate."""
    slots: dict[str, dict[str, Any] | None] = {}  # direction (the subject's key) -> its current row
    negatives: dict[tuple, dict[str, Any]] = {}
    outcome: dict[int, str] = {}

    def close(row: dict[str, Any] | None, how: str) -> None:
        if row is not None:
            outcome.setdefault(id(row), how)

    for a in history:
        d, v = _subject(a, r), _norm(a["value"])
        if a["polarity"] == "negative":
            target = d if slots.get(d) is not None and _norm(slots[d]["value"]) == v else next(
                (o for o, held in slots.items() if o != d and held is not None and _norm(held["value"]) == v
                 and symmetric(held["value"])), None)
            if target is None:
                negatives[(d, v)] = a
                continue
            close(slots[target], "ended")
            slots[target] = a
            continue
        for key in [k for k in negatives if k[1] == v and (k[0] == d or symmetric(a["value"]))]:
            close(negatives.pop(key), "superseded")
        close(slots.get(d), "superseded")
        slots[d] = a
        for o, held in slots.items():
            if o != d and held is not None and (symmetric(a["value"]) or symmetric(held["value"])):
                close(held, "superseded")
                slots[o] = None
    current_rows = [s for s in slots.values() if s is not None] + list(negatives.values())
    for row in current_rows:
        outcome[id(row)] = "current"
    entries = [_entry(h, outcome) for h in history]
    return [{**row, "versions": len(history), "history": entries, "claims": []} for row in current_rows]


def _entry(h: dict[str, Any], outcome: dict[int, str]) -> dict[str, Any]:
    """One history entry of a fact version; a canon statement names its canon key (ADR 0047)."""
    out = {"position": h["position"], "turn": h["turn"], "predicate": h["predicate"], "subject": h["subject"],
           "value": h["value"], "object": h["object"], "polarity": h["polarity"],
           "outcome": outcome.get(id(h), "superseded"), "knowledge": h.get("knowledge"),
           "known_by": h.get("known_by"), "hidden_from": h.get("hidden_from")}
    if h.get("canon"):
        out["canon"] = h["canon"]
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
        return _pair_versions(history, r)
    slots: dict[str, dict[str, Any] | None] = {}
    negatives: dict[tuple, dict[str, Any]] = {}
    disputed_by: dict[str, Any] | None = None
    outcome: dict[int, str] = {}  # id() of a history row -> outcome, for rows that were closed

    def close(row: dict[str, Any] | None, how: str) -> None:
        if row is not None:
            outcome.setdefault(id(row), how)

    for a in history:
        slot = a["predicate"] if whereabouts(a) else ""
        if slot == "destroyed":
            disputed_by = None  # a new end, or a denial of the end, settles the item's existence
        elif slot and a["polarity"] == "positive":
            end = slots.get("destroyed")
            if end is not None and end["polarity"] == "positive" and _unit(end) != _unit(a):
                disputed_by = end
                close(end, "conflicting")
        current = slots.get(slot)
        rel = relation(a, r)
        if a["polarity"] == "negative" and current is not None and relation(current, r) != rel:
            negatives[rel] = a
            continue
        close(negatives.pop(rel, None), "superseded")
        if slot and a["polarity"] == "positive":
            for other, held in list(slots.items()):
                if other != slot and held is not None and _unit(held) != _unit(a):
                    close(held, "ended" if slot == "destroyed" else "superseded")
                    slots[other] = None
        close(current, "ended" if a["polarity"] == "negative" else "superseded")
        slots[slot] = a
    ended = slots.get("destroyed")
    if ended is not None and ended["polarity"] == "positive":
        close(slots.get("possesses"), "ended")
        close(slots.get("located_in"), "ended")
        slots["possesses"] = slots["located_in"] = None
    current_rows = [s for s in slots.values() if s is not None] + list(negatives.values())
    for row in current_rows:
        outcome[id(row)] = "current"
    entries = [_entry(h, outcome) for h in history]
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


LIVE: Any = object()  # `canon_facts` of a live read: decided from the manifest the request names (ADR 0047)


def memory_view(conn: psycopg.Connection, head: UUID, extractor_key: str | None, upto: int | None = None,
                known_at: datetime | None = None, canon_manifest: str | None = None,
                canon_exact: bool = False, canon_key: str | None = None,
                canon_facts: Any = LIVE, what_if: dict[str, Any] | None = None) -> dict[str, list[dict[str, Any]]]:
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
    """
    if extractor_key is None:
        return {"facts": [], "claims": [], "other": [], "entities": [], "ambiguous": [], "conflicts": [],
                "items": [], "threads": [], "unmatched": [], "secrets": [], "unrevealed": [], "repairs": [],
                "assertions": [], "resolution": None}
    rows = [r for r in served_assertions(conn, head, extractor_key, upto, known_at) if r["predicate"] in REGISTRY]
    # The conversation, the owner's repairs as of the read (ADR 0044) and the read's last turn, in one query.
    found = conn.execute(
        "SELECT w.conversation_id, c.host_persona_name, c.canon_manifest_id, r.id, r.kind, r.target, r.value, r.note,"
        " r.created_at,"
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
    last_turn = conv["last_turn"] if repairs else None
    in_force = live(repairs, last_turn)
    # Names from canon (PHASE-14 Q6): the request's own manifest, else the canon in force at the read.
    canon_names, canon_used = (canon.names(conn, conv["conversation_id"], known_at, canon_manifest, canon_exact)
                               if conv["canon_manifest_id"] or canon_manifest else ([], None))
    links = links_of(conn, conv["conversation_id"], known_at)
    if what_if:
        links = [x for x in links if str(x["id"]) not in what_if.get("drop_links", ())] + list(
            what_if.get("add_links", ()))
    r = resolve(conv["conversation_id"], rows, persona_of(conv["host_persona_name"]), links, splits_of(in_force),
                canon_names)
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
    rows = canon_rows + kept
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
    restored_at = sorted({rep["target"].get("turn") for rep in in_force if rep["kind"] == "fact_restore"} - {None})
    turn_info = {x["turn"]: (x["p"], x["h"]) for x in conn.execute(  # PHASE-22 Q7: where a restored fact goes
        "SELECT turn, max(position) AS p, max(turn_hash) AS h FROM active_membership WHERE commit_id = %s"
        " AND turn = ANY(%s) AND (%s::int IS NULL OR position <= %s::int) GROUP BY turn",
        (head, restored_at, upto, upto)).fetchall()} if restored_at else {}
    rows, retracted = apply_facts(rows, in_force, r, applied, _annotate, turn_positions, turn_info)
    locks = apply_locks(rows, in_force, r, applied)  # PHASE-14 Q7
    # Secrets (PHASE-10, ADR 0033): a reveal ends a secret for the character who found it out, from its
    # turn on: its hidden_from drops that name and its known_by gains it (amendment 1: the scene, strict mode
    # and a narrator must count them as knowing it). `learned` is not a fact itself. Before the threads, which copy
    # the marks of the row that opens them: a revealed goal or promise is revealed as a thread too (ADR 0039).
    secrets, unrevealed, reveals = fold_secrets([x for x in rows if not x.get("canon")] if canon_rows else rows, r,
                                                secret_events(in_force, r, applied))
    ended = {s["id"]: set(s["ended"]) for s in secrets if s["ended"]}
    by_repair = {s["id"]: s["repair"] for s in secrets if s.get("repair")}
    for row in rows:
        if row["id"] in by_repair:
            row["repair"] = by_repair[row["id"]]
        if row["id"] in ended:
            row["hidden_from"] = [n for n in row["hidden_from"] if n not in ended[row["id"]]] or None
            row["known_by"] = list(row.get("known_by") or []) + sorted(ended[row["id"]] - set(row.get("known_by") or []))
            row["revealed"] = [{"to": n, **s["ended"][n]} for s in secrets if s["id"] == row["id"] for n in s["ended"]]
    threads, unmatched, consumed = fold_threads(promises, r, thread_events(in_force, r, applied))
    consumed |= reveals
    for row in rows:
        if row["id"] in consumed:
            continue
        if row["source"] == "character_claim" and row["modality"] in ("actual", "unknown"):
            # A claim's truth is unknown by nature; the model may say so (owner decision 2026-09-24).
            claimed[version_key(row, r) + (_norm(row["asserted_by"]),)] = row  # latest wins
        elif row["modality"] != "actual":
            other.append(row)
        else:
            narrated.setdefault(version_key(row, r), []).append(row)
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
    by_key: dict[tuple, list[dict[str, Any]]] = {}
    for f in facts:
        by_key.setdefault(version_key(f, r), []).append(f)
    claims = sorted(claimed.values(), key=lambda c: c["position"], reverse=True)
    for c in claims:
        for f in by_key.get(version_key(c, r), []):
            f["claims"].append({"by": c["asserted_by"], "turn": c["turn"], "position": c["position"],
                                "object": c["object"], "value": c["value"], "polarity": c["polarity"]})
    facts.sort(key=lambda f: f["position"], reverse=True)
    for rid, gone in retracted.items():  # the version a retraction made current again names it (ADR 0044, Q7)
        for f in by_key.get(version_key(gone, r), []):
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
    return {"facts": facts, "claims": claims, "other": other, "entities": r.entities(),
            "ambiguous": r.ambiguous_mentions(), "conflicts": conflicts, "items": list(items.values()),
            "threads": threads, "unmatched": unmatched, "secrets": secrets, "unrevealed": unrevealed,
            "repairs": [_report(rep, applied, r) for rep in repairs], "assertions": rows, "resolution": r,
            "canon_names": canon_used, "canon_facts": len(canon_rows), "canon_facts_manifest": canon_facts}


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
    direction or a symmetric one (ADR 0038); for every other key, any."""
    if locked["predicate"] == "relationship" and a["predicate"] == "relationship":
        return _subject(a, r) == _subject(locked, r) or symmetric(a["value"]) or symmetric(locked["value"])
    return True


def _restates(a: dict[str, Any], b: dict[str, Any], r: Resolution | None) -> bool:
    """Whether two statements say the same: predicate, polarity, value, subject and object (as entities). A
    relationship said either way round is the same when it holds both ways (ADR 0038)."""
    if a["predicate"] != b["predicate"] or a.get("polarity") != b.get("polarity") \
            or _norm(a.get("value")) != _norm(b.get("value")):
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


def _report(rep: dict[str, Any], applied: dict[str, str | None], r: Resolution) -> dict[str, Any]:
    """A repair with what it applies to now (ADR 0044); a name split, the entity it left and the names that still
    join the two when it could not separate them."""
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
    return f"{text}: {f['value']}" if f.get("value") else text


FIRST_PERSON = re.compile(r"(^|\s)(내|나는|나를|나한테|나에게|나의|저는|제가|저를|제|i|my|me|mine)(\s|$|[?,.!])", re.IGNORECASE)
LEXICAL_BAR = 0.35  # trigram overlap with the query that makes an unmentioned fact relevant
# How two characters stand with each other (ADR 0026): one current value per pair, so a scene's cast has
# few of them, and the reply goes wrong without them (a speech level or a form of address forgotten, ADR
# 0028), or a role one holds toward the other (ADR 0059). Read side only, like HOLDER_PER_ITEM: outside REGISTRY, so
# changing it needs no new generation.
STANDING = frozenset({"relationship", "role_toward", "feels_toward", "addresses"})
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


def asked_nouns(query: str) -> tuple[str, ...]:
    """The question's one-syllable Hangul words that can name something (빵, 달): what a short question asks about
    (PHASE-35 Q2; PHASE-36 Q1, amended: a fact holding one is named by its character's name)."""
    return tuple(dict.fromkeys(w for w in re.findall(r"[가-힣]+", query)
                               if len(w) == 1 and w not in FUNCTION_SYLLABLES))


def asked_predicates(query: str) -> frozenset[str]:
    """The predicates the question's own words ask for (ASKS)."""
    return frozenset(p for pattern, preds in ASKS if pattern.search(query) for p in preds)
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


def relevant_facts(facts: list[dict[str, Any]], query: str, previous_ai: str, in_context: set[str],
                   limit: int, events_limit: int | None = None,
                   persona: frozenset[str] = frozenset(), present: frozenset[str] = frozenset(),
                   causes: bool = False, first_cue: bool = False,
                   window_start: int | None = None, marks: bool = False,
                   aliases: Mapping[str, frozenset[str]] | None = None,
                   named: set[str] | None = None, named_by_words: bool = False,
                   risky: frozenset[str] | None = None) -> list[dict[str, Any]]:
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

    The persona's names (`USER_NAMES` and `persona`, the resolver's `persona_names`; ADR 0023) are never
    a mention: the persona is in every chat, and a user who narrates it by name writes that name in every
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
    """
    q = _norm(query)
    ai = _norm(previous_ai)
    q_grams = _grams(query)
    first_person = bool(FIRST_PERSON.search(query))
    why = causes and bool(WHY.search(query))
    oldest = first_cue and bool(FIRST_CUE.search(query))
    asked = asked_predicates(query) if named_by_words else frozenset()
    nouns = asked_nouns(query) if named_by_words else ()
    user = USER_NAMES | persona
    scored = []
    for f in facts:
        if f["host_logical_id"] in in_context and not f.get("held_off"):  # a lock holds against the story (ADR 0047)
            if not (oldest and window_start is not None and _started_before(f, window_start, in_context, marks)):
                continue
        names = [n for n in _widened(f.get("names") or [f["subject"], f.get("object")], aliases)
                 if len(n) >= 2 and n not in user]
        mention = 2.0 if any(n in q for n in names) else (1.0 if any(n in ai for n in names) else 0.0)
        hidden = [n for n in _widened(f.get("hidden_from") or [], aliases) if len(n) >= 2 and n not in user]
        grams = _grams(fact_text(f) + (f" {f['because']}" if causes and f.get("because") else ""))
        lexical = len(grams & q_grams) / max(1, len(q_grams))
        if named is not None and any(n in q for n in names + hidden) and (  # the question names it (PHASE-34 Q1)
                not named_by_words or f["predicate"] in NOW | STANDING | asked or f.get("known_by")
                or f.get("hidden_from") or lexical >= LEXICAL_BAR or any(n in fact_text(f) for n in nouns)):
            named.add(str(f["id"]))
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
    if oldest:
        events = sorted((x for x in scored if x[2]["predicate"] == "event"),
                        key=lambda x: (plain(x[2]), x[3] > 0, -x[1], x[2].get("salience") == "major", x[0]),
                        reverse=True)
    else:
        events = sorted((x for x in scored if x[2]["predicate"] == "event"),
                        key=lambda x: (plain(x[2]), x[3], x[2].get("salience") == "major", x[0], x[1]), reverse=True)
    kept_events = {id(x[2]) for x in events[:events_limit]} if events_limit is not None else None
    out: list[dict[str, Any]] = []
    for _, _, f, _ in scored:
        if len(out) >= limit:
            break
        if f["predicate"] == "event" and kept_events is not None and id(f) not in kept_events:
            continue
        out.append(f)
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


def fact_line(f: dict[str, Any], before: bool = False, cause: bool = False, marks: bool = False) -> str:
    """One <Fact> with its knowledge marks exactly as stored (D19): knowledge="public", or known_by /
    hidden_from for limited facts, or no mark at all when who knows is unknown. A negated fact is
    explicitly not (or no longer) true (ADR 0013). A disputed fact carries what contradicts it in the same
    line, and neither side is presented as certain (PHASE-6 Q1). With `before` (packet-v5), a standing fact that
    replaced another names it and its turn (ADR 0038); with `cause` (packet-v6), the cause the story states (ADR 0040).
    A canon fact says so in place of a turn, and a fact the owner locked says that (ADR 0047)."""
    turn = f["turn"] if f.get("turn") is not None else f["position"]
    attrs = f" kind={quoteattr(f['predicate'])}" + (' source="canon"' if f.get("canon") else f" turn=\"{turn}\"")
    if f.get("locked"):
        attrs += ' locked="true"'
    if f.get("polarity") == "negative":
        attrs += ' negated="true"'
    if f.get("disputed_by"):
        attrs += ' disputed="true"'
    if f.get("epistemic") == "implied":
        attrs += ' certainty="implied"'
    attrs += _knowledge_attrs(f)
    text = fact_text(f)
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


def _when(h: dict[str, Any]) -> str:
    """Where a history entry comes from, for a packet line: its turn, or canon (ADR 0047)."""
    if h.get("canon"):
        return "in canon"
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


def thread_line(t: dict[str, Any]) -> str:
    """An open promise (PHASE-7 Q5), with the knowledge marks of the turn that made it."""
    turn = t["turn"] if t.get("turn") is not None else t["position"]
    attrs = f" kind={quoteattr(t['kind'])} by={quoteattr(t['by'])}"
    if t.get("to"):
        attrs += f" to={quoteattr(t['to'])}"
    attrs += f" turn=\"{turn}\"" + _knowledge_attrs(t)
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
               marks: bool = False) -> Line:
    """A fact as a packet line with its provenance (ADR 0027): the assertion, and the words a reply can
    echo (its value, else its object). `private`: only some characters in the scene know it (ADR 0034).
    `before`: name the version a standing fact replaced (packet-v5, ADR 0038); `cause`: the stated cause (ADR 0040);
    `marks`: only versions the line's knowledge marks cover (ADR 0038 amendment 1)."""
    return Line("fact", fact_line(f, before, cause, marks), _ref(f), f.get("turn"), fact_text(f),
                f.get("value") or f.get("object") or "", _marks(f), private)


def claim_entry(c: dict[str, Any], private: bool = False, cause: bool = False) -> Line:
    """A claim as a packet line. It shows no knowledge marks (ADR 0013), except in the Private section
    (packet-v3), where who knows it is the point (ADR 0035). `cause`: the cause they give (packet-v6, ADR 0040)."""
    marks = {"by": c["asserted_by"]} if c.get("asserted_by") else {}
    return Line("claim", claim_line(c, cause=cause), _ref(c), c.get("turn"), fact_text(c),
                c.get("value") or c.get("object") or "", {**marks, **_marks(c)}, private,
                claim_line(c, marked=True, cause=cause) if private else "")


def _ref(a: dict[str, Any]) -> dict[str, Any]:
    """A line's provenance (ADR 0027): its assertion, and the owner's repair that changed it (ADR 0044)."""
    return {"assertion": a["id"], "repair": a["repair"]} if a.get("repair") else {"assertion": a["id"]}


def thread_entry(t: dict[str, Any], private: bool = False) -> Line:
    return Line("thread", thread_line(t), _ref(t), t.get("turn"),
                f"{t['by']} → {t.get('to') or '?'}: {t.get('text') or ''}", t.get("text") or "", _marks(t), private)
