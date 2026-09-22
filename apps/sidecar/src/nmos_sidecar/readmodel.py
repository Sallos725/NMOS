"""Read-only queries for the inspector and list APIs."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from .normtext import NORMALIZER_VERSION


def list_conversations(conn: psycopg.Connection, limit: int = 200) -> list[dict[str, Any]]:
    return conn.execute(
        """
        SELECT c.id, c.host_chat_ref, c.host_character_ref, c.created_at, c.head_commit_id,
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
    normalized chars covered by the active embedding projection and seen by the active extractor."""
    return conn.execute(
        """
        SELECT am.position, so.host_logical_id, sr.id AS revision_id, sr.lifecycle, sr.metadata->>'role' AS role,
               sr.metadata->>'disabled' AS disabled, left(sr.content, 240) AS preview, length(sr.content) AS length,
               rt.clean_chars,
               (SELECT max(re.text_end) FROM revision_embedding re
                WHERE re.source_revision_id = sr.id AND re.projection = %(pj)s) AS embedded_chars,
               (SELECT (x.coverage->>'target_used')::int FROM extraction x
                WHERE x.source_revision_id = sr.id AND x.window_hash = am.window_hash
                  AND x.extractor_key = %(ex)s) AS extracted_chars
        FROM active_membership am
        JOIN source_revision sr ON sr.id = am.source_revision_id
        JOIN source_object so ON so.id = sr.source_object_id
        LEFT JOIN revision_text rt ON rt.source_revision_id = sr.id AND rt.normalizer = %(norm)s
        WHERE am.commit_id = %(head)s ORDER BY am.position DESC LIMIT %(limit)s
        """,
        {"head": head, "limit": limit, "ex": extractor_key or "", "pj": projection_key or "",
         "norm": NORMALIZER_VERSION},
    ).fetchall()


def commits(conn: psycopg.Connection, conv_id: UUID, limit: int = 100) -> list[dict[str, Any]]:
    return conn.execute(
        """
        SELECT w.seq, w.id, w.reason, w.created_at,
               (SELECT count(*) FROM jsonb_array_elements(w.delta->'changes')) AS changes,
               (SELECT string_agg(DISTINCT x->>'kind', ', ') FROM jsonb_array_elements(w.delta->'changes') x) AS kinds
        FROM worldline_commit w WHERE w.conversation_id = %s ORDER BY w.seq DESC LIMIT %s
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
