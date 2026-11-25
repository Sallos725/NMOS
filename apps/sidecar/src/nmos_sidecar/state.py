"""State projection: parse stored revisions into state_observation; read current state via head membership."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import tuple_row

from .parsers import RuleSet, needs_card, parse

_UNSET: Any = object()
STATE_BACKFILL_BATCH = 500

# Tier 4 G7.2: {host character ref: the card name its status rules and pins are filed under}, in `app_config`. A ref is
# bound the first time a chat with that ref and a name is seen, to the name it had then, and never rebound: a rename in
# the host changes the chat's label, not the card its rules, history and pins are under. A chat without a ref is read
# by its name, as before. Rules and pins stay keyed by name (their documents, ids and `rules_version` are unchanged).
CARD_BINDINGS_KEY = "card_bindings"
# The card a chat's status rules and pins are read under (alias `c` for `conversation`).
CARD_SQL = ("coalesce((SELECT b.value->>c.host_character_ref FROM app_config b WHERE b.key = 'card_bindings'),"
            " c.host_character_name)")


def card_of(conn: psycopg.Connection, conv_id: UUID) -> str | None:
    """The card a chat's status rules and pins are read under: its card ref's binding, else its character name."""
    with conn.cursor(row_factory=tuple_row) as cur:
        return (cur.execute(f"SELECT {CARD_SQL} FROM conversation c WHERE c.id = %s", (conv_id,)).fetchone()
                or (None,))[0]


def bind_ref(conn: psycopg.Connection, ref: str, card: str) -> None:
    """Bind a card ref to `card` unless it is bound already (the first binding wins; nothing is ever rebound)."""
    conn.execute(
        "INSERT INTO app_config (key, value, updated_at) VALUES (%(key)s, jsonb_build_object(%(ref)s::text, %(card)s::text),"
        " now()) ON CONFLICT (key) DO UPDATE SET value = CASE WHEN jsonb_typeof(app_config.value) = 'object'"
        " THEN app_config.value ELSE '{}'::jsonb END || EXCLUDED.value, updated_at = now()"
        " WHERE jsonb_typeof(app_config.value) IS DISTINCT FROM 'object' OR NOT app_config.value ? %(ref)s",
        {"key": CARD_BINDINGS_KEY, "ref": ref, "card": card})


def card_before_sync(conn: psycopg.Connection, host: str, chat_ref: str, character_ref: str | None,
                     character_name: str | None) -> str | None:
    """Before a sync's lock writes the chat's labels: bind its card ref (the one it keeps, else the one sent) to the
    name it had before this sync (else the one sent), and return the card its observations were read under (None for
    a chat not seen yet). The caller reads the chat again when `card_of` then differs (a chat without a ref renamed, a
    ref arriving for a card bound under another name), never for a rename alone."""
    with conn.cursor(row_factory=tuple_row) as cur:
        row = cur.execute(
            f"SELECT c.host_character_ref, c.host_character_name, {CARD_SQL},"
            " coalesce((SELECT b.value ? coalesce(c.host_character_ref, %(ref)s) FROM app_config b"
            " WHERE b.key = 'card_bindings' AND jsonb_typeof(b.value) = 'object'), false)"
            " FROM conversation c WHERE c.host = %(host)s AND c.host_chat_ref = %(chat)s",
            {"host": host, "chat": chat_ref, "ref": character_ref or None}).fetchone()
        bound = row[3] if row else bool(character_ref) and bool(cur.execute(
            "SELECT 1 FROM app_config WHERE key = 'card_bindings' AND jsonb_typeof(value) = 'object' AND value ? %s",
            (character_ref,)).fetchone())
    ref = (row[0] if row else None) or character_ref or None
    name = (row[1] if row else None) or (character_name or "").strip() or None
    if ref and name and not bound:
        bind_ref(conn, ref, name)
    return row[2] if row else None


def resolve_card(conn: psycopg.Connection, card: str) -> str:
    """The card a write by name lands on (the panel and Settings send names): `card` itself when some chat is read
    under it; otherwise, when every chat now labelled `card` is read under one other card (a card bound under its
    earlier name), that card; otherwise `card`. A label shared by chats read under different cards is taken as
    written, so no card's rules or pins move to another card."""
    with conn.cursor(row_factory=tuple_row) as cur:
        under = {r[0] for r in cur.execute(f"SELECT DISTINCT {CARD_SQL} FROM conversation c"
                                           f" WHERE c.host_character_name = %(card)s OR {CARD_SQL} = %(card)s",
                                           {"card": card}).fetchall()} - {None}
    return next(iter(under)) if len(under) == 1 else card


