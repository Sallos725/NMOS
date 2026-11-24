"""PHASE-61 S6 (ADR 0089): migration 0039, `model_call`. Additive: every earlier release's database passes through it
with its rows unchanged, and a row of no conversation, of a conversation, and one that breaks a check behave as the
table says. Synthetic names only."""

from __future__ import annotations

import shutil
from pathlib import Path

import psycopg
import pytest

from nmos_sidecar.ids import uuid7
from nmos_sidecar.migrate import apply_migrations, migrations_dir
from test_upgrade import FIXTURES, restore

CALLS = "0039_model_call.sql"
TABLES = ("conversation", "assertion", "extraction", "job", "retrieval_trace", "source_revision")


def state(url: str) -> dict[str, tuple]:
    """Row count and a hash of each row of each table the migration must leave as it was."""
    with psycopg.connect(url) as conn:
        return {t: conn.execute(f"SELECT count(*), md5(string_agg(x::text, ',' ORDER BY x::text)) FROM {t} x").fetchone()
                for t in TABLES}


@pytest.mark.parametrize("dump", FIXTURES, ids=[p.stem for p in FIXTURES])
def test_every_upgrade_fixture_applies_0039_and_keeps_its_rows(dump, database_url, tmp_path):
    """Each earlier release's database, migrated up to the migration before 0039, then 0039 alone."""
    before_dir = tmp_path / "migrations"
    before_dir.mkdir()
    for path in migrations_dir().glob("[0-9][0-9][0-9][0-9]_*.sql"):
        if path.name < CALLS:
            shutil.copy(path, before_dir / path.name)
    restore(database_url, dump)
    apply_migrations(database_url, directory=before_dir)
    with psycopg.connect(database_url) as conn:
        assert conn.execute("SELECT to_regclass('model_call')").fetchone()[0] is None
    before = state(database_url)
    assert before["conversation"][0] > 0 and before["assertion"][0] > 0
    shutil.copy(migrations_dir() / CALLS, before_dir / CALLS)  # 0039 alone, whatever later migrations come
    assert apply_migrations(database_url, directory=before_dir) == [CALLS]
    assert state(database_url) == before
    with psycopg.connect(database_url) as conn:
        assert conn.execute("SELECT count(*) FROM model_call").fetchone()[0] == 0


def a_conversation(conn: psycopg.Connection) -> object:
    return conn.execute("INSERT INTO conversation (id, host, host_chat_ref) VALUES (%s, 'test', %s) RETURNING id",
                        (uuid7(), f"chat-{uuid7()}")).fetchone()[0]


def insert(conn: psycopg.Connection, **kw) -> None:
    row = {"id": uuid7(), "kind": "extract", "conversation_id": None, "model": "model-a",
           "endpoint": "http://llm.test/v1", "outcome": "ok", "ms": 12, "error": None} | kw
    conn.execute("INSERT INTO model_call (id, kind, conversation_id, model, endpoint, outcome, ms, error)"
                 " VALUES (%(id)s, %(kind)s, %(conversation_id)s, %(model)s, %(endpoint)s, %(outcome)s, %(ms)s,"
                 " %(error)s)", row)


def test_the_table_takes_its_rows_and_refuses_what_its_checks_refuse(migrated):
    with psycopg.connect(migrated, autocommit=True) as conn:
        cid = a_conversation(conn)
        insert(conn)
        insert(conn, conversation_id=cid, kind="note", outcome="http", error="x" * 300)
        assert conn.execute("SELECT count(*) FROM model_call WHERE at IS NOT NULL").fetchone()[0] == 2
        for bad in ({"kind": "rerank"}, {"outcome": "slow"}, {"error": "x" * 301}):
            with pytest.raises(psycopg.errors.CheckViolation):
                insert(conn, **bad)
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            insert(conn, conversation_id=uuid7())
        # a job id is kept without a job: jobs are pruned, their calls stay
        conn.execute("INSERT INTO model_call (id, kind, job_id, model, endpoint, outcome, ms)"
                     " VALUES (%s, 'embed', 987654321, 'embed-a', 'http://embed.test/v1', 'ok', 3)", (uuid7(),))
        # deleting the conversation deletes its rows, others stay (the foreign key cascades)
        conn.execute("DELETE FROM conversation WHERE id = %s", (cid,))
        assert conn.execute("SELECT count(*) FROM model_call").fetchone()[0] == 2
        indexes = {r[0] for r in conn.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'model_call'")}
        assert {"model_call_at", "model_call_conversation"} <= indexes


def test_the_migration_says_where_it_comes_from():
    text = (Path(migrations_dir()) / CALLS).read_text()
    assert "PHASE-61" in text and "ADR 0089" in text
