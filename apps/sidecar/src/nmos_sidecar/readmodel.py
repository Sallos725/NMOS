"""Read-only queries for the inspector and list APIs."""

from __future__ import annotations

from collections.abc import Collection
from typing import Any
from uuid import UUID

import psycopg

from .extraction import TARGET_CHARS
from . import normtext


def list_conversations(conn: psycopg.Connection, limit: int = 200, host_chat_ref: str | None = None,
                       host: str | None = None) -> list[dict[str, Any]]:
    """The most recently used chats first; with `host_chat_ref` (and `host`: a chat ref is unique per host only), that
    host chat only, however old."""
    return conn.execute(
        """
        SELECT c.id, c.host_chat_ref, c.host_character_ref, c.host_character_name, c.host_chat_name, c.created_at, c.head_commit_id,
               c.branched_from_host_chat_ref,
               (SELECT count(*) FROM active_membership am WHERE am.commit_id = c.head_commit_id) AS messages,
               (SELECT count(*) FROM worldline_commit w WHERE w.conversation_id = c.id) AS commits,
               (SELECT max(t.created_at) FROM retrieval_trace t WHERE t.conversation_id = c.id) AS last_retrieval
        FROM conversation c
        WHERE c.head_commit_id IS NOT NULL AND (%s::text IS NULL OR c.host_chat_ref = %s)
          AND (%s::text IS NULL OR c.host = %s)
        ORDER BY coalesce((SELECT max(t.created_at) FROM retrieval_trace t WHERE t.conversation_id = c.id), c.created_at) DESC
        LIMIT %s
        """,
        (host_chat_ref, host_chat_ref, host, host, limit),
    ).fetchall()


def conversation(conn: psycopg.Connection, conv_id: UUID) -> dict[str, Any] | None:
    return conn.execute("SELECT * FROM conversation WHERE id = %s", (conv_id,)).fetchone()


def orphan_conversations(conn: psycopg.Connection, host: str, active_chat_refs: Collection[str]) -> dict[str, Any]:
    """Conversations recorded for `host` whose `host_chat_ref` is absent from `active_chat_refs` (PHASE-68, H22).

    Reads every conversation for `host` (no 200-row cap, and includes `head_commit_id IS NULL` stubs per Q2).
    Attaches active `conversation_carry` targets (`removed_at IS NULL`) and `branch_children` counts so the panel
    can warn before the owner confirms deletion. Read-only.
    """
    active = set(active_chat_refs)
    rows = conn.execute(
        """
        SELECT c.id, c.host_chat_ref, c.host_character_name, c.host_chat_name, c.created_at, c.head_commit_id,
               CASE WHEN c.head_commit_id IS NULL THEN 0
                    ELSE (SELECT count(*) FROM active_membership am WHERE am.commit_id = c.head_commit_id)
               END AS messages,
               (SELECT count(*) FROM worldline_commit w WHERE w.conversation_id = c.id) AS commits,
               (SELECT max(t.created_at) FROM retrieval_trace t WHERE t.conversation_id = c.id) AS last_retrieval,
               (SELECT count(*) FROM conversation ch WHERE ch.branched_from_conversation_id = c.id) AS branch_children
        FROM conversation c
        WHERE c.host = %s
        ORDER BY coalesce((SELECT max(t.created_at) FROM retrieval_trace t WHERE t.conversation_id = c.id),
                          c.created_at) DESC, c.id DESC
        """,
        (host,),
    ).fetchall()
    orphan_rows = [r for r in rows if r["host_chat_ref"] not in active]
    matched_active = len(rows) - len(orphan_rows)

    carried_map: dict[UUID, list[dict[str, Any]]] = {}
    if orphan_rows:
        orphan_ids = [r["id"] for r in orphan_rows]
        carry_rows = conn.execute(
            """
            SELECT cc.source_conversation_id, cc.mode,
                   t.id AS target_id, t.host AS target_host, t.host_chat_ref AS target_host_chat_ref,
                   t.host_character_name AS target_character, t.host_chat_name AS target_chat
            FROM conversation_carry cc
            JOIN conversation t ON t.id = cc.target_conversation_id
            WHERE cc.source_conversation_id = ANY(%s) AND cc.removed_at IS NULL
            ORDER BY cc.created_at DESC, t.id DESC
            """,
            (orphan_ids,),
        ).fetchall()
        for cr in carry_rows:
            carried_map.setdefault(cr["source_conversation_id"], []).append({
                "id": str(cr["target_id"]),
                "character": cr["target_character"],
                "chat": cr["target_chat"],
                "mode": cr["mode"],
                "target_missing": cr["target_host"] != host or cr["target_host_chat_ref"] not in active,
            })

    return {
        "host": host,
        "total_host_conversations": len(rows),
        "matched_active": matched_active,
        "orphans": [
            {
                "id": str(r["id"]),
                "host_chat_ref": r["host_chat_ref"],
                "character": r["host_character_name"],
                "chat": r["host_chat_name"],
                "messages": int(r["messages"] or 0),
                "commits": int(r["commits"] or 0),
                "created_at": r["created_at"],
                "last_retrieval": r["last_retrieval"],
                "carried_by": carried_map.get(r["id"], []),
                "branch_children": int(r["branch_children"] or 0),
            }
            for r in orphan_rows
        ],
    }


