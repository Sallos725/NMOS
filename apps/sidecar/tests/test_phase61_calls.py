"""PHASE-61 S6 (ADR 0089): a log of model calls, the parts below the call sites. A row is built from a call's facts
(`calls.record_of`), keeps no reply text and no key, says how the call ended (`llm.call_outcome`), and is written in a
connection of its own, bounded and fail open (`calls.write`). Stub transports only; synthetic names only."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
import psycopg
import pytest

from nmos_sidecar import calls, llm
from nmos_sidecar.archive import MIN_SECRET
from nmos_sidecar.ids import uuid7

MARKER = "세라-MARKER-카이토"  # chat text a reply may hold: it must never reach a row
KEY = "sk-test-0123456789abcdef"


def stub(monkeypatch, *answers: Any) -> list[dict[str, Any]]:
    """`httpx.post` answering each call with the next of `answers` (a Response, or an exception to raise)."""
    sent: list[dict[str, Any]] = []
    queue = list(answers)

    def post(url, json, headers, timeout):
        sent.append({"url": url, "json": json})
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(answer, BaseException):
            raise answer
        return answer

    monkeypatch.setattr(llm.httpx, "post", post)
    return sent


def reply(content: Any, **extra: Any) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}], **extra})


def observed_facts(model: llm.ChatModel | llm.Embedder, call) -> tuple[list[dict[str, Any]], BaseException | None]:
    facts: list[dict[str, Any]] = []
    twin = model.observed(facts.append)
    try:
        call(twin)
    except llm.LLMError as exc:
        return facts, exc
    return facts, None


def chat(url: str = "http://llm.test/v1", key: str = "") -> llm.ChatModel:
    return llm.ChatModel(url, "model-a", key, timeout_s=5)


def complete(m: llm.ChatModel) -> Any:
    return m.complete_metered("SYS", "사용자")


# --- step 2: a row ----------------------------------------------------------------------------------------------------

def test_the_endpoint_never_keeps_a_user_a_password_or_a_query():
    assert calls.endpoint_of("https://user:pass@host/v1?key=x") == "https://host/v1"
    assert calls.endpoint_of("HTTP://Host:8080/v1/#frag") == "http://host:8080/v1"
    assert calls.endpoint_of("http://llm.test/v1/") == "http://llm.test/v1"


def test_a_row_has_every_column_and_an_error_on_one_line_cut_to_300():
    started = time.monotonic() - 0.25
    row = calls.record_of("extract", "model-a", "http://llm.test/v1", started, outcome="http", http_status=429,
                          usage={"calls": 1, "ms": 250, "input": 10, "output": 2, "model": "model-a@x", "odd": "no"},
                          error="HTTP 429:\n\n  slow   down " + "x" * 400, conversation_id=str(uuid7()), job_id=7,
                          generation="extract-abc")
    assert set(row) == set(calls.COLUMNS)
    assert row["error"].startswith("HTTP 429: slow down x") and len(row["error"]) == 300
    assert row["usage"] == {"calls": 1, "ms": 250, "input": 10, "output": 2, "model": "model-a@x"}
    assert 240 <= row["ms"] < 5000 and row["http_status"] == 429 and row["job_id"] == 7
    ok = calls.record_of("embed", "embed-a", "http://embed.test/v1", started, outcome="ok", http_status=200,
                         error="ignored")
    assert ok["error"] is None and ok["http_status"] is None and ok["usage"] is None
    with pytest.raises(ValueError):
        calls.record_of("rerank", "m", "http://x", started, outcome="ok")
    with pytest.raises(ValueError):
        calls.record_of("extract", "m", "http://x", started, outcome="slow")


def test_a_bad_reply_keeps_the_kind_of_fault_only():
    started = time.monotonic()
    for error in (MARKER, f"invalid JSON in model reply: {MARKER}", None):
        row = calls.record_of("extract", "m", "http://x", started, outcome="bad_reply", error=error)
        assert row["error"] == calls.UNREADABLE
    for fault in calls.BAD_REPLY:
        assert calls.record_of("extract", "m", "http://x", started, outcome="bad_reply", error=fault)["error"] == fault
    # a timeout or a transport fault keeps an exception class name, nothing longer
    assert calls.record_of("embed", "m", "http://x", started, outcome="timeout", error="ReadTimeout")["error"] \
        == "ReadTimeout"
    assert calls.record_of("embed", "m", "http://x", started, outcome="transport",
                           error=f"failed for {MARKER}")["error"] == "transport"


@pytest.mark.parametrize("answer", [
    reply(f"{MARKER} and no JSON at all"),                              # no JSON object
    reply('{"assertions": [' + f'"{MARKER}",' + ' oops]}'),             # invalid JSON
    reply(f'["{MARKER}"]'),                                             # not a JSON object
    reply({"text": MARKER}),                                            # content is not text
    httpx.Response(200, text=f"{MARKER} plain text"),                   # not JSON
    httpx.Response(200, json={"choices": [], "note": MARKER}),          # unexpected response shape
], ids=["no-object", "invalid", "not-object", "not-text", "not-json", "shape"])
def test_no_path_puts_reply_text_into_a_row(monkeypatch, answer):
    stub(monkeypatch, answer)
    rows: list[dict[str, Any]] = []
    monkeypatch.setattr(calls, "write", lambda dsn, row: rows.append(row) or True)
    with pytest.raises(llm.ReplyError) as raised:
        chat().observed(calls.observer("postgresql://unused", "extract")).complete_metered("SYS", "사용자")
    assert MARKER in raised.value.raw  # the job still sees the reply, as before
    (row,) = rows
    assert row["outcome"] == "bad_reply" and row["error"] in calls.BAD_REPLY
    assert MARKER not in repr(row)


def test_a_key_is_never_stored(monkeypatch):
    assert calls.MIN_SECRET == MIN_SECRET
    rows: list[dict[str, Any]] = []
    monkeypatch.setattr(calls, "write", lambda dsn, row: rows.append(row) or True)
    # the provider echoes the key, past the point where the error is cut: no part of it survives the cut
    stub(monkeypatch, httpx.Response(401, text="x" * 285 + f" invalid key {KEY} given"))
    with pytest.raises(llm.ReplyError):
        chat(key=KEY).observed(calls.observer("postgresql://unused", "test")).complete_metered("SYS", "사용자")
    (row,) = rows
    assert row["http_status"] == 401 and KEY[:7] not in repr(row) and len(row["error"]) <= 300
    stub(monkeypatch, httpx.Response(401, text=f"invalid key {KEY}"))
    with pytest.raises(llm.ReplyError):
        chat(key=KEY).observed(calls.observer("postgresql://unused", "test")).complete_metered("SYS", "사용자")
    assert rows[1]["error"] == f"HTTP 401: invalid key {calls.REDACTED}"
    # the guard on the row itself: an endpoint or a model holding the key
    started = time.monotonic()
    row = calls.record_of("test", f"model-{KEY}", f"https://host/{KEY}/v1", started, outcome="http", http_status=403,
                          error=f"denied {KEY}", usage={"model": KEY})
    safe = calls.redact(row, [KEY, "", None, "ab"])
    assert KEY not in repr(safe) and safe["endpoint"] == f"https://host/{calls.REDACTED}/v1"
    assert calls.redact(row, ["", None]) == row  # no key, or one too short to look for: nothing replaced


# --- step 3: how a call ended -----------------------------------------------------------------------------------------

def test_every_end_of_a_chat_call(monkeypatch):
    stub(monkeypatch, reply('{"ok": true}', usage={"prompt_tokens": 5, "completion_tokens": 1}))
    facts, exc = observed_facts(chat(), complete)
    assert exc is None and facts[0]["outcome"] == "ok" and facts[0]["usage"]["input"] == 5
    assert facts[0]["model"] == "model-a" and facts[0]["url"] == "http://llm.test/v1"

    stub(monkeypatch, httpx.Response(429, text="slow down"))
    facts, exc = observed_facts(chat(), complete)
    assert str(exc) == "HTTP 429: slow down"  # the message is what it was
    assert (exc.fault, exc.status) == ("http", 429) and llm.call_outcome(exc) == ("http", 429, "HTTP 429: slow down")
    assert facts[0]["outcome"] == "http" and facts[0]["http_status"] == 429

    stub(monkeypatch, httpx.ReadTimeout("read timed out"))
    facts, exc = observed_facts(chat(), complete)
    assert str(exc).startswith("request failed: ") and llm.call_outcome(exc) == ("timeout", None, "ReadTimeout")

    stub(monkeypatch, httpx.ConnectError("refused"))
    facts, exc = observed_facts(chat(), complete)
    assert llm.call_outcome(exc) == ("transport", None, "ConnectError") and facts[0]["outcome"] == "transport"

    stub(monkeypatch, reply("no json here"))
    facts, exc = observed_facts(chat(), complete)
    assert str(exc) == "no JSON object in model reply"
    assert llm.call_outcome(exc) == ("bad_reply", None, "no JSON object")
    assert llm.call_outcome(None) == ("ok", None, None)


def test_every_end_of_an_embedding_call(monkeypatch):
    emb = llm.Embedder("http://embed.test/v1", "embed-a")
    metered = lambda e: e.embed_metered(["하나"], timeout_s=5)  # noqa: E731
    stub(monkeypatch, httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1]}],
                                                "usage": {"total_tokens": 3}}))
    facts, exc = observed_facts(emb, metered)
    assert exc is None and facts[0]["outcome"] == "ok" and facts[0]["usage"]["input"] == 3
    stub(monkeypatch, httpx.Response(504, text="gateway timeout"))
    facts, exc = observed_facts(emb, metered)
    assert str(exc) == "embedding HTTP 504: gateway timeout"
    assert llm.call_outcome(exc) == ("http", 504, "HTTP 504: gateway timeout")
    stub(monkeypatch, httpx.WriteTimeout("slow"))
    assert llm.call_outcome(observed_facts(emb, metered)[1]) == ("timeout", None, "WriteTimeout")
    stub(monkeypatch, httpx.Response(200, text="<html>"))
    assert llm.call_outcome(observed_facts(emb, metered)[1]) == ("bad_reply", None, "not JSON")
    stub(monkeypatch, httpx.Response(200, json={"rows": []}))
    assert llm.call_outcome(observed_facts(emb, metered)[1]) == ("bad_reply", None, "unexpected response shape")

    # `embed` (the settings test's) runs its request in `asyncio.run`: its whole-deadline timeout is a TimeoutError
    def late(coro):
        coro.close()
        raise TimeoutError

    monkeypatch.setattr(llm.asyncio, "run", late)
    facts, exc = observed_facts(emb, lambda e: e.embed(["하나"], timeout_s=1))
    assert str(exc) == "embedding request exceeded 1 s total deadline"
    assert llm.call_outcome(exc) == ("timeout", None, "TimeoutError")

    def answered(coro):
        coro.close()
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.5, 0.5]}]})

    monkeypatch.setattr(llm.asyncio, "run", answered)
    facts, exc = observed_facts(emb, lambda e: e.embed(["하나"], timeout_s=1))
    assert exc is None and facts[0]["outcome"] == "ok"


def test_an_error_that_made_no_call_tells_no_one():
    assert llm.call_outcome(llm.LLMError("the key gave no token")) is None
    assert llm.call_outcome(ValueError("x")) is None
    told: list[dict[str, Any]] = []
    llm.tell(told.append, time.monotonic(), "m", "http://x", "", llm.LLMError("no token"), None)
    assert told == []


def test_a_failing_observer_never_breaks_the_call(monkeypatch, caplog):
    stub(monkeypatch, reply('{"ok": true}'))

    def broken(facts):
        raise RuntimeError(f"observer bug {MARKER}")

    with caplog.at_level(logging.WARNING, logger="nmos.llm"):
        parsed, _, _ = chat().observed(broken).complete_metered("SYS", "사용자")
    assert parsed == {"ok": True}
    (record,) = [r for r in caplog.records if r.name == "nmos.llm"]
    assert record.getMessage() == "model call observer failed: RuntimeError"
    stub(monkeypatch, httpx.Response(500, text="boom"))
    with pytest.raises(llm.ReplyError, match="HTTP 500"):  # the call's own error, not the observer's
        chat().observed(broken).complete_metered("SYS", "사용자")


def test_without_an_observer_nothing_is_told_and_the_model_is_shared_unchanged(monkeypatch):
    stub(monkeypatch, reply('{"ok": true}'))
    base = chat()
    assert base.observer is None and llm.Embedder("http://e", "m").observer is None
    told: list[dict[str, Any]] = []
    twin = base.observed(told.append)
    assert base.observer is None and twin.observer is not None and twin.model == base.model
    base.complete_metered("SYS", "사용자")
    assert told == []


# --- step 4: writing a row --------------------------------------------------------------------------------------------

def a_conversation(conn: psycopg.Connection) -> Any:
    return conn.execute("INSERT INTO conversation (id, host, host_chat_ref) VALUES (%s, 'test', %s) RETURNING id",
                        (uuid7(), f"chat-{uuid7()}")).fetchone()[0]


def a_row(**kw: Any) -> dict[str, Any]:
    return calls.record_of("extract", "model-a", "http://llm.test/v1", time.monotonic(), outcome="ok",
                           usage={"calls": 1, "ms": 3, "input": 4}, **kw)


def test_a_row_is_written_and_survives_the_rollback_of_the_transaction_around_it(migrated):
    with psycopg.connect(migrated) as job_conn:  # a job's transaction, open while the call's row is written
        cid = a_conversation(job_conn)
        job_conn.commit()
        job_conn.execute("UPDATE conversation SET host_chat_name = 'x' WHERE id = %s", (cid,))
        assert calls.write(migrated, a_row(conversation_id=cid, job_id=11, generation="extract-k"))
        job_conn.rollback()
    with psycopg.connect(migrated) as conn:
        (row,) = calls.recent(conn)
    assert row["conversation_id"] == str(cid) and row["job_id"] == 11 and row["usage"]["input"] == 4
    assert row["kind"] == "extract" and row["endpoint"] == "http://llm.test/v1" and row["at"].endswith("+00:00")


def test_a_nul_in_a_provider_error_or_model_name_does_not_lose_the_row(migrated):
    """PostgreSQL text and jsonb hold no NUL: a provider's error body with one would fail the write and drop the row."""
    row = calls.record_of("extract", "model\x00-a", "http://llm.test/v1", time.monotonic(), outcome="http",
                          http_status=400, error="HTTP 400: bad\x00 request",
                          usage={"calls": 1, "model": "model\x00-a@x"})
    assert (row["model"], row["error"], row["usage"]["model"]) == ("model-a", "HTTP 400: bad request", "model-a@x")
    assert calls.write(migrated, {**a_row(), "error": "HTTP 400: bad\x00 request", "outcome": "http",
                                  "generation": "extract\x00-k"})  # the write guards itself too
    with psycopg.connect(migrated) as conn:
        (stored,) = calls.recent(conn)
    assert stored["error"] == "HTTP 400: bad request" and stored["generation"] == "extract-k"


