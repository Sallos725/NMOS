"""ADR 0061 (K34): the query embedding is asked for when recall starts and collected after its reads."""

from __future__ import annotations

import time
from threading import Event
from types import SimpleNamespace

import pytest

from conftest import make_client
from memeval import StubEmbedder
from nmos_sidecar.llm import LLMError
from nmos_sidecar.retrieval import EMBED_CALL_FACTOR, QueryEmbedding
from test_packet_ledger import ask, settings_for, story

ANSWER = [1.0, 0.0]


class Slow:
    """An embedder that answers after `delay_s`, or fails the way httpx does when the call's timeout comes first."""

    def __init__(self, delay_s: float, fail: bool = False):
        self.delay_s, self.fail = delay_s, fail
        self.calls: list[float] = []

    def embed(self, texts, timeout_s):
        self.calls.append(timeout_s)
        if self.delay_s > timeout_s:
            time.sleep(timeout_s)
            raise LLMError("embedding request failed: ReadTimeout")
        time.sleep(self.delay_s)
        if self.fail:
            raise LLMError("embedding service down")
        return [ANSWER for _ in texts]


def test_an_embedding_slower_than_the_timeout_arrives_when_the_reads_took_the_difference(monkeypatch):
    """A call completed during recall's reads remains usable even when its duration exceeded the result wait.

    Events pin the order and a logical clock pins the duration; busy runners cannot change either assertion.
    The separate timeout test checks the actual bounded wait.
    """
    started, release = Event(), Event()
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr("nmos_sidecar.retrieval.time", SimpleNamespace(perf_counter=lambda: clock.now))

    class Controlled:
        calls: list[float]

        def __init__(self):
            self.calls = []

        def embed(self, texts, timeout_s):
            self.calls.append(timeout_s)
            started.set()
            assert release.wait(5), "the simulated reads did not finish"
            return [ANSWER for _ in texts]

    emb = Controlled()
    pending = QueryEmbedding(emb, "q", timeout_ms=100)
    try:
        assert started.wait(5), "the embedding did not start alongside the reads"
        assert pending.call_ms is None
        clock.now = 0.2  # the reads outlast the 100 ms result wait; the call's own budget is 200 ms
    finally:
        release.set()
        pending._thread.join(5)
    assert not pending._thread.is_alive()
    assert pending.result() == ANSWER
    assert pending.call_ms == 200
    assert emb.calls == [EMBED_CALL_FACTOR * 0.1]


def test_the_wait_after_the_reads_is_at_most_the_timeout():
    """An embedder that does not answer costs the request the timeout after the reads, as it cost before them."""
    pending = QueryEmbedding(Slow(1.0), "q", timeout_ms=100)
    t0 = time.perf_counter()
    with pytest.raises(LLMError, match="not answered within 100 ms after recall's reads"):
        pending.result()
    assert 0.09 <= time.perf_counter() - t0 < 0.3


def test_a_failed_call_is_reported_at_once():
    pending = QueryEmbedding(Slow(0.0, fail=True), "q", timeout_ms=1000)
    time.sleep(0.02)
    t0 = time.perf_counter()
    with pytest.raises(LLMError, match="embedding service down"):
        pending.result()
    assert time.perf_counter() - t0 < 0.1  # a failure does not wait out the timeout


def test_an_answer_of_the_wrong_shape_is_a_value_error_as_before():
    class Two:
        def embed(self, texts, timeout_s):
            return [[1.0], [2.0]]

    pending = QueryEmbedding(Two(), "q", timeout_ms=1000)
    with pytest.raises(ValueError):
        pending.result()


def test_the_trace_records_the_wait_and_the_call(migrated):
    with make_client(migrated, embedder=StubEmbedder(), **settings_for("full")) as client:
        chat = story(client, migrated, vectors=True)
        out = ask(client, chat, "혹시 그 반짝이는 은빛 물건은 어디 숨겼지?")
        timings = client.get(f"/v1/trace/{out['trace_id']}").json()["latency_ms"]
    assert out["vectors"] == "on" and timings["vector_mode"] == "on"
    assert "embed_wait" in timings and timings["embed"] is not None and "vector" in timings


def test_a_slow_embedder_falls_back_after_the_timeout_not_the_call(migrated):
    """The waiter gives up `embed_timeout_ms` after the reads; the call (twice that) ends on its own."""
    with make_client(migrated, embedder=StubEmbedder(), **settings_for("full")) as client:
        chat = story(client, migrated, vectors=True)
    with make_client(migrated, embedder=Slow(5.0), **settings_for("full"), embed_timeout_ms=100) as slow:
        out = ask(slow, chat, "혹시 그 반짝이는 은빛 물건은 어디 숨겼지?")
        timings = slow.get(f"/v1/trace/{out['trace_id']}").json()["latency_ms"]
    assert out["vectors"] == "fallback"
    assert timings["vector_mode"].startswith("fallback: embedding not answered within 100 ms")
    assert timings["embed_wait"] < 1000 and "embed" not in timings


def test_http_trickle_obeys_the_total_call_deadline():
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from nmos_sidecar.llm import Embedder

    body = json.dumps({"data": [{"index": 0, "embedding": ANSWER}]}).encode()
    received = Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            received.set()
            try:
                if self.path.startswith("/trickle"):
                    for byte in body:
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                        time.sleep(0.03)  # activity is always sooner than the 300 ms inactivity timeout
                else:
                    self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # expected cancellation closes the socket

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    runner = threading.Thread(target=server.serve_forever, daemon=True)
    runner.start()
    base = f"http://127.0.0.1:{server.server_port}"
    pending = None
    try:
        fast = QueryEmbedding(Embedder(base + "/fast", "synthetic"), "q", timeout_ms=1000)
        assert fast.result() == ANSWER
        fast._thread.join(1)
        received.clear()
        pending = QueryEmbedding(Embedder(base + "/trickle", "synthetic"), "q", timeout_ms=50,
                                 call_timeout_ms=300)
        assert received.wait(2)
        with pytest.raises(LLMError, match="not answered within 50 ms"):
            pending.result()
        pending._thread.join(0.8)
        assert not pending._thread.is_alive()  # the original inactivity timeout permits the whole ~1.7 s body
        with pytest.raises(LLMError, match="total deadline"):
            pending._future.result()
    finally:
        server.shutdown()
        server.server_close()
        runner.join(2)
        if pending is not None:
            pending._thread.join(3)


def test_query_concurrency_is_bounded_and_saturation_fails_open(monkeypatch):
    import threading
    from nmos_sidecar import retrieval
    entered, release = Event(), Event()
    monkeypatch.setattr(retrieval, "_QUERY_EMBED_SLOTS", threading.BoundedSemaphore(1))

    class Held:
        def embed(self, texts, timeout_s):
            entered.set()
            assert release.wait(5)
            return [ANSWER]

    first = QueryEmbedding(Held(), "first", timeout_ms=1000)
    try:
        assert entered.wait(2)
        second = QueryEmbedding(Held(), "second", timeout_ms=1000)
        with pytest.raises(LLMError, match="concurrency limit"):
            second.result()
        second._thread.join(1)
        assert not second._thread.is_alive()
    finally:
        release.set()
        first._thread.join(2)
    assert first.result() == ANSWER
    # The failed attempt did not consume a slot and completion returned the original one.
    assert QueryEmbedding(Slow(0), "third", timeout_ms=1000).result() == ANSWER
