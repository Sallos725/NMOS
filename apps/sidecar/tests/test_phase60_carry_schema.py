"""PHASE-60 S6 (ADR 0085): schema and constraints for `conversation_carry` (migration 0036).

Synthetic names only."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from nmos_sidecar.ids import uuid7

MINIMAL_SNAPSHOT: dict[str, object] = {
    "shape": 1,
    "facts": [],
    "aliases": [],
    "threads": [],
    "story": None,
    "characters": [],
}


def _make_conversation(conn: psycopg.Connection, chat_ref: str) -> UUID:
    cid = uuid7()
    conn.execute(
        "INSERT INTO conversation (id, host, host_chat_ref) VALUES (%s, 'pocketrisu', %s)",
        (cid, chat_ref),
    )
    return cid


def _insert_link(
    conn: psycopg.Connection,
    target_id: UUID,
    source_id: UUID,
    *,
    mode: str = "continue",
    entity_names: object = None,
    cutoff_commit_id: UUID | None = None,
    cutoff_position: int = 0,
    cutoff_turn: int | None = None,
    generations: object = None,
    snapshot: object = MINIMAL_SNAPSHOT,
    removed_at: datetime | None = None,
) -> UUID:
    link_id = uuid7()
    commit_id = cutoff_commit_id or uuid7()
    if entity_names is None:
        conn.execute(
            "INSERT INTO conversation_carry"
            " (id, target_conversation_id, source_conversation_id, mode,"
            "  cutoff_commit_id, cutoff_position, cutoff_turn, generations, snapshot, removed_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                link_id,
                target_id,
                source_id,
                mode,
                commit_id,
                cutoff_position,
                cutoff_turn,
                Jsonb(generations) if generations is not None else None,
                Jsonb(snapshot),
                removed_at,
            ),
        )
    else:
        conn.execute(
            "INSERT INTO conversation_carry"
            " (id, target_conversation_id, source_conversation_id, mode, entity_names,"
            "  cutoff_commit_id, cutoff_position, cutoff_turn, generations, snapshot, removed_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                link_id,
                target_id,
                source_id,
                mode,
                Jsonb(entity_names),
                commit_id,
                cutoff_position,
                cutoff_turn,
                Jsonb(generations) if generations is not None else None,
                Jsonb(snapshot),
                removed_at,
            ),
        )
    return link_id


def test_table_and_indexes_exist(migrated: str) -> None:
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        assert conn.execute("SELECT to_regclass('public.conversation_carry') AS rel").fetchone()["rel"] == "conversation_carry"
        indexes = {
            r["indexname"]: r["indexdef"]
            for r in conn.execute(
                "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' AND tablename = 'conversation_carry'"
            ).fetchall()
        }
        assert "conversation_carry_in_force" in indexes
        assert "UNIQUE INDEX" in indexes["conversation_carry_in_force"]
        assert "removed_at IS NULL" in indexes["conversation_carry_in_force"]
        assert "conversation_carry_source" in indexes
        assert "source_conversation_id" in indexes["conversation_carry_source"]


def test_mode_and_self_link_checks(migrated: str) -> None:
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        a = _make_conversation(conn, "chat-a")
        b = _make_conversation(conn, "chat-b")

        with pytest.raises(psycopg.errors.CheckViolation):
            _insert_link(conn, a, b, mode="merge")

        with pytest.raises(psycopg.errors.CheckViolation):
            _insert_link(conn, a, a, mode="continue")

        lid = _insert_link(conn, a, b, mode="regression", entity_names=["Hana"])
        row = conn.execute("SELECT mode, entity_names, created_at FROM conversation_carry WHERE id = %s", (lid,)).fetchone()
        assert row["mode"] == "regression"
        assert row["entity_names"] == ["Hana"]
        assert row["created_at"] is not None


def test_one_link_in_force_per_target_but_removed_allowed(migrated: str) -> None:
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        target = _make_conversation(conn, "chat-target")
        src1 = _make_conversation(conn, "chat-src-1")
        src2 = _make_conversation(conn, "chat-src-2")

        first = _insert_link(conn, target, src1, mode="continue")
        with pytest.raises(psycopg.errors.UniqueViolation):
            _insert_link(conn, target, src2, mode="continue")

        now = datetime.now(timezone.utc)
        conn.execute("UPDATE conversation_carry SET removed_at = %s WHERE id = %s", (now, first))
        second = _insert_link(conn, target, src2, mode="continue")
        # Another already-removed row is still permitted alongside the active one.
        third = _insert_link(conn, target, src1, mode="regression", entity_names=["Kaito"], removed_at=now)
        rows = conn.execute(
            "SELECT id, removed_at FROM conversation_carry WHERE target_conversation_id = %s",
            (target,),
        ).fetchall()
        assert {r["id"] for r in rows} == {first, second, third}
        assert [r["id"] for r in rows if r["removed_at"] is None] == [second]


def test_foreign_keys_refuse_missing_conversation(migrated: str) -> None:
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        existing = _make_conversation(conn, "chat-existing")
        missing = uuid7()

        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            _insert_link(conn, missing, existing)

        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            _insert_link(conn, existing, missing)


def test_jsonb_shape_checks(migrated: str) -> None:
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        a = _make_conversation(conn, "chat-json-a")
        b = _make_conversation(conn, "chat-json-b")

        with pytest.raises(psycopg.errors.CheckViolation):
            _insert_link(conn, a, b, entity_names={"name": "Hana"})

        with pytest.raises(psycopg.errors.CheckViolation):
            _insert_link(conn, a, b, entity_names="Hana")

        with pytest.raises(psycopg.errors.CheckViolation):
            _insert_link(conn, a, b, snapshot=[])

        with pytest.raises(psycopg.errors.CheckViolation):
            _insert_link(conn, a, b, snapshot="not an object")

        # Default entity_names is an empty JSON array; cutoff_commit_id needs no FK.
        lid = _insert_link(conn, a, b, mode="continue")
        row = conn.execute("SELECT entity_names, snapshot FROM conversation_carry WHERE id = %s", (lid,)).fetchone()
        assert row["entity_names"] == []
        assert row["snapshot"] == MINIMAL_SNAPSHOT
