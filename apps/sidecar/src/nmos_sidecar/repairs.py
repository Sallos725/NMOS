"""Owner repair (PHASE-13, ADR 0044): what the owner says memory got wrong, applied on every read.

A repair is owner input (`owner_repair`, migration 0024), like the owner's name joins (ADR 0025): a rebuild and a new
extractor generation keep it, and nothing here edits an assertion or a message (invariants 1, 2).

A repair names its target by what the target says, not by its assertion id, which a new generation replaces: the turn
it was stated in, that turn's hash (ADR 0008) while the turn reads as it did, its kind and maker, and its text. A read
applies it to the one current item of that turn whose kind and maker match and whose text is closest, at least as
close as a thread match (ADR 0019, `MATCH_MIN`). A new generation words an item its own way but quotes the same
message, so when no item of that turn is close enough, a read takes the one item of that kind and maker, at any turn,
whose quote of the raw text shares at least `QUOTE_MIN_CHARS` characters with the quote the repair stored (ADR 0044
amendment 2). One that matches nothing does nothing and is reported, so the owner can see it; an edit of the target's
turn makes that happen (as reveals, ADR 0033 amendment 2).

A repair takes effect at a turn (by default the head's last turn when it was made): it is an event of the thread or
secret fold after every row of that turn, so what the story says later still counts (PHASE-13 Q4): the same aim stated
again opens a new thread, and a later reveal ends a secret the owner kept. A read of the head as of an earlier turn does
not apply it, and a read as of an earlier time (ADR 0027 replay) does not see it. Repairs of one turn apply in the order
they were made.

Pure: no database here, except `repairs_of`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from functools import lru_cache
from typing import Any
from uuid import UUID

import psycopg

from .entities import Resolution, norm
from .predicates import OUTCOMES, REGISTRY
from .secrets import secret_text
from .threads import MATCH_MIN, similarity

KINDS = ("thread_close", "thread_reopen", "secret_found_out", "secret_keep", "fact_retract", "fact_correct",
         "name_split", "fact_lock")
ENABLED = frozenset(KINDS)  # threads and secrets since step 3, facts and names since step 4, locks since Phase 14
PROMISE_OUTCOMES = ("kept", "broken")
# A quote names the same item when it shares this many characters with the stored one: extract-v14's own minimum for
# a quote (extraction.EVIDENCE_MIN_CHARS); a shorter run is shared by most turns.
QUOTE_MIN_CHARS = 12


def outcomes(kind: str) -> tuple[str, ...]:
    """The outcomes an owner may close a thread of this kind with (ADR 0019, 0039)."""
    return PROMISE_OUTCOMES if kind == "promise" else OUTCOMES


def default_outcome(kind: str) -> str:
    return {"promise": "kept", "question": "answered", "threat": "averted", "debt": "paid"}.get(kind, "achieved")


def repairs_of(conn: psycopg.Connection, conversation: UUID, known_at: datetime | None = None) -> list[dict[str, Any]]:
    """The owner's repairs in force for a conversation, oldest first; with `known_at`, those in force at that time
    (ADR 0027), as `facts.links_of`. (A memory read fetches them with its conversation, in one query: `IN_FORCE`.)"""
    if known_at is None:
        return conn.execute("SELECT id, kind, target, value, note, created_at FROM owner_repair"
                            " WHERE conversation_id = %s AND removed_at IS NULL ORDER BY created_at, id",
                            (conversation,)).fetchall()
    return conn.execute("SELECT id, kind, target, value, note, created_at FROM owner_repair"
                        " WHERE conversation_id = %s AND created_at <= %s AND (removed_at IS NULL OR removed_at > %s)"
                        " ORDER BY created_at, id", (conversation, known_at, known_at)).fetchall()


# A repair `r` in force now, or at `%(at)s` (ADR 0027), for SQL that joins owner_repair.
IN_FORCE = {False: "r.removed_at IS NULL",
            True: "r.created_at <= %(at)s AND (r.removed_at IS NULL OR r.removed_at > %(at)s)"}
REPAIR_COLUMNS = ("id", "kind", "target", "value", "note", "created_at")


def _key(r: Resolution | None, name: str | None) -> str:
    return r.key("character", name) if r is not None and name else "text:" + norm(name)


def thread_target(t: dict[str, Any]) -> dict[str, Any]:
    """What a repair stores to find this thread again."""
    return {"turn": t.get("turn"), "turn_hash": t.get("turn_hash"), "kind": t["kind"], "by": t["by"],
            "to": t.get("to"), "text": t.get("text") or "", "evidence": t.get("evidence")}


def secret_target(s: dict[str, Any], evidence: str | None = None) -> dict[str, Any]:
    """What a repair stores to find this secret again: its head (subject and predicate), text and quote."""
    return {"turn": s.get("turn"), "turn_hash": s.get("turn_hash"), "subject": s.get("subject"),
            "predicate": s.get("predicate"), "object": s.get("object"), "holders": list(s.get("holders") or []),
            "text": s["text"], "evidence": evidence}


def _closest(target: dict[str, Any], items: list[dict[str, Any]], text_of) -> dict[str, Any] | None:
    """The one item closest to the target's text, when it reaches MATCH_MIN; None when two are equally close."""
    scored = sorted(((similarity(target.get("text"), text_of(x)), i) for i, x in enumerate(items)), reverse=True)
    if not scored or scored[0][0] < MATCH_MIN or (len(scored) > 1 and scored[1][0] == scored[0][0]):
        return None
    return items[scored[0][1]]


