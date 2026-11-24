"""PHASE-61 S6 (ADR 0089): reading the log of model calls. `calls.recent` (newest first, at most 500), `calls.summary`
(the last hour in numbers, the shape the Status card reads) and `GET /v1/worker/calls`. Synthetic names only."""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from conftest import make_client
from nmos_sidecar import calls
from nmos_sidecar.ids import uuid7


def log_row(conn: psycopg.Connection, outcome: str = "ok", status: int | None = None, ms: int = 10,
            minutes_ago: float = 1, conversation_id: Any = None, **kw: Any) -> None:
    row = {"id": uuid7(), "kind": "extract", "conversation_id": conversation_id, "job_id": None, "generation": None,
           "model": "model-a", "endpoint": "http://llm.test/v1", "outcome": outcome, "http_status": status, "ms": ms,
           "usage": None, "error": None} | kw
    conn.execute("INSERT INTO model_call (id, at, kind, conversation_id, job_id, generation, model, endpoint, outcome,"
                 " http_status, ms, usage, error) VALUES (%(id)s, now() - make_interval(secs => %(ago)s), %(kind)s,"
                 " %(conversation_id)s, %(job_id)s, %(generation)s, %(model)s, %(endpoint)s, %(outcome)s,"
                 " %(http_status)s, %(ms)s, %(usage)s, %(error)s)",
                 {**row, "ago": minutes_ago * 60, "usage": None if row["usage"] is None else Jsonb(row["usage"])})


def a_conversation(conn: psycopg.Connection) -> Any:
    return conn.execute("INSERT INTO conversation (id, host, host_chat_ref) VALUES (%s, 'test', %s) RETURNING id",
                        (uuid7(), f"chat-{uuid7()}")).fetchone()[0]


def test_recent_is_newest_first_clamped_and_filtered(migrated):
    with psycopg.connect(migrated, autocommit=True) as conn:
        cid = a_conversation(conn)
        for i in range(5):
            log_row(conn, minutes_ago=10 - i, ms=i, conversation_id=cid if i % 2 else None, job_id=i)
        rows = calls.recent(conn)
        assert [r["ms"] for r in rows] == [4, 3, 2, 1, 0]
        assert set(rows[0]) == {"at", *calls.COLUMNS} and isinstance(rows[0]["id"], str)
        assert rows[0]["at"].endswith("+00:00") and rows[1]["conversation_id"] == str(cid)
        assert len(calls.recent(conn, 0)) == 1 and len(calls.recent(conn, 2)) == 2
        assert [r["ms"] for r in calls.recent(conn, conversation_id=cid)] == [3, 1]
        for _ in range(500):
            log_row(conn, minutes_ago=30)
        assert len(calls.recent(conn, 9999)) == calls.MAX_LIMIT == 500


def test_the_summary_of_the_last_hour(migrated):
    with psycopg.connect(migrated, autocommit=True) as conn:
        assert calls.summary(conn) == {"minutes": 60, "total": 0, "ok": 0, "failed": 0,
                                       "by_fault": {"timeout": 0, "transport": 0, "bad_reply": 0, "http_other": 0},
                                       "median_ms": None, "last_ok_at": None, "last_failed_at": None}
        for ms in (10, 20, 30):
            log_row(conn, ms=ms, minutes_ago=5)
        for status, n in ((429, 4), (504, 2), (500, 1), (502, 1), (503, 1), (400, 1)):
            for _ in range(n):
                log_row(conn, "http", status, ms=100, minutes_ago=2)
        log_row(conn, "http", None, ms=100)  # an HTTP fault without a status counts as another
        for fault in ("timeout", "transport", "bad_reply"):
            log_row(conn, fault, ms=60000 if fault == "timeout" else 5, minutes_ago=1)
        log_row(conn, ms=1, minutes_ago=90)  # outside the hour
        out = calls.summary(conn)
    assert out["total"] == 17 and out["ok"] == 3 and out["failed"] == 14
    # the five most frequent statuses by name (a tie by the lower status), the rest summed
    assert out["by_fault"] == {"timeout": 1, "transport": 1, "bad_reply": 1, "http_other": 2,
                               "429": 4, "504": 2, "400": 1, "500": 1, "502": 1}
    assert out["median_ms"] == 100
    assert out["last_ok_at"] < out["last_failed_at"] and out["last_ok_at"].endswith("+00:00")
    with psycopg.connect(migrated) as conn:
        assert calls.summary(conn, minutes=120)["total"] == 18
        assert calls.summary(conn, minutes=0)["minutes"] == 1


def test_the_route_returns_the_calls_and_the_summary(migrated):
    with psycopg.connect(migrated, autocommit=True) as conn:
        cid = a_conversation(conn)
        log_row(conn, conversation_id=cid, usage={"calls": 1, "ms": 10, "input": 9, "output": 2}, job_id=42,
                generation="extract-k")
        log_row(conn, "http", 429, error="HTTP 429: slow down")
    with make_client(migrated) as c:
        out = c.get("/v1/worker/calls").json()
        assert [r["outcome"] for r in out["calls"]] == ["http", "ok"]
        assert out["calls"][1] | {"id": "x", "at": "y"} == {
            "id": "x", "at": "y", "kind": "extract", "conversation_id": str(cid), "job_id": 42,
            "generation": "extract-k", "model": "model-a", "endpoint": "http://llm.test/v1", "outcome": "ok",
            "http_status": None, "ms": 10, "usage": {"calls": 1, "ms": 10, "input": 9, "output": 2}, "error": None}
        assert out["summary"]["total"] == 2 and out["summary"]["by_fault"]["429"] == 1
        assert len(c.get("/v1/worker/calls", params={"limit": 1}).json()["calls"]) == 1
        assert len(c.get("/v1/worker/calls", params={"conversation_id": str(cid)}).json()["calls"]) == 1
        assert c.get("/v1/worker/calls", params={"conversation_id": "not-a-uuid"}).status_code == 422
        del c.headers["Authorization"]
        assert c.get("/v1/worker/calls").status_code == 401
