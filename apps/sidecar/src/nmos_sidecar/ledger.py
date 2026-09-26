"""Source-ledger repository: explicit SQL over psycopg. No HTTP concerns here."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from .canonical import normalize_text, revision_hash, storable
from .ids import uuid7
from .reconcile import Entry, Lifecycle, Plan, RevKey, apply_ops, turn_layout, window_hashes

META_KEYS = ("chatId", "role", "saying", "name", "otherUser", "isComment", "disabled", "swipeId", "generationId")


@dataclass
class Conversation:
    id: UUID
    head_commit_id: UUID | None
    head_manifest_hash: str | None


@dataclass
class ConversationState:
    head: list[Entry] | None
    known: set[RevKey]
    lifecycle: dict[RevKey, Lifecycle]
    revision_ids: dict[RevKey, UUID]


def lock_conversation(conn: psycopg.Connection, host: str, chat_ref: str, character_ref: str | None,
                      character_name: str | None = None, chat_name: str | None = None,
                      persona_name: str | None = None) -> Conversation:
    """Get-or-create the conversation row and lock it for the rest of the transaction."""
    conn.execute(
        "INSERT INTO conversation (id, host, host_chat_ref, host_character_ref) VALUES (%s, %s, %s, %s)"
        " ON CONFLICT (host, host_chat_ref) DO NOTHING",
        (uuid7(), host, chat_ref, character_ref),
    )
    row = conn.execute(
        "SELECT id, head_commit_id, head_manifest_hash FROM conversation WHERE host = %s AND host_chat_ref = %s FOR UPDATE",
        (host, chat_ref),
    ).fetchone()
    assert row is not None
    if character_ref:
        conn.execute(
            "UPDATE conversation SET host_character_ref = %s WHERE id = %s AND host_character_ref IS NULL",
            (character_ref, row["id"]),
        )
    names = {k: v.strip() for k, v in (("host_character_name", character_name), ("host_chat_name", chat_name),
                                       ("host_persona_name", persona_name)) if v and v.strip()}
    if names:  # labels follow renames in the host; written only when they changed
        sets = ", ".join(f"{k} = %({k})s" for k in names)
        changed = " OR ".join(f"{k} IS DISTINCT FROM %({k})s" for k in names)
        conn.execute(f"UPDATE conversation SET {sets} WHERE id = %(id)s AND ({changed})", {**names, "id": row["id"]})
    return Conversation(row["id"], row["head_commit_id"], row["head_manifest_hash"])


def find_conversation(conn: psycopg.Connection, host: str, chat_ref: str) -> Conversation | None:
    row = conn.execute(
        "SELECT id, head_commit_id, head_manifest_hash FROM conversation WHERE host = %s AND host_chat_ref = %s",
        (host, chat_ref),
    ).fetchone()
    return Conversation(row["id"], row["head_commit_id"], row["head_manifest_hash"]) if row else None


def entry_from_metadata(logical_id: str, rev_hash: str, meta: dict[str, Any]) -> Entry:
    return Entry(
        host_logical_id=logical_id,
        revision_hash=rev_hash,
        role=meta.get("role") or "char",
        disabled=meta.get("disabled"),
        is_comment=meta.get("isComment"),
        swipe_id=meta.get("swipeId"),
        swipe_count=meta.get("swipeCount") or 0,
        generation_id=meta.get("generationId"),
        special_comments=tuple(meta.get("specialComments") or ()),
    )


def load_state(conn: psycopg.Connection, conv: Conversation) -> ConversationState:
    rows = conn.execute(
        "SELECT so.host_logical_id, sr.revision_hash, sr.lifecycle, sr.id"
        " FROM source_revision sr JOIN source_object so ON so.id = sr.source_object_id"
        " WHERE so.conversation_id = %s",
        (conv.id,),
    ).fetchall()
    known = {(r["host_logical_id"], r["revision_hash"]) for r in rows}
    lifecycle = {(r["host_logical_id"], r["revision_hash"]): r["lifecycle"] for r in rows}
    ids = {(r["host_logical_id"], r["revision_hash"]): r["id"] for r in rows}
    head: list[Entry] | None = None
    if conv.head_commit_id is not None:
        members = conn.execute(
            "SELECT so.host_logical_id, sr.revision_hash, sr.metadata"
            " FROM active_membership am"
            " JOIN source_revision sr ON sr.id = am.source_revision_id"
            " JOIN source_object so ON so.id = sr.source_object_id"
            " WHERE am.commit_id = %s ORDER BY am.position",
            (conv.head_commit_id,),
        ).fetchall()
        head = [entry_from_metadata(m["host_logical_id"], m["revision_hash"], m["metadata"]) for m in members]
    return ConversationState(head, known, lifecycle, ids)


def record_observation(
    conn: psycopg.Connection, conv_id: UUID, kind: str, manifest_hash: str | None, raw: dict, key: str
) -> UUID:
    row = conn.execute(
        "INSERT INTO host_observation (id, conversation_id, kind, manifest_hash, idempotency_key, raw_manifest)"
        " VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (idempotency_key) DO NOTHING RETURNING id",
        (uuid7(), conv_id, kind, manifest_hash, key, Jsonb(raw)),
    ).fetchone()
    if row:
        return row["id"]
    existing = conn.execute("SELECT id FROM host_observation WHERE idempotency_key = %s", (key,)).fetchone()
    assert existing is not None
    return existing["id"]


def store_bodies(
    conn: psycopg.Connection, conv_id: UUID, bodies: list[dict[str, Any]],
    on_insert: Callable[[UUID, str, dict[str, Any]], None] | None = None,
) -> tuple[int, list[RevKey]]:
    """Insert verified revisions. Idempotent: an existing (object, hash) row is left untouched."""
    stored = 0
    rejected: list[RevKey] = []
    for body in bodies:
        meta = dict(body["metadata"])
        content = normalize_text(body["content"])
        if meta.get("chatId") != body["host_logical_id"] or revision_hash(meta, content) != body["revision_hash"]:
            rejected.append((body["host_logical_id"], body["revision_hash"]))
            continue
        content = storable(content)  # verified as sent, stored as PostgreSQL can hold it (ADR 0029)
        conn.execute(
            "INSERT INTO source_object (id, conversation_id, host_logical_id) VALUES (%s, %s, %s)"
            " ON CONFLICT (conversation_id, host_logical_id) DO NOTHING",
            (uuid7(), conv_id, body["host_logical_id"]),
        )
        obj = conn.execute(
            "SELECT id FROM source_object WHERE conversation_id = %s AND host_logical_id = %s",
            (conv_id, body["host_logical_id"]),
        ).fetchone()
        assert obj is not None
        stored_meta = {k: meta.get(k) for k in META_KEYS}
        stored_meta["swipeCount"] = meta.get("swipeCount") or 0
        stored_meta["specialComments"] = list(meta.get("specialComments") or [])
        stored_meta = storable(stored_meta)
        initial = "accepted" if meta.get("role") == "user" or meta.get("isComment") else "provisional"
        row = conn.execute(
            "INSERT INTO source_revision (id, source_object_id, revision_hash, content, metadata, lifecycle)"
            " VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (source_object_id, revision_hash) DO NOTHING RETURNING id",
            (uuid7(), obj["id"], body["revision_hash"], content, Jsonb(stored_meta), initial),
        ).fetchone()
        if row:
            stored += 1
            if on_insert:
                on_insert(row["id"], content, stored_meta)
    return stored, rejected


def _membership_rows(conn: psycopg.Connection, commit_id: UUID, members: list[Entry], ids: dict[RevKey, UUID],
                     window: int, turns: int, start: int = 0, previous: list[Entry] | None = None) -> None:
    """Insert head membership rows for positions >= start, with their D7 window hashes and turn data
    (ADR 0008). An append can change the last turn of the rows before `start` (a second reply moves
    the anchor): those rows, whose layout differs from the one `previous` gave them, are rewritten."""
    keys = [m.key for m in members]
    windows = window_hashes(keys, window)
    layout = turn_layout(members, turns)
    with conn.cursor() as cur:
        if start and previous is not None:
            old = turn_layout(previous, turns)
            changed = [(layout[i][0], layout[i][1], commit_id, i) for i in range(start) if layout[i] != old[i]]
            if changed:
                cur.executemany("UPDATE active_membership SET turn = %s, turn_hash = %s"
                                " WHERE commit_id = %s AND position = %s", changed)
        cur.executemany(
            "INSERT INTO active_membership (commit_id, position, source_revision_id, window_hash, turn, turn_hash)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            [(commit_id, i, ids[keys[i]], windows[i], *layout[i]) for i in range(start, len(members))],
        )


def _record_append(conn: psycopg.Connection, commit_id: UUID, ops: list[dict], changes: list[dict],
                   observation_id: UUID) -> None:
    conn.execute("INSERT INTO worldline_append (commit_id, ops, changes, host_observation_id) VALUES (%s, %s, %s, %s)",
                 (commit_id, Jsonb(ops), Jsonb(changes), observation_id))


def apply_plan(
    conn: psycopg.Connection, conv: Conversation, state: ConversationState, result: Plan, observation_id: UUID,
    manifest: list[Entry], window: int = 6, turns: int = 3,
) -> UUID:
    """Write lifecycle/lineage changes, the commit (if any) and head membership. Returns head commit id.
    `manifest` is the host manifest the plan was made from; its keys are the new membership."""
    assert [e.key for e in manifest] == result.membership
    ids = state.revision_ids
    for key, target in sorted(result.lifecycle.items()):
        conn.execute("UPDATE source_revision SET lifecycle = %s WHERE id = %s AND lifecycle <> %s", (target, ids[key], target))
    for child, parent in sorted(result.lineage.items()):
        conn.execute(
            "UPDATE source_revision SET lineage_parent_revision_id = %s WHERE id = %s AND lineage_parent_revision_id IS NULL",
            (ids[parent], ids[child]),
        )
    changes = [
        {"kind": c.kind, "host_logical_id": c.host_logical_id, "position": c.position,
         "old": list(c.old) if c.old else None, "new": list(c.new) if c.new else None}
        for c in result.changes
    ]

    if result.commit_reason is None:
        # D4: append-only — no new commit; the head commit gains an append row (migration 0013).
        assert conv.head_commit_id is not None and state.head is not None
        _record_append(conn, conv.head_commit_id, result.ops, changes, observation_id)
        _membership_rows(conn, conv.head_commit_id, manifest, ids, window, turns, start=len(state.head),
                         previous=state.head)
        head_id = conv.head_commit_id
    else:
        head_id = uuid7()
        parents = [conv.head_commit_id] if conv.head_commit_id else []
        conn.execute(
            "INSERT INTO worldline_commit (id, conversation_id, parent_commit_ids, reason, manifest_hash, delta, host_observation_id)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (head_id, conv.id, parents, result.commit_reason, result.manifest_hash,
             Jsonb({"ops": result.ops, "changes": changes}), observation_id),
        )
        if conv.head_commit_id:
            conn.execute("DELETE FROM active_membership WHERE commit_id = %s", (conv.head_commit_id,))
        _membership_rows(conn, head_id, manifest, ids, window, turns)

    branch = result.branch
    if branch:
        origin = conn.execute(
            "SELECT id FROM conversation WHERE host = 'pocketrisu' AND host_chat_ref = %s", (branch["chat_ref"],)
        ).fetchone()
        conn.execute(
            "UPDATE conversation SET branched_from_host_chat_ref = %s, branched_from_message_ref = %s,"
            " branched_from_conversation_id = %s WHERE id = %s",
            (branch["chat_ref"], branch["message_ref"], origin["id"] if origin else None, conv.id),
        )
    conn.execute(
        "UPDATE conversation SET head_commit_id = %s, head_manifest_hash = %s WHERE id = %s",
        (head_id, result.manifest_hash, conv.id),
    )
    return head_id


@dataclass
class HeadTail:
    """The end of the stored head that an append can change (Track A, A1).

    `entries` start at `start`. Turn `first_turn` begins at `turn_start`; from `exact_turn` on (member
    positions >= `exact_start`), a turn's K-turn hash window lies inside the tail, so layouts computed
    from `turn_start` equal the whole head's. Every head member that is not accepted is at or after
    `exact_start`.
    """

    start: int
    turn_start: int
    first_turn: int
    exact_start: int
    entries: list[Entry]
    lifecycle: dict[RevKey, Lifecycle]
    revision_ids: dict[RevKey, UUID]


def head_length(conn: psycopg.Connection, head_commit_id: UUID) -> int:
    row = conn.execute("SELECT max(position) AS p FROM active_membership WHERE commit_id = %s",
                       (head_commit_id,)).fetchone()
    return 0 if row is None or row["p"] is None else row["p"] + 1


def revisions_of(conn: psycopg.Connection, conv: Conversation, logical_ids: list[str]
                 ) -> tuple[dict[RevKey, tuple[Lifecycle, UUID]], bool]:
    """Stored revisions of these messages, and whether any of them is a head member."""
    rows = conn.execute(
        "SELECT so.host_logical_id, sr.revision_hash, sr.lifecycle, sr.id,"
        " EXISTS (SELECT 1 FROM active_membership am WHERE am.source_revision_id = sr.id AND am.commit_id = %s) AS member"
        " FROM source_object so JOIN source_revision sr ON sr.source_object_id = so.id"
        " WHERE so.conversation_id = %s AND so.host_logical_id = ANY(%s)",
        (conv.head_commit_id, conv.id, logical_ids),
    ).fetchall()
    return ({(r["host_logical_id"], r["revision_hash"]): (r["lifecycle"], r["id"]) for r in rows},
            any(r["member"] for r in rows))


def load_tail(conn: psycopg.Connection, conv: Conversation, length: int, window: int, turns: int) -> HeadTail | None:
    """Load the head from the start of turn `last - 2K` (and at least the last `window` members).

    None when the stored head does not support an append: no turns yet, a member that is not
    accepted before the exact region, or stored turn data that differs from what the tail computes
    (e.g. K changed). The caller then uses the full path.
    """
    head = conv.head_commit_id
    last = conn.execute("SELECT max(turn) AS t FROM active_membership WHERE commit_id = %s", (head,)).fetchone()["t"]
    if last is None:
        return None
    first_turn = max(0, last - 2 * turns)
    exact_turn = first_turn + turns if first_turn > 0 else 0

    def turn_position(turn: int) -> int:
        return conn.execute("SELECT min(position) AS p FROM active_membership WHERE commit_id = %s AND turn = %s",
                            (head, turn)).fetchone()["p"]

    turn_start = turn_position(first_turn)
    exact_start = turn_position(exact_turn) if exact_turn != first_turn else turn_start
    if turn_start is None or exact_start is None:
        return None
    start = max(0, min(turn_start, length - window))
    if conn.execute(
        "SELECT EXISTS (SELECT 1 FROM active_membership am JOIN source_revision sr ON sr.id = am.source_revision_id"
        " WHERE am.commit_id = %s AND am.position < %s AND sr.lifecycle <> 'accepted') AS found",
        (head, exact_start),
    ).fetchone()["found"]:
        return None
    rows = conn.execute(
        "SELECT am.position, am.turn, am.turn_hash, so.host_logical_id, sr.revision_hash, sr.metadata, sr.lifecycle,"
        " sr.id FROM active_membership am"
        " JOIN source_revision sr ON sr.id = am.source_revision_id"
        " JOIN source_object so ON so.id = sr.source_object_id"
        " WHERE am.commit_id = %s AND am.position >= %s ORDER BY am.position",
        (head, start),
    ).fetchall()
    if len(rows) != length - start or rows[0]["position"] != start:
        return None
    entries = [entry_from_metadata(r["host_logical_id"], r["revision_hash"], r["metadata"]) for r in rows]
    tail = HeadTail(start, turn_start, first_turn, exact_start, entries,
                    {e.key: r["lifecycle"] for e, r in zip(entries, rows)},
                    {e.key: r["id"] for e, r in zip(entries, rows)})
    # Replay check: the tail's own layout must reproduce the stored turn data it is trusted for.
    layout = _absolute(turn_layout(entries[turn_start - start:], turns), first_turn)
    for (turn, turn_hash), r in zip(layout, rows[turn_start - start:]):
        if turn != r["turn"] or (r["position"] >= exact_start and turn_hash != r["turn_hash"]):
            return None
    return tail


def _absolute(layout: list[tuple[int | None, str | None]], first_turn: int) -> list[tuple[int | None, str | None]]:
    return [(None if t is None else t + first_turn, h) for t, h in layout]


def apply_append(
    conn: psycopg.Connection, conv: Conversation, tail: HeadTail, result: Plan, observation_id: UUID,
    entries: list[Entry], ids: dict[RevKey, UUID], window: int = 6, turns: int = 3,
) -> UUID:
    """`apply_plan` for a `plan_append` result: the same rows, written from the tail only. `entries`
    are the request's messages from position `tail.start` on."""
    assert result.commit_reason is None and conv.head_commit_id is not None
    for key, target in sorted(result.lifecycle.items()):
        conn.execute("UPDATE source_revision SET lifecycle = %s WHERE id = %s AND lifecycle <> %s", (target, ids[key], target))
    changes = [{"kind": c.kind, "host_logical_id": c.host_logical_id, "position": c.position, "old": None,
                "new": list(c.new) if c.new else None} for c in result.changes]
    _record_append(conn, conv.head_commit_id, result.ops, changes, observation_id)
    length, offset = tail.start + len(tail.entries), tail.turn_start - tail.start
    old = _absolute(turn_layout(tail.entries[offset:], turns), tail.first_turn)
    new = _absolute(turn_layout(entries[offset:], turns), tail.first_turn)
    windows = window_hashes([e.key for e in entries], window)
    with conn.cursor() as cur:
        changed = [(*new[i], conv.head_commit_id, tail.turn_start + i) for i in range(length - tail.turn_start)
                   if new[i] != old[i]]
        if changed:
            cur.executemany("UPDATE active_membership SET turn = %s, turn_hash = %s"
                            " WHERE commit_id = %s AND position = %s", changed)
        cur.executemany(
            "INSERT INTO active_membership (commit_id, position, source_revision_id, window_hash, turn, turn_hash)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            [(conv.head_commit_id, tail.start + j, ids[entries[j].key], windows[j], *new[j - offset])
             for j in range(len(tail.entries), len(entries))],
        )
    conn.execute("UPDATE conversation SET head_manifest_hash = %s WHERE id = %s", (result.manifest_hash, conv.id))
    return conv.head_commit_id