def _same_turn(target: dict[str, Any], item: dict[str, Any]) -> bool:
    """The item was stated in the target's turn, and that turn reads as it did when the repair was made."""
    if item.get("turn") != target.get("turn"):
        return False
    return target.get("turn_hash") is None or item.get("turn_hash") == target["turn_hash"]


@lru_cache(maxsize=4096)
def _runs(text: str) -> frozenset[str]:
    """Every QUOTE_MIN_CHARS-character run of a normalized quote (a stored quote is compared on every read)."""
    return frozenset(text[i:i + QUOTE_MIN_CHARS] for i in range(len(text) - QUOTE_MIN_CHARS + 1))


def quoted(a: str | None, b: str | None) -> bool:
    """Two quotes of the raw text share a run of at least QUOTE_MIN_CHARS characters (case and spacing aside)."""
    a, b = norm(a), norm(b)
    if len(a) < QUOTE_MIN_CHARS or len(b) < QUOTE_MIN_CHARS:
        return False
    runs = _runs(a)
    return any(b[i:i + QUOTE_MIN_CHARS] in runs for i in range(len(b) - QUOTE_MIN_CHARS + 1))


def _by_quote(target: dict[str, Any], items: list[dict[str, Any]], same: Callable[[dict[str, Any]], bool],
              quote_of: Callable[[dict[str, Any]], str | None]) -> dict[str, Any] | None:
    """The one item of the same head whose quote shares a run with the target's (ADR 0044 amendment 2), at any turn
    but an edited target turn (an edit still makes the repair match nothing there); None without a stored quote or
    when two do."""
    if not target.get("evidence"):
        return None
    hits = [x for x in items if (x.get("turn") != target.get("turn") or _same_turn(target, x)) and same(x)
            and quoted(target["evidence"], quote_of(x))]
    return hits[0] if len(hits) == 1 else None


def match_thread(target: dict[str, Any], threads: list[dict[str, Any]], r: Resolution | None) -> dict[str, Any] | None:
    """The thread a repair names: same kind and maker, the same counterpart for a promise or a debt (as a
    restatement, ADR 0019), and the closest text of its turn, or else the one quote that shares a run with its own."""
    maker = _key(r, target.get("by"))
    to = _key(r, target.get("to")) if target.get("kind") in ("promise", "debt") else None

    def same(t: dict[str, Any]) -> bool:
        return t["kind"] == target.get("kind") and _key(r, t["by"]) == maker and (to is None or _key(r, t.get("to")) == to)
    return (_closest(target, [t for t in threads if _same_turn(target, t) and same(t)], lambda t: t.get("text"))
            or _by_quote(target, threads, same, lambda t: t.get("evidence")))