def write_state(conn: psycopg.Connection, ruleset: RuleSet, conv_id: UUID, revision_id: UUID,
                content: str, meta: dict[str, Any], card: str | None = _UNSET) -> int:
    if not ruleset.rules:
        return 0
    if card is _UNSET:  # a rule bound to a card (PHASE-39 Q2) reads the chat's card (its ref's binding, G7.2)
        card = card_of(conn, conv_id) if needs_card(ruleset) else None
    pairs = parse(ruleset, content, meta.get("role"), meta.get("saying"), card)
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO state_observation (conversation_id, source_revision_id, rules_version, rule_id, key, value)"
            " VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            [(conv_id, revision_id, ruleset.version, rule_id, key, value) for rule_id, key, value in pairs],
        )
    return len(pairs)


def sync_rules(conn: psycopg.Connection, ruleset: RuleSet) -> int:
    """Drop other rule versions, then parse messages without an observation under the current rules.

    Normalized text can commit before parsing (or be filled by a worker), so it cannot mark state as complete.
    A message with no matching field is checked once per invocation; the keyset advances even when parsing yields
    no observation. Positive observations are preserved, and the caller keeps its transaction boundary.
    """
    conn.execute("DELETE FROM state_observation WHERE rules_version <> %s", (ruleset.version,))
    if not ruleset.rules:
        return 0
    total = 0
    after: UUID | None = None
    while True:
        rows = conn.execute(
            f"SELECT sr.id, sr.content, sr.metadata, so.conversation_id, {CARD_SQL} AS card FROM source_revision sr"
            " JOIN source_object so ON so.id = sr.source_object_id JOIN conversation c ON c.id = so.conversation_id"
            " WHERE so.source_kind = 'message' AND (%s::uuid IS NULL OR sr.id > %s)"
            " AND NOT EXISTS (SELECT 1 FROM state_observation st WHERE st.source_revision_id = sr.id"
            " AND st.rules_version = %s) ORDER BY sr.id LIMIT %s",
            (after, after, ruleset.version, STATE_BACKFILL_BATCH),
        ).fetchall()
        for row in rows:
            total += write_state(conn, ruleset, row["conversation_id"], row["id"], row["content"], row["metadata"],
                                 row["card"])
        if len(rows) < STATE_BACKFILL_BATCH:
            return total
        after = rows[-1]["id"]


def reparse_conversation(conn: psycopg.Connection, ruleset: RuleSet, conv_id: UUID) -> int:
    """Read one chat's messages again, when the card its rules read changed (PHASE-39; G7.2: a chat without a card ref
    renamed, or a ref arriving bound under another name; never a rename alone). One transaction (a savepoint inside
    the caller's): no reader sees the chat without its state between the delete and the rewrite, and a failure keeps
    the old rows."""
    with conn.transaction():
        conn.execute("DELETE FROM state_observation WHERE conversation_id = %s", (conv_id,))
        return _parse(conn, ruleset, "so.conversation_id = %s", (conv_id,)) if ruleset.rules else 0


def _parse(conn: psycopg.Connection, ruleset: RuleSet, where: str, params: tuple) -> int:
    total = 0
    rows = conn.execute(
        f"SELECT sr.id, sr.content, sr.metadata, so.conversation_id, {CARD_SQL} AS card FROM source_revision sr"
        " JOIN source_object so ON so.id = sr.source_object_id JOIN conversation c ON c.id = so.conversation_id"
        f" WHERE so.source_kind = 'message' AND {where}", params).fetchall()  # not canon (ADR 0045)
    for r in rows:
        total += write_state(conn, ruleset, r["conversation_id"], r["id"], r["content"], r["metadata"],
                             r["card"])
    return total


def rebuild_state(conn: psycopg.Connection, ruleset: RuleSet) -> int:
    """Read every message again under new rules, in one transaction (a savepoint inside the caller's)."""
    with conn.transaction():
        conn.execute("DELETE FROM state_observation")
        return _parse(conn, ruleset, "true", ())