def rebuild_membership(conn: psycopg.Connection, conv_id: UUID, window: int = 6,
                       turns: int = 3) -> tuple[UUID | None, int]:
    """Reconstruct the head's active_membership purely from worldline_commit deltas and their appends."""
    commits = conn.execute(
        "SELECT id, delta FROM worldline_commit WHERE conversation_id = %s ORDER BY seq", (conv_id,)
    ).fetchall()
    if not commits:
        return None, 0
    appends: dict[UUID, list[list[dict]]] = {}
    for row in conn.execute("SELECT commit_id, ops FROM worldline_append WHERE commit_id = ANY(%s) ORDER BY seq",
                            ([c["id"] for c in commits],)).fetchall():
        appends.setdefault(row["commit_id"], []).append(row["ops"])
    members: list[RevKey] = []
    for commit in commits:
        members = apply_ops(members, commit["delta"]["ops"])
        for ops in appends.get(commit["id"], []):  # appends after the commit (migration 0013)
            members = apply_ops(members, ops)
    rows = conn.execute(
        "SELECT so.host_logical_id, sr.revision_hash, sr.id, sr.metadata FROM source_revision sr"
        " JOIN source_object so ON so.id = sr.source_object_id WHERE so.conversation_id = %s",
        (conv_id,),
    ).fetchall()
    ids = {(r["host_logical_id"], r["revision_hash"]): r["id"] for r in rows}
    meta = {(r["host_logical_id"], r["revision_hash"]): r["metadata"] for r in rows}
    head_id = commits[-1]["id"]
    conn.execute(
        "DELETE FROM active_membership WHERE commit_id IN (SELECT id FROM worldline_commit WHERE conversation_id = %s)",
        (conv_id,),
    )
    _membership_rows(conn, head_id, [entry_from_metadata(k[0], k[1], meta[k]) for k in members], ids, window, turns)
    conn.execute("UPDATE conversation SET head_commit_id = %s WHERE id = %s", (head_id, conv_id))
    return head_id, len(members)


