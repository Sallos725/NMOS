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

from collections.abc import Callable, Mapping
from datetime import datetime
from functools import lru_cache
from typing import Any
from uuid import UUID

import psycopg

from .entities import Resolution, norm
from .predicates import (CONDITIONED_PREDICATES, EXTENSIONS, OUTCOMES, REGISTRY, V21_ONTOLOGY, V21_PREDICATES, Predicate,
                         address_slot, is_address_all)
from .secrets import secret_text
from .statewatch import target as flag_target
from .threads import MATCH_MIN, similarity

KINDS = ("thread_close", "thread_reopen", "secret_found_out", "secret_keep", "fact_retract", "fact_correct",
         "name_split", "fact_lock", "fact_restore", "state_dismiss", "entity_exclude", "entity_pin",
         "fact_add", "told_retract", "fact_hidden", "attention_dismiss")
# threads and secrets since step 3, facts and names since step 4, locks since Phase 14, restores since Phase 22, a
# status flag's dismissal since Phase 39 (Q4: no memory read applies it; the Inspector leaves the flag out), a pin since
# Phase 60 (S8, ADR 0087: stored and listed; the packet's read of it is packet-v20's); since PHASE-67 part 4 (migration
# 0044) a statement the extraction missed (`fact_add`), a told row taken back (`told_retract`; a claim is retracted as a
# fact is, `fact_retract`), a name added to or taken from a fact's hidden_from (`fact_hidden`) and a held role ending or
# alias the owner dismissed from "Needs attention" (`attention_dismiss`). A reader before 0044 ignores these kinds.
ENABLED = frozenset(KINDS)
PROMISE_OUTCOMES = ("kept", "broken")
# A quote names the same item when it shares this many characters with the stored one: extract-v14's own minimum for
# a quote (extraction.EVIDENCE_MIN_CHARS); a shorter run is shared by most turns.
QUOTE_MIN_CHARS = 12


def outcomes(kind: str) -> tuple[str, ...]:
    """The outcomes an owner may close a thread of this kind with (ADR 0019, 0039)."""
    return PROMISE_OUTCOMES if kind == "promise" else OUTCOMES


# The endings the panel offers a thread of each kind, the default first: the extractor's own (`resolved` in
# extraction.py), with "abandoned" for a question or debt that is dropped. `outcomes` still accepts all of them.
OFFERED = {"promise": ("kept", "broken"), "goal": ("achieved", "abandoned", "failed"),
           "question": ("answered", "abandoned"), "threat": ("averted", "failed"), "debt": ("paid", "abandoned")}


def offered(kind: str) -> tuple[str, ...]:
    """The endings the panel offers for closing a thread of this kind, the default first (PHASE-52)."""
    return OFFERED.get(kind) or (default_outcome(kind),) + tuple(o for o in outcomes(kind) if o != default_outcome(kind))


def default_outcome(kind: str) -> str:
    return {"promise": "kept", "question": "answered", "threat": "averted", "debt": "paid"}.get(kind, "achieved")


def repairs_of(conn: psycopg.Connection, conversation: UUID, known_at: datetime | None = None) -> list[dict[str, Any]]:
    """The owner's repairs in force for a conversation, oldest first; with `known_at`, those in force at that time
    (ADR 0027), as `facts.links_of`. (A memory read fetches them with its conversation, in one query: `IN_FORCE`.)"""
    if known_at is None:
        return conn.execute("SELECT id, kind, target, value, note, created_at, anchor, anchored_at FROM owner_repair"
                            " WHERE conversation_id = %s AND removed_at IS NULL ORDER BY created_at, id",
                            (conversation,)).fetchall()
    return conn.execute("SELECT id, kind, target, value, note, created_at, anchor, anchored_at FROM owner_repair"
                        " WHERE conversation_id = %s AND created_at <= %s AND (removed_at IS NULL OR removed_at > %s)"
                        " ORDER BY created_at, id", (conversation, known_at, known_at)).fetchall()


# A repair `r` in force now, or at `%(at)s` (ADR 0027), for SQL that joins owner_repair.
IN_FORCE = {False: "r.removed_at IS NULL",
            True: "r.created_at <= %(at)s AND (r.removed_at IS NULL OR r.removed_at > %(at)s)"}
REPAIR_COLUMNS = ("id", "kind", "target", "value", "note", "created_at", "anchor", "anchored_at")


# --- The anchor (PHASE-67 part 4, audit D7, owner decision 11b) ---------------------------------------------------
#
# A repair is anchored to the message it was made on, not to a turn number. Host message ids (`host_logical_id`, the
# message `chatId`) are unique within a chat, a reroll and a continuation are new messages and a swipe is a new
# revision of the same one (HOST-FACTS Q3), so a message with its revision in the head is on a worldline that holds
# it: no commit ancestry or chain of earlier ids is needed (a rewind is a delete commit, a child of the old head, so
# ancestry cannot tell the continuations apart; a chain of earlier ids would detach repairs next to a deleted message).
#
# - `target`: the target turn's anchor message (its last reply, whose extraction stated the item), its revision (the
#   `source_revision` id: one per message and revision hash) and its own turn's revisions in order (`turn_revisions`;
#   not the K-turn window). The repair applies while that message is in the head with that revision and its turn reads
#   as it did; renumbering and edits of other turns do not matter, an edit of its own turn detaches it exactly as the
#   turn hash did (and its quote with it). Revision ids rather than hashes: a revision hash covers the message id, so a
#   branch's copy of a message has another one, while a branch's prefix copy maps each revision id (`reanchor`).
# - `apply`: the first and last message of the turn it applies from (`value.turn`), matched by id only: the turn is
#   where the first of them is now. A reroll of the turn's reply (a new id) keeps its user message, a typo fix keeps
#   both ids; a new continuation after a rewind has neither, so the repair does not fire there.
#
# A read maps each anchored repair onto the head's numbering (`rebase`): target turn and turn hash, and the apply turn,
# as the head has them now, so every matcher below reads it as a repair made on this head. A repair without an anchor
# (written before migration 0044) keeps the legacy rule; a live read records its anchor the first time it matches the
# head (`legacy_anchors`). A replay as of a time before `anchored_at` reads the legacy target (ADR 0027).

# The kinds whose target names an item of a story turn, and so get a target anchor (a canon or carried target, at
# turn -1, never does); the kinds that take effect from a turn carry an apply anchor when `value.turn` is set.
TARGET_ANCHORED = frozenset({"thread_close", "thread_reopen", "secret_found_out", "secret_keep", "fact_retract",
                             "fact_correct", "fact_restore", "fact_add", "told_retract", "fact_hidden",
                             "attention_dismiss"})


