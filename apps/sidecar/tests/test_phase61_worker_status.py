"""PHASE-61 S5: what the worker is doing, as counts from the job table (read-only)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import psycopg

from conftest import make_client
from nmos_sidecar import calls
from nmos_sidecar.extraction import worker_status
from test_phase61_calls_read import log_row

EMPTY = {"queued": {"extract": 0, "reveal": 0, "summarize": 0, "canon": 0, "embed": 0}, "queued_total": 0,
         "set_aside": 0, "running": 0, "retrying": 0, "dead_recent": 0, "done_recent": 0, "recent_minutes": 30,
         "dead_hours": 24, "last_error": None}
NO_CALLS = {"minutes": 60, "total": 0, "ok": 0, "failed": 0,
            "by_fault": {"timeout": 0, "transport": 0, "bad_reply": 0, "http_other": 0},
            "median_ms": None, "last_ok_at": None, "last_failed_at": None}


def _conversation(conn: psycopg.Connection) -> str:
    conv = str(uuid4())
    conn.execute("INSERT INTO conversation (id, host, host_chat_ref) VALUES (%s, 'pocketrisu', %s)", (conv, conv))
    return conv


def _job(conn: psycopg.Connection, conv: str, kind: str, status: str, *, attempts: int = 0,
         error: str | None = None, ago: str = "0 seconds") -> None:
    conn.execute("INSERT INTO job (kind, dedupe_key, conversation_id, payload, status, attempts, last_error,"
                 " updated_at) VALUES (%s, %s, %s, '{}', %s, %s, %s, now() - %s::interval)",
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


def test_a_job_of_a_generation_that_is_no_longer_active_is_set_aside_not_waiting(db):
    """No worker claims a job of a generation its kind left (a model change with "carry on" leaves them queued), so
    it must not read as waiting, or as being retried, for ever."""
    conv = _conversation(db)
    for key, ago in (("canon-old", "2 hours"), ("canon-new", "1 hour"), ("extract-only", "1 hour")):
        db.execute("INSERT INTO projection_generation (key, kind, model, endpoint, spec, activated_at)"
                   " VALUES (%s, %s, 'm', 'e', '{}', now() - %s::interval)", (key, key.split("-")[0], ago))

    def job(kind: str, generation: str | None, status: str = "queued", **more) -> None:
        _job(db, conv, kind, status, **more)
        if generation:
            db.execute("UPDATE job SET payload = jsonb_build_object('generation', %s::text)"
                       " WHERE id = (SELECT max(id) FROM job)", (generation,))

    job("canon", "canon-old")
    job("canon", "canon-old", attempts=2, error="HTTP 504")  # not a retry either: nothing will try it
    job("canon", "canon-new")
    job("canon", "canon-new", attempts=1, error="HTTP 429")
    job("canon", None)                                       # a job that names no generation waits as before
    job("extract", "extract-only")
    job("embed", "embed-unknown")                            # a kind with no generation row: waits as before
    job("canon", "canon-old", "dead", attempts=5, error="gone")

    s = worker_status(db)
    assert s["queued"] == {"extract": 1, "reveal": 0, "summarize": 0, "canon": 3, "embed": 1}
    assert (s["queued_total"], s["set_aside"], s["retrying"], s["dead_recent"]) == (5, 2, 1, 1)


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
    assert last["at"].endswith("+00:00") and "." not in last["at"]  # whole seconds, UTC
    at = datetime.fromisoformat(last["at"])
    assert at.utcoffset().total_seconds() == 0 and abs((datetime.now(timezone.utc) - at).total_seconds() - 300) < 60


def test_the_route_answers_with_the_counts_and_needs_the_token(migrated):
    with make_client(migrated) as c:
        res = c.get("/v1/worker/status")
        assert res.status_code == 200 and res.json() == {**EMPTY, "calls": NO_CALLS}
        with psycopg.connect(migrated, autocommit=True) as conn:
            _job(conn, _conversation(conn), "extract", "queued", attempts=1, error="HTTP 429")
        body = c.get("/v1/worker/status").json()
        assert body["queued"]["extract"] == 1 and body["retrying"] == 1
        assert set(body["last_error"]) == {"kind", "status", "at", "text"}
        del c.headers["Authorization"]
        assert c.get("/v1/worker/status").status_code == 401


def test_the_route_carries_the_last_hour_of_calls(migrated):
    with psycopg.connect(migrated, autocommit=True) as conn:
        for ms in (1000, 3000, 5000):
            log_row(conn, ms=ms, minutes_ago=5)
        log_row(conn, "http", 429, ms=200, minutes_ago=2)
        log_row(conn, "timeout", ms=60000, minutes_ago=1)
        log_row(conn, ms=1, minutes_ago=90)  # outside the hour
    with make_client(migrated) as c:
        body = c.get("/v1/worker/status").json()
    assert {k: v for k, v in body.items() if k != "calls"} == EMPTY
    out = body["calls"]
    assert (out["minutes"], out["total"], out["ok"], out["failed"], out["median_ms"]) == (60, 5, 3, 2, 3000)
    assert out["by_fault"] == {"timeout": 1, "transport": 0, "bad_reply": 0, "http_other": 0, "429": 1}
    assert out["last_ok_at"] < out["last_failed_at"]


def test_a_failed_call_log_read_gives_null_and_keeps_the_rest(migrated, monkeypatch):
    with make_client(migrated) as c:
        with psycopg.connect(migrated, autocommit=True) as conn:  # after the start, as the route test does
            _job(conn, _conversation(conn), "extract", "queued", attempts=1, error="HTTP 429")
        monkeypatch.setattr(calls, "summary", lambda conn, minutes=60: 1 / 0)
        body = c.get("/v1/worker/status").json()
        assert body["calls"] is None and body["queued"]["extract"] == 1 and body["retrying"] == 1
        monkeypatch.undo()
        # a failing statement (the table missing on a database not migrated): the route keeps answering, request after
        # request (the summary is the route's last read, so this does not tell its savepoint from the pool's rollback)
        with psycopg.connect(migrated, autocommit=True) as conn:
            conn.execute("DROP TABLE model_call")
        for _ in range(3):
            res = c.get("/v1/worker/status")
            assert res.status_code == 200 and res.json()["calls"] is None
            assert res.json()["queued"]["extract"] == 1 and res.json()["last_error"]["text"] == "HTTP 429"
