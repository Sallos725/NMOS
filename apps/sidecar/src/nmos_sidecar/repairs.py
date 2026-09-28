"""Owner repair (PHASE-13, ADR 0044): what the owner says memory got wrong, applied on every read.

A repair is owner input (`owner_repair`, migration 0024), like the owner's name joins (ADR 0025): a rebuild and a new
extractor generation keep it, and nothing here edits an assertion or a message (invariants 1, 2).

A repair names its target by what the target says, not by its assertion id, which a new generation replaces: the turn
it was stated in, that turn's hash (ADR 0008) while the turn reads as it did, its kind and maker, and its text. A read
applies it to the one current item of that turn whose kind and maker match and whose text is closest, at least as
close as a thread match (ADR 0019, `MATCH_MIN`). One that matches nothing does nothing and is reported, so the owner
can see it; an edit of the target's turn makes that happen (as reveals, ADR 0033 amendment 2).

A repair takes effect at a turn (by default the head's last turn when it was made): a read of the head as of an earlier
turn does not apply it, and a read as of an earlier time (ADR 0027 replay) does not see it. Repairs apply in the order
they were made, so a later one wins (a close, then a reopen).

Pure: no database here, except `repairs_of`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg

from .entities import Resolution, norm
from .predicates import OUTCOMES
from .threads import MATCH_MIN, similarity

KINDS = ("thread_close", "thread_reopen", "secret_found_out", "secret_keep", "fact_retract", "fact_correct",
         "name_split")
ENABLED = frozenset({"thread_close", "thread_reopen", "secret_found_out", "secret_keep"})  # Phase 13 step 3
PROMISE_OUTCOMES = ("kept", "broken")


def outcomes(kind: str) -> tuple[str, ...]:
    """The outcomes an owner may close a thread of this kind with (ADR 0019, 0039)."""
    return PROMISE_OUTCOMES if kind == "promise" else OUTCOMES


def default_outcome(kind: str) -> str:
    return {"promise": "kept", "question": "answered", "threat": "averted", "debt": "paid"}.get(kind, "achieved")


def repairs_of(conn: psycopg.Connection, conversation: UUID, known_at: datetime | None = None) -> list[dict[str, Any]]:
    """The owner's repairs in force for a conversation, oldest first; with `known_at`, those in force at that time
    (ADR 0027), as `facts.links_of`."""
    if known_at is None:
        return conn.execute("SELECT id, kind, target, value, note, created_at FROM owner_repair"
                            " WHERE conversation_id = %s AND removed_at IS NULL ORDER BY created_at, id",
                            (conversation,)).fetchall()
    return conn.execute("SELECT id, kind, target, value, note, created_at FROM owner_repair"
                        " WHERE conversation_id = %s AND created_at <= %s AND (removed_at IS NULL OR removed_at > %s)"
                        " ORDER BY created_at, id", (conversation, known_at, known_at)).fetchall()


def _key(r: Resolution | None, name: str | None) -> str:
    return r.key("character", name) if r is not None and name else "text:" + norm(name)


def thread_target(t: dict[str, Any]) -> dict[str, Any]:
    """What a repair stores to find this thread again."""
    return {"turn": t.get("turn"), "turn_hash": t.get("turn_hash"), "kind": t["kind"], "by": t["by"],
            "to": t.get("to"), "text": t.get("text") or ""}


def secret_target(s: dict[str, Any]) -> dict[str, Any]:
    """What a repair stores to find this secret again."""
    return {"turn": s.get("turn"), "turn_hash": s.get("turn_hash"), "holders": list(s.get("holders") or []),
            "text": s["text"]}


def _closest(target: dict[str, Any], items: list[dict[str, Any]], text_of) -> dict[str, Any] | None:
    """The item closest to the target's text, when it reaches MATCH_MIN."""
    scored = sorted(((similarity(target.get("text"), text_of(x)), -x["position"], i) for i, x in enumerate(items)),
                    reverse=True)
    if not scored or scored[0][0] < MATCH_MIN:
        return None
    return items[scored[0][2]]


def _same_turn(target: dict[str, Any], item: dict[str, Any]) -> bool:
    """The item was stated in the target's turn, and that turn reads as it did when the repair was made."""
    if item.get("turn") != target.get("turn"):
        return False
    return target.get("turn_hash") is None or item.get("turn_hash") == target["turn_hash"]


def match_thread(target: dict[str, Any], threads: list[dict[str, Any]], r: Resolution | None) -> dict[str, Any] | None:
    maker = _key(r, target.get("by"))
    pool = [t for t in threads if _same_turn(target, t) and t["kind"] == target.get("kind") and _key(r, t["by"]) == maker]
    return _closest(target, pool, lambda t: t.get("text"))


def match_secret(target: dict[str, Any], secrets: list[dict[str, Any]]) -> dict[str, Any] | None:
    return _closest(target, [s for s in secrets if _same_turn(target, s)], lambda s: s["text"])


