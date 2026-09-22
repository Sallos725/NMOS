"""Source-ledger repository: explicit SQL over psycopg. No HTTP concerns here."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from .canonical import normalize_text, revision_hash
from .ids import uuid7
from .reconcile import Entry, Lifecycle, Plan, RevKey, apply_ops, window_hashes

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
                      character_name: str | None = None, chat_name: str | None = None) -> Conversation:
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
    names = {k: v.strip() for k, v in (("host_character_name", character_name), ("host_chat_name", chat_name))
             if v and v.strip()}
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


def _membership_rows(conn: psycopg.Connection, commit_id: UUID, members: list[RevKey], ids: dict[RevKey, UUID],
                     window: int, start: int = 0) -> None:
    """Insert head membership rows for positions >= start, with their D7 window hashes."""
    windows = window_hashes(members, window)
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO active_membership (commit_id, position, source_revision_id, window_hash) VALUES (%s, %s, %s, %s)",
            [(commit_id, i, ids[members[i]], windows[i]) for i in range(start, len(members))],
        )


def apply_plan(
    conn: psycopg.Connection, conv: Conversation, state: ConversationState, result: Plan, observation_id: UUID,
    window: int = 6,
) -> UUID:
    """Write lifecycle/lineage changes, the commit (if any) and head membership. Returns head commit id."""
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
        # D4: append-only — no new commit; the head commit's delta gains the append ops.
        assert conv.head_commit_id is not None and state.head is not None
        conn.execute(
            "UPDATE worldline_commit SET delta = jsonb_set(jsonb_set(delta, '{ops}', (delta->'ops') || %s),"
            " '{changes}', (delta->'changes') || %s) WHERE id = %s",
            (Jsonb(result.ops), Jsonb(changes), conv.head_commit_id),
        )
        _membership_rows(conn, conv.head_commit_id, result.membership, ids, window, start=len(state.head))
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
        _membership_rows(conn, head_id, result.membership, ids, window)

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


def rebuild_membership(conn: psycopg.Connection, conv_id: UUID, window: int = 6) -> tuple[UUID | None, int]:
    """Reconstruct the head's active_membership purely from worldline_commit deltas."""
    commits = conn.execute(
        "SELECT id, delta FROM worldline_commit WHERE conversation_id = %s ORDER BY seq", (conv_id,)
    ).fetchall()
    if not commits:
        return None, 0
    members: list[RevKey] = []
    for commit in commits:
        members = apply_ops(members, commit["delta"]["ops"])
    rows = conn.execute(
        "SELECT so.host_logical_id, sr.revision_hash, sr.id FROM source_revision sr"
        " JOIN source_object so ON so.id = sr.source_object_id WHERE so.conversation_id = %s",
        (conv_id,),
    ).fetchall()
    ids = {(r["host_logical_id"], r["revision_hash"]): r["id"] for r in rows}
    head_id = commits[-1]["id"]
    conn.execute(
        "DELETE FROM active_membership WHERE commit_id IN (SELECT id FROM worldline_commit WHERE conversation_id = %s)",
        (conv_id,),
    )
    _membership_rows(conn, head_id, members, ids, window)
    conn.execute("UPDATE conversation SET head_commit_id = %s WHERE id = %s", (head_id, conv_id))
    return head_id, len(members)
