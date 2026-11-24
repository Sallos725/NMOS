"""PHASE-61 S6 (ADR 0089): where model calls are logged. Every worker job's calls (one row per call, with the job's
kind, conversation, id and generation), the author's note (`note`) and the settings test (`test`); never the request
path (`/v1/retrieve`). A row outlives its job's failed attempt; a failed log write fails no job. Stub transports and
the suite's stub models only; synthetic names only."""

from __future__ import annotations

import logging
from typing import Any

import httpx
import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import calls, llm, notes, runtime, worker
from nmos_sidecar.config import Settings
from nmos_sidecar.runtime import effective, stored
from test_generations import EMB, LLM
from test_phase61_calls import reply, stub
from test_phase61_pins import BASE
from test_sidecar_integration import recall, sync
from test_summaries import story_chat

ONLY_EXTRACT = {**LLM, "summaries": False, "canon_facts": False}
EMPTY = reply('{"assertions": []}', usage={"prompt_tokens": 120, "completion_tokens": 7})


def rows_of(url: str) -> list[dict[str, Any]]:
    with psycopg.connect(url) as conn:
        return list(reversed(calls.recent(conn, 500)))  # oldest first


def queued_chat(url: str, turns: int = 3) -> None:
    with make_client(url, **ONLY_EXTRACT) as c:
        sync(c, story_chat(turns))


def run_jobs(url: str, log_to: str | None) -> bool:
    """Run one job as the worker does (its handlers from the saved settings)."""
    with psycopg.connect(url, row_factory=dict_row, autocommit=True) as conn:
        jobs = worker.handlers(effective(Settings(database_url=url, **ONLY_EXTRACT), stored(conn)), log_to=log_to)
        return worker.run_once(conn, jobs)


def ran(url: str) -> dict[str, Any]:
    """The one job a worker has attempted."""
    with psycopg.connect(url, row_factory=dict_row) as conn:
        (job,) = conn.execute("SELECT * FROM job WHERE attempts > 0").fetchall()
        return job


def test_an_extraction_that_answers_writes_an_ok_row_with_its_usage_and_the_jobs_ids(migrated, monkeypatch):
    queued_chat(migrated)
    sent = stub(monkeypatch, EMPTY)
    assert run_jobs(migrated, migrated)
    job = ran(migrated)
    (row,) = rows_of(migrated)
    assert len(sent) == 1
    assert row["kind"] == "extract" and row["outcome"] == "ok" and row["error"] is None
    assert row["usage"]["input"] == 120 and row["usage"]["output"] == 7 and row["usage"]["calls"] == 1
    assert row["job_id"] == job["id"] and row["conversation_id"] == str(job["conversation_id"])
    assert row["generation"] == job["payload"]["generation"]
    assert row["model"] == "fake" and row["endpoint"] == "http://fake-llm/v1" and row["ms"] >= 0


def test_a_429_then_a_200_leave_both_rows_though_the_first_attempt_rolled_back(migrated, monkeypatch):
    queued_chat(migrated)
    stub(monkeypatch, httpx.Response(429, text="rate limited, try later"), EMPTY)
    assert run_jobs(migrated, migrated)
    job = ran(migrated)
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        failed = conn.execute("SELECT status, last_error FROM job WHERE id = %s", (job["id"],)).fetchone()
        assert failed["status"] == "queued" and failed["last_error"].startswith("HTTP 429")
        conn.execute("UPDATE job SET run_after = now() WHERE id = %s", (job["id"],))  # the retry, now
    assert run_jobs(migrated, migrated)
    first, second = rows_of(migrated)
    assert (first["outcome"], first["http_status"], first["error"]) == ("http", 429, "HTTP 429: rate limited, try later")
    assert (second["outcome"], second["http_status"]) == ("ok", None)
    assert first["job_id"] == second["job_id"] == job["id"]
    with psycopg.connect(migrated) as conn:
        assert conn.execute("SELECT status FROM job WHERE id = %s", (job["id"],)).fetchone()[0] == "done"


def test_a_call_that_times_out_writes_a_timeout_row(migrated, monkeypatch):
    queued_chat(migrated)
    stub(monkeypatch, httpx.ReadTimeout("timed out"))
    assert run_jobs(migrated, migrated)
    (row,) = rows_of(migrated)
    assert (row["outcome"], row["http_status"], row["error"]) == ("timeout", None, "ReadTimeout")


def test_every_call_of_a_job_writes_its_own_row_with_the_jobs_id(migrated, monkeypatch):
    """An extraction's confirmation calls go through the same `complete` as the extraction (`process_extract`)."""
    queued_chat(migrated)
    stub(monkeypatch, EMPTY)

    def three_calls(conn, job, complete, gen, turns):
        for _ in range(3):
            complete("SYS", "사용자")
        return "done"

    monkeypatch.setattr(worker, "process_extract", three_calls)
    assert run_jobs(migrated, migrated)
    job = ran(migrated)
    rows = rows_of(migrated)
    assert len(rows) == 3 and {r["job_id"] for r in rows} == {job["id"]} and {r["kind"] for r in rows} == {"extract"}