def membership(conn: psycopg.Connection, head: UUID, extractor_key: str | None = None,
               projection_key: str | None = None, limit: int = 2000) -> list[dict[str, Any]]:
    """Head members with how much of each was semantically processed (#13): raw and normalized length,
    normalized chars covered by the active embedding projection and seen by the extraction serving the member's turn
    (ADR 0008), chosen as `facts.ACTIVE_ASSERTIONS` chooses it: the active extractor's, else the most recently
    activated generation's that still matches the turn (ADR 0014: after a model or cap change carried on, an earlier
    generation serves the turn, which is not unextracted). None without an active extractor."""
    return conn.execute(
        """
        SELECT am.position, am.turn, so.host_logical_id, sr.id AS revision_id, sr.lifecycle, sr.metadata->>'role' AS role,
               sr.metadata->>'disabled' AS disabled, left(sr.content, 240) AS preview, length(sr.content) AS length,
               rt.clean_chars,
               (SELECT max(re.text_end) FROM revision_embedding re
                WHERE re.source_revision_id = sr.id AND re.projection = %(pj)s) AS embedded_chars,
               (SELECT least(rt.clean_chars, coalesce((x.coverage->>'target_cap')::int, %(target)s))  -- its own cap
                FROM active_membership a
                JOIN extraction x ON x.source_revision_id = a.source_revision_id AND x.window_hash = a.turn_hash
                 AND x.discarded_at IS NULL
                JOIN projection_generation g ON g.key = x.extractor_key
                WHERE a.commit_id = am.commit_id AND a.turn = am.turn AND a.turn_hash IS NOT NULL AND %(ex)s <> ''
                ORDER BY x.extractor_key = %(ex)s DESC, g.activated_at DESC, g.key
                LIMIT 1) AS extracted_chars
        FROM active_membership am
        JOIN source_revision sr ON sr.id = am.source_revision_id
        JOIN source_object so ON so.id = sr.source_object_id
        LEFT JOIN revision_text rt ON rt.source_revision_id = sr.id AND rt.normalizer = %(norm)s
        WHERE am.commit_id = %(head)s ORDER BY am.position DESC LIMIT %(limit)s
        """,
        {"head": head, "limit": limit, "ex": extractor_key or "", "pj": projection_key or "",
         "norm": normtext.active(), "target": TARGET_CHARS},
    ).fetchall()


def commits(conn: psycopg.Connection, conv_id: UUID, limit: int = 100) -> list[dict[str, Any]]:
    return conn.execute(
        """
        SELECT w.seq, w.id, w.reason, w.created_at,
               jsonb_array_length(j.changes) AS changes,
               -- per kind with its count, e.g. "delete ×12, edit ×1" (ADR 0008: mass deletions are visible)
               (SELECT string_agg(k.kind || ' ×' || k.n, ', ' ORDER BY k.n DESC, k.kind)
                FROM (SELECT x->>'kind' AS kind, count(*) AS n FROM jsonb_array_elements(j.changes) x
                      GROUP BY 1) k) AS kinds
        FROM worldline_commit w
        -- the commit's own changes, then those of the appends it gained (migration 0013)
        CROSS JOIN LATERAL (SELECT (w.delta->'changes') || coalesce(
            (SELECT jsonb_agg(c ORDER BY a.seq) FROM worldline_append a, jsonb_array_elements(a.changes) c
             WHERE a.commit_id = w.id), '[]') AS changes) j
        WHERE w.conversation_id = %s ORDER BY w.seq DESC LIMIT %s
        """,
        (conv_id, limit),
    ).fetchall()


