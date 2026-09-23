"""Fact versions over valid assertions whose extraction matches the head window (D8). Each turn is served
by exactly one extractor generation (ADR 0014): the active one if it has the turn, otherwise the most
recently active earlier generation that does. Discarded extractions (per-chat rebuild, D22) and rows
from before generations existed stay stored for audit only. A turn extraction (ADR 0008) matches its
anchor's turn hash, a per-message one (older generations) the message window hash."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

import psycopg
from xml.sax.saxutils import escape, quoteattr

from .entities import Resolution, resolve
from .predicates import HOLDER_PER_ITEM, REGISTRY

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
SELECT a.id, a.subject, a.subject_type, a.predicate, a.object, a.value, a.epistemic, a.confidence, a.evidence,
       a.knowledge, a.known_by, a.hidden_from, a.polarity, a.modality, a.source, a.asserted_by,
       l.position, l.turn, l.host_logical_id, l.extractor_key AS generation
FROM live l
JOIN assertion a ON a.extraction_id = l.eid
WHERE l.extractor_key = l.chosen AND a.status = 'valid'
ORDER BY l.position, a.id
"""


def _norm(value: str | None) -> str:
    return " ".join((value or "").lower().split())


def _subject(a: dict[str, Any], r: Resolution | None) -> str:
    return r.key(a.get("subject_type"), a["subject"]) if r else _norm(a["subject"])


def _object(a: dict[str, Any], r: Resolution | None) -> str:
    return r.key(a.get("object_type"), a["object"]) if r and a.get("object") else _norm(a["object"])


def version_key(a: dict[str, Any], r: Resolution | None = None) -> tuple:
    """Subject and object are entity ids where the resolver links them (ADR 0012), text otherwise."""
    if a["predicate"] in HOLDER_PER_ITEM:  # one current holder per item (ADR 0011)
        return (a["predicate"], "item", _object(a, r))
    pred = REGISTRY[a["predicate"]]
    if pred.cardinality == "single":
        return (a["predicate"], _subject(a, r)) + ((_object(a, r),) if pred.per_object else ())
    return (a["predicate"], _subject(a, r), _object(a, r), _norm(a["value"]))


def relation(a: dict[str, Any], r: Resolution | None = None) -> tuple:
    """What a negation must match, beyond the version key, to end a version (ADR 0013, item 4): the same
    holder for an item, the same object and value for other single-valued predicates. Multi-valued keys
    already contain everything."""
    if a["predicate"] in HOLDER_PER_ITEM:
        return (_subject(a, r),)
    pred = REGISTRY[a["predicate"]]
    if pred.cardinality == "single":
        return ((_norm(a["value"]),) if pred.per_object else (_object(a, r), _norm(a["value"])))
    return ()


def _versions(history: list[dict[str, Any]], r: Resolution | None = None) -> list[dict[str, Any]]:
    """One version key's facts from its narrated, actual assertions in position order.

    A positive assertion becomes current. A negative one ends the current version only if it denies the
    same relation, and is then current itself (rendered negated); otherwise it stands as its own negative
    fact ("not in the harbor" while at home) until a positive assertion of that relation replaces it.
    """
    current: dict[str, Any] | None = None
    negatives: dict[tuple, dict[str, Any]] = {}
    for a in history:
        rel = relation(a, r)
        if a["polarity"] == "negative" and current is not None and relation(current, r) != rel:
            negatives[rel] = a
            continue
        negatives.pop(rel, None)
        current = a
    out = []
    for fact in ([current] if current else []) + list(negatives.values()):
        f = dict(fact)
        f["versions"] = len(history)
        f["history"] = [{"position": h["position"], "turn": h["turn"], "subject": h["subject"], "value": h["value"],
                         "object": h["object"], "polarity": h["polarity"]} for h in history]
        f["claims"] = []
        out.append(f)
    return out