def test_a_log_write_that_fails_fails_no_job_and_warns_once(migrated, monkeypatch, caplog):
    queued_chat(migrated)
    stub(monkeypatch, EMPTY)
    monkeypatch.setattr(calls, "_INSERT", "INSERT INTO no_such_table VALUES (1)")
    with caplog.at_level(logging.WARNING):
        assert run_jobs(migrated, migrated)
    job = ran(migrated)
    assert [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING] == \
        ["model call not logged: UndefinedTable"]
    with psycopg.connect(migrated) as conn:
        assert conn.execute("SELECT status FROM job WHERE id = %s", (job["id"],)).fetchone()[0] == "done"
    assert rows_of(migrated) == []


def test_without_an_observer_nothing_is_written(migrated, monkeypatch):
    queued_chat(migrated)
    sent = stub(monkeypatch, EMPTY)
    assert run_jobs(migrated, None)
    assert len(sent) == 1 and rows_of(migrated) == []


def test_the_worker_logs_to_its_own_database(monkeypatch):
    """The maintenance builds its handlers with `log_to` = the worker's database; a handler's model stays bare."""
    seen: list[str | None] = []
    real = worker.handlers
    monkeypatch.setattr(worker, "handlers", lambda s, log_to=None: seen.append(log_to) or real(s, log_to))
    monkeypatch.setattr(worker, "stored", lambda conn: {})

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, *a, **k):
            raise psycopg.OperationalError("stop here")

    monkeypatch.setattr(worker.psycopg, "connect", lambda *a, **k: Conn())
    import threading
    stop = threading.Event()
    monkeypatch.setattr(stop, "wait", lambda *_: stop.set())
    worker.maintenance(Settings(**BASE), stop, {"jobs": {}})
    assert seen == ["postgresql://x"]


# --- the sidecar's own calls ------------------------------------------------------------------------------------------

def a_conversation(url: str) -> Any:
    from nmos_sidecar.ids import uuid7

    with psycopg.connect(url, autocommit=True) as conn:
        return conn.execute("INSERT INTO conversation (id, host, host_chat_ref) VALUES (%s, 'test', 'chat-n')"
                            " RETURNING id", (uuid7(),)).fetchone()[0]


def test_the_authors_note_model_logs_a_note_of_its_chat(migrated, monkeypatch):
    cid = a_conversation(migrated)
    stub(monkeypatch, reply('{"lines": []}'))
    notes.model_for(Settings(**BASE), log_to=migrated, conversation_id=cid)("SYS", "사용자")
    (row,) = rows_of(migrated)
    assert row["kind"] == "note" and row["conversation_id"] == str(cid) and row["job_id"] is None
    stub(monkeypatch, reply('{"lines": []}'))
    notes.model_for(Settings(**BASE))("SYS", "사용자")  # without `log_to`: as before, nothing
    assert len(rows_of(migrated)) == 1


def test_the_note_route_asks_for_a_logged_model(migrated, monkeypatch):
    asked: list[dict[str, Any]] = []
    monkeypatch.setattr(notes, "model_for", lambda settings, **kw: asked.append(kw) or None)
    with make_client(migrated, **ONLY_EXTRACT) as c:
        chat = story_chat(2)
        sync(c, chat)
        cid = next(x["id"] for x in c.get("/v1/conversations").json() if x["host_chat_ref"] == chat.id)
        assert c.post(f"/v1/conversations/{cid}/notes", json={"sections": ["diverged"]}).status_code == 200
    assert [(kw["log_to"], str(kw["conversation_id"])) for kw in asked] == [(migrated, cid)]


def test_the_settings_test_logs_a_test_call(migrated, monkeypatch):
    with make_client(migrated, **LLM) as c:
        stub(monkeypatch, httpx.Response(401, text="no such key"))
        out = c.post("/v1/config/test", json={"kind": "llm"}).json()
    assert out["ok"] is False
    (row,) = rows_of(migrated)
    assert (row["kind"], row["outcome"], row["http_status"]) == ("test", "http", 401)
    assert row["conversation_id"] is None and row["job_id"] is None and row["generation"] is None

    def answered(coro):
        coro.close()
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.5, 0.5]}]})

    monkeypatch.setattr(llm.asyncio, "run", answered)
    assert runtime.test_embeddings("http://fake-emb/v1", "fake-embed", "",
                                   observer=calls.observer(migrated, "test"))["ok"] is True
    assert [(r["kind"], r["outcome"], r["model"]) for r in rows_of(migrated)][1] == ("test", "ok", "fake-embed")


def test_a_retrieve_writes_no_row(migrated, monkeypatch):
    """The request path's query embedding (the real `Embedder` the sidecar builds, stubbed at its transport) is not
    observed, and a recall writes no `model_call` row."""
    embedded: list[Any] = []

    def embed(self, texts, timeout_s):
        embedded.append(self.observer)
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(llm.Embedder, "embed", embed)
    with make_client(migrated, **LLM, **EMB, summaries=False, canon_facts=False) as c:
        chat = story_chat(3)
        sync(c, chat)
        recall(c, chat, "Where does turn 1 begin?")
    assert embedded and all(o is None for o in embedded)
    assert rows_of(migrated) == []