def _named(names: list[str] | dict[str, Any], character: str, r: Resolution | None) -> str | None:
    """The name among `names` that is this character (the same entity), as the item spells it."""
    want = _key(r, character)
    return next((n for n in names if _key(r, n) == want), None)


def _takes_effect(repair: dict[str, Any], last_turn: int | None) -> bool:
    turn = (repair.get("value") or {}).get("turn")
    return turn is None or last_turn is None or turn <= last_turn


def apply_secrets(secrets: list[dict[str, Any]], repairs: list[dict[str, Any]], r: Resolution | None,
                  last_turn: int | None) -> dict[str, str | None]:
    """Found out and kept, per character (Q1 item 4), in place; `open` is recomputed. Returns {repair id: the secret
    it applied to, or None}."""
    applied: dict[str, str | None] = {}
    for rep in repairs:
        if rep["kind"] not in ("secret_found_out", "secret_keep"):
            continue
        s = match_secret(rep["target"], secrets)
        value = rep.get("value") or {}
        name = _named(s["kept_from"], value.get("character", ""), r) if s else None
        if s is None or name is None or not _takes_effect(rep, last_turn):
            applied[str(rep["id"])] = None
            continue
        if rep["kind"] == "secret_found_out":
            s["ended"][name] = {"turn": value.get("turn"), "position": None, "subject": name, "owner": str(rep["id"]),
                                "evidence": rep.get("note")}
        else:
            s["ended"].pop(name, None)
        s["repair"] = str(rep["id"])
        s["open"] = [n for n in s["kept_from"] if n not in s["ended"]]
        applied[str(rep["id"])] = str(s["id"])
    return applied


def apply_threads(threads: list[dict[str, Any]], repairs: list[dict[str, Any]], r: Resolution | None,
                  last_turn: int | None) -> dict[str, str | None]:
    """Close with an outcome and reopen (Q1 item 1), in place. Returns {repair id: the thread it applied to, or
    None}."""
    applied: dict[str, str | None] = {}
    for rep in repairs:
        if rep["kind"] not in ("thread_close", "thread_reopen"):
            continue
        t = match_thread(rep["target"], threads, r)
        if t is None or not _takes_effect(rep, last_turn):
            applied[str(rep["id"])] = None
            continue
        value = rep.get("value") or {}
        if rep["kind"] == "thread_close":
            t["status"] = value.get("outcome") or default_outcome(t["kind"])
            t["closed_by"] = {"id": None, "turn": value.get("turn"), "position": None, "subject": t["by"],
                              "predicate": "fulfilled" if t["kind"] == "promise" else "resolved",
                              "value": t["status"], "outcome": t["status"], "owner": str(rep["id"]),
                              "evidence": rep.get("note")}
        else:
            t["status"], t["closed_by"] = "open", None
        t["repair"] = str(rep["id"])
        applied[str(rep["id"])] = str(t["id"])
    return applied


class RepairError(ValueError):
    """A repair that cannot be made now: the message says why (the API answers 422)."""


def plan(kind: str, item: str, view: dict[str, Any], last_turn: int | None, outcome: str | None = None,
         character: str | None = None, turn: int | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """The target and value a new repair stores, for the item the Inspector shows now (a thread's or a secret's id),
    checked against the current memory."""
    if kind not in ENABLED:
        raise RepairError(f"{kind} is not available yet")
    r = view.get("resolution")
    at = last_turn if turn is None else turn
    if kind.startswith("thread_"):
        t = next((t for t in view["threads"] if str(t["id"]) == item), None)
        if t is None:
            raise RepairError("no thread with that id in this chat now")
        if kind == "thread_reopen":
            if t["status"] == "open":
                raise RepairError("the thread is open")
            return thread_target(t), {}
        if t["status"] != "open":
            raise RepairError("the thread is already closed")
        chosen = outcome or default_outcome(t["kind"])
        if chosen not in outcomes(t["kind"]):
            raise RepairError(f"a {t['kind']} closes as one of: {', '.join(outcomes(t['kind']))}")
        if at is None or (t.get("turn") is not None and at < t["turn"]) or (last_turn is not None and at > last_turn):
            raise RepairError("the turn must be between the thread's turn and the chat's last turn")
        return thread_target(t), {"outcome": chosen, "turn": at}
    s = next((s for s in view["secrets"] if str(s["id"]) == item), None)
    if s is None:
        raise RepairError("no secret with that id in this chat now")
    if not character:
        raise RepairError("name the character")
    if kind == "secret_keep":
        name = _named(list(s["ended"]), character, r)
        if name is None:
            raise RepairError("the secret is not over for that character")
        return secret_target(s), {"character": name}
    name = _named(s["open"], character, r)
    if name is None:
        raise RepairError("the secret is not kept from that character now")
    if at is None or (s.get("turn") is not None and at < s["turn"]) or (last_turn is not None and at > last_turn):
        raise RepairError("the turn must be between the secret's turn and the chat's last turn")
    return secret_target(s), {"character": name, "turn": at}
