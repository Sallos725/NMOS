"""PHASE-61 S6 (ADR 0089): how long the log of model calls is kept and where it never goes. The worker's maintenance
prunes it with the traces (`NMOS_TRACE_RETENTION_DAYS`); no archive holds it and a restore neither needs nor touches
it (like `job`); deleting a chat deletes its rows. Synthetic names only."""

from __future__ import annotations

from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from nmos_sidecar import archive, worker
from nmos_sidecar.ids import uuid7
from test_archive import play, read
from test_generations import conv_id
from test_restore import client, export_to


def log_row(conn: psycopg.Connection, conversation_id=None, days_ago: float = 0, kind: str = "extract") -> None:
    conn.execute("INSERT INTO model_call (id, at, kind, conversation_id, model, endpoint, outcome, ms)"
                 " VALUES (%s, now() - make_interval(secs => %s), %s, %s, 'model-a', 'http://llm.test/v1', 'ok', 5)",
                 (uuid7(), days_ago * 86400, kind, conversation_id))


def count(url: str, where: str = "true", args: tuple = ()) -> int:
    with psycopg.connect(url) as conn:
        return conn.execute(f"SELECT count(*) FROM model_call WHERE {where}", args).fetchone()[0]


def test_the_maintenance_prunes_calls_older_than_the_trace_retention(migrated):
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        for days in (0, 1, 29.9, 30.1, 400):
            log_row(conn, days_ago=days)
        worker.prune(conn, 30)
        assert count(migrated) == 3
        worker.prune(conn, 1)
        assert count(migrated) == 1
        # 0 has no meaning of its own, as for the traces: nothing older than now is kept past the next pass
        worker.prune(conn, 0)
        assert count(migrated) == 0


def test_no_archive_holds_the_log_and_a_restore_leaves_it_as_it_is(migrated, tmp_path: Path):
    assert "model_call" in archive.NEVER and "model_call" not in archive.KNOWN
    with client(migrated) as c:
        chat, branch = play(c, migrated)
        cid, bid = conv_id(c, chat), conv_id(c, branch)
        with psycopg.connect(migrated, autocommit=True) as conn:
            log_row(conn, cid)
            log_row(conn, bid, kind="summarize")
            log_row(conn, None, kind="test")
        whole = export_to(tmp_path, migrated, "whole")
        source = export_to(tmp_path, migrated, "chat", conversations=[cid])
        for path in (whole, source):
            manifest, tables, _ = read(path.read_bytes())
            assert "model_call" not in tables
            assert "model_call" not in {f["table"] for f in manifest["files"]}
        res = c.post(f"/v1/conversations/{cid}/delete")
        assert res.status_code == 200 and res.json()["deleted"]["model_calls"] == 1
    assert count(migrated) == 2 and count(migrated, "conversation_id = %s", (cid,)) == 0
    with psycopg.connect(migrated) as conn:
        before = conn.execute("SELECT id, at, kind, conversation_id FROM model_call ORDER BY id").fetchall()
    done = archive.restore_file(migrated, str(source))
    assert "model_call" not in done.rows
    with psycopg.connect(migrated) as conn:  # the chat came back without a log; the others' rows are untouched
        assert conn.execute("SELECT id, at, kind, conversation_id FROM model_call ORDER BY id").fetchall() == before
        assert conn.execute("SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'nmos_restore_%'").fetchone()[0] == 0


def test_deleting_a_chat_deletes_its_calls_and_no_others(migrated):
    with psycopg.connect(migrated, autocommit=True) as conn:
        a, b = (conn.execute("INSERT INTO conversation (id, host, host_chat_ref) VALUES (%s, 'test', %s) RETURNING id",
                             (uuid7(), f"chat-{n}")).fetchone()[0] for n in ("a", "b"))
        for cid in (a, a, b):
            log_row(conn, cid)
        from nmos_sidecar.ledger import delete_conversation

        assert delete_conversation(conn, a)["model_calls"] == 2
        # a row removed by the foreign key alone (an image without the step) goes the same way
        conn.execute("DELETE FROM conversation WHERE id = %s", (b,))
    assert count(migrated) == 0