def delete_conversation(conn: psycopg.Connection, conv_id: UUID) -> dict[str, int] | None:
    """Delete one conversation and everything recorded for it (ADR 0009): raw revisions, commits,
    observations, derived rows, traces and jobs. Irreversible; only on the owner's explicit request.
    Returns deleted row counts, or None if the conversation does not exist.

    Runs in one transaction and takes the conversation lock first, so a concurrent sync waits and
    then records the chat as new. Branches keep their origin's host refs; only the link is cleared."""
    with conn.transaction():
        if conn.execute("SELECT 1 FROM conversation WHERE id = %s FOR UPDATE", (conv_id,)).fetchone() is None:
            return None
        # Lets the source_revision guard (migration 0012) pass for this conversation's rows only.
        conn.execute("SELECT set_config('nmos.delete_conversation', %s, true)", (str(conv_id),))
        revs = ("SELECT sr.id FROM source_revision sr JOIN source_object so ON so.id = sr.source_object_id"
                " WHERE so.conversation_id = %(c)s")
        extractions = f"SELECT id FROM extraction WHERE source_revision_id IN ({revs})"
        steps = [
            ("branch_links", "UPDATE conversation SET branched_from_conversation_id = NULL"
                             " WHERE branched_from_conversation_id = %(c)s"),
            ("jobs", "DELETE FROM job WHERE conversation_id = %(c)s"),
            ("traces", "DELETE FROM retrieval_trace WHERE conversation_id = %(c)s"),
            ("assertions", f"DELETE FROM assertion WHERE extraction_id IN ({extractions})"),
            ("assertions", f"DELETE FROM assertion WHERE source_revision_id IN ({revs})"),
            ("extractions", f"DELETE FROM extraction WHERE source_revision_id IN ({revs})"),
            ("embeddings", f"DELETE FROM revision_embedding WHERE source_revision_id IN ({revs})"),
            ("texts", f"DELETE FROM revision_text WHERE source_revision_id IN ({revs})"),
            ("state", "DELETE FROM state_observation WHERE conversation_id = %(c)s"),
            ("entity_links", "DELETE FROM entity_link WHERE conversation_id = %(c)s"),
            ("head", "UPDATE conversation SET head_commit_id = NULL WHERE id = %(c)s"),
            ("membership", "DELETE FROM active_membership WHERE commit_id IN"
                           " (SELECT id FROM worldline_commit WHERE conversation_id = %(c)s)"),
            ("appends", "DELETE FROM worldline_append WHERE commit_id IN"
                        " (SELECT id FROM worldline_commit WHERE conversation_id = %(c)s)"),
            ("commits", "DELETE FROM worldline_commit WHERE conversation_id = %(c)s"),
            ("revisions", f"DELETE FROM source_revision WHERE id IN ({revs})"),
            ("messages", "DELETE FROM source_object WHERE conversation_id = %(c)s"),
            ("observations", "DELETE FROM host_observation WHERE conversation_id = %(c)s"),
            ("conversation", "DELETE FROM conversation WHERE id = %(c)s"),
        ]
        counts: dict[str, int] = {}
        for name, sql in steps:
            n = conn.execute(sql, {"c": conv_id}).rowcount
            if name != "head":
                counts[name] = counts.get(name, 0) + n
        return counts


