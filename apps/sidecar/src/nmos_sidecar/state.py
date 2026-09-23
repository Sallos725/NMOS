"""State projection: parse stored revisions into state_observation; read current state via head membership."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from .parsers import RuleSet, parse


def write_state(conn: psycopg.Connection, ruleset: RuleSet, conv_id: UUID, revision_id: UUID,
                content: str, meta: dict[str, Any]) -> int:
    if not ruleset.rules:
        return 0
    pairs = parse(ruleset, content, meta.get("role"), meta.get("saying"))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO state_observation (conversation_id, source_revision_id, rules_version, rule_id, key, value)"
            " VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            [(conv_id, revision_id, ruleset.version, rule_id, key, value) for rule_id, key, value in pairs],
        )
    return len(pairs)


def sync_rules(conn: psycopg.Connection, ruleset: RuleSet) -> int:
    """Drop rows from other rule versions and backfill the current version if it is missing."""
    conn.execute("DELETE FROM state_observation WHERE rules_version <> %s", (ruleset.version,))
    if not ruleset.rules:
        return 0
    has = conn.execute("SELECT 1 FROM state_observation LIMIT 1").fetchone()
    if has:
        return 0
    return rebuild_state(conn, ruleset)


def rebuild_state(conn: psycopg.Connection, ruleset: RuleSet) -> int:
    conn.execute("DELETE FROM state_observation")
    total = 0
    rows = conn.execute(
        "SELECT sr.id, sr.content, sr.metadata, so.conversation_id FROM source_revision sr"
        " JOIN source_object so ON so.id = sr.source_object_id"
    ).fetchall()
    for r in rows:
        total += write_state(conn, ruleset, r["conversation_id"], r["id"], r["content"], r["metadata"])
    return total


def current_state(conn: psycopg.Connection, head_commit_id: UUID, rules_version: str) -> list[dict[str, Any]]:
    """Latest value per key from accepted, active, visible revisions of the head (D8: via membership)."""
    return conn.execute(
        """
        WITH m AS (
            SELECT am.position, sr.id, sr.lifecycle, sr.metadata, so.host_logical_id
            FROM active_membership am
            JOIN source_revision sr ON sr.id = am.source_revision_id
            JOIN source_object so ON so.id = sr.source_object_id
            WHERE am.commit_id = %(head)s
        )
        SELECT DISTINCT ON (st.key) st.key, st.value, m.position, m.host_logical_id, st.rule_id
        FROM state_observation st
        JOIN m ON m.id = st.source_revision_id
        WHERE st.rules_version = %(version)s
          AND m.lifecycle = 'accepted'
          -- a scalar subquery runs once; a joined CTE could be re-run per row (see facts.ACTIVE_ASSERTIONS)
          AND m.position > (SELECT coalesce(max(position), -1) FROM m WHERE metadata->>'disabled' = 'allBefore')
          AND coalesce(m.metadata->>'disabled', '') NOT IN ('true', 'allBefore')
        ORDER BY st.key, m.position DESC
        """,
        {"head": head_commit_id, "version": rules_version},
    ).fetchall()
