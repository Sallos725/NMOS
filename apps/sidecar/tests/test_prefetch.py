"""ADR 0061 item 7: the newest user message's embedding starts when its sync arrives, and the retrieve that follows
takes it instead of asking again."""

from __future__ import annotations

import gc
import time
import weakref

import pytest

from conftest import make_client
from memeval import StubEmbedder
from nmos_sidecar import retrieval
from nmos_sidecar.llm import LLMError
from nmos_sidecar.retrieval import EMBED_CALL_FACTOR, PREFETCH_CALL_MIN_MS, PREFETCH_TTL_S, Prefetched, QueryEmbedding
from test_packet_ledger import ask, settings_for, story
from test_sidecar_integration import recall, sync


class Counting(StubEmbedder):
    def __init__(self):
        self.texts: list[str] = []
        self.timeouts: list[float] = []

    def embed(self, texts, timeout_s):
        self.texts += texts
        self.timeouts.append(timeout_s)
        return super().embed(texts, timeout_s)


def settle(pending: QueryEmbedding) -> None:
    pending.result()  # the thread has answered


def test_a_sync_with_a_new_user_message_starts_its_embedding_and_the_retrieve_takes_it(migrated):
    emb = Counting()
    with make_client(migrated, embedder=emb, **settings_for("full")) as client:
        chat = story(client, migrated, vectors=True)
        before = len(emb.texts)
        question = "혹시 그 반짝이는 은빛 물건은 어디 숨겼지?"
        chat.user(question)
        sync(client, chat)  # the bodies carry the question: its embedding is asked for now
        time.sleep(0.05)
        assert len(emb.texts) == before + 1 and emb.texts[-1].endswith(question)
        assert emb.timeouts[-1] == max(EMBED_CALL_FACTOR * 0.3, PREFETCH_CALL_MIN_MS / 1000)  # the prefetched call's cap
        out = recall(client, chat, question, in_context=[m["chatId"] for m in chat.messages[-2:]], budget=600)
        timings = client.get(f"/v1/trace/{out['trace_id']}").json()["latency_ms"]
        assert out["vectors"] == "on" and len(emb.texts) == before + 1  # not asked again
        assert timings["embed_lead"] >= 0 and timings["embed_wait"] < 50
        # a second retrieve of the same text has no prefetched embedding left: it asks, as a request does
        out = recall(client, chat, question, in_context=[m["chatId"] for m in chat.messages[-2:]], budget=600)
        timings = client.get(f"/v1/trace/{out['trace_id']}").json()["latency_ms"]
        assert out["vectors"] == "on" and len(emb.texts) == before + 2 and "embed_lead" not in timings


def test_another_question_or_a_reply_last_is_not_prefetched(migrated):
    emb = Counting()
    with make_client(migrated, embedder=emb, **settings_for("full")) as client:
        chat = story(client, migrated, vectors=True)  # ends with a reply
        before = len(emb.texts)
        chat.reply("Another reply.")
        sync(client, chat)
        time.sleep(0.05)
        assert len(emb.texts) == before  # the newest message is the character's: nothing to ask for
        out = ask(client, chat, "하나는 지도를 가지고 있어?")  # ask() syncs the message, then retrieves the same text
        assert out["vectors"] == "on" and len(emb.texts) == before + 1
        out = recall(client, chat, "다른 질문이야", in_context=[], budget=600)
        timings = client.get(f"/v1/trace/{out['trace_id']}").json()["latency_ms"]
        assert out["vectors"] == "on" and len(emb.texts) == before + 2 and "embed_lead" not in timings


def test_a_replay_leaves_the_prefetched_embedding_to_the_live_request(migrated):
    """`audit.replay` runs gather with `known_at`: it never takes a prefetched embedding (ADR 0027: a replay compiles
    from what it reads, and the live request that follows the sync must still find its embedding)."""
    from nmos_sidecar import audit
    from nmos_sidecar.retrieval import RecallOptions
    from test_packet_ledger import db

    emb = Counting()
    with make_client(migrated, embedder=emb, **settings_for("full")) as client:
        chat = story(client, migrated, vectors=True)
        out = ask(client, chat, "혹시 그 반짝이는 은빛 물건은 어디 숨겼지?")
        trace = client.get(f"/v1/trace/{out['trace_id']}").json()
        chat.user("혹시 그 반짝이는 은빛 물건은 어디 숨겼지?")
        sync(client, chat)  # prefetched again for the same text
        time.sleep(0.05)
        with db(migrated) as conn:
            audit.replay(conn, out["trace_id"], RecallOptions(embedder=emb, embed_projection=trace["embed_projection"]))
        assert retrieval.prefetched.take(emb, trace["embed_projection"], retrieval.query_prefix("fake-embed", "auto")
                                         + "혹시 그 반짝이는 은빛 물건은 어디 숨겼지?") is not None


def test_prefetched_entries_expire_and_are_taken_once():
    class Instant:
        def embed(self, texts, timeout_s):
            return [[1.0, 0.0] for _ in texts]

    cache = Prefetched()
    emb = Instant()
    first = cache.start(emb, "embed-p", "q", 300)
    assert cache.start(emb, "embed-p", "q", 300) is first  # already in flight: not asked twice
    settle(first)
    assert cache.take(emb, "embed-p", "q") is first and cache.take(emb, "embed-p", "q") is None
    again = cache.start(emb, "embed-p", "q", 300)
    assert cache.take(emb, "embed-other", "q") is None and cache.take(emb, "embed-p", "q2") is None  # not this one
    assert cache.take(emb, "embed-p", "q") is again
    again = cache.start(emb, "embed-p", "q", 300)
    cache._entries[("embed-p", "q")] = (again, emb, time.monotonic() - PREFETCH_TTL_S - 1)
    assert cache.take(emb, "embed-p", "q") is None  # too old: a request that never came


