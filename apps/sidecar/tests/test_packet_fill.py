"""packet-v9 (PHASE-15 Q1–Q4, ADR 0049): recall grows with the budget. The request's own excerpt count, each excerpt's
length and its fact limit scale by the budget's share of 2,000 (up to 4, facts up to 2); every other limit stays; at
2,000 and below it is packet-v8; a recorded packet-v8 request replays as it was."""

from __future__ import annotations

import dataclasses
from uuid import UUID

import pytest

from conftest import make_client
from memeval import _sync, settings_for
from nmos_sidecar import audit
from nmos_sidecar.packet import FIT_CAP, MAX_EXCERPT_CHARS, excerpt, fill
from nmos_sidecar.retrieval import RecallOptions, filled
from simchat import SimChat
from test_packet_ledger import db, extract

V9 = RecallOptions(policy="packet-v9")


def test_the_factor_and_the_limits_it_grows():
    assert [fill(b, "packet-v9") for b in (0, 800, 2000, 3000, 4000, 8000, 20000)] == [1, 1, 1, 1.5, 2, 4, 4]
    assert fill(8000, "packet-v8") == 1.0  # every earlier policy keeps its recall
    assert filled(V9, 2000) is V9 and filled(V9, 600) is V9
    assert filled(dataclasses.replace(V9, policy="packet-v8"), 8000).top_k == 5
    grown = filled(V9, 3000)
    assert (grown.top_k, grown.facts_limit, grown.excerpt_chars) == (7, 12, 720)  # floor(5 × 1.5), 8 × 1.5
    top = filled(V9, 8000)
    assert (top.top_k, top.facts_limit, top.excerpt_chars) == (20, 16, 1920)  # facts at most twice
    assert filled(V9, 20000) == top  # recall stops growing at 8,000
    # threads, events and every other option stay packet-v8's
    assert (top.threads_limit, top.events_limit, top.threshold) == (V9.threads_limit, V9.events_limit, V9.threshold)
    # from the request's own settings; a limit of 0 stays 0
    mine = filled(dataclasses.replace(V9, top_k=3, facts_limit=5), 4000)
    assert (mine.top_k, mine.facts_limit) == (6, 10)
    off = filled(dataclasses.replace(V9, top_k=0, facts_limit=0), 8000)
    assert (off.top_k, off.facts_limit) == (0, 0)
    assert FIT_CAP == 8000


def test_an_excerpt_is_still_cut_at_its_sentences():
    long = "The keeper walked " + "far " * 200 + "along the shore. The tide came in. Gulls cried."
    short = excerpt(long, "keeper shore", max_chars=MAX_EXCERPT_CHARS)
    assert len(short) <= MAX_EXCERPT_CHARS + 2 and short.endswith("……")  # cut, and more sentences follow
    wide = excerpt(long, "keeper shore", max_chars=1920)
    assert wide == "The keeper walked " + "far " * 200 + "along the shore. The tide came in.…"  # two sentences, as before


def lighthouse_chat(client, url: str) -> SimChat:
    chat = SimChat()
    chat.reply("Welcome to the story.")
    for i in range(24):
        chat.user(f"Tell me more about the lighthouse, part {i}.")
        chat.reply(f"The lighthouse keeper Mira kept logbook {i} by the lamp, "  # one sentence of ≈700 characters
                   + ", ".join(f"noting ship {i}-{j} and the weather over the bay" for j in range(12)) + ".")
    chat.user("Hana has the map.")
    chat.reply("Noted.")
    _sync(client, chat)
    extract(url)
    return chat


def ask(client, chat: SimChat, text: str, budget: int) -> dict:
    return client.post("/v1/retrieve", json={"chat_id": chat.id, "query": text, "previous_ai": "",
                                             "in_context_ids": [m["chatId"] for m in chat.messages[-4:]],
                                             "budget_tokens": budget}).json()


