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