class Members:
    """The head members a set of repairs names: each message by id ((position, turn, revision id)), and each turn's
    members in order with its hash (the anchor's), from `members_of`."""

    def __init__(self, rows: list[Mapping[str, Any]]) -> None:
        self.messages: dict[str, tuple[int, int | None, str]] = {}
        self.turns: dict[int, list[Mapping[str, Any]]] = {}
        self.hashes: dict[int, str | None] = {}
        seen: set[int] = set()
        for x in sorted(rows, key=lambda x: x["position"]):
            if x["position"] in seen:
                continue
            seen.add(x["position"])
            self.messages[x["host_logical_id"]] = (x["position"], x["turn"], str(x["rid"]))
            if x["turn"] is not None:
                self.turns.setdefault(x["turn"], []).append(x)
                if x.get("turn_hash"):
                    self.hashes[x["turn"]] = x["turn_hash"]

    def turn_of(self, message: str | None) -> int | None:
        hit = self.messages.get(message or "")
        return hit[1] if hit else None

    def own(self, turn: int) -> list[str] | None:
        """A turn's own revisions, in order."""
        rows = self.turns.get(turn)
        return [str(x["rid"]) for x in rows] if rows else None

    def target_anchor(self, turn: int | None) -> dict[str, Any] | None:
        """The anchor of an item stated in this turn: its anchor message (the one with the turn's hash, else its last)."""
        rows = self.turns.get(turn) if isinstance(turn, int) and turn >= 0 else None
        if not rows:
            return None
        at = next((x for x in reversed(rows) if x.get("turn_hash")), rows[-1])
        return {"message": at["host_logical_id"], "revision": str(at["rid"]), "turn_revisions": self.own(turn)}

    def message_anchor(self, message: str) -> dict[str, Any] | None:
        """The anchor of an item the owner states on this message (`fact_add`)."""
        hit = self.messages.get(message)
        if hit is None or hit[1] is None:
            return None
        return {"message": message, "revision": hit[2], "turn_revisions": self.own(hit[1])}

    def apply_anchor(self, turn: int | None) -> dict[str, Any] | None:
        rows = self.turns.get(turn) if isinstance(turn, int) else None
        if not rows:
            return None
        return {"messages": list(dict.fromkeys([rows[0]["host_logical_id"], rows[-1]["host_logical_id"]]))}


_MEMBER = ("SELECT am.position, am.turn, am.turn_hash, so.host_logical_id, sr.id AS rid FROM active_membership am"
           " JOIN source_revision sr ON sr.id = am.source_revision_id JOIN source_object so ON so.id = sr.source_object_id")


def members_of(conn: psycopg.Connection, head: UUID, messages: list[str], turns: list[int]) -> Members:
    """The head members of these messages, and every member of these turns and of the turns those messages are in now
    (by index: source_object by (conversation, id), membership by revision, membership by (commit, turn))."""
    rows: list[Mapping[str, Any]] = []
    if messages:
        rows = conn.execute(
            "SELECT am.position, am.turn, am.turn_hash, so.host_logical_id, sr.id AS rid FROM worldline_commit w"
            " JOIN source_object so ON so.conversation_id = w.conversation_id AND so.host_logical_id = ANY(%s)"
            " JOIN source_revision sr ON sr.source_object_id = so.id"
            " JOIN active_membership am ON am.source_revision_id = sr.id AND am.commit_id = w.id WHERE w.id = %s",
            (list(messages), head)).fetchall()
    want = sorted(set(turns) | {x["turn"] for x in rows if x["turn"] is not None})
    if want:
        rows = list(rows) + conn.execute(_MEMBER + " WHERE am.commit_id = %s AND am.turn = ANY(%s)", (head, want)).fetchall()
    return Members(rows)