def test_an_entry_asked_of_a_replaced_embedder_is_not_given_to_the_new_one():
    """An entry is the embedder object's it was asked of, not its `id()`'s: `api.rebuild` makes a new Embedder on every
    settings save, and a new object can get a collected one's id (Codex on #242 reproduced a stale vector searching a
    new projection that way). The same projection with a new object is not served either; the entry is dropped."""
    class Instant:
        def embed(self, texts, timeout_s):
            return [[1.0, 0.0] for _ in texts]

    cache = Prefetched()
    old, new = Instant(), Instant()
    alive = weakref.ref(old)
    pending = cache.start(old, "embed-p", "q", 300)
    settle(pending)
    pending._thread.join()  # the call's thread let go of its arguments
    del old
    gc.collect()
    assert alive() is not None  # the entry holds its embedder: its id cannot be reused while the entry lives
    assert cache.take(new, "embed-p", "q") is None  # another object is not it: dropped, not given
    gc.collect()
    assert alive() is None  # let go with the entry
    old = Instant()
    pending = cache.start(old, "embed-p", "q", 300)
    settle(pending)
    assert cache.take(new, "embed-p", "q") is None and cache.take(old, "embed-p", "q") is None  # dropped, not given
    pending = cache.start(old, "embed-p", "q", 300)
    assert cache.start(new, "embed-p", "q", 300) is not pending  # a sync retried after the save: the new one's call
    assert cache.take(new, "embed-p", "q") is not pending and cache.take(old, "embed-p", "q") is None


def test_a_settings_save_between_the_sync_and_its_retrieve_leaves_the_prefetched_embedding_unused(migrated,
                                                                                                 monkeypatch):
    """Through the API: the sync asks the embedder the app built; `PUT /v1/config` rebuilds it (a new object, here a
    new projection too); the retrieve of the same text embeds with the new one and records no `embed_lead`."""
    from nmos_sidecar import api

    made: list[Counting] = []

    class Embed(Counting):
        def __init__(self, url, model, api_key=""):
            super().__init__()
            self.url = url
            made.append(self)

    monkeypatch.setattr(api, "Embedder", Embed)
    with make_client(migrated, **settings_for("full")) as client:  # no injected embedder: `api.rebuild` builds one
        chat = story(client, migrated, vectors=True)
        first = made[-1]  # the embedder the app serves requests with now (startup rebuilds once more)
        question = "혹시 그 반짝이는 은빛 물건은 어디 숨겼지?"
        chat.user(question)
        sync(client, chat)
        time.sleep(0.05)
        assert len(first.texts) == 1 and first.texts[0].endswith(question)
        assert client.put("/v1/config", json={"embed_url": "http://stub-embed-two/v1"}).status_code == 200
        second = made[-1]
        assert second is not first and second.url == "http://stub-embed-two/v1"
        out = recall(client, chat, question, in_context=[m["chatId"] for m in chat.messages[-2:]], budget=600)
        timings = client.get(f"/v1/trace/{out['trace_id']}").json()["latency_ms"]
        assert out["vectors"] == "on" and "embed_lead" not in timings  # asked of the new embedder, not taken
        assert len(first.texts) == 1 and len(second.texts) == 1 and second.texts[0].endswith(question)
        # the same projection with a rebuilt object (a save that touched nothing of the embedding): not served either
        chat.user(question)
        sync(client, chat)
        time.sleep(0.05)
        assert len(second.texts) == 2
        assert client.put("/v1/config", json={"recall_threshold": 0.5}).status_code == 200
        third = made[-1]
        assert third is not second and third.url == second.url
        out = recall(client, chat, question, in_context=[m["chatId"] for m in chat.messages[-2:]], budget=600)
        timings = client.get(f"/v1/trace/{out['trace_id']}").json()["latency_ms"]
        assert out["vectors"] == "on" and "embed_lead" not in timings
        assert len(third.texts) == 1 and len(second.texts) == 2


def test_a_prefetched_call_that_failed_is_not_given_to_the_request():
    """Codex (#244): a sync's call that failed (the embedder down for that moment) must not cost the request its
    vectors by being inherited; the request asks again, as one without a prefetch does."""
    class Failing:
        def embed(self, texts, timeout_s):
            raise LLMError("embedding request failed: connection refused")

    cache = Prefetched()
    emb = Failing()
    pending = cache.start(emb, "embed-p", "q", 300)
    with pytest.raises(LLMError):
        pending.result()
    assert pending.failed() and cache.take(emb, "embed-p", "q") is None


def test_a_request_whose_prefetch_failed_asks_again_and_has_vectors(migrated):
    class FlakyOnce(Counting):
        def __init__(self):
            super().__init__()
            self.fail_next = False

        def embed(self, texts, timeout_s):
            if self.fail_next:
                self.fail_next = False
                self.texts += texts
                raise LLMError("embedding request failed: connection refused")
            return super().embed(texts, timeout_s)

    emb = FlakyOnce()
    with make_client(migrated, embedder=emb, **settings_for("full")) as client:
        chat = story(client, migrated, vectors=True)
        before = len(emb.texts)
        question = "혹시 그 반짝이는 은빛 물건은 어디 숨겼지?"
        chat.user(question)
        emb.fail_next = True
        sync(client, chat)  # the prefetched call fails
        time.sleep(0.05)
        assert len(emb.texts) == before + 1 and not emb.fail_next
        out = recall(client, chat, question, in_context=[m["chatId"] for m in chat.messages[-2:]], budget=600)
        timings = client.get(f"/v1/trace/{out['trace_id']}").json()["latency_ms"]
        assert out["vectors"] == "on" and "embed_lead" not in timings and len(emb.texts) == before + 2