def test_the_bounds_are_added_to_the_options_a_database_url_already_has(migrated):
    bounds = f"-c statement_timeout={calls.TIMEOUT_S * 1000} -c lock_timeout={calls.TIMEOUT_S * 1000}"
    assert calls.session_options("postgresql://nmos@db.test/nmos") == bounds
    assert calls.session_options("postgresql://nmos@db.test/nmos?options=-c%20search_path%3Dside") \
        == "-c search_path=side " + bounds
    assert calls.session_options("host=db.test dbname=nmos options='-c search_path=side'") \
        == "-c search_path=side " + bounds
    assert calls.session_options("not a database url") == bounds  # the connect then fails, and fails open
    sep = "&" if "?" in migrated else "?"
    assert calls.write(migrated + sep + "options=-c%20application_name%3Dnmos-log-test", a_row())


def test_a_write_that_fails_is_one_warning_and_false(migrated, caplog):
    with caplog.at_level(logging.WARNING, logger="nmos.calls"):
        assert calls.write("postgresql://nmos:nmos@127.0.0.1:1/nope", a_row()) is False
        assert calls.write(migrated, a_row(conversation_id=uuid7())) is False  # a chat deleted meanwhile
    messages = [r.getMessage() for r in caplog.records if r.name == "nmos.calls"]
    assert messages == ["model call not logged: OperationalError", "model call not logged: ForeignKeyViolation"]


def test_a_write_waits_for_a_lock_no_longer_than_its_bound(migrated):
    """A chat being deleted holds its row: the write gives up after its lock timeout and the caller goes on."""
    with psycopg.connect(migrated, autocommit=True) as conn:
        cid = a_conversation(conn)
    with psycopg.connect(migrated) as deleting:
        deleting.execute("SELECT 1 FROM conversation WHERE id = %s FOR UPDATE", (cid,))
        started = time.monotonic()
        assert calls.write(migrated, a_row(conversation_id=cid)) is False
        assert time.monotonic() - started < calls.TIMEOUT_S + 2
        deleting.rollback()
