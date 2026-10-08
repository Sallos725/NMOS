"""State projection: parse stored revisions into state_observation; read current state via head membership."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import tuple_row

from .parsers import RuleSet, needs_card, parse

_UNSET: Any = object()


def write_state(conn: psycopg.Connection, ruleset: RuleSet, conv_id: UUID, revision_id: UUID,
                content: str, meta: dict[str, Any], card: str | None = _UNSET) -> int:
    if not ruleset.rules:
        return 0
    if card is _UNSET:  # a rule bound to a card (PHASE-39 Q2) reads the chat's character name
        card = None
        if needs_card(ruleset):
            with conn.cursor(row_factory=tuple_row) as cur:
                card = (cur.execute("SELECT host_character_name FROM conversation WHERE id = %s",
                                    (conv_id,)).fetchone() or (None,))[0]
    pairs = parse(ruleset, content, meta.get("role"), meta.get("saying"), card)
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
        "SELECT sr.id, sr.content, sr.metadata, so.conversation_id, c.host_character_name FROM source_revision sr"
        " JOIN source_object so ON so.id = sr.source_object_id JOIN conversation c ON c.id = so.conversation_id"
        " WHERE so.source_kind = 'message'"  # not canon (ADR 0045)
    ).fetchall()
    for r in rows:
        total += write_state(conn, ruleset, r["conversation_id"], r["id"], r["content"], r["metadata"],
                             r["host_character_name"])
    return total


def current_state(conn: psycopg.Connection, head_commit_id: UUID, rules_version: str,
                  upto: int | None = None) -> list[dict[str, Any]]:
    """Latest value per key from accepted, active, visible revisions of the head (D8: via membership);
    with `upto`, of the head up to that position (a replay, ADR 0027)."""
    return conn.execute(
        """
        WITH m AS (
            SELECT am.position, am.turn, sr.id, sr.lifecycle, sr.metadata, so.host_logical_id
            FROM active_membership am
            JOIN source_revision sr ON sr.id = am.source_revision_id
            JOIN source_object so ON so.id = sr.source_object_id
            WHERE am.commit_id = %(head)s AND am.position <= %(upto)s
        )
        SELECT DISTINCT ON (st.key) st.key, st.value, m.position, m.turn, m.host_logical_id, st.rule_id
        FROM state_observation st
        JOIN m ON m.id = st.source_revision_id
        WHERE st.rules_version = %(version)s
          AND m.lifecycle = 'accepted'
          -- a scalar subquery runs once; a joined CTE could be re-run per row (see facts.ACTIVE_ASSERTIONS)
          AND m.position > (SELECT coalesce(max(position), -1) FROM m WHERE metadata->>'disabled' = 'allBefore')
          AND coalesce(m.metadata->>'disabled', '') NOT IN ('true', 'allBefore')
        ORDER BY st.key, m.position DESC
        """,
        {"head": head_commit_id, "version": rules_version, "upto": 2**31 - 1 if upto is None else upto},
    ).fetchall()