def _message_ids(repairs: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for rep in repairs:
        a = rep.get("anchor") or {}
        if (t := a.get("target")) and t.get("message"):
            out.append(t["message"])
        out.extend((a.get("apply") or {}).get("messages") or ())
    return sorted(set(out))


def anchored(rep: Mapping[str, Any], known_at: datetime | None = None) -> bool:
    """Whether a read takes this repair by its anchor: it has one, recorded by the read's time (a replay as of an
    earlier time reads the legacy target it had then, ADR 0027)."""
    if not rep.get("anchor"):
        return False
    at = rep.get("anchored_at")
    return known_at is None or at is None or at <= known_at


DETACHED = {"gone": "its message is not in the chat now (deleted, or a continuation the chat left)",
            "edited": "its turn was edited since",
            "turn_gone": "the turn it applies from is not in the chat now (deleted, or a continuation the chat left)"}


def rebase(repairs: list[dict[str, Any]], members: Members, known_at: datetime | None = None) -> list[dict[str, Any]]:
    """Each anchored repair as a repair made on this head (pure): its target's turn and turn hash, and the turn it
    applies from, where its messages are now. One whose message is gone or whose turn was edited is `detached` (the
    reason, `DETACHED`): a read leaves it out and reports it, as a legacy repair that matches nothing. Others as given."""
    out = []
    for rep in repairs:
        if not anchored(rep, known_at):
            out.append(rep)
            continue
        a = rep["anchor"]
        target, value, why = dict(rep.get("target") or {}), dict(rep.get("value") or {}), None
        if t := a.get("target"):
            hit = members.messages.get(t.get("message") or "")
            if hit is None or hit[1] is None:
                why = "gone"
            elif hit[2] != t.get("revision") or (t.get("turn_revisions") and members.own(hit[1]) != t["turn_revisions"]):
                why = "edited"
            else:
                target["turn"], target["turn_hash"] = hit[1], members.hashes.get(hit[1])
        if why is None and (ap := a.get("apply")):
            turn = next((members.turn_of(m) for m in ap.get("messages") or () if members.turn_of(m) is not None), None)
            if turn is None:
                why = "turn_gone"
            else:
                value["turn"] = turn
        out.append({**rep, "target": target, "value": value, **({"detached": why} if why else {})})
    return out


def _legacy_turns(rep: Mapping[str, Any]) -> tuple[int | None, int | None]:
    """A legacy repair's story target turn (None for a canon, carried or nameless target) and its apply turn."""
    t, v = rep.get("target") or {}, rep.get("value") or {}
    turn = t.get("turn") if rep["kind"] in TARGET_ANCHORED and _before_story(t) is None else None
    turn = turn if isinstance(turn, int) and turn >= 0 else None
    at = v.get("turn") if isinstance(v.get("turn"), int) else None
    return turn, at


def anchor_for(kind: str, target: Mapping[str, Any], value: Mapping[str, Any], members: Members,
               message: str | None = None) -> dict[str, Any] | None:
    """The anchor of a repair as it stands on this head (None when it has nothing to anchor): its target's turn (or
    the message the owner named, `message`) and the turn it applies from. A target whose turn no longer reads as it did
    (its stored hash differs from the head's) gets none: it matches nothing, and an anchor must not revive it."""
    out: dict[str, Any] = {}
    turn, at = _legacy_turns({"kind": kind, "target": target, "value": value})
    if message is not None:
        if (ta := members.message_anchor(message)) is None:
            return None
        out["target"] = ta
    elif turn is not None:
        if target.get("turn_hash") is not None and members.hashes.get(turn) != target["turn_hash"]:
            return None
        if (ta := members.target_anchor(turn)) is None:
            return None
        out["target"] = ta
    if at is not None:
        if (ap := members.apply_anchor(at)) is None:
            return None
        out["apply"] = ap
    return out or None


def anchor_turns(kind: str, target: Mapping[str, Any], value: Mapping[str, Any]) -> list[int]:
    """The head turns `anchor_for` reads for a repair."""
    return [x for x in _legacy_turns({"kind": kind, "target": target, "value": value}) if x is not None]


def anchor_now(conn: psycopg.Connection, head: UUID, kind: str, target: Mapping[str, Any],
               value: Mapping[str, Any]) -> dict[str, Any] | None:
    """The anchor a new repair stores, from the head it is made on (`anchor_for`); a `fact_add` is anchored to the
    message the owner named (`target["message"]`)."""
    message = target.get("message") if kind == "fact_add" else None
    turns = anchor_turns(kind, target, value)
    if message is None and not turns:
        return None
    return anchor_for(kind, target, value, members_of(conn, head, [message] if message else [], turns), message)


def legacy_anchors(repairs: list[dict[str, Any]], members: Members) -> dict[str, dict[str, Any]]:
    """{repair id: its anchor} for each repair without one that matches this head now (`anchor_for`): recorded once by
    a live read (`record_anchors`), so it survives the next renumbering."""
    out = {}
    for rep in repairs:
        if rep.get("anchor") or rep.get("detached"):
            continue
        if (a := anchor_for(rep["kind"], rep.get("target") or {}, rep.get("value") or {}, members)) is not None:
            out[str(rep["id"])] = a
    return out


def record_anchors(conn: psycopg.Connection, anchors: Mapping[str, Mapping[str, Any]]) -> int:
    """Record legacy repairs' anchors (one write a repair, only where none is recorded yet; a row another read is
    recording is skipped, never waited for). In a savepoint and failing open: a read that cannot write (a read-only
    transaction) reads as before and a later read records them. Returns how many were recorded."""
    if not anchors:
        return 0
    from psycopg.types.json import Jsonb
    try:
        with conn.transaction():
            return conn.execute(
                "UPDATE owner_repair r SET anchor = v.anchor, anchored_at = now()"
                " FROM jsonb_to_recordset(%s) AS v(id uuid, anchor jsonb)"
                " WHERE r.id = v.id AND r.anchor IS NULL AND r.id IN ("
                "  SELECT id FROM owner_repair WHERE id = ANY(%s::uuid[]) AND anchor IS NULL FOR UPDATE SKIP LOCKED)",
                (Jsonb([{"id": k, "anchor": dict(v)} for k, v in anchors.items()]), list(anchors))).rowcount
    except psycopg.Error:
        return 0


def anchors_needed(repairs: list[dict[str, Any]], legacy: bool) -> tuple[list[str], list[int]]:
    """The message ids and turns a read must look up: every anchored repair's messages, and with `legacy` (a live read
    that may record anchors) every legacy repair's turns."""
    turns: set[int] = set()
    if legacy:
        for rep in repairs:
            if not rep.get("anchor"):
                turns.update(anchor_turns(rep["kind"], rep.get("target") or {}, rep.get("value") or {}))
    return _message_ids(repairs), sorted(turns)


def reanchor(anchor: Mapping[str, Any] | None, mapping: Mapping[str, str]) -> dict[str, Any] | None:
    """An anchor moved onto another chat's messages (a branch the host made, PHASE-67 part 2), pure: `mapping` maps each
    origin message id and revision id (as text) to the branch's message and revision of the same content at the same
    position (`branch.Prefix.remap`, matched against the origin's head now). None when there is no anchor (a legacy
    repair: its legacy target is copied as it is) or the anchor names a message or revision the mapping lacks: outside
    the branch's prefix, or a revision the origin's head no longer shows (the repair is detached there: an edit of its
    turn), so it is not inherited. The apply anchor's first message must map: the turn it applies from begins in the
    prefix, as it does in the origin."""
    if not anchor:
        return None
    out: dict[str, Any] = {}
    if t := anchor.get("target"):
        names = [t.get("message"), t.get("revision"), *(t.get("turn_revisions") or ())]
        if any(x not in mapping for x in names):
            return None
        out["target"] = {**t, "message": mapping[t["message"]], "revision": mapping[t["revision"]],
                         "turn_revisions": [mapping[x] for x in t.get("turn_revisions") or ()]}
    if ap := anchor.get("apply"):
        first = (ap.get("messages") or [None])[0]
        if first not in mapping:
            return None
        out["apply"] = {**ap, "messages": [mapping[m] for m in ap["messages"] if m in mapping]}
    return out or None


# The predicates a read folds (PHASE-66): REGISTRY's, and extract-v21's own for a row of extract-v21. One dict, built
# once: `predicates.registry_for` merges on every call. `believes` and `forgot` are kinds of their own (`EPISTEMIC`), never
# facts about the world; `told` stays out (PHASE-60 S8: its own list).
READ_REGISTRY: dict[str, Predicate] = {**REGISTRY, **{p.name: p for p in V21_ONTOLOGY}}
EPISTEMIC = frozenset({"believes", "forgot"})
_V21_COMPILERS = frozenset(c for c, ext in EXTENSIONS.items() if V21_PREDICATES <= ext.keys())


def is_v21(row: Mapping[str, Any]) -> bool:
    """Whether a row was written by extract-v21 (PHASE-66): its compiler, or its `knowledge_scope`, which extract-v21
    sets on every row and no earlier generation has. The mark survives the rows that are not served: a carried row
    (`carry.FACT_KEYS`), a restored one (`restore_target`) and an owner's correction (a copy of the row)."""
    return row.get("knowledge_scope") is not None or row.get("compiler") in _V21_COMPILERS


def read_predicate(row: Mapping[str, Any]) -> bool:
    """Whether a read folds this row as a fact: a REGISTRY predicate, or one of extract-v21's own (but `believes` and
    `forgot`, `EPISTEMIC`) on an extract-v21 row; a stored row of an earlier generation can never be one."""
    p = row.get("predicate")
    return p in REGISTRY or (p in V21_PREDICATES and p not in EPISTEMIC and is_v21(row))


def epistemic(row: Mapping[str, Any]) -> bool:
    """An extract-v21 `believes` or `forgot` row (PHASE-66): a kind of its own in the view, never a fact."""
    return row.get("predicate") in EPISTEMIC and is_v21(row)


def cardinality(row: Mapping[str, Any]) -> str | None:
    """How a row's facts accumulate: its predicate's cardinality (READ_REGISTRY), but an extract-v21 `role_toward`
    accumulates (PHASE-66: several roles toward one counterpart, each ended by its own denial). None for a predicate
    no read folds."""
    if row.get("predicate") == "role_toward" and is_v21(row):
        return "multi"
    pred = READ_REGISTRY.get(str(row.get("predicate") or ""))
    return pred.cardinality if pred is not None else None


def fungible(row: Mapping[str, Any]) -> bool:
    """An extract-v21 `possesses` of an item one of many alike (`item_kind = fungible`): each holder's own, never
    exclusive (PHASE-66); `unique` or none keeps one holder per item (ADR 0011)."""
    return row.get("predicate") == "possesses" and row.get("item_kind") == "fungible"


def slotted(predicate: str | None) -> bool:
    """Whether a predicate's facts hold in condition slots: `addresses` by its `address_condition` (PHASE-64, ADR
    0091), extract-v21's conditioned predicates by their `condition` (PHASE-66)."""
    return predicate == "addresses" or predicate in CONDITIONED_PREDICATES


def slot(row: Mapping[str, Any]) -> tuple[str, ...]:
    """A row's condition slot: an address's (`predicates.address_slot`), a conditioned predicate's read from its
    `condition` the same way (its scope and `when`; `audience` and `as_guise` ride along), `("default",)` otherwise:
    for a row without a condition, of every earlier generation, every slot is the default one."""
    if row.get("predicate") == "addresses":
        return address_slot(row)
    cond = row.get("condition")
    if row.get("predicate") in CONDITIONED_PREDICATES and isinstance(cond, Mapping):
        return address_slot({"address_condition": cond})
    return ("default",)


def unifies(row: Mapping[str, Any]) -> bool:
    """Whether a row explicitly unifies an earlier split of its slots (`scope="all"`): an address's `address_condition`
    or a conditioned predicate's `condition`."""
    if row.get("predicate") == "addresses":
        return is_address_all(row)
    cond = row.get("condition")
    return row.get("predicate") in CONDITIONED_PREDICATES and isinstance(cond, Mapping) and cond.get("scope") == "all"


def conditional(row: Mapping[str, Any]) -> bool:
    """Whether a row states a condition at all (an `address_condition`, or a conditioned predicate's `condition`)."""
    return bool(row.get("address_condition")) or (row.get("predicate") in CONDITIONED_PREDICATES
                                                   and bool(row.get("condition")))


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


def unedited_quotes(repairs: list[dict[str, Any]], turn_hashes: dict[int, str | None]) -> list[dict[str, Any]]:
    """The repairs a read applies, without the quote of one whose target turn no longer reads as it did (`turn_hashes`:
    the head's hash of each turn a quote names): an edit makes a repair match nothing (item 3), so its quote must not
    find the item at another turn."""
    out = []
    for rep in repairs:
        t = rep.get("target") or {}
        turn = t.get("turn")
        if t.get("evidence") and t.get("turn_hash") and turn is not None and turn >= 0 \
                and turn_hashes.get(turn) != t["turn_hash"]:
            rep = {**rep, "target": {**t, "evidence": None}}
        out.append(rep)
    return out


def quoted_turns(repairs: list[dict[str, Any]]) -> list[int]:
    """The story turns whose hash a read needs for `unedited_quotes`."""
    return sorted({t["turn"] for rep in repairs if (t := rep.get("target") or {}).get("evidence")
                   and t.get("turn") is not None and t["turn"] >= 0})


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
    """What a repair stores to find this fact again: its turn, the turn's hash, its head, its line and its quote; and
    for a fact from before turn 0, whether it is canon's or carried from another chat (both have turn -1); and for a
    conditional address, its condition (PHASE-64)."""
    out = {"turn": f.get("turn"), "turn_hash": f.get("turn_hash"), "predicate": f["predicate"],
           "source": f.get("source"), "subject": f["subject"], "subject_type": f.get("subject_type"),
           "object": f.get("object"), "object_type": f.get("object_type"), "text": secret_text(f),
           "evidence": f.get("evidence"),
           **({"canon": f["canon"]} if f.get("canon") else {}), **({"carried": f["carried"]} if f.get("carried") else {})}
    if f.get("address_condition"):
        out["address_condition"] = f["address_condition"]
    if f.get("condition"):  # PHASE-66: a conditional fact names its slot as an address does
        out["condition"] = f["condition"]
    return out


def _before_story(target: dict[str, Any]) -> str | None:
    """Which facts from before turn 0 a target names: "canon", "carried" (ADR 0085), or None for the story's. A target
    stored before carried facts existed names only its turn (-1): canon's, as it always was (`apply_locks`)."""
    turn_hash = str(target.get("turn_hash") or "")
    if target.get("carried") or turn_hash.startswith(("carried:", "carry:")):
        return "carried"
    if target.get("canon") or turn_hash.startswith("canon:") or target.get("turn") == -1:
        return "canon"
    return None


def match_fact(target: dict[str, Any], rows: list[dict[str, Any]], r: Resolution | None,
               quote: bool = True) -> dict[str, Any] | None:
    """The assertion a fact repair names: same predicate, source, subject and object (as entities), and the closest
    line of its turn, or else the one quote among `rows` that shares a run with its own. The story's, canon's and a
    carried fact never cross."""
    subject = _ekey(r, target.get("subject_type"), target.get("subject"))
    obj = _ekey(r, target.get("object_type"), target.get("object"))
    before = _before_story(target)
    target_slot = slot(target) if slotted(target.get("predicate")) else None

    def where(a: dict[str, Any]) -> str | None:
        return "canon" if a.get("canon") else "carried" if a.get("carried") else None

    def same(a: dict[str, Any]) -> bool:
        return (not a.get("owner") and where(a) == before and a["predicate"] == target.get("predicate")
                and (a.get("source") or "narration") == (target.get("source") or "narration")
                and _ekey(r, a.get("subject_type"), a["subject"]) == subject
                and _ekey(r, a.get("object_type"), a.get("object")) == obj
                and (target_slot is None or slot(a) == target_slot))
    return (_closest(target, [a for a in rows if _same_turn(target, a) and same(a)], secret_text)
            or (_by_quote(target, rows, same, lambda a: a.get("evidence")) if quote else None))


def _established(b: dict[str, Any]) -> bool:
    """A row that states how things stand, as `facts.memory_view` takes facts: narrated (legacy rows without a source
    count as narration) and actual. A character's claim or a plan, a dream or a guess restates no fact (PHASE-22 Q5)."""
    return (b.get("source") or "narration") == "narration" and (b.get("modality") or "actual") == "actual"


# PHASE-22 Q5 level 2 for a predicate that accumulates: two of one character's events (traits, things known) state the
# same one only when their values are this close; any two of them used to.
RESTATE_VALUE_MIN = 0.5


def _restates(level: int, a: dict[str, Any], b: dict[str, Any], r: Resolution | None) -> bool:
    """Whether `b`, a narrated actual row, states the fact `a` again, at one of PHASE-22 Q5's levels, closest first:
    (1) the same predicate, subject and object (as entities) and, for a predicate that accumulates, the same value;
    (2) the same predicate, subject and object and, for a predicate that accumulates, a similar value
    (RESTATE_VALUE_MIN); (3) the same predicate and subject with a quote sharing a run (the object worded otherwise).
    Always with the same polarity: a denial does not state the fact it denies."""
    if a["predicate"] != b["predicate"] or not _established(b) or (
            (a.get("polarity") or "positive") != (b.get("polarity") or "positive")) or (
            _ekey(r, a.get("subject_type"), a["subject"]) != _ekey(r, b.get("subject_type"), b["subject"])):
        return False
    if level == 3:
        return quoted(a.get("evidence"), b.get("evidence"))
    if _ekey(r, a.get("object_type"), a.get("object")) != _ekey(r, b.get("object_type"), b.get("object")):
        return False
    if slotted(a["predicate"]) and slot(a) != slot(b):
        return False
    if cardinality(a) == "single":
        return True
    same = norm(a.get("value")) == norm(b.get("value"))
    return same or (level == 2 and similarity(a.get("value"), b.get("value")) >= RESTATE_VALUE_MIN)


def restated(old: list[dict[str, Any]], new: list[dict[str, Any]], r: Resolution | None) -> dict[int, dict[str, Any]]:
    """PHASE-22 Q5: which facts of a replaced extraction (`old`) the extraction that replaced it (`new`) states again,
    matched one to one (a row of `new` restates at most one fact), closest level first. {index in old: its row in
    new}: a quote shared with another character's fact never counts, and of two belongings one sentence lists only the
    one stated again is."""
    out: dict[int, dict[str, Any]] = {}
    free = list(new)
    for level in (1, 2, 3):
        for i, a in enumerate(old):
            if i in out:
                continue
            b = next((b for b in free if _restates(level, a, b, r)), None)
            if b is not None:
                out[i] = b
                free.remove(b)
    return out


def _owner_id(rep: dict[str, Any]) -> int:
    """An owner's version is not an assertion: a negative id, stable for the repair."""
    return -(UUID(str(rep["id"])).int % 2**62) - 1


ANNOTATIONS = ("subject_entity", "object_entity", "names", "participant_entities")


# The repairs `apply_facts` applies to the head's assertions (PHASE-67 part 4 adds `fact_add` and `fact_hidden`).
FACT_KINDS = ("fact_retract", "fact_correct", "fact_restore", "fact_add", "fact_hidden")


def _apply_hidden(rows: list[dict[str, Any]], reps: list[dict[str, Any]], r: Resolution | None,
                  applied: dict[str, str | None]) -> list[dict[str, Any]]:
    """A name added to or taken from a fact's hidden_from (`fact_hidden`, PHASE-67 part 4), in the order made, on a copy
    of the story's row (same id and position: the turn's other repairs still find it; the row's `repair` names it). A
    name kept from a character makes the fact limited knowledge (a secret: its folds and gates); a name taken back is
    no longer kept from that character. The marks are the owner's; what the story reveals later still ends the secret."""
    out = list(rows)
    for rep in reps:
        t, v = rep.get("target") or {}, rep.get("value") or {}
        found = match_fact(t, [x for x in out if not x.get("owner") and x.get("turn") == t.get("turn")], r, quote=False)
        if found is None and t.get("evidence"):
            found = match_fact(t, [x for x in out if not x.get("owner")], r)
        name = str(v.get("character") or "").strip()
        if found is None or not name:
            continue
        want = _key(r, name)
        hidden = [n for n in found.get("hidden_from") or () if _key(r, n) != want]
        known = [n for n in found.get("known_by") or () if _key(r, n) != want]
        new = {**found, "repair": str(rep["id"])}
        if v.get("hidden"):
            new.update({"hidden_from": hidden + [name], "known_by": known or None, "knowledge": "limited"})
        else:
            new["hidden_from"] = hidden or None
        out[next(i for i, x in enumerate(out) if x is found)] = new
        applied[str(rep["id"])] = str(found["id"])
    return out


def apply_told(rows: list[dict[str, Any]], repairs: list[dict[str, Any]], r: Resolution | None,
               applied: dict[str, str | None]) -> list[dict[str, Any]]:
    """The served `told` rows without those the owner took back (`told_retract`, PHASE-67 part 4), found as a fact
    repair finds its target (its turn, then its quote)."""
    gone: set[int] = set()
    for rep in repairs:
        if rep["kind"] != "told_retract":
            continue
        applied.setdefault(str(rep["id"]), None)
        t = rep.get("target") or {}
        left = [x for x in rows if id(x) not in gone]
        hit = match_fact(t, [x for x in left if x.get("turn") == t.get("turn")], r, quote=False) or (
            match_fact(t, left, r) if t.get("evidence") else None)
        if hit is not None:
            gone.add(id(hit))
            applied[str(rep["id"])] = str(hit["id"])
    return [x for x in rows if id(x) not in gone] if gone else rows


def apply_facts(rows: list[dict[str, Any]], repairs: list[dict[str, Any]], r: Resolution | None,
                applied: dict[str, str | None], annotate: Callable[[dict[str, Any], Any], None] | None = None,
                turn_positions: dict[int, int] | None = None,
                turn_info: dict[int, tuple[int, str | None]] | None = None,
                ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Retract and correct (Q1 items 2 and 3) on the head's assertions, in the order they were made. A retracted
    assertion is left out, so the version before it is current again. A correction is an owner's version of the fact:
    at the fact's own turn, or for a fact that accumulates (a trait, an event), it replaces it in place (same position
    and turn hash, so the turn's other repairs still find it); from a later turn it is a version at the end of that
    turn, which supersedes the fact from there, and a later turn that states the fact again supersedes it (Q4). Its
    entities are resolved again (`annotate`). A restore (PHASE-22 Q7) adds back a fact a re-extraction dropped, as the
    owner's version at the end of its turn (`turn_info`: each restored turn's last position and hash on the head), while
    that turn reads as it did; when the turn's rows state it again, it applies to that row and adds nothing. Returns the
    new list and {repair id: the retracted assertion}; `applied` gets {repair id: the assertion it applied to, or
    None}."""
    mine = [rep for rep in repairs if rep["kind"] in FACT_KINDS]
    for rep in mine:
        applied.setdefault(str(rep["id"]), None)
    if not mine:
        return rows, {}
    if any(rep["kind"] == "fact_hidden" for rep in mine):  # first, so a later correction copies the marks the owner set
        rows = _apply_hidden(rows, [rep for rep in mine if rep["kind"] == "fact_hidden"], r, applied)
        mine = [rep for rep in mine if rep["kind"] != "fact_hidden"]
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
        if rep["kind"] in ("fact_restore", "fact_add"):
            new = _restore(rep, by_turn.get(rep["target"].get("turn"), ()), r, applied, turn_info or {})
            if new is not None:
                later.append(new)
                if annotate is not None and r is not None:
                    annotate(new, r)
            continue
        a = match_fact(rep["target"], [x for x in by_turn.get(rep["target"].get("turn"), ()) if id(x) not in gone], r,
                       quote=False)
        if a is None and rep["target"].get("evidence"):  # by its quote, among every row: a quote names one or none
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
        # at the fact's own turn: in place, at the turn the (maybe new generation's) fact is stated now
        in_place = at == own or cardinality(a) == "multi"
        # PHASE-67 part 4 (D7 item 3): the owner's version states what the correction gives, never the replaced row's
        # feeling detail or stated cause (they may contradict the new object or value): `because` only when given.
        new = {k: v for k, v in a.items() if k not in ANNOTATIONS and k != "feeling"}
        new.update({"id": _owner_id(rep), "host_logical_id": None, "object": value.get("object", a.get("object")),
                    "value": value.get("value", a.get("value")), "because": value.get("because"),
                    "source": "narration", "asserted_by": None,
                    "evidence": rep.get("note") or "", "owner": True, "repair": str(rep["id"])})
        if in_place:
            # at the fact's own turn the version keeps its message (the in-context rule, D3: a misreading corrected is
            # what that message says, sent again only when it is not in context); from a later turn it is the owner's
            # word about a later time, which an earlier message in context does not carry
            new.update({"turn": a.get("turn"), "turn_hash": a.get("turn_hash"), "position": a["position"],
                        "host_logical_id": a.get("host_logical_id")})
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


ONTOLOGY_MARKS = ("condition", "guise", "item_kind", "knowledge_scope")  # extract-v21's (PHASE-66), = facts.ONTOLOGY_MARKS

# A restored fact's columns, as the fact read serves a row (`facts.ACTIVE_ASSERTIONS`) and a restore's target stores them.
RESTORED = ("subject", "subject_type", "predicate", "object", "object_type", "value", "epistemic", "confidence",
            "evidence", "knowledge", "known_by", "hidden_from", "polarity", "modality", "source", "asserted_by",
            "salience", "participants", "outcome", "because")


def restore_target(f: dict[str, Any]) -> dict[str, Any]:
    """What a restore stores (PHASE-22 Q7): the dropped fact as it was (`dropped.find`), its turn and the turn's hash,
    and its line and quote to show it."""
    return {"turn": f["turn"], "turn_hash": f["turn_hash"], "predicate": f["predicate"], "subject": f["subject"],
            "object": f.get("object"), "text": f["text"], "evidence": f.get("evidence"),
            "fact": ({k: f.get(k) for k in RESTORED}
                     | ({"feeling": f["feeling"]} if f.get("feeling") else {})
                     | ({"when_happened": f["when_happened"]} if f.get("when_happened") else {})
                     | ({"address_condition": f["address_condition"]} if f.get("address_condition") else {})
                     | {k: f[k] for k in ONTOLOGY_MARKS if f.get(k)})}


def _restore(rep: dict[str, Any], turn_rows: Any, r: Resolution | None, applied: dict[str, str | None],
             turn_info: dict[int, tuple[int, str | None]]) -> dict[str, Any] | None:
    """The owner's version a restore adds, or None: its turn edited or gone (applies to nothing), or stated again by
    the turn's rows now (applies to that row)."""
    t = rep["target"] or {}
    fact = t.get("fact") or {}
    at = turn_info.get(t.get("turn"))
    if at is None or at[1] != t.get("turn_hash") or not fact.get("predicate"):
        return None
    again = next((b for level in (1, 2, 3) for b in turn_rows if not b.get("owner") and _restates(level, fact, b, r)),
                 None)
    if again is not None:
        applied[str(rep["id"])] = str(again["id"])
        return None
    new = {k: fact.get(k) for k in RESTORED}
    new["participants"] = tuple(fact["participants"]) if fact.get("participants") else None
    if fact.get("feeling"):  # PHASE-58: a restored feeling keeps how it felt
        new["feeling"] = fact["feeling"]
    if fact.get("when_happened"):  # PHASE-60 S7: a restored event or promise keeps when it happened
        new["when_happened"] = fact["when_happened"]
    if fact.get("address_condition"):  # PHASE-64: a restored conditional address keeps its condition
        new["address_condition"] = fact["address_condition"]
    for k in ONTOLOGY_MARKS:  # PHASE-66: a restored extract-v21 fact keeps its marks (and so reads as v21's)
        if fact.get(k):
            new[k] = fact[k]
    new.update({"id": _owner_id(rep), "turn": t["turn"], "turn_hash": t["turn_hash"], "position": at[0],
                # a statement the owner adds keeps the message it names (the in-context rule, D3)
                "host_logical_id": t.get("message") if rep["kind"] == "fact_add" else None,
                "generation": None, "compiler": None, "listed_hash": None,
                "source": "narration", "owner": True, "repair": str(rep["id"])})
    applied[str(rep["id"])] = str(new["id"])
    return new


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
         version_key: Callable[..., tuple] | None = None, scope: str = "cast", new_because: str | None = None,
         fact: Mapping[str, Any] | None = None, hidden: bool | None = None,
         attention: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """The target and value a new repair stores, for the item the Inspector shows now (a thread's or a secret's id),
    checked against the current memory."""
    if kind not in ENABLED:
        raise RepairError(f"{kind} is not available yet")
    r = view.get("resolution")
    if kind == "name_split":
        return _plan_split(item, other, entity_type, r)
    if kind == "entity_exclude":
        return _plan_exclude(item, entity_type, scope, view)
    if kind == "entity_pin":
        return _plan_pin(item, entity_type, view)
    if kind == "state_dismiss":  # the caller lists the chat's undismissed status flags (`state_flags`, PHASE-39 Q4)
        flag = next((f for f in view.get("state_flags") or () if f["id"] == item), None)
        if flag is None:
            raise RepairError("no status flag with that id in this chat now")
        return flag_target(flag), {}
    if kind == "fact_restore":  # the caller lists the dropped facts and held role endings (`dropped`, `endings.held`)
        f = next((d for d in view.get("dropped") or () if str(d["id"]) == item), None)
        if f is None:
            raise RepairError("no fact a re-extraction dropped, or role ending held, with that id in this chat now")
        return restore_target(f), {}
    if kind == "fact_add":  # the caller names the message's turn and hash (`view["messages"]`)
        return _plan_add(item, fact or {}, view)
    if kind == "told_retract":  # the caller reads the view with who told whom (`view["told"]`)
        return _plan_told(item, view)
    if kind == "fact_hidden":
        return _plan_hidden(item, character, hidden, view)
    if kind == "attention_dismiss":  # the caller lists what needs a look and is not dismissed (`view["attention"]`)
        return _plan_dismiss(item, attention, view)
    if kind.startswith("fact_"):
        return _plan_fact(kind, item, view, last_turn, new_object, new_value, turn, version_key, new_because)
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


def _plan_add(message: str, fact: Mapping[str, Any], view: dict[str, Any]) -> tuple[dict, dict]:
    """A statement the extraction missed (`fact_add`, PHASE-67 part 4), on a message of the head the owner names: a
    REGISTRY predicate (not a name join: that is a link) validated as the extractor's output is (`predicates.validate`),
    narrated, actual and positive, with the knowledge marks the owner gives (a name kept from someone makes it limited
    knowledge). Read as a restored fact is: the owner's version at the end of the message's turn while the turn reads as
    it did, and nothing once the turn's rows state it."""
    from .predicates import validate
    at = (view.get("messages") or {}).get(message)
    if at is None or at[0] is None or at[0] < 0:
        raise RepairError("no message with that id in this chat now")
    turn, turn_hash = at
    names = lambda k: [n.strip() for n in fact.get(k) or () if str(n).strip()] or None  # noqa: E731
    row: dict[str, Any] = {k: None for k in RESTORED}
    row.update({"subject": str(fact.get("subject") or "").strip(), "subject_type": fact.get("subject_type") or "character",
                "predicate": str(fact.get("predicate") or ""), "object": str(fact.get("object") or "").strip() or None,
                "object_type": fact.get("object_type"), "value": str(fact.get("value") or "").strip() or None,
                "known_by": names("known_by"), "hidden_from": names("hidden_from"), "polarity": "positive",
                "modality": "actual", "source": "narration", "evidence": ""})
    row["knowledge"] = "limited" if row["hidden_from"] else "public"
    if row["predicate"] not in REGISTRY or row["predicate"] == "also_called":
        raise RepairError("the predicate is not one memory states (two names of one character are joined, not added)")
    status, reason = validate(row)
    if status != "valid":
        raise RepairError(f"the statement is not complete: {reason}")
    r = view.get("resolution")
    if any(b.get("turn") == turn and not b.get("owner") and _restates(1, row, b, r) for b in view.get("assertions") or ()):
        raise RepairError("the chat's memory states that already at that turn")
    return {"turn": turn, "turn_hash": turn_hash, "message": message, "predicate": row["predicate"],
            "subject": row["subject"], "object": row["object"], "text": secret_text(row), "evidence": None,
            "fact": row}, {}


def _plan_told(item: str, view: dict[str, Any]) -> tuple[dict, dict]:
    """A told row taken back (`told_retract`, PHASE-67 part 4): one of the view's who-told-whom rows, by id."""
    t = next((x for x in view.get("told") or () if str(x["id"]) == item), None)
    if t is None:
        raise RepairError("no told row with that id in this chat now")
    if t.get("carried") or t.get("canon"):
        raise RepairError("only a told row of this chat's story is taken back")
    target = fact_target(t)
    if match_fact(target, view["told"], view.get("resolution")) is not t:
        raise RepairError("the told row cannot be told apart from another one of its turn")
    return target, {}


def _plan_hidden(item: str, character: str | None, hidden: bool | None, view: dict[str, Any]) -> tuple[dict, dict]:
    """A name added to (`hidden`) or taken from a fact's hidden_from (`fact_hidden`, PHASE-67 part 4): a fact of the
    story (not canon's, a carried one or the owner's correction), at its own turn."""
    f = next((x for x in view["facts"] if str(x["id"]) == item), None)
    if f is None:
        raise RepairError("no fact with that id in this chat now")
    if f.get("owner") or f.get("canon") or f.get("carried"):
        raise RepairError("only a fact of this chat's story is marked: correct the owner's version, or take it back")
    if hidden is None:
        raise RepairError("say whether the fact is kept from the character")
    name = (character or "").strip()
    if not name:
        raise RepairError("name the character")
    r = view.get("resolution")
    kept = any(_key(r, n) == _key(r, name) for n in f.get("hidden_from") or ())
    if hidden and (kept or _key(r, name) == _key(r, f.get("subject"))):
        raise RepairError("the fact is kept from that character already, or is about them")
    if not hidden and not kept:
        raise RepairError("the fact is not kept from that character now")
    target = fact_target(f)
    hit = match_fact(target, view.get("assertions") or view["facts"], r)
    if hit is None or str(hit["id"]) != item:
        raise RepairError("the fact cannot be told apart from another one of its turn")
    return target, {"character": name, "hidden": bool(hidden)}


ATTENTION = ("role_held", "alias_held")  # what "Needs attention" asks the owner to confirm, and a dismissal names


def attention_target(what: str, a: Mapping[str, Any]) -> dict[str, Any]:
    """What a dismissal stores to find a held role ending or alias again: its turn, the turn's hash and its head."""
    return {"what": what, "turn": a.get("turn"), "turn_hash": a.get("turn_hash"), "predicate": a.get("predicate"),
            "subject": a.get("subject"), "subject_type": a.get("subject_type"), "object": a.get("object"),
            "object_type": a.get("object_type"), "value": a.get("value"), "text": secret_text(dict(a))}


def _plan_dismiss(item: str, what: str | None, view: dict[str, Any]) -> tuple[dict, dict]:
    """A held role ending or alias the owner dismissed (`attention_dismiss`, PHASE-67 part 4): no longer listed under
    "Needs attention"; the memory is as it is (a held ending can still be restored, a held alias's names still linked)."""
    if what not in ATTENTION:
        raise RepairError("say what is dismissed: role_held or alias_held")
    a = next((x for x in (view.get("attention") or {}).get(what) or () if str(x["id"]) == item), None)
    if a is None:
        raise RepairError("nothing held with that id needs a look in this chat now")
    return attention_target(what, a), {}


def undismissed(items: list[dict[str, Any]], repairs: list[dict[str, Any]], what: str,
                r: Resolution | None) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """`items` (held role endings or aliases, `what`) without those a dismissal in force names (its turn as the read
    rebased it, its head by entity), and {dismissal id: the row it applies to}."""
    mine = [rep for rep in repairs if rep["kind"] == "attention_dismiss" and not rep.get("detached")
            and not rep.get("removed_at") and (rep.get("target") or {}).get("what") == what]
    if not mine:
        return items, {}

    def same(t: Mapping[str, Any], a: Mapping[str, Any]) -> bool:
        return (a.get("turn") == t.get("turn") and (t.get("turn_hash") is None or a.get("turn_hash") == t["turn_hash"])
                and a.get("predicate") == t.get("predicate")
                and _ekey(r, a.get("subject_type"), a.get("subject")) == _ekey(r, t.get("subject_type"), t.get("subject"))
                and _ekey(r, a.get("object_type"), a.get("object")) == _ekey(r, t.get("object_type"), t.get("object"))
                and norm(a.get("value")) == norm(t.get("value")))
    kept, hits = [], {}
    for a in items:
        rep = next((x for x in mine if same(x["target"] or {}, a)), None)
        if rep is None:
            kept.append(a)
        else:
            hits.setdefault(str(rep["id"]), str(a["id"]))
    return kept, hits


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


SCOPES = ("cast", "memory")  # PHASE-47 Q1: out of the cast (every fact stays), or out of memory too


def _plan_exclude(name: str, entity_type: str, scope: str, view: dict[str, Any]) -> tuple[dict, dict]:
    """Leave an entity out of the cast, or out of memory (PHASE-47 S1, S3): named as the owner saw it, matched on every
    read through entity resolution. The persona, a name the chat does not mention and an entity already left out are
    refused (the API also refuses a character the host names for the chat)."""
    r = view.get("resolution")
    if scope not in SCOPES:
        raise RepairError("the scope is cast or memory")
    by_id = next((e for e in view.get("entities") or () if str(e["id"]) == name.strip()), None)
    if by_id is not None:  # the panel names the entity by its id; the repair stores the name it goes by now
        name, entity_type = by_id["name"], by_id["type"]
    if r is not None and (r.is_persona(entity_type, name) or entity_type == "character" and norm(name) in r.persona_names):
        raise RepairError("the persona is always a character")
    if r is None or not name.strip() or r.status(entity_type, name) == "unresolved":
        raise RepairError("the name is not mentioned in this chat")
    e = r.entity(entity_type, name)
    if e is None:
        raise RepairError("the name is not one entity now")
    if str(e["id"]) in (view.get("excluded") or {}):
        raise RepairError("that entity is already left out")
    return {"entity_type": entity_type, "name": name.strip(), "scope": scope}, {}


def exclusions(repairs: list[dict[str, Any]], r: Resolution | None) -> dict[str, dict[str, Any]]:
    """The entities the owner left out (PHASE-47 S2), by entity id: each exclusion's name resolved now, so a name the
    story joins to it follows and a split name does not; one that resolves to nothing hides nothing. With two on one
    entity, `memory` wins."""
    out: dict[str, dict[str, Any]] = {}
    if r is None:
        return out
    for rep in repairs:
        if rep["kind"] != "entity_exclude":
            continue
        t = rep["target"]
        e = r.entity(t.get("entity_type") or "character", t.get("name"))
        if e is None or e.get("persona"):  # a name left out that the story later joins to the persona hides nothing
            continue
        was = out.get(str(e["id"]))
        if was is None or (t.get("scope") == "memory" and was["scope"] != "memory"):
            out[str(e["id"])] = {"scope": t.get("scope") or "cast", "repair": rep["id"], "name": e["name"]}
    return out


def _plan_pin(name: str, entity_type: str, view: dict[str, Any]) -> tuple[dict, dict]:
    """Pin a character (PHASE-60 S8, ADR 0087): named as the owner saw it, as an exclusion names its target, and matched
    on every read through entity resolution. A name that is no character of the chat, the persona, an entity the owner
    left out (item 5: the exclusion wins) and a character already pinned are refused."""
    r = view.get("resolution")
    by_id = next((e for e in view.get("entities") or () if str(e["id"]) == name.strip()), None)
    if by_id is not None:  # the panel names the entity by its id; the repair stores the name it goes by now
        name, entity_type = by_id["name"], by_id["type"]
    if entity_type != "character":
        raise RepairError("only a character can be pinned")
    if r is not None and (r.is_persona(entity_type, name) or norm(name) in r.persona_names):
        raise RepairError("the persona is not pinned: it is in every scene already")
    if r is None or not name.strip() or r.status(entity_type, name) == "unresolved":
        raise RepairError("the name is not mentioned in this chat")
    e = r.entity(entity_type, name)
    if e is None:
        raise RepairError("the name is not one character now")
    if str(e["id"]) in (view.get("excluded") or exclusions(view.get("repairs") or [], r)):
        raise RepairError("that name is marked not a character: take that back first")
    if any(str(p["entity_id"]) == str(e["id"]) for p in pins(view.get("repairs") or [], r)):
        raise RepairError("that character is pinned already")
    return {"entity_type": entity_type, "name": name.strip()}, {}


def pins(repairs: list[dict[str, Any]], r: Resolution | None) -> list[dict[str, Any]]:
    """The characters the owner pinned (PHASE-60 S8), newest pin first, one entry a character: each pin's name resolved
    now, so a name the story joins to it follows and a split name does not; one that resolves to nothing pins nothing.
    An entity the owner left out is not pinned (ADR 0087 item 5), whatever the exclusion's scope. `repairs` oldest
    first, as every read fetches them; of two pins that name one character now, the newer counts."""
    if r is None:
        return []
    left_out = exclusions(repairs, r)
    out: dict[str, tuple[int, dict[str, Any]]] = {}
    for i, rep in enumerate(repairs):
        if rep["kind"] != "entity_pin":
            continue
        t = rep.get("target") or {}
        e = r.entity(t.get("entity_type") or "character", t.get("name"))
        if e is None or str(e["id"]) in left_out:
            continue
        out[str(e["id"])] = (i, {"entity_id": e["id"], "name": e["name"], "repair": rep["id"],
                                 "created_at": rep.get("created_at")})
    return [p for _, p in sorted(out.values(), key=lambda x: x[0], reverse=True)]


def _plan_fact(kind: str, item: str, view: dict[str, Any], last_turn: int | None, new_object: str | None,
               new_value: str | None, turn: int | None, version_key: Callable[..., tuple] | None = None,
               new_because: str | None = None) -> tuple[dict, dict]:
    f = next((f for f in view["facts"] if str(f["id"]) == item), None)
    if f is None:  # PHASE-66: a belief or a forgetting the view lists apart is repaired as a fact is
        f = next((b for b in (*(view.get("beliefs") or ()), *(view.get("forgotten") or ())) if str(b["id"]) == item),
                 None)
    if f is None and kind == "fact_retract":  # PHASE-67 part 4: a character's claim, taken back as a fact is
        f = next((c for c in view.get("claims") or () if str(c["id"]) == item), None)
    if f is None and kind in ("fact_retract", "fact_lock", "fact_correct"):
        # a canon fact the story superseded: the owner keeps the story's (retract) or canon's (lock) (PHASE-14 Q4), or
        # canon's as corrected (PHASE-57 B2: the correction is locked with it)
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
    pred = READ_REGISTRY.get(f["predicate"])
    if new_object and new_object.strip() and pred is not None and pred.object_types is None:
        raise RepairError(f"a {f['predicate']} fact has no object: correct its value")
    if new_value and new_value.strip() and pred is not None and not pred.needs_value and not f.get("value"):
        raise RepairError(f"a {f['predicate']} fact has no value: correct its object")
    value: dict[str, Any] = {}
    if new_object is not None and new_object.strip() and new_object.strip() != (f.get("object") or ""):
        value["object"] = new_object.strip()
    if new_value is not None and new_value.strip() and new_value.strip() != (f.get("value") or ""):
        value["value"] = new_value.strip()
    if new_because is not None and new_because.strip() and new_because.strip() != (f.get("because") or ""):
        value["because"] = new_because.strip()  # PHASE-67 part 4: the stated cause, given by the owner, else none
    if not value:
        raise RepairError("give a new object, value or cause that differs from the fact's")
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
    if epistemic(f):  # PHASE-66: a belief is no statement about the world a later one could replace
        raise RepairError("a belief or a forgetting is not locked: correct or retract it")
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
