"""Fact versions over valid assertions whose extraction matches the head window (D8). Each turn is served
by exactly one extractor generation (ADR 0014): the active one if it has the turn, otherwise the most
recently active earlier generation that does. Discarded extractions (per-chat rebuild, D22) and rows
from before generations existed stay stored for audit only. A turn extraction (ADR 0008) matches its
anchor's turn hash, a per-message one (older generations) the message window hash."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any
from uuid import UUID

import psycopg
from xml.sax.saxutils import escape, quoteattr

from .entities import USER_NAMES, Resolution, resolve
from .predicates import HOLDER_PER_ITEM, REGISTRY, whereabouts
from .threads import PREDICATES as THREAD_PREDICATES, fold as fold_threads

# `unit` is the turn (a message without one counts alone). `live` holds every extraction that still
# matches the head, and `chosen` the one generation that serves its unit: the active one first, then the
# most recently activated. Rows without a generation (before migration 0008) never qualify. A window
# function, not a self-join: the CTE's row estimate is far too low for a join (a nested loop at 10k).
# The allBefore cut is an uncorrelated scalar subquery, so it runs once (InitPlan). As a joined CTE, a
# head commit without fresh statistics (every edit makes one) let the planner re-run it per row: ≈7 s
# at 10k messages instead of ≈60 ms.
ACTIVE_ASSERTIONS = """
WITH m AS (
    SELECT am.position, am.turn, coalesce(am.turn, -1 - am.position) AS unit, am.source_revision_id AS rid,
           am.window_hash, am.turn_hash, sr.lifecycle, sr.metadata, so.host_logical_id
    FROM active_membership am
    JOIN source_revision sr ON sr.id = am.source_revision_id
    JOIN source_object so ON so.id = sr.source_object_id
    WHERE am.commit_id = %(head)s
),
live AS (
    SELECT e.id AS eid, e.extractor_key, m.position, m.turn, m.host_logical_id,
           first_value(e.extractor_key) OVER (PARTITION BY m.unit
               ORDER BY e.extractor_key = %(key)s DESC, g.activated_at DESC, g.key) AS chosen
    FROM extraction e
    JOIN projection_generation g ON g.key = e.extractor_key
    JOIN m ON m.rid = e.source_revision_id AND e.window_hash IN (m.turn_hash, m.window_hash)
    WHERE e.discarded_at IS NULL AND m.lifecycle = 'accepted'
      AND m.position > (SELECT coalesce(max(position), -1) FROM m WHERE metadata->>'disabled' = 'allBefore')
      AND coalesce(m.metadata->>'disabled', '') NOT IN ('true', 'allBefore')
)
SELECT a.id, a.subject, a.subject_type, a.predicate, a.object, a.object_type, a.value, a.epistemic, a.confidence, a.evidence,
       a.knowledge, a.known_by, a.hidden_from, a.polarity, a.modality, a.source, a.asserted_by, a.salience,
       a.participants::text AS participants,
       l.position, l.turn, l.host_logical_id, l.extractor_key AS generation
FROM live l
JOIN assertion a ON a.extraction_id = l.eid
WHERE l.extractor_key = l.chosen AND a.status = 'valid'
ORDER BY l.position, a.id
"""


def served_assertions(conn: psycopg.Connection, head: UUID, extractor_key: str) -> list[dict[str, Any]]:
    """ACTIVE_ASSERTIONS with participants parsed. They are fetched as text and parsed only where present:
    decoding every jsonb value through the driver cost ≈10 ms per fact read at 10,000 messages
    (docs/perf/phase8-extraction.md)."""
    rows = conn.execute(ACTIVE_ASSERTIONS, {"head": head, "key": extractor_key}).fetchall()
    for r in rows:
        if r["participants"] is not None:
            r["participants"] = _parse_participants(r["participants"])
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
    entries = [{"position": h["position"], "turn": h["turn"], "predicate": h["predicate"], "subject": h["subject"],
                "value": h["value"], "object": h["object"], "polarity": h["polarity"],
                "outcome": outcome.get(id(h), "superseded")} for h in history]
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


def memory_view(conn: psycopg.Connection, head: UUID, extractor_key: str | None) -> dict[str, list[dict[str, Any]]]:
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
    """
    if extractor_key is None:
        return {"facts": [], "claims": [], "other": [], "entities": [], "ambiguous": [], "conflicts": [],
                "items": [], "threads": [], "unmatched": [], "resolution": None}
    rows = [r for r in served_assertions(conn, head, extractor_key) if r["predicate"] in REGISTRY]
    conv = conn.execute("SELECT w.conversation_id, c.host_persona_name FROM worldline_commit w"
                        " JOIN conversation c ON c.id = w.conversation_id WHERE w.id = %s", (head,)).fetchone()
    r = resolve(conv["conversation_id"], rows, persona_of(conv["host_persona_name"]),
                links_of(conn, conv["conversation_id"]))
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
    rows = kept
    threads, unmatched, consumed = fold_threads(promises, r)
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
    other.sort(key=lambda a: a["position"], reverse=True)
    conflicts = [{"fact": f["id"], "turn": f["turn"], "position": f["position"], "text": fact_text(f),
                  "against": f["disputed_by"]} for f in facts if f.get("disputed_by")]
    items: dict[tuple, dict[str, Any]] = {}
    for f in facts:  # one timeline per item, newest first (facts are sorted by position)
        if whereabouts(f):
            items.setdefault(version_key(f, r), {
                "item": f["object"] if f["predicate"] in HOLDER_PER_ITEM else f["subject"],
                "position": f["position"], "history": f["history"]})
    return {"facts": facts, "claims": claims, "other": other, "entities": r.entities(),
            "ambiguous": r.ambiguous_mentions(), "conflicts": conflicts, "items": list(items.values()),
            "threads": threads, "unmatched": unmatched, "resolution": r}


