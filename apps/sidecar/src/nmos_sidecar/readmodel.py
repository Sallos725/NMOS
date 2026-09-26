"""Read-only queries for the inspector and list APIs."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from .extraction import TARGET_CHARS
from .normtext import NORMALIZER_VERSION


def list_conversations(conn: psycopg.Connection, limit: int = 200) -> list[dict[str, Any]]:
    return conn.execute(
        """
        SELECT c.id, c.host_chat_ref, c.host_character_ref, c.host_character_name, c.host_chat_name, c.created_at, c.head_commit_id,
               c.branched_from_host_chat_ref,
               (SELECT count(*) FROM active_membership am WHERE am.commit_id = c.head_commit_id) AS messages,
               (SELECT count(*) FROM worldline_commit w WHERE w.conversation_id = c.id) AS commits,
               (SELECT max(t.created_at) FROM retrieval_trace t WHERE t.conversation_id = c.id) AS last_retrieval
        FROM conversation c
        WHERE c.head_commit_id IS NOT NULL
        ORDER BY coalesce((SELECT max(t.created_at) FROM retrieval_trace t WHERE t.conversation_id = c.id), c.created_at) DESC
        LIMIT %s
        """,
        (limit,),
    ).fetchall()


def conversation(conn: psycopg.Connection, conv_id: UUID) -> dict[str, Any] | None:
    return conn.execute("SELECT * FROM conversation WHERE id = %s", (conv_id,)).fetchone()


def membership(conn: psycopg.Connection, head: UUID, extractor_key: str | None = None,
               projection_key: str | None = None, limit: int = 2000) -> list[dict[str, Any]]:
    """Head members with how much of each was semantically processed (#13): raw and normalized length,
    normalized chars covered by the active embedding projection and seen by the active extractor (the
    extraction of the member's turn, ADR 0008, or its own for per-message generations)."""
    return conn.execute(
        """
        SELECT am.position, am.turn, so.host_logical_id, sr.id AS revision_id, sr.lifecycle, sr.metadata->>'role' AS role,
               sr.metadata->>'disabled' AS disabled, left(sr.content, 240) AS preview, length(sr.content) AS length,
               rt.clean_chars,
               (SELECT max(re.text_end) FROM revision_embedding re
                WHERE re.source_revision_id = sr.id AND re.projection = %(pj)s) AS embedded_chars,
               (SELECT least(rt.clean_chars, %(target)s) FROM active_membership a
                JOIN extraction x ON x.source_revision_id = a.source_revision_id AND x.window_hash = a.turn_hash
                 AND x.extractor_key = %(ex)s AND x.discarded_at IS NULL
                WHERE a.commit_id = am.commit_id AND a.turn = am.turn AND a.turn_hash IS NOT NULL) AS extracted_chars
        FROM active_membership am
        JOIN source_revision sr ON sr.id = am.source_revision_id
        JOIN source_object so ON so.id = sr.source_object_id
        LEFT JOIN revision_text rt ON rt.source_revision_id = sr.id AND rt.normalizer = %(norm)s
        WHERE am.commit_id = %(head)s ORDER BY am.position DESC LIMIT %(limit)s
        """,
        {"head": head, "limit": limit, "ex": extractor_key or "", "pj": projection_key or "",
         "norm": NORMALIZER_VERSION, "target": TARGET_CHARS},
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
               jsonb_array_length(excluded_in_context) AS excluded, latency_ms
        FROM retrieval_trace WHERE conversation_id = %s ORDER BY created_at DESC LIMIT %s
        """,
        (conv_id, limit),
    ).fetchall()
