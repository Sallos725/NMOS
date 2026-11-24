"""A local stand-in for a `standard` reranker (PHASE-60 S5, ADR 0084): `POST <base>/rerank` on 127.0.0.1.

Tests configure what it answers: `score` (a function of a document's text), `delay_s` (to outlast a client
timeout), `status` (a non-2xx answer), `raw_body` (a malformed answer) and `key` (`results` or `data`). It counts
calls and records each request's JSON and Authorization header. No network beyond the loopback interface.

Use the `rerank_server` fixture: import it into a test module (`from rerank_stub import rerank_server`).
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest


class RerankStub:
    def __init__(self) -> None:
        self.score: Callable[[str], float] = lambda doc: 0.0
        self.delay_s = 0.0
        self.status = 200
        self.raw_body: bytes | None = None
        self.key = "results"
        self.calls = 0
        self.requests: list[dict[str, Any]] = []  # each request's JSON body, in order
        self.auth: list[str | None] = []  # each request's Authorization header, in order
        self._lock = threading.Lock()
        self._release = threading.Event()  # set on teardown: a delayed answer stops waiting
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: Any) -> None:  # quiet: nothing of a request reaches the test's logs
                pass

            def do_POST(self) -> None:
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if not self.path.split("?", 1)[0].endswith("/rerank"):
                    self._send(404, b'{"error": "not found"}')
                    return
                try:
                    body = json.loads(raw)
                except ValueError:
                    body = {"_unparsed": raw.decode("utf-8", "replace")}
                with stub._lock:
                    stub.calls += 1
                    stub.requests.append(body)
                    stub.auth.append(self.headers.get("Authorization"))
                if stub.delay_s:
                    stub._release.wait(stub.delay_s)
                if stub.status != 200:
                    self._send(stub.status, b'{"error": "synthetic failure"}')
                    return
                if stub.raw_body is not None:
                    self._send(200, stub.raw_body)
                    return
                docs = body.get("documents") if isinstance(body, dict) else None
                results = [{"index": i, "relevance_score": stub.score(d)} for i, d in enumerate(docs or [])]
                results.sort(key=lambda r: -r["relevance_score"])  # as hosted rerankers answer: best first
                self._send(200, json.dumps({stub.key: results}).encode())

            def _send(self, status: int, payload: bytes) -> None:
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # the client gave up first (a timeout test)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, name="rerank-stub", daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        """The base URL a reranker is configured with; the client appends `/rerank`."""
        return f"http://127.0.0.1:{self._server.server_port}/v1"

    @property
    def last_json(self) -> dict[str, Any] | None:
        return self.requests[-1] if self.requests else None

    @property
    def last_auth(self) -> str | None:
        return self.auth[-1] if self.auth else None

    def close(self) -> None:
        self._release.set()
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(2)


@pytest.fixture
def rerank_server() -> Iterator[RerankStub]:
    stub = RerankStub()
    try:
        yield stub
    finally:
        stub.close()