def links_of(conn: psycopg.Connection, conversation: UUID) -> list[dict[str, Any]]:
    """The owner's current entity links of a conversation, oldest first (ADR 0025)."""
    return conn.execute("SELECT id, entity_type, name, same_as, created_at FROM entity_link"
                        " WHERE conversation_id = %s AND removed_at IS NULL ORDER BY created_at, id",
                        (conversation,)).fetchall()


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


def relevant_facts(facts: list[dict[str, Any]], query: str, previous_ai: str, in_context: set[str],
                   limit: int, events_limit: int | None = None,
                   persona: frozenset[str] = frozenset()) -> list[dict[str, Any]]:
    """Facts about entities mentioned now, then lexically related ones; never from in-context sources.

    Knowledge marks count as mentions: a fact hidden from a character who is being addressed is the one
    the model most needs to see (so it does not leak), and "내/my" questions concern the user's facts.

    At most `events_limit` of them are `event` facts (PHASE-7 Q4): events are the most frequent predicate
    and all stay current, so a main character's newest events would otherwise take every slot. Among
    events a `major` one comes before any `minor` or unlabeled one with the same mention score, and a
    `minor` one needs the lexical bar: a name mention alone does not bring it (ADR 0020). Unlabeled
    events (older generations) rank as before.

    The persona's names (`USER_NAMES` and `persona`, the resolver's `persona_names`; ADR 0023) are never
    a mention: the persona is in every chat, and a user who narrates it by name writes that name in every
    message. A first-person question still brings the persona's own facts.
    """
    q = _norm(query)
    ai = _norm(previous_ai)
    q_grams = _grams(query)
    first_person = bool(FIRST_PERSON.search(query))
    user = USER_NAMES | persona
    scored = []
    for f in facts:
        if f["host_logical_id"] in in_context:
            continue
        names = [n for n in {_norm(x) for x in (f.get("names") or [f["subject"], f.get("object")])}
                 if len(n) >= 2 and n not in user]
        mention = 2.0 if any(n in q for n in names) else (1.0 if any(n in ai for n in names) else 0.0)
        hidden = [_norm(n) for n in f.get("hidden_from") or [] if len(_norm(n)) >= 2 and _norm(n) not in user]
        known = [_norm(n) for n in f.get("known_by") or [] if len(_norm(n)) >= 2 and _norm(n) not in user]
        if any(n in q for n in hidden):
            mention += 2.5
        elif any(n in q for n in known):
            mention += 1.0
        if first_person and (_norm(f["subject"]) in user or _norm(f.get("value")).startswith(tuple(user))):
            mention += 1.0
        grams = _grams(fact_text(f))
        lexical = len(grams & q_grams) / max(1, len(q_grams))
        score = mention + lexical
        if f["predicate"] == "event" and f.get("salience") == "minor" and (
                len(_grams(f.get("value") or "") & q_grams) / max(1, len(q_grams)) < LEXICAL_BAR):
            continue  # the query must be about the event itself, not just name its subject
        if mention or lexical >= LEXICAL_BAR:
            scored.append((score, f["position"], f, mention))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    events = sorted((x for x in scored if x[2]["predicate"] == "event"),
                    key=lambda x: (x[3], x[2].get("salience") == "major", x[0], x[1]), reverse=True)
    kept_events = {id(x[2]) for x in events[:events_limit]} if events_limit is not None else None
    out: list[dict[str, Any]] = []
    for _, _, f, _ in scored:
        if len(out) >= limit:
            break
        if f["predicate"] == "event" and kept_events is not None and id(f) not in kept_events:
            continue
        out.append(f)
    return out


def fact_line(f: dict[str, Any]) -> str:
    """One <Fact> with its knowledge marks exactly as stored (D19): knowledge="public", or known_by /
    hidden_from for limited facts, or no mark at all when who knows is unknown. A negated fact is
    explicitly not (or no longer) true (ADR 0013). A disputed fact carries what contradicts it in the same
    line, and neither side is presented as certain (PHASE-6 Q1)."""
    turn = f["turn"] if f.get("turn") is not None else f["position"]
    attrs = f" kind={quoteattr(f['predicate'])} turn=\"{turn}\""
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
    return f"    <Fact{attrs}>{escape(text)}</Fact>"


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


def claim_line(c: dict[str, Any]) -> str:
    """What a character said (ADR 0013): never a fact, whatever the narration says."""
    turn = c["turn"] if c.get("turn") is not None else c["position"]
    attrs = f" by={quoteattr(c.get('asserted_by') or '?')} kind={quoteattr(c['predicate'])} turn=\"{turn}\""
    if c.get("polarity") == "negative":
        attrs += ' negated="true"'
    return f"    <Claim{attrs}>{escape(fact_text(c))}</Claim>"
