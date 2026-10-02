"""ADR 0061 item 7: the newest user message's embedding starts when its sync arrives, and the retrieve that follows
takes it instead of asking again."""

from __future__ import annotations

import time

from conftest import make_client
from memeval import StubEmbedder
from nmos_sidecar import retrieval
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
        assert retrieval.prefetched.take(emb, retrieval.query_prefix("fake-embed", "auto")
                                         + "혹시 그 반짝이는 은빛 물건은 어디 숨겼지?") is not None


def test_prefetched_entries_expire_and_are_taken_once():
    class Instant:
        def embed(self, texts, timeout_s):
            return [[1.0, 0.0] for _ in texts]

    cache = Prefetched()
    emb = Instant()
    first = cache.start(emb, "q", 300)
    assert cache.start(emb, "q", 300) is first  # already in flight: not asked twice
    settle(first)
    assert cache.take(emb, "q") is first and cache.take(emb, "q") is None
    again = cache.start(emb, "q", 300)
    cache._entries[(id(emb), "q")] = (again, time.monotonic() - PREFETCH_TTL_S - 1)
    assert cache.take(emb, "q") is None  # too old: a request that never came
    assert cache.take(Instant(), "q") is None  # another embedder's text is another entry