def match_secret(target: dict[str, Any], secrets: list[dict[str, Any]], r: Resolution | None = None) -> dict[str, Any] | None:
    """The secret a repair names: same head (predicate, subject and object, as entities), and the closest text of its
    turn, or else the one quote that shares a run with its own (the fold's `_evidence`)."""
    subject = _key(r, target.get("subject")) if target.get("subject") else None
    obj = _key(r, target.get("object")) if target.get("object") else None

    def same(s: dict[str, Any]) -> bool:
        return ((target.get("predicate") is None or s.get("predicate") == target["predicate"])
                and (subject is None or _key(r, s.get("subject")) == subject)
                and (obj is None or _key(r, s.get("object")) == obj))
    return (_closest(target, [s for s in secrets if _same_turn(target, s) and same(s)], lambda s: s["text"])
            or _by_quote(target, secrets, same, lambda s: s.get("_evidence")))


def _named(names: list[str] | dict[str, Any], character: str, r: Resolution | None) -> str | None:
    """The name among `names` that is this character (the same entity), as the item spells it."""
    want = _key(r, character)
    return next((n for n in names if _key(r, n) == want), None)


def live(repairs: list[dict[str, Any]], last_turn: int | None) -> list[dict[str, Any]]:
    """The repairs a read of the head up to `last_turn` applies: those whose turn it reaches."""
    def reached(rep: dict[str, Any]) -> bool:
        turn = (rep.get("value") or {}).get("turn")
        return turn is None or last_turn is None or turn <= last_turn
    return [rep for rep in repairs if reached(rep)]


def _at(rep: dict[str, Any]) -> int:
    turn = (rep.get("value") or {}).get("turn")
    return turn if turn is not None else 2**31  # older rows without a turn: after the story


def secret_events(repairs: list[dict[str, Any]], r: Resolution | None, applied: dict[str, str | None]) -> list[Any]:
    """Found out and kept (Q1 item 4) as events of their turn in the secret fold (secrets.fold): a reveal the story
    makes later still ends the secret (Q4). `applied` gets {repair id: the secret it applied to, or None}."""
    def event(rep: dict[str, Any]):
        def run(secrets: list[dict[str, Any]]) -> None:
            s = match_secret(rep["target"], secrets, r)
            name = _named(s["kept_from"], (rep.get("value") or {}).get("character", ""), r) if s else None
            if s is None or name is None:
                return
            if rep["kind"] == "secret_found_out":
                s["ended"].setdefault(name, {"turn": _at(rep), "position": None, "subject": name,
                                             "owner": str(rep["id"]), "evidence": rep.get("note")})
            else:
                s["ended"].pop(name, None)
            s["repair"] = str(rep["id"])
            applied[str(rep["id"])] = str(s["id"])
        return run

    out = []
    for i, rep in enumerate(repairs):
        if rep["kind"] in ("secret_found_out", "secret_keep"):
            applied.setdefault(str(rep["id"]), None)
            out.append((_at(rep), i, event(rep)))
    return out


def thread_events(repairs: list[dict[str, Any]], r: Resolution | None, applied: dict[str, str | None]) -> list[Any]:
    """Close with an outcome and reopen (Q1 item 1) as events of their turn in the thread fold (threads.fold): a
    later turn that opens the same thread again opens a new one, and one that closes a reopened thread closes it
    (Q4). `applied` gets {repair id: the thread it applied to, or None}."""
    def event(rep: dict[str, Any]):
        def run(threads: list[dict[str, Any]]) -> None:
            t = match_thread(rep["target"], threads, r)
            if t is None:
                return
            if rep["kind"] == "thread_close":
                status = (rep.get("value") or {}).get("outcome") or default_outcome(t["kind"])
                t["status"] = status
                t["closed_by"] = {"id": None, "turn": _at(rep), "position": None, "subject": t["by"],
                                  "predicate": "fulfilled" if t["kind"] == "promise" else "resolved", "value": status,
                                  "outcome": status, "owner": str(rep["id"]), "evidence": rep.get("note")}
            else:
                t["status"], t["closed_by"] = "open", None
            t["repair"] = str(rep["id"])
            applied[str(rep["id"])] = str(t["id"])
        return run

    out = []
    for i, rep in enumerate(repairs):
        if rep["kind"] in ("thread_close", "thread_reopen"):
            applied.setdefault(str(rep["id"]), None)
            out.append((_at(rep), i, event(rep)))
    return out