@pytest.fixture
def v9(migrated: str):
    settings = {k: v for k, v in settings_for("full").items() if not k.startswith("embed_")} | {"embed_backfill": 0}
    with make_client(migrated, **(settings | {"packet_policy": "packet-v9"})) as c:
        yield c, migrated


def test_a_larger_budget_brings_more_and_longer_excerpts_and_nothing_else_grows(v9):
    client, url = v9
    chat = lighthouse_chat(client, url)
    chat.user("What did the lighthouse keeper write in the logbook?")
    _sync(client, chat)
    query = "What did the lighthouse keeper write in the logbook?"
    small, large, huge = (ask(client, chat, query, b) for b in (2000, 8000, 20000))
    for out, budget in ((small, 2000), (large, 8000), (huge, 20000)):
        assert out["packet"]["token_estimate"] <= budget  # the packet never exceeds its budget
    n = lambda out: out["packet"]["excerpt_count"]
    assert n(small) <= 5 < n(large) <= 20
    longest = lambda out: max(len(line) for line in out["packet"]["text"].splitlines() if "<Excerpt " in line)
    assert longest(large) > longest(small) and longest(small) < MAX_EXCERPT_CHARS + 120
    with db(url) as conn:
        traces = {r["budget_tokens"]: r for r in conn.execute(
            "SELECT budget_tokens, recall_options, lines FROM retrieval_trace WHERE budget_tokens IN (2000, 8000, 20000)")}
    # the trace records the configured limits and the growth its budget bought
    assert traces[8000]["recall_options"]["top_k"] == 5 and traces[8000]["recall_options"]["fill"] == 4.0
    assert traces[20000]["recall_options"]["fill"] == 4.0  # 20,000 compiles with 8,000's limits
    offered = lambda b, kind: sum(1 for e in traces[b]["lines"] if e["kind"] == kind)
    assert offered(20000, "excerpt") == offered(8000, "excerpt")
    for kind in ("thread", "summary", "secret", "state"):
        assert offered(8000, kind) == offered(2000, kind)
    # each replays as recorded
    for out in (small, large, huge):
        assert client.get(f"/v1/trace/{out['trace_id']}/replay").json()["reproduced"] is True


def test_at_2000_and_below_packet_v9_is_packet_v8_and_a_recorded_v8_request_replays_as_it_was(migrated):
    settings = {k: v for k, v in settings_for("full").items() if not k.startswith("embed_")} | {"embed_backfill": 0}
    with make_client(migrated, **(settings | {"packet_policy": "packet-v8"})) as client:
        chat = lighthouse_chat(client, migrated)
        chat.user("What did the lighthouse keeper write in the logbook?")
        _sync(client, chat)
        recorded = [ask(client, chat, "What did the lighthouse keeper write in the logbook?", b)
                    for b in (600, 2000, 8000)]
    with db(migrated) as conn:
        for out in recorded:
            tid = UUID(out["trace_id"])
            assert audit.replay(conn, tid, RecallOptions())["reproduced"] is True  # packet-v8, as recorded
            v9 = audit.replay(conn, tid, RecallOptions(), "packet-v9")
            if out["packet"]["text"] and conn.execute("SELECT budget_tokens FROM retrieval_trace WHERE id = %s",
                                                     (tid,)).fetchone()["budget_tokens"] <= 2000:
                assert v9["text"] == out["packet"]["text"]
            else:  # 8,000: packet-v9 recalls more than the packet-v8 request did
                assert v9["text"].count("<Excerpt ") > out["packet"]["text"].count("<Excerpt ")
        # with non-default settings too
        tid = UUID(recorded[1]["trace_id"])
        mine = dict(top_k=3, facts_limit=4)
        assert audit.replay(conn, tid, RecallOptions(), "packet-v9", **mine)["text"] == \
            audit.replay(conn, tid, RecallOptions(), "packet-v8", **mine)["text"]