def memory_view(conn: psycopg.Connection, head: UUID, extractor_key: str | None) -> dict[str, list[dict[str, Any]]]:
    """The head's assertions by what they may do (ADR 0013).

    - facts: current fact versions from actual narration (legacy rows without a source count as
      narration), each with the characters' claims about the same key;
    - claims: the latest claim per speaker and version key, whether or not a narrated fact exists; a claim
      never supersedes narration;
    - other: hypothetical, dreamed and unknown assertions, stored and inspectable, never in the packet;
    - entities / ambiguous: the read-time entity resolution those keys use (ADR 0012). `also_called`
      assertions feed it and are not facts themselves.
    """
    if extractor_key is None:
        return {"facts": [], "claims": [], "other": [], "entities": [], "ambiguous": []}
    rows = [r for r in conn.execute(ACTIVE_ASSERTIONS, {"head": head, "key": extractor_key}).fetchall()
            if r["predicate"] in REGISTRY]
    conv = conn.execute("SELECT conversation_id FROM worldline_commit WHERE id = %s", (head,)).fetchone()
    r = resolve(conv["conversation_id"], rows)
    narrated: dict[tuple, list[dict[str, Any]]] = {}
    claimed: dict[tuple, dict[str, Any]] = {}
    other: list[dict[str, Any]] = []
    for row in rows:
        if row["predicate"] == "also_called":
            continue
        _annotate(row, r)
        if row["modality"] != "actual":
            other.append(row)
        elif row["source"] == "character_claim":
            claimed[version_key(row, r) + (_norm(row["asserted_by"]),)] = row  # latest wins
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
    return {"facts": facts, "claims": claims, "other": other, "entities": r.entities(),
            "ambiguous": r.ambiguous_mentions()}


def _annotate(row: dict[str, Any], r: Resolution) -> None:
    """Entity of subject and object, and every name they go by (recall matches any of them)."""
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
USER_NAMES = {"{{user}}", "{user}", "user", "유저"}


def relevant_facts(facts: list[dict[str, Any]], query: str, previous_ai: str, in_context: set[str],
                   limit: int) -> list[dict[str, Any]]:
    """Facts about entities mentioned now, then lexically related ones; never from in-context sources.

    Knowledge marks count as mentions: a fact hidden from a character who is being addressed is the one
    the model most needs to see (so it does not leak), and "내/my" questions concern the user's facts.
    """
    q = _norm(query)
    ai = _norm(previous_ai)
    q_grams = _grams(query)
    first_person = bool(FIRST_PERSON.search(query))
    scored = []
    for f in facts:
        if f["host_logical_id"] in in_context:
            continue
        names = [n for n in {_norm(x) for x in (f.get("names") or [f["subject"], f.get("object")])} if len(n) >= 2]
        mention = 2.0 if any(n in q for n in names) else (1.0 if any(n in ai for n in names) else 0.0)
        hidden = [_norm(n) for n in f.get("hidden_from") or [] if len(_norm(n)) >= 2]
        known = [_norm(n) for n in f.get("known_by") or [] if len(_norm(n)) >= 2 and _norm(n) not in USER_NAMES]
        if any(n in q for n in hidden):
            mention += 2.5
        elif any(n in q for n in known):
            mention += 1.0
        if first_person and (_norm(f["subject"]) in USER_NAMES or _norm(f.get("value")).startswith(tuple(USER_NAMES))):
            mention += 1.0
        grams = _grams(fact_text(f))
        lexical = len(grams & q_grams) / max(1, len(q_grams))
        score = mention + lexical
        if mention or lexical >= 0.35:
            scored.append((score, f["position"], f))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [f for _, _, f in scored[:limit]]


def fact_line(f: dict[str, Any]) -> str:
    """One <Fact> with its knowledge marks exactly as stored (D19): knowledge="public", or known_by /
    hidden_from for limited facts, or no mark at all when who knows is unknown. A negated fact is
    explicitly not (or no longer) true (ADR 0013)."""
    turn = f["turn"] if f.get("turn") is not None else f["position"]
    attrs = f" kind={quoteattr(f['predicate'])} turn=\"{turn}\""
    if f.get("polarity") == "negative":
        attrs += ' negated="true"'
    if f.get("epistemic") == "implied":
        attrs += ' certainty="implied"'
    if f.get("knowledge") == "public":
        attrs += ' knowledge="public"'
    elif f.get("knowledge") == "limited":
        if f.get("known_by"):
            attrs += f" known_by={quoteattr(', '.join(f['known_by']))}"
        if f.get("hidden_from"):
            attrs += f" hidden_from={quoteattr(', '.join(f['hidden_from']))}"
    return f"    <Fact{attrs}>{escape(fact_text(f))}</Fact>"


def claim_line(c: dict[str, Any]) -> str:
    """What a character said (ADR 0013): never a fact, whatever the narration says."""
    turn = c["turn"] if c.get("turn") is not None else c["position"]
    attrs = f" by={quoteattr(c.get('asserted_by') or '?')} kind={quoteattr(c['predicate'])} turn=\"{turn}\""
    if c.get("polarity") == "negative":
        attrs += ' negated="true"'
    return f"    <Claim{attrs}>{escape(fact_text(c))}</Claim>"