def splits_of(repairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The owner's name splits (K8) as entity resolution takes them, with the links (ADR 0025)."""
    return [{**rep["target"], "id": rep["id"], "created_at": rep.get("created_at")} for rep in repairs
            if rep["kind"] == "name_split"]


def _ekey(r: Resolution | None, entity_type: str | None, name: str | None) -> str | None:
    if not name:
        return None
    return r.key(entity_type, name) if r is not None else "text:" + norm(name)


def fact_target(f: dict[str, Any]) -> dict[str, Any]:
    """What a repair stores to find this fact again: its turn, the turn's hash, its head, its line and its quote."""
    return {"turn": f.get("turn"), "turn_hash": f.get("turn_hash"), "predicate": f["predicate"],
            "source": f.get("source"), "subject": f["subject"], "subject_type": f.get("subject_type"),
            "object": f.get("object"), "object_type": f.get("object_type"), "text": secret_text(f),
            "evidence": f.get("evidence")}


def match_fact(target: dict[str, Any], rows: list[dict[str, Any]], r: Resolution | None) -> dict[str, Any] | None:
    """The assertion a fact repair names: same predicate, source, subject and object (as entities), and the closest
    line of its turn, or else the one quote among `rows` that shares a run with its own."""
    subject = _ekey(r, target.get("subject_type"), target.get("subject"))
    obj = _ekey(r, target.get("object_type"), target.get("object"))
    canon = target.get("turn") == -1  # a canon fact's turn (apply_locks); the story's and canon's never cross

    def same(a: dict[str, Any]) -> bool:
        return (not a.get("owner") and bool(a.get("canon")) == canon and a["predicate"] == target.get("predicate")
                and (a.get("source") or "narration") == (target.get("source") or "narration")
                and _ekey(r, a.get("subject_type"), a["subject"]) == subject
                and _ekey(r, a.get("object_type"), a.get("object")) == obj)
    return (_closest(target, [a for a in rows if _same_turn(target, a) and same(a)], secret_text)
            or _by_quote(target, rows, same, lambda a: a.get("evidence")))


def _owner_id(rep: dict[str, Any]) -> int:
    """An owner's version is not an assertion: a negative id, stable for the repair."""
    return -(UUID(str(rep["id"])).int % 2**62) - 1


ANNOTATIONS = ("subject_entity", "object_entity", "names", "participant_entities")


def apply_facts(rows: list[dict[str, Any]], repairs: list[dict[str, Any]], r: Resolution | None,
                applied: dict[str, str | None], annotate: Callable[[dict[str, Any], Any], None] | None = None,
                turn_positions: dict[int, int] | None = None) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Retract and correct (Q1 items 2 and 3) on the head's assertions, in the order they were made. A retracted
    assertion is left out, so the version before it is current again. A correction is an owner's version of the fact:
    at the fact's own turn, or for a fact that accumulates (a trait, an event), it replaces it in place (same position
    and turn hash, so the turn's other repairs still find it); from a later turn it is a version at the end of that
    turn, which supersedes the fact from there, and a later turn that states the fact again supersedes it (Q4). Its
    entities are resolved again (`annotate`). Returns the new list and {repair id: the retracted assertion}; `applied`
    gets {repair id: the assertion it applied to, or None}."""
    mine = [rep for rep in repairs if rep["kind"] in ("fact_retract", "fact_correct")]
    for rep in mine:
        applied.setdefault(str(rep["id"]), None)
    if not mine:
        return rows, {}
    turns = {rep["target"].get("turn") for rep in mine}
    by_turn: dict[Any, list[dict[str, Any]]] = {}  # the story's rows a repair can name, by turn (one pass, not one a repair)
    for a in rows:
        if a.get("turn") in turns and not a.get("owner"):
            by_turn.setdefault(a.get("turn"), []).append(a)
    gone: set[int] = set()  # rows retracted or replaced, by identity
    swap: dict[int, dict[str, Any]] = {}  # a row replaced in place -> the owner's version
    later: list[dict[str, Any]] = []  # owner's versions from a later turn, in the order made
    retracted: dict[str, dict[str, Any]] = {}
    for rep in mine:
        a = match_fact(rep["target"], [x for x in by_turn.get(rep["target"].get("turn"), ()) if id(x) not in gone], r)
        if a is None and rep["target"].get("evidence"):  # a new generation's fact at another turn, by its quote
            a = match_fact(rep["target"], [x for x in rows if not x.get("owner") and id(x) not in gone], r)
        if a is None:
            continue
        applied[str(rep["id"])] = str(a["id"])
        value = rep.get("value") or {}
        if rep["kind"] == "fact_retract":
            gone.add(id(a))
            retracted[str(rep["id"])] = a
            continue
        own = rep["target"].get("turn", a.get("turn"))  # the fact's turn when the repair was made
        at = value.get("turn", own)
        pred = REGISTRY.get(a["predicate"])
        # at the fact's own turn: in place, at the turn the (maybe new generation's) fact is stated now
        in_place = at == own or (pred is not None and pred.cardinality == "multi")
        new = {k: v for k, v in a.items() if k not in ANNOTATIONS}
        new.update({"id": _owner_id(rep), "host_logical_id": None, "object": value.get("object", a.get("object")),
                    "value": value.get("value", a.get("value")), "source": "narration", "asserted_by": None,
                    "evidence": rep.get("note") or "", "owner": True, "repair": str(rep["id"])})
        if in_place:
            new.update({"turn": a.get("turn"), "turn_hash": a.get("turn_hash"), "position": a["position"]})
            gone.add(id(a))  # replaced; a correction from a later turn keeps the story's version as history
            swap[id(a)] = new
        else:
            position = (turn_positions or {}).get(at)
            if position is None:
                now = [x for x in rows if id(x) not in gone] + list(swap.values()) + later
                position = max((x["position"] for x in now if x.get("turn") is not None and x["turn"] <= at),
                               default=a["position"])
            new.update({"turn": at, "turn_hash": None, "position": position})
            later.append(new)
        if annotate is not None and r is not None:
            annotate(new, r)
    # The result in one pass: a version from a later turn goes after every row of its position (the end of its turn),
    # versions of one position in the order they were made.
    if not later:
        drop = gone - swap.keys()
        return [swap.get(i, x) for x in rows if (i := id(x)) not in drop], retracted
    later.sort(key=lambda x: x["position"])
    out: list[dict[str, Any]] = []
    i = 0
    for x in rows:
        while i < len(later) and later[i]["position"] < x["position"]:
            out.append(later[i])
            i += 1
        if id(x) in swap:
            out.append(swap[id(x)])
        elif id(x) not in gone:
            out.append(x)
    out.extend(later[i:])
    return out, retracted


def apply_locks(rows: list[dict[str, Any]], repairs: list[dict[str, Any]], r: Resolution | None,
                applied: dict[str, str | None]) -> dict[int, str]:
    """The owner's locks (PHASE-14 Q7, ADR 0047) on the rows after retractions and corrections: a canon fact, found by
    what it says as a fact repair finds its target (its turn is -1, its turn hash the canon key), or an owner's
    correction, found by its repair. Returns {id() of the locked row: the lock's id}; `applied` gets {lock id: the
    row's id, or None}."""
    out: dict[int, str] = {}
    for rep in repairs:
        if rep["kind"] != "fact_lock":
            continue
        applied.setdefault(str(rep["id"]), None)
        t = rep["target"] or {}
        if t.get("repair"):
            a = next((x for x in rows if x.get("owner") and str(x.get("repair")) == str(t["repair"])), None)
        else:
            a = match_fact(t, [x for x in rows if x.get("canon")], r)
        if a is None or id(a) in out:
            continue
        out[id(a)] = str(rep["id"])
        applied[str(rep["id"])] = str(a["id"])
    return out


class RepairError(ValueError):
    """A repair that cannot be made now: the message says why (the API answers 422)."""


def plan(kind: str, item: str, view: dict[str, Any], last_turn: int | None, outcome: str | None = None,
         character: str | None = None, turn: int | None = None, new_object: str | None = None,
         new_value: str | None = None, other: str | None = None, entity_type: str = "character",
         version_key: Callable[..., tuple] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """The target and value a new repair stores, for the item the Inspector shows now (a thread's or a secret's id),
    checked against the current memory."""
    if kind not in ENABLED:
        raise RepairError(f"{kind} is not available yet")
    r = view.get("resolution")
    if kind == "name_split":
        return _plan_split(item, other, entity_type, r)
    if kind.startswith("fact_"):
        return _plan_fact(kind, item, view, last_turn, new_object, new_value, turn, version_key)
    at = last_turn if turn is None else turn
    if kind.startswith("thread_"):
        t = next((t for t in view["threads"] if str(t["id"]) == item), None)
        if t is None:
            raise RepairError("no thread with that id in this chat now")
        if kind == "thread_reopen" and t["status"] == "open":
            raise RepairError("the thread is open")
        if kind == "thread_close" and t["status"] != "open":
            raise RepairError("the thread is already closed")
        closed_at = (t.get("closed_by") or {}).get("turn") if kind == "thread_reopen" else None
        _check_turn(at, closed_at if closed_at is not None else t.get("turn"), last_turn, "thread")
        target = thread_target(t)
        if match_thread(target, view["threads"], r) is not t:
            raise RepairError("the thread cannot be told apart from another one of its turn")
        if kind == "thread_reopen":
            return target, {"turn": at}
        chosen = outcome or default_outcome(t["kind"])
        if chosen not in outcomes(t["kind"]):
            raise RepairError(f"a {t['kind']} closes as one of: {', '.join(outcomes(t['kind']))}")
        return target, {"outcome": chosen, "turn": at}
    s = next((s for s in view["secrets"] if str(s["id"]) == item), None)
    if s is None:
        raise RepairError("no secret with that id in this chat now")
    if not character:
        raise RepairError("name the character")
    name = _named(list(s["ended"]) if kind == "secret_keep" else s["open"], character, r)
    if name is None:
        raise RepairError("the secret is not over for that character" if kind == "secret_keep"
                          else "the secret is not kept from that character now")
    revealed_at = s["ended"][name].get("turn") if kind == "secret_keep" else None
    _check_turn(at, revealed_at if revealed_at is not None else s.get("turn"), last_turn, "secret")
    target = secret_target(s, next((a.get("evidence") for a in view.get("assertions") or () if a["id"] == s["id"]), None))
    if match_secret(target, view["secrets"], r) is not s:
        raise RepairError("the secret cannot be told apart from another one of its turn")
    return target, {"character": name, "turn": at}


def _check_turn(at: int | None, since: int | None, last_turn: int | None, what: str) -> None:
    """A repair takes effect from a turn no earlier than what it changes (the item's turn, or the story's close or
    reveal it undoes) and no later than the chat's last turn."""
    if at is None or (since is not None and at < since) or (last_turn is not None and at > last_turn):
        raise RepairError(f"the turn must be between the {what}'s turn (or the story's close or reveal it undoes)"
                          " and the chat's last turn")


def _plan_split(name: str, other: str | None, entity_type: str, r: Resolution | None) -> tuple[dict, dict]:
    if not other:
        raise RepairError("name the other name")
    if r is None or any(r.status(entity_type, n) == "unresolved" for n in (name, other)):
        raise RepairError("both names must be mentioned in this chat")
    if r.node(entity_type, name) == r.node(entity_type, other):
        raise RepairError("the two names are the same")
    a, b = r.entity(entity_type, name), r.entity(entity_type, other)
    if a is None or b is None or a["id"] != b["id"]:
        raise RepairError("the two names are not one entity now")
    return {"entity_type": entity_type, "name": name.strip(), "other": other.strip()}, {}


def _plan_fact(kind: str, item: str, view: dict[str, Any], last_turn: int | None, new_object: str | None,
               new_value: str | None, turn: int | None, version_key: Callable[..., tuple] | None = None) -> tuple[dict, dict]:
    f = next((f for f in view["facts"] if str(f["id"]) == item), None)
    if f is None and kind in ("fact_retract", "fact_lock"):
        # a canon fact the story superseded: the owner keeps the story's (retract) or canon's (lock) (PHASE-14 Q4)
        f = next((a for a in view.get("assertions") or () if a.get("canon") and str(a["id"]) == item), None)
    if f is None:
        raise RepairError("no fact with that id in this chat now")
    r = view.get("resolution")
    if kind == "fact_lock":
        return _plan_lock(f, view, r)
    if f.get("owner"):
        raise RepairError("that is the owner's correction: take the repair back instead")
    target = fact_target(f)
    hit = match_fact(target, view.get("assertions") or view["facts"], r)  # the rows a read matches against
    if hit is None or str(hit["id"]) != item:
        raise RepairError("the fact cannot be told apart from another one of its turn")
    if kind == "fact_retract":
        return target, {}
    pred = REGISTRY.get(f["predicate"])
    if new_object and new_object.strip() and pred is not None and pred.object_types is None:
        raise RepairError(f"a {f['predicate']} fact has no object: correct its value")
    if new_value and new_value.strip() and pred is not None and not pred.needs_value and not f.get("value"):
        raise RepairError(f"a {f['predicate']} fact has no value: correct its object")
    value: dict[str, Any] = {}
    if new_object is not None and new_object.strip() and new_object.strip() != (f.get("object") or ""):
        value["object"] = new_object.strip()
    if new_value is not None and new_value.strip() and new_value.strip() != (f.get("value") or ""):
        value["value"] = new_value.strip()
    if not value:
        raise RepairError("give a new object or value that differs from the fact's")
    at = f.get("turn") if turn is None else turn
    _check_turn(at, f.get("turn"), last_turn, "fact")
    if ("object" in value and at != f.get("turn") and version_key is not None
            and version_key(f, r) != version_key({**f, "object": value["object"]}, r)):
        raise RepairError("from a later turn a new object would leave the old fact current too: correct it at its own"
                          " turn, or retract it")
    return target, {**value, "turn": at}


def _plan_lock(f: dict[str, Any], view: dict[str, Any], r: Resolution | None) -> tuple[dict, dict]:
    """A lock (PHASE-14 Q7): a canon fact or the owner's correction, as a fact (narrated, actual), not locked yet."""
    if not (f.get("canon") or f.get("owner")):
        raise RepairError("only a canon fact or the owner's correction can be locked")
    if f.get("locked"):
        raise RepairError("the fact is locked already")
    if (f.get("source") or "narration") != "narration" or f.get("modality", "actual") != "actual":
        raise RepairError("only a fact can be locked, not a claim or a plan")
    if f.get("owner"):
        return {"repair": str(f["repair"]), "turn": f.get("turn"), "predicate": f["predicate"], "subject": f["subject"],
                "object": f.get("object"), "text": secret_text(f)}, {}
    target = fact_target(f)
    hit = match_fact(target, [a for a in view.get("assertions") or () if a.get("canon")], r)
    if hit is None or str(hit["id"]) != str(f["id"]):
        raise RepairError("the fact cannot be told apart from another one of its canon text")
    return target, {}
