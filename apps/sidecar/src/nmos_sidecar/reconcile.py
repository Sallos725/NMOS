"""Pure reconciliation planning: previous head + new host manifest → plan.

No I/O. Revisions are referenced by `(host_logical_id, revision_hash)` keys; the ledger maps them
to row ids. Case table: docs/phases/PHASE-0.md "Reconciliation cases"; host behavior: H4/H5/H6.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Literal

from .canonical import manifest_hash

Lifecycle = Literal["provisional", "accepted", "retracted", "superseded"]
RevKey = tuple[str, str]  # (host_logical_id, revision_hash)

BRANCH_MARKER = re.compile(r"\{\{specialcomment::branchedfrom::(?P<chat>[^:]*)::(?P<name>.*?)::(?P<message>[^:]*)::\}\}")


@dataclass(frozen=True)
class Entry:
    """One host message as seen in a manifest (or in the stored head)."""

    host_logical_id: str
    revision_hash: str
    role: str
    disabled: bool | str | None = None
    is_comment: bool | None = None
    swipe_id: int | None = None
    swipe_count: int = 0
    generation_id: str | None = None
    special_comments: tuple[str, ...] = ()

    @property
    def key(self) -> RevKey:
        return (self.host_logical_id, self.revision_hash)


@dataclass(frozen=True)
class Change:
    kind: Literal["append", "edit", "swipe", "continue", "disable", "reroll", "delete", "insert"]
    host_logical_id: str
    position: int
    old: RevKey | None = None
    new: RevKey | None = None


@dataclass
class Plan:
    kind: Literal["noop", "needs_bodies", "apply"]
    manifest_hash: str
    needed: list[RevKey] = field(default_factory=list)
    membership: list[RevKey] = field(default_factory=list)
    changes: list[Change] = field(default_factory=list)
    commit_reason: str | None = None  # None → no commit (append-only, D4)
    ops: list[dict] = field(default_factory=list)
    lifecycle: dict[RevKey, Lifecycle] = field(default_factory=dict)
    lineage: dict[RevKey, RevKey] = field(default_factory=dict)
    branch: dict[str, str] | None = None

    @property
    def summary(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for change in self.changes:
            out[change.kind] = out.get(change.kind, 0) + 1
        return out


def parse_branch_marker(entries: list[Entry]) -> dict[str, str] | None:
    for entry in entries:
        for comment in entry.special_comments:
            match = BRANCH_MARKER.search(comment)
            if match:
                return {"chat_ref": match["chat"], "chat_name": match["name"], "message_ref": match["message"]}
    return None


def _is_disabled(entry: Entry) -> bool:
    return entry.disabled is True or entry.disabled == "true"


def _acceptance(membership: list[Entry], current: dict[RevKey, Lifecycle]) -> dict[RevKey, Lifecycle]:
    """User revisions are accepted; an AI revision is accepted once a later user turn exists."""
    out: dict[RevKey, Lifecycle] = {}
    later_user = False
    for entry in reversed(membership):
        state = current.get(entry.key)
        if entry.role == "user" or entry.is_comment:
            target: Lifecycle = "accepted"
        else:
            target = "accepted" if later_user or state == "accepted" else "provisional"
        if state != target:
            out[entry.key] = target
        if entry.role == "user" and not entry.is_comment and not _is_disabled(entry):
            later_user = True
    return out


def plan(
    head: list[Entry] | None,
    head_manifest_hash: str | None,
    manifest: list[Entry],
    known: set[RevKey],
    lifecycle: dict[RevKey, Lifecycle],
    large_divergence_ratio: float = 0.5,
) -> Plan:
    """Plan how `manifest` changes the conversation whose current head is `head`.

    `known` holds every revision key already stored for the conversation (any lifecycle);
    `lifecycle` their current lifecycle states.
    """
    new_hash = manifest_hash([(e.host_logical_id, e.revision_hash) for e in manifest])
    if head is not None and head_manifest_hash == new_hash:
        return Plan(kind="noop", manifest_hash=new_hash)

    needed = []
    for entry in manifest:
        if entry.key not in known and entry.key not in needed:
            needed.append(entry.key)
    if needed:
        return Plan(kind="needs_bodies", manifest_hash=new_hash, needed=needed)

    result = Plan(kind="apply", manifest_hash=new_hash, membership=[e.key for e in manifest])
    states: dict[RevKey, Lifecycle] = dict(lifecycle)

    if head is None:
        result.branch = parse_branch_marker(manifest)
        result.commit_reason = "branch" if result.branch else "import"
        result.changes = [Change("append", e.host_logical_id, i, new=e.key) for i, e in enumerate(manifest)]
        result.ops = [{"op": "set", "members": [list(k) for k in result.membership]}]
        result.lifecycle = _acceptance(manifest, states)
        return result

    old_by_id = {e.host_logical_id: (i, e) for i, e in enumerate(head)}
    new_by_id = {e.host_logical_id: (i, e) for i, e in enumerate(manifest)}
    removed = [(i, e) for i, e in enumerate(head) if e.host_logical_id not in new_by_id]
    added = [(i, e) for i, e in enumerate(manifest) if e.host_logical_id not in old_by_id]

    # Reroll (H4): the tail AI message disappears and a new AI message takes the same tail slot.
    reroll_pairs: list[tuple[Entry, Entry, int]] = []
    if removed and added:
        old_tail_i, old_tail = removed[-1]
        new_tail_i, new_tail = added[-1]
        if (
            old_tail_i == len(head) - 1
            and new_tail_i == len(manifest) - 1
            and old_tail_i == new_tail_i
            and old_tail.role == "char"
            and new_tail.role == "char"
        ):
            reroll_pairs.append((old_tail, new_tail, new_tail_i))
            removed = removed[:-1]
            added = added[:-1]

    changes: list[Change] = []
    for old, new, pos in reroll_pairs:
        changes.append(Change("reroll", new.host_logical_id, pos, old=old.key, new=new.key))
        states[old.key] = "retracted"
        result.lineage[new.key] = old.key
    # Live reroll (HOST-FACTS Q2/S2: the host drops the tail reply *before* beforeRequest runs):
    # the manifest is exactly the head minus its tail AI message.
    live_reroll = (
        len(removed) == 1 and not added and removed[0][0] == len(head) - 1 and head[-1].role == "char"
        and [e.key for e in head[:-1]] == [e.key for e in manifest]
    )
    for i, old in removed:
        changes.append(Change("reroll" if live_reroll else "delete", old.host_logical_id, i, old=old.key))
        if live_reroll or states.get(old.key) == "provisional":
            states[old.key] = "retracted"  # discarded AI output (D5)

    old_order = [e.host_logical_id for e in head if e.host_logical_id in new_by_id]
    new_order = [e.host_logical_id for e in manifest if e.host_logical_id in old_by_id]
    reordered = old_order != new_order

    for i, new in enumerate(manifest):
        if new.host_logical_id not in old_by_id:
            continue
        _, old = old_by_id[new.host_logical_id]
        if old.revision_hash == new.revision_hash:
            continue
        if old.disabled != new.disabled:
            kind = "disable"
        elif old.swipe_id != new.swipe_id:
            kind = "swipe"
        elif new.role == "char" and old.generation_id != new.generation_id:
            kind = "continue"  # H4: continue keeps chatId, replaces generationId
            result.lineage[new.key] = old.key
        else:
            kind = "edit"
        changes.append(Change(kind, new.host_logical_id, i, old=old.key, new=new.key))
        states[old.key] = "superseded"

    first_added = len(head) - len(removed) - len(reroll_pairs)
    for i, new in added:
        kind = "append" if i >= first_added else "insert"
        changes.append(Change(kind, new.host_logical_id, i, new=new.key))

    kinds = {c.kind for c in changes}
    divergent = kinds - {"append"}
    touched = sum(1 for c in changes if c.kind in ("delete", "reroll", "edit", "swipe", "continue", "disable"))
    large = reordered or (bool(head) and touched / len(head) > large_divergence_ratio)
    if large:
        result.commit_reason = "reconciliation"
    elif not divergent:
        result.commit_reason = None
    elif len(divergent) == 1:
        only = next(iter(divergent))
        result.commit_reason = {"continue": "edit", "insert": "reconciliation"}.get(only, only)
    else:
        result.commit_reason = "reconciliation"  # several kinds of change since the last request

    result.changes = changes
    result.ops = _ops([e.key for e in head], result.membership, full=large)
    # Revisions that re-enter membership (e.g. swiping back) are active again; acceptance decides.
    for key in result.membership:
        if states.get(key) in ("superseded", "retracted"):
            states[key] = "provisional"
    accepted = _acceptance(manifest, states)
    states.update(accepted)
    result.lifecycle = {k: v for k, v in states.items() if lifecycle.get(k) != v}
    return result


def _ops(old: list[RevKey], new: list[RevKey], full: bool) -> list[dict]:
    """Delta ops turning `old` membership into `new`; verified by replay, else a full set."""
    if full:
        return [{"op": "set", "members": [list(k) for k in new]}]
    new_ids = {k[0]: k for k in new}
    old_ids = {k[0]: k for k in old}
    ops: list[dict] = []
    for key in old:
        if key[0] not in new_ids:
            ops.append({"op": "remove", "member": list(key)})
        elif new_ids[key[0]] != key:
            ops.append({"op": "replace", "from": list(key), "to": list(new_ids[key[0]])})
    previous: RevKey | None = None
    for key in new:
        if key[0] not in old_ids:
            ops.append({"op": "insert", "after": list(previous) if previous else None, "member": list(key)})
        previous = key
    if apply_ops(old, ops) != new:
        return [{"op": "set", "members": [list(k) for k in new]}]
    return ops


def window_hashes(members: list[RevKey], k: int) -> list[str]:
    """Per position: hash of the revision and the previous k members (D7 bounded context)."""
    out = []
    for i in range(len(members)):
        window = [rev_hash for _, rev_hash in members[max(0, i - k): i + 1]]
        out.append(hashlib.sha256("\n".join(window).encode()).hexdigest()[:32])
    return out


def apply_ops(members: list[RevKey], ops: list[dict]) -> list[RevKey]:
    """Replay delta ops (used for commit verification and membership rebuild)."""
    out = list(members)
    for op in ops:
        kind = op["op"]
        if kind == "set":
            out = [tuple(m) for m in op["members"]]  # type: ignore[misc]
        elif kind == "remove":
            out.remove(tuple(op["member"]))  # type: ignore[arg-type]
        elif kind == "replace":
            out[out.index(tuple(op["from"]))] = tuple(op["to"])  # type: ignore[call-overload]
        elif kind == "insert":
            index = 0 if op["after"] is None else out.index(tuple(op["after"])) + 1  # type: ignore[arg-type]
            out.insert(index, tuple(op["member"]))  # type: ignore[arg-type]
        else:
            raise ValueError(f"unknown op {kind}")
    return out