def history(conn: psycopg.Connection, head_commit_id: UUID, rules_version: str, upto: int | None = None,
            keys: list[str] | None = None, redone: bool = False) -> dict[str, list[dict[str, Any]]]:
    """Every value each key held along the head (PHASE-39 Q3), oldest first, from the bars `current_state` reads (D8:
    via membership; accepted, active, visible). A bar restating the value before it extends that entry (`last_turn`)
    instead of adding one: a bar repeats every field each turn. With `keys`, only those keys. With `redone`, each entry
    says whether its first bar's reply was rerolled, swiped or edited (it holds swipes, H4, or its message has another
    revision)."""
    rows = conn.execute(
        """
        WITH m AS (
            SELECT am.position, am.turn, sr.id, sr.lifecycle, sr.metadata, so.host_logical_id, so.id AS object_id
            FROM active_membership am
            JOIN source_revision sr ON sr.id = am.source_revision_id
            JOIN source_object so ON so.id = sr.source_object_id
            WHERE am.commit_id = %(head)s AND am.position <= %(upto)s
        )
        SELECT st.key, st.value, st.rule_id, m.position, m.turn, m.host_logical_id, m.id AS revision_id,
               CASE WHEN NOT %(redone)s THEN false
                    ELSE coalesce(jsonb_typeof(m.metadata->'swipeCount') = 'number'
                                  AND (m.metadata->>'swipeCount')::numeric > 1, false)
                         OR EXISTS (SELECT 1 FROM source_revision o WHERE o.source_object_id = m.object_id AND o.id <> m.id)
               END AS redone
        FROM state_observation st
        JOIN m ON m.id = st.source_revision_id
        WHERE st.rules_version = %(version)s
          AND (%(keys)s::text[] IS NULL OR st.key = ANY(%(keys)s::text[]))
          AND m.lifecycle = 'accepted'
          AND m.position > (SELECT coalesce(max(position), -1) FROM m WHERE metadata->>'disabled' = 'allBefore')
          AND coalesce(m.metadata->>'disabled', '') NOT IN ('true', 'allBefore')
        ORDER BY st.key, m.position
        """,
        {"head": head_commit_id, "version": rules_version, "upto": 2**31 - 1 if upto is None else upto,
         "keys": keys, "redone": redone},
    ).fetchall()
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        entries = out.setdefault(r["key"], [])
        if entries and entries[-1]["value"] == r["value"]:
            entries[-1].update(last_position=r["position"], last_turn=r["turn"])
            continue
        entries.append({"value": r["value"], "position": r["position"], "turn": r["turn"],
                        "last_position": r["position"], "last_turn": r["turn"], "rule_id": r["rule_id"],
                        "host_logical_id": r["host_logical_id"], "revision_id": r["revision_id"],
                        "redone": bool(r["redone"])})
    return out


def windows(conn: psycopg.Connection, head_commit_id: UUID, rules_version: str, upto: int | None = None,
            last: int = 10) -> list[dict[str, Any]]:
    """The last `last` status windows along the head, oldest first (PHASE-43 S4): each reply holding observations under
    `rules_version`, from the bars `current_state` reads (D8: via membership; accepted, active, visible), as
    {position, turn, host_logical_id, values: {key: value}}."""
    rows = conn.execute(
        """
        WITH m AS (
            SELECT am.position, am.turn, sr.id, sr.lifecycle, sr.metadata, so.host_logical_id
            FROM active_membership am
            JOIN source_revision sr ON sr.id = am.source_revision_id
            JOIN source_object so ON so.id = sr.source_object_id
            WHERE am.commit_id = %(head)s AND am.position <= %(upto)s
        ), obs AS (
            SELECT st.key, st.value, st.id AS observation_id, m.position, m.turn, m.host_logical_id
            FROM state_observation st
            JOIN m ON m.id = st.source_revision_id
            WHERE st.rules_version = %(version)s
              AND m.lifecycle = 'accepted'
              AND m.position > (SELECT coalesce(max(position), -1) FROM m WHERE metadata->>'disabled' = 'allBefore')
              AND coalesce(m.metadata->>'disabled', '') NOT IN ('true', 'allBefore')
        )
        SELECT key, value, position, turn, host_logical_id FROM obs
        WHERE position IN (SELECT DISTINCT position FROM obs ORDER BY position DESC LIMIT %(last)s)
        ORDER BY position, observation_id
        """,
        {"head": head_commit_id, "version": rules_version, "upto": 2**31 - 1 if upto is None else upto, "last": last},
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        if not out or out[-1]["position"] != r["position"]:
            out.append({"position": r["position"], "turn": r["turn"], "host_logical_id": r["host_logical_id"],
                        "values": {}})
        out[-1]["values"][r["key"]] = r["value"]
    return out


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
