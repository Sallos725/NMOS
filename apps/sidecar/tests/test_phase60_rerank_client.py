"""Phase 60 S5 (ADR 0084): unit tests for `rerank.py`, the opt-in standard reranker client."""

from __future__ import annotations

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
import pytest

from nmos_sidecar import rerank
from nmos_sidecar.rerank import DEFAULT_TIMEOUT_MS, FORMATS, MAX_CANDIDATES, MAX_DOC_CHARS, Reranker, endpoint, reorder, score


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_constants_and_defaults():
    assert FORMATS == ("standard",)
    assert MAX_CANDIDATES == 30
    assert MAX_DOC_CHARS == 1000
    assert DEFAULT_TIMEOUT_MS == 600
    r = Reranker(url="http://rerank.test/v1", model="rerank-v1")
    assert r.api_key == ""
    assert r.timeout_ms == 600
    assert r.format == "standard"


@pytest.mark.parametrize("raw, expected", [
    ("http://x/v1", "http://x/v1/rerank"),
    ("http://x/v1/", "http://x/v1/rerank"),
    ("http://x/v1///", "http://x/v1/rerank"),
    ("http://x/v1/rerank", "http://x/v1/rerank"),
    ("http://x/v1/rerank/", "http://x/v1/rerank"),
    ("http://x", "http://x/rerank"),
    ("http://x/", "http://x/rerank"),
    ("http://x/v1/myrerank", "http://x/v1/myrerank/rerank"),
    ("http://x/v1/?api-version=1", "http://x/v1/rerank?api-version=1"),
    ("http://x/v1/rerank?api-version=1", "http://x/v1/rerank?api-version=1"),
])
def test_endpoint_normalization(raw: str, expected: str):
    assert endpoint(raw) == expected


def test_results_answer_returns_scores_in_input_order():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={
            "results": [
                {"index": 0, "relevance_score": 0.2},
                {"index": 1, "relevance_score": 0.9},
                {"index": 2, "relevance_score": 0.5},
            ],
        })

    r = Reranker(url="http://rerank.test/v1", model="rerank-v1")
    docs = ["세라의 열쇠", "카이토의 편지", "하나의 지도"]
    with _mock_client(handler) as client:
        got = score(r, "편지가 어디 있지?", docs, client=client)

    assert got == [0.2, 0.9, 0.5]
    assert len(seen) == 1
    assert str(seen[0].url) == "http://rerank.test/v1/rerank"
    payload = json.loads(seen[0].content)
    assert payload == {
        "model": "rerank-v1",
        "query": "편지가 어디 있지?",
        "documents": docs,
        "top_n": 3,
    }


def test_data_answer_returns_scores_in_input_order():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "data": [
                {"index": 0, "relevance_score": 0.1},
                {"index": 1, "relevance_score": 0.8},
            ],
        })

    r = Reranker(url="http://rerank.test/v1", model="rerank-v1")
    with _mock_client(handler) as client:
        got = score(r, "유나는 어디로 갔지?", ["유나는 광장에 있다", "카이토는 쉬고 있다"], client=client)
    assert got == [0.1, 0.8]


def test_reversed_index_order_still_returns_input_order():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "results": [
                {"index": 2, "relevance_score": 0.95},
                {"index": 1, "relevance_score": 0.4},
                {"index": 0, "relevance_score": 0.15},
            ],
        })

    r = Reranker(url="http://rerank.test/v1", model="rerank-v1")
    with _mock_client(handler) as client:
        got = score(r, "질문", ["세라", "카이토", "하나"], client=client)
    assert got == [0.15, 0.4, 0.95]


