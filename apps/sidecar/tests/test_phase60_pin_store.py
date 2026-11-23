"""PHASE-60 S8 (ADR 0087): the owner pins a character, the store side. A pin is an owner repair (`entity_pin`,
migration 0038): stored, listed, undone, archived, kept by rebuilds and deleted with the chat like every repair. Nothing
here reads a pin into a packet. Synthetic names only."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import psycopg
import pytest
from psycopg.types.json import Jsonb

from nmos_sidecar.ids import uuid7
from nmos_sidecar.migrate import apply_migrations, migrations_dir
from test_upgrade import FIXTURES, restore

PIN = "0038_entity_pin.sql"
TABLES = ("owner_repair", "conversation", "assertion")
# The kind list of 0031 (the newest migration that set it) and the pin.
KINDS = {"thread_close", "thread_reopen", "secret_found_out", "secret_keep", "fact_retract", "fact_correct",
         "name_split", "fact_lock", "fact_restore", "state_dismiss", "entity_exclude", "entity_pin"}


def kinds_of(url: str) -> set[str]:
    with psycopg.connect(url) as conn:
        check = conn.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
            " WHERE conrelid = 'owner_repair'::regclass AND conname = 'owner_repair_kind_check'").fetchone()[0]
    return set(re.findall(r"'(\w+)'", check))


def a_conversation(conn: psycopg.Connection) -> object:
    return conn.execute("INSERT INTO conversation (id, host, host_chat_ref) VALUES (%s, 'test', %s) RETURNING id",
                        (uuid7(), f"chat-{uuid7()}")).fetchone()[0]


def test_an_entity_pin_inserts_and_an_unknown_kind_is_still_refused(migrated):
    assert kinds_of(migrated) == KINDS
    with psycopg.connect(migrated) as conn:
        cid = a_conversation(conn)
        conn.execute("INSERT INTO owner_repair (id, conversation_id, kind, target, value) VALUES (%s, %s, 'entity_pin',"
                     " %s, '{}')", (uuid7(), cid, Jsonb({"entity_type": "character", "name": "세라"})))
        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.transaction():
                conn.execute("INSERT INTO owner_repair (id, conversation_id, kind, target, value) VALUES"
                             " (%s, %s, 'entity_star', '{}', '{}')", (uuid7(), cid))
        assert conn.execute("SELECT count(*) FROM owner_repair WHERE kind = 'entity_pin'").fetchone()[0] == 1


def state(url: str) -> dict[str, tuple[int, str | None]]:
    """Row count and id hash of each table the migration must leave as it was (A4)."""
    with psycopg.connect(url) as conn:
        return {t: conn.execute(f"SELECT count(*), md5(string_agg(id::text, ',' ORDER BY id)) FROM {t}").fetchone()
                for t in TABLES}


@pytest.mark.parametrize("dump", FIXTURES, ids=[p.stem for p in FIXTURES])
def test_every_upgrade_fixture_applies_0038_and_keeps_its_rows(dump, database_url, tmp_path):
    """A4: each earlier release's database, migrated up to the migration before 0038, then 0038 alone."""
    before_dir = tmp_path / "migrations"
    before_dir.mkdir()
    for path in migrations_dir().glob("[0-9][0-9][0-9][0-9]_*.sql"):
        if path.name < PIN:
            shutil.copy(path, before_dir / path.name)
    restore(database_url, dump)
    apply_migrations(database_url, directory=before_dir)
    assert "entity_pin" not in kinds_of(database_url)
    before = state(database_url)
    assert before["conversation"][0] > 0 and before["assertion"][0] > 0
    assert apply_migrations(database_url) == [PIN]
    assert state(database_url) == before
    assert kinds_of(database_url) == KINDS


def test_the_migration_says_where_it_comes_from():
    text = (Path(migrations_dir()) / PIN).read_text()
    assert "PHASE-60" in text and "ADR 0087" in text