def refresh_turns(conn: psycopg.Connection, turns: int) -> int:
    """Bring every head's turn data up to date (ADR 0008): after migration 0011, or when K changed.
    Idempotent; returns the number of rewritten rows."""
    updated = 0
    heads = conn.execute("SELECT head_commit_id FROM conversation WHERE head_commit_id IS NOT NULL").fetchall()
    for head in heads:
        with conn.transaction():
            rows = conn.execute(
                "SELECT am.position, am.turn, am.turn_hash, so.host_logical_id, sr.revision_hash, sr.metadata"
                " FROM active_membership am JOIN source_revision sr ON sr.id = am.source_revision_id"
                " JOIN source_object so ON so.id = sr.source_object_id WHERE am.commit_id = %s ORDER BY am.position",
                (head["head_commit_id"],),
            ).fetchall()
            layout = turn_layout([entry_from_metadata(r["host_logical_id"], r["revision_hash"], r["metadata"])
                                  for r in rows], turns)
            changed = [(t, h, head["head_commit_id"], r["position"]) for r, (t, h) in zip(rows, layout)
                       if (r["turn"], r["turn_hash"]) != (t, h)]
            if changed:
                with conn.cursor() as cur:
                    cur.executemany("UPDATE active_membership SET turn = %s, turn_hash = %s"
                                    " WHERE commit_id = %s AND position = %s", changed)
            updated += len(changed)
    return updated