@pytest.mark.parametrize("body", [
    # partial (only 2 of 3)
    {"results": [{"index": 0, "relevance_score": 0.5}, {"index": 1, "relevance_score": 0.4}]},
    # extra item
    {"results": [
        {"index": 0, "relevance_score": 0.5},
        {"index": 1, "relevance_score": 0.4},
        {"index": 2, "relevance_score": 0.3},
        {"index": 3, "relevance_score": 0.2},
    ]},
    # duplicate index (missing index 2)
    {"results": [
        {"index": 0, "relevance_score": 0.5},
        {"index": 0, "relevance_score": 0.4},
        {"index": 1, "relevance_score": 0.3},
    ]},
    # out of range (high)
    {"results": [
        {"index": 0, "relevance_score": 0.5},
        {"index": 1, "relevance_score": 0.4},
        {"index": 3, "relevance_score": 0.3},
    ]},
    # out of range (negative)
    {"results": [
        {"index": -1, "relevance_score": 0.5},
        {"index": 1, "relevance_score": 0.4},
        {"index": 2, "relevance_score": 0.3},
    ]},
    # string score
    {"results": [
        {"index": 0, "relevance_score": "0.5"},
        {"index": 1, "relevance_score": 0.4},
        {"index": 2, "relevance_score": 0.3},
    ]},
    # bool index / bool score
    {"results": [
        {"index": False, "relevance_score": 0.5},
        {"index": 1, "relevance_score": 0.4},
        {"index": 2, "relevance_score": 0.3},
    ]},
    {"results": [
        {"index": 0, "relevance_score": True},
        {"index": 1, "relevance_score": 0.4},
        {"index": 2, "relevance_score": 0.3},
    ]},
    # an integer score too large for a float (valid JSON): OverflowError on conversion
    {"results": [
        {"index": 0, "relevance_score": 10 ** 400},
        {"index": 1, "relevance_score": 0.4},
        {"index": 2, "relevance_score": 0.3},
    ]},
    # missing results/data list
    {"scores": [0.1, 0.2, 0.3]},
    # non-list results
    {"results": "bad"},
    # non-dict item
    {"results": ["a", "b", "c"]},
    # non-dict top-level
    [{"index": 0, "relevance_score": 0.1}],
])
def test_malformed_answers_fail_open_to_none(body: Any):
    r = Reranker(url="http://rerank.test/v1", model="rerank-v1")
    with _mock_client(lambda _req: httpx.Response(200, json=body)) as client:
        assert score(r, "질문", ["세라", "카이토", "하나"], client=client) is None


def test_non_finite_scores_fail_open_to_none():
    r = Reranker(url="http://rerank.test/v1", model="rerank-v1")
    raw_nan = b'{"results": [{"index": 0, "relevance_score": NaN}]}'
    raw_inf = b'{"results": [{"index": 0, "relevance_score": Infinity}]}'
    with _mock_client(lambda _req: httpx.Response(200, content=raw_nan)) as client:
        assert score(r, "질문", ["세라"], client=client) is None
    with _mock_client(lambda _req: httpx.Response(200, content=raw_inf)) as client:
        assert score(r, "질문", ["세라"], client=client) is None


@pytest.mark.parametrize("status_code", [302, 400, 401, 429, 500, 503])
def test_non_2xx_fails_open_to_none(status_code: int):
    r = Reranker(url="http://rerank.test/v1", model="rerank-v1")
    with _mock_client(lambda _req: httpx.Response(status_code, json={"error": "boom"})) as client:
        assert score(r, "질문", ["세라"], client=client) is None


def test_non_json_body_fails_open_to_none():
    r = Reranker(url="http://rerank.test/v1", model="rerank-v1")
    with _mock_client(lambda _req: httpx.Response(200, text="<html>not json</html>")) as client:
        assert score(r, "질문", ["세라"], client=client) is None


