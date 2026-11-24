"""PHASE-61 S5: what the worker is doing, as counts from the job table (read-only)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import psycopg

from nmos_sidecar.extraction import worker_status

EMPTY = {"queued": {"extract": 0, "reveal": 0, "summarize": 0, "canon": 0, "embed": 0}, "queued_total": 0,
         "running": 0, "retrying": 0, "dead_recent": 0, "done_recent": 0, "recent_minutes": 30, "dead_hours": 24,
         "last_error": None}


def _conversation(conn: psycopg.Connection) -> str:
    conv = str(uuid4())
    conn.execute("INSERT INTO conversation (id, host, host_chat_ref) VALUES (%s, 'pocketrisu', %s)", (conv, conv))
    return conv


def _job(conn: psycopg.Connection, conv: str, kind: str, status: str, *, attempts: int = 0,
         error: str | None = None, ago: str = "0 seconds") -> None:
    conn.execute("INSERT INTO job (kind, dedupe_key, conversation_id, payload, status, attempts, last_error, updated_at)"
                 " VALUES (%s, %s, %s, '{}', %s, %s, %s, now() - %s::interval)",
                 (kind, str(uuid4()), conv, status, attempts, error, ago))


def test_an_empty_table_reads_as_all_zeros(db):
    assert worker_status(db) == EMPTY


def test_counts_by_kind_and_state(db):
    conv = _conversation(db)
    for kind, n in (("extract", 3), ("canon", 2), ("summarize", 1), ("custom_kind", 1)):
        for _ in range(n):
            _job(db, conv, kind, "queued")
    _job(db, conv, "extract", "queued", attempts=2, error="HTTP 429", ago="1 minute")  # waiting again after a failure
    _job(db, conv, "canon", "running")
    _job(db, conv, "canon", "running", attempts=1, error="HTTP 504")  # running again after a failure
    _job(db, conv, "extract", "queued", attempts=1)  # an attempt without an error is not a retry
    _job(db, conv, "extract", "dead", attempts=5, error="old", ago="25 hours")
    _job(db, conv, "extract", "dead", attempts=5, error="recent", ago="23 hours")
    _job(db, conv, "embed", "done", ago="31 minutes")
    _job(db, conv, "embed", "done", ago="29 minutes")
    _job(db, conv, "reveal", "done", ago="1 minute")
    _job(db, conv, "reveal", "obsolete", attempts=3, error="never shown")
    _job(db, conv, "only_obsolete", "obsolete")

    s = worker_status(db)
    assert s["queued"] == {"extract": 5, "reveal": 0, "summarize": 1, "canon": 2, "embed": 0, "custom_kind": 1,
                           "only_obsolete": 0}
    assert s["queued_total"] == 9
    assert (s["running"], s["retrying"], s["dead_recent"], s["done_recent"]) == (2, 2, 1, 2)
    assert s["last_error"]["text"] == "HTTP 504" and s["last_error"]["status"] == "running"


def test_the_last_error_is_the_newest_cut_and_on_one_line(db):
    conv = _conversation(db)
    _job(db, conv, "extract", "dead", attempts=5, error="older", ago="2 hours")
    long = "HTTP 504:\n  upstream\ttimed out\r\n\x07" + "x" * 400
    _job(db, conv, "canon", "queued", attempts=1, error=long, ago="5 minutes")
    _job(db, conv, "canon", "done", error="a finished job is not a failure", ago="1 minute")

    last = worker_status(db)["last_error"]
    assert last["kind"] == "canon" and last["status"] == "queued"
    assert last["text"].startswith("HTTP 504: upstream timed out x") and len(last["text"]) == 200
    assert "\n" not in last["text"] and "\x07" not in last["text"] and "  " not in last["text"]
    at = datetime.fromisoformat(last["at"])
    assert at.utcoffset().total_seconds() == 0 and abs((datetime.now(timezone.utc) - at).total_seconds() - 300) < 60