def traces(conn: psycopg.Connection, conv_id: UUID, limit: int = 30) -> list[dict[str, Any]]:
    return conn.execute(
        """
        SELECT id, created_at, left(query, 160) AS query, freshness, token_estimate,
               jsonb_array_length(candidates) AS candidates, jsonb_array_length(selected) AS selected,
               jsonb_array_length(excluded_in_context) AS excluded, latency_ms, recall_options
        FROM retrieval_trace WHERE conversation_id = %s ORDER BY created_at DESC LIMIT %s
        """,
        (conv_id, limit),
    ).fetchall()


# --- the source-turn page (PHASE-33 Q7) ---------------------------------------------------------------------------

TURN_TRACES = 300  # the latest requests a turn's uses are looked for in


def turn_messages(conn: psycopg.Connection, head: UUID, turn: int) -> list[dict[str, Any]]:
    """The messages of one turn on the head, in order, with the text NMOS read (the normalized projection)."""
    return conn.execute(
        """
        SELECT am.position, am.turn, am.turn_hash, sr.id AS revision_id, sr.lifecycle,
               sr.metadata->>'role' AS role, sr.metadata->>'name' AS name, sr.metadata->>'disabled' AS disabled,
               length(sr.content) AS length, coalesce(rt.clean_content, sr.content) AS text
        FROM active_membership am
        JOIN source_revision sr ON sr.id = am.source_revision_id
        LEFT JOIN revision_text rt ON rt.source_revision_id = sr.id AND rt.normalizer = %(norm)s
        WHERE am.commit_id = %(head)s AND am.turn = %(turn)s ORDER BY am.position
        """, {"head": head, "turn": turn, "norm": normtext.active()}).fetchall()


def turn_bounds(conn: psycopg.Connection, head: UUID) -> tuple[int | None, int | None]:
    row = conn.execute("SELECT min(turn) AS lo, max(turn) AS hi FROM active_membership WHERE commit_id = %s",
                       (head,)).fetchone()
    return row["lo"], row["hi"]


def turn_generations(conn: psycopg.Connection, revision_ids: list[UUID],
                     head: UUID | None = None) -> list[dict[str, Any]]:
    """Every extractor generation's extraction of these messages: when, and how many assertions it made, and whether
    one matches the message's turn on `head` (default: its conversation's head). Read against that one commit: a join
    on every commit that ever held the message counted each assertion once per commit (Tier 1 D5)."""
    return conn.execute(
        """
        SELECT x.extractor_key, max(x.created_at) AS created_at, count(a.id) AS assertions,
               bool_or(x.window_hash = am.turn_hash) AS current_window
        FROM extraction x
        JOIN source_revision sr ON sr.id = x.source_revision_id
        JOIN source_object so ON so.id = sr.source_object_id
        JOIN conversation c ON c.id = so.conversation_id
        JOIN active_membership am ON am.source_revision_id = x.source_revision_id
         AND am.commit_id = coalesce(%(head)s::uuid, c.head_commit_id)
        LEFT JOIN assertion a ON a.extraction_id = x.id
        WHERE x.source_revision_id = ANY(%(ids)s) AND x.discarded_at IS NULL
        GROUP BY x.extractor_key ORDER BY max(x.created_at) DESC
        """, {"ids": revision_ids, "head": head}).fetchall()


def turn_uses(conn: psycopg.Connection, conv_id: UUID, revisions: set[str], assertions: set[str],
              limit: int = TURN_TRACES) -> list[dict[str, Any]]:
    """The packet lines of the latest `limit` requests that came from this turn: an excerpt or quote of one of its
    messages, a fact or claim one of its assertions made (the ledger's `ref`, ADR 0027). Newest first."""
    out = []
    for t in conn.execute(
            "SELECT id, created_at, policy, lines FROM retrieval_trace WHERE conversation_id = %s AND lines IS NOT NULL"
            " ORDER BY created_at DESC LIMIT %s", (conv_id, limit)).fetchall():
        for e in t["lines"] or []:
            ref = e.get("ref") or {}
            if str(ref.get("revision")) in revisions or str(ref.get("assertion")) in assertions:
                out.append({"trace": str(t["id"]), "created_at": t["created_at"], "policy": t["policy"], **e})
    return out


def ledgers(conn: psycopg.Connection, conv_id: UUID, limit: int = 100) -> list[list[dict[str, Any]]]:
    """The ledgers of the chat's latest `limit` requests, oldest first (PHASE-34 Q7)."""
    rows = conn.execute("SELECT lines FROM retrieval_trace WHERE conversation_id = %s AND lines IS NOT NULL"
                        " ORDER BY created_at DESC LIMIT %s", (conv_id, limit)).fetchall()
    return [r["lines"] or [] for r in reversed(rows)]