def test_transport_timeout_and_connection_error_fail_open_to_none():
    r = Reranker(url="http://rerank.test/v1", model="rerank-v1")

    def raise_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    def raise_connect(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with _mock_client(raise_timeout) as client:
        assert score(r, "질문", ["세라"], client=client) is None
    with _mock_client(raise_connect) as client:
        assert score(r, "질문", ["세라"], client=client) is None


def test_real_server_sleeping_and_trickling_past_timeout_fail_open():
    body = json.dumps({"results": [{"index": 0, "relevance_score": 0.9}]}).encode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            if self.path.startswith("/sleep"):
                time.sleep(0.35)
                try:
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                if self.path.startswith("/trickle"):
                    for b in body:
                        self.wfile.write(bytes([b]))
                        self.wfile.flush()
                        time.sleep(0.02)
                else:
                    self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        fast = Reranker(url=f"{base}/fast", model="rerank-v1", timeout_ms=1000)
        assert score(fast, "질문", ["세라"]) == [0.9]

        slow = Reranker(url=f"{base}/sleep", model="rerank-v1", timeout_ms=60)
        t0 = time.monotonic()
        assert score(slow, "질문", ["세라"]) is None
        assert time.monotonic() - t0 < 0.25

        trickle = Reranker(url=f"{base}/trickle", model="rerank-v1", timeout_ms=1000)
        t0 = time.monotonic()
        assert score(trickle, "질문", ["세라"], timeout_s=0.06) is None
        assert time.monotonic() - t0 < 0.25
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_a_stuck_name_lookup_is_bounded_by_the_timeout_and_never_queues(monkeypatch):
    """The timeout bounds the whole call, name resolution included (a lookup cannot be cancelled): a 2 s lookup
    under a 200 ms timeout returns None well under 1 s, a second call meanwhile too, and once every worker is stuck
    the next call returns None at once without starting another lookup (fail open, nothing queues)."""
    import socket

    body = json.dumps({"results": [{"index": 0, "relevance_score": 0.9}]}).encode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    real = socket.getaddrinfo
    gate = threading.Event()
    lookups = 0
    lock = threading.Lock()

    def stuck(*args, **kwargs):
        nonlocal lookups
        with lock:
            lookups += 1
        gate.wait(2.0)  # a resolver that hangs (released at teardown so no worker outlives the test)
        return real(*args, **kwargs)

    def drain() -> None:
        gate.set()
        deadline = time.monotonic() + 5
        while rerank._in_flight() and time.monotonic() < deadline:
            time.sleep(0.02)

    # an IP literal skips resolution: the host name makes the client resolve it
    r = Reranker(url=f"http://localhost:{server.server_port}/v1", model="rerank-v1", timeout_ms=200)
    try:
        assert score(r, "질문", ["세라"]) == [0.9]  # resolves and answers before the resolver is stuck
        monkeypatch.setattr(socket, "getaddrinfo", stuck)
        t0 = time.monotonic()
        assert score(r, "질문", ["세라"]) is None
        assert time.monotonic() - t0 < 1.0
        t0 = time.monotonic()
        assert score(r, "질문", ["세라"]) is None  # the first lookup is still stuck
        assert time.monotonic() - t0 < 1.0
        assert lookups == 2
        for _ in range(rerank._MAX_WORKERS - 2):  # fill every worker with a stuck lookup
            assert score(r, "질문", ["세라"]) is None
        assert lookups == rerank._MAX_WORKERS
        t0 = time.monotonic()
        assert score(r, "질문", ["세라"]) is None  # every worker stuck: at once, no new lookup
        assert time.monotonic() - t0 < 0.15
        assert lookups == rerank._MAX_WORKERS
        drain()
        monkeypatch.undo()
        assert rerank._in_flight() == 0
        assert score(r, "질문", ["세라"]) == [0.9]  # the stuck workers ended by themselves; the pool serves again
    finally:
        drain()
        monkeypatch.undo()
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_bearer_header_sent_only_when_key_set():
    seen_headers: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers)
        return httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 0.7}]})

    with _mock_client(handler) as client:
        assert score(Reranker(url="http://rerank.test/v1", model="m", api_key=""), "q", ["세라"], client=client) == [0.7]
        assert score(
            Reranker(url="http://rerank.test/v1", model="m", api_key="sk-secret-123"),
            "q",
            ["세라"],
            client=client,
        ) == [0.7]

    assert "authorization" not in seen_headers[0]
    assert seen_headers[1]["authorization"] == "Bearer sk-secret-123"


def test_documents_truncated_to_max_doc_chars():
    seen_payloads: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_payloads.append(json.loads(request.content))
        return httpx.Response(200, json={
            "results": [
                {"index": 0, "relevance_score": 0.4},
                {"index": 1, "relevance_score": 0.8},
            ],
        })

    long_doc = "가" * (MAX_DOC_CHARS + 250)
    short_doc = "유나의 짧은 메모"
    r = Reranker(url="http://rerank.test/v1", model="m")
    with _mock_client(handler) as client:
        got = score(r, "질문", [long_doc, short_doc], client=client)

    assert got == [0.4, 0.8]
    sent_docs = seen_payloads[0]["documents"]
    assert len(sent_docs[0]) == MAX_DOC_CHARS
    assert sent_docs[0] == long_doc[:MAX_DOC_CHARS]
    assert sent_docs[1] == short_doc


def test_candidate_cap_empty_and_invalid_config_guards():
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"results": []})

    r = Reranker(url="http://rerank.test/v1", model="m")
    with _mock_client(handler) as client:
        assert score(r, "질문", [], client=client) == []
        assert score(r, "질문", [f"doc-{i}" for i in range(MAX_CANDIDATES + 1)], client=client) is None
        assert score(Reranker(url="http://rerank.test/v1", model="m", format="other"), "q", ["a"], client=client) is None
        assert score(r, "질문", ["세라"], timeout_s=0.0, client=client) is None
    assert calls == 0


def test_repr_hides_api_key_and_url_userinfo():
    r = Reranker(url="http://alice:hunter2@rerank.test/v1", model="rerank-v1", api_key="sk-secret-123")
    text = repr(r)
    assert "sk-secret" not in text
    assert "hunter2" not in text
    assert "alice" not in text
    assert "rerank-v1" in text


def test_debug_logs_never_contain_key_userinfo_query_or_document(caplog):
    secret_key = "sk-secret-123"
    query = "세라가 숨긴 비밀 암호는 무엇인가"
    doc = "카이토가 기록한 비밀 문서 본문"
    r = Reranker(url="http://alice:hunter2@rerank.test/v1", model="rerank-v1", api_key=secret_key)

    def ok_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 0.9}]})

    def fail_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(f"timeout calling {request.url}", request=request)

    with caplog.at_level(logging.DEBUG):
        with _mock_client(ok_handler) as client:
            assert score(r, query, [doc], client=client) == [0.9]
        with _mock_client(fail_handler) as client:
            assert score(r, query, [doc], client=client) is None

    all_text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert secret_key not in all_text
    assert query not in all_text
    assert doc not in all_text

    own_records = [rec.getMessage() for rec in caplog.records if rec.name == rerank.log.name]
    assert len(own_records) == 2
    for msg in own_records:
        assert secret_key not in msg
        assert "alice" not in msg
        assert "hunter2" not in msg
        assert query not in msg
        assert doc not in msg
        assert "ms=" in msg


def test_reorder_descending_and_stable_on_ties():
    candidates = [
        {"id": "세라"},
        {"id": "카이토"},
        {"id": "하나"},
        {"id": "유나"},
    ]
    original = list(candidates)
    got = reorder(candidates, [0.5, 0.9, 0.5, 0.9])
    assert [c["id"] for c in got] == ["카이토", "유나", "세라", "하나"]
    assert candidates == original  # pure: input list untouched

    assert reorder([], []) == []
    assert reorder(["a", "b", "c"], [-2.0, -0.5, -2.0]) == ["b", "a", "c"]
    with pytest.raises(ValueError):
        reorder(["a", "b"], [0.5])
