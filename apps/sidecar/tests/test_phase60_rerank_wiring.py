"""PHASE-60 S5 (ADR 0084 items 3–6, A8): the optional reranker, wired into recall through `/v1/retrieve`.

`RecallOptions.reranker` (a `rerank.Reranker`, None = off). With one, a live request sends the top 30 eligible fused
candidates (none the prompt already holds), each cut to 1,000 normalized characters, once, with the user's message as
the query; on success those 30 are reordered by score (stable) and the rest keep their fused order; each reranked
candidate's trace entry carries `"rerank": <score>`, and `recall_options` records `rerank_used` and `rerank_ms`. A
timeout, an error status or a malformed answer leaves the fused order with `rerank_used` False. Unconfigured, nothing
is called and no `rerank*` key is in the trace. A replay never calls: it applies the recorded scores.

Written before the code (the tests are the contract). The settings slice (`NMOS_RERANK_*`) is not on this branch, so a
test configures the reranker by handing `/v1/retrieve` its options with `reranker` set (`configure`): the real route,
the real `retrieval.retrieve`, the real HTTP client against the local stub (tests/rerank_stub.py). The archive refusal
of A8 waits for that slice and is not here.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from memeval import settings_for
from nmos_sidecar import audit, rerank, retrieval
from nmos_sidecar.canonical import normalize_text
from nmos_sidecar.packet import clean_text
from nmos_sidecar.retrieval import RecallOptions
from rerank_stub import RerankStub, rerank_server  # noqa: F401  (the fixture)
from simchat import SimChat
from test_sidecar_integration import recall, sync

N = 45  # messages the query's words find: 42 eligible once the last three are in the prompt
IN_CONTEXT = 6  # the last six messages: user messages #42–#44 and their replies
LONG = {20, 25}  # messages over 1,000 characters (their lexical score puts them among the 30 sent)
QUERY = "등대 열쇠 이야기"  # short: the reranker's query is the message, never the reply-tail text
PREVIOUS = "세라는 한참 동안 창밖을 바라보다가 조용히 고개를 끄덕였다. " * 20  # a long previous reply
KEY = "nmos-synthetic-rerank-key-7f3a9c41"
TAG = re.compile(r"기록 #(\d+):")


def message(i: int) -> str:
    text = f"기록 #{i:02d}: 하나는 등대 열쇠 이야기를 다시 꺼냈다."
    if i in LONG:
        text += " " + "바다 위로 안개가 천천히 흘러가고 있었다." * 60
    return text


def score_of(doc: str) -> float:
    """The stub's score: a permutation of the tags, unrelated to the fused order (exact in binary: k / 16)."""
    return ((int(TAG.search(doc).group(1)) * 17) % 47) / 16


def build(client) -> SimChat:
    chat = SimChat()
    chat.reply("이야기가 시작된다.")
    for i in range(N):
        chat.user(message(i))
        chat.reply(f"알겠어. 다음 장면으로 넘어가자 ({i}).")
    sync(client, chat)
    return chat


def settings() -> dict[str, Any]:
    return {**settings_for("lexical"), "packet_policy": "packet-v20"}


def configure(monkeypatch, reranker: rerank.Reranker) -> None:
    """The app's recall options with `reranker` set, for every /v1/retrieve the route serves (see the docstring)."""
    from nmos_sidecar import api

    real = retrieval.retrieve

    def with_reranker(conn, request, options):
        return real(conn, request, dataclasses.replace(options, reranker=reranker))

    monkeypatch.setattr(api, "retrieve", with_reranker)


def ask(client, chat: SimChat) -> dict[str, Any]:
    out = recall(client, chat, QUERY, in_context=[m["chatId"] for m in chat.messages[-IN_CONTEXT:]],
                 previous_ai=PREVIOUS, budget=600)
    return client.get(f"/v1/trace/{out['trace_id']}").json()


def texts(chat: SimChat) -> dict[str, str]:
    """Each message's normalized text by host id, as the corpus holds it."""
    return {m["chatId"]: clean_text(normalize_text(m["data"])) for m in chat.messages}


def tag(text: str) -> int:
    return int(TAG.search(text).group(1))


def eligible(trace: dict[str, Any]) -> list[dict[str, Any]]:
    held = set(trace["in_context"])
    return [c for c in trace["candidates"] if c["host_logical_id"] not in held]


def keys_named_rerank(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [k for k in value if "rerank" in str(k)] + [k for v in value.values() for k in keys_named_rerank(v)]
    if isinstance(value, list):
        return [k for v in value for k in keys_named_rerank(v)]
    return []


def db(url: str) -> psycopg.Connection:
    return psycopg.connect(url, row_factory=dict_row, autocommit=True)


def reranker(stub: RerankStub, **kw: Any) -> rerank.Reranker:
    return rerank.Reranker(url=stub.url, model="synthetic-rerank", api_key=KEY, **kw)


# --- the stub itself (passes before the wiring exists: a later failure is the wiring's, not the stub's) ---------------

def test_the_stub_answers_the_built_client(rerank_server):
    rerank_server.score = score_of
    docs = [message(i) for i in range(30)]
    scores = rerank.score(reranker(rerank_server), QUERY, docs)
    assert scores == [score_of(d) for d in docs]  # in input order, though the stub answers best first
    assert rerank_server.calls == 1 and rerank_server.last_auth == f"Bearer {KEY}"
    sent = rerank_server.last_json
    assert sent["query"] == QUERY and sent["model"] == "synthetic-rerank" and len(sent["documents"]) == 30
    assert max(len(d) for d in sent["documents"]) == 1000  # the client cut the long ones
    rerank_server.key = "data"
    assert rerank.score(reranker(rerank_server), QUERY, docs[:3]) == [score_of(d) for d in docs[:3]]
    rerank_server.status = 500
    assert rerank.score(reranker(rerank_server), QUERY, docs[:3]) is None
    assert rerank_server.calls == 3


# --- through /v1/retrieve -------------------------------------------------------------------------------------------

def test_unconfigured_nothing_is_called_and_the_trace_has_no_rerank_key(migrated, rerank_server):
    rerank_server.score = score_of
    with make_client(migrated, **settings()) as client:
        chat = build(client)
        trace = ask(client, chat)
    assert len(eligible(trace)) >= 35 and trace["excluded_in_context"]  # the fixture shows the cap and the prompt
    assert rerank_server.calls == 0
    assert keys_named_rerank(trace) == []


def test_configured_the_30_eligible_are_sent_once_and_reordered_by_score(migrated, rerank_server, monkeypatch):
    rerank_server.score = score_of
    with make_client(migrated, **settings()) as client:
        chat = build(client)
        fused = ask(client, chat)  # unconfigured: the fused order
        assert rerank_server.calls == 0
        # what the fused request shows, checked before the reranker is configured
        by_id = texts(chat)
        before = eligible(fused)
        assert len(before) >= 35
        top = before[:rerank.MAX_CANDIDATES]
        top_tags = [tag(by_id[c["host_logical_id"]]) for c in top]
        assert LONG <= set(top_tags)  # both long messages are among the 30
        held = {tag(by_id[c["host_logical_id"]]) for c in fused["candidates"]
                if c["host_logical_id"] in fused["in_context"]}
        assert held == {42, 43, 44} and len(fused["excluded_in_context"]) == 3
        expected = sorted(top, key=lambda c: -score_of(by_id[c["host_logical_id"]])) + before[rerank.MAX_CANDIDATES:]
        assert [c["revision_id"] for c in expected] != [c["revision_id"] for c in before]
        best = expected[0]["revision_id"]
        assert best not in {s["revision_id"] for s in fused["selected"]}  # the fused packet did not place it
        configure(monkeypatch, reranker(rerank_server))
        trace = ask(client, chat)

    # one call: the message as the query, the key as a Bearer token, the 30 eligible in fused order, each cut
    assert rerank_server.calls == 1
    sent = rerank_server.last_json
    assert rerank_server.last_auth == f"Bearer {KEY}"
    assert sent["query"] == QUERY and sent["model"] == "synthetic-rerank"
    assert len(sent["documents"]) == rerank.MAX_CANDIDATES
    assert [tag(d) for d in sent["documents"]] == top_tags
    assert all(len(d) <= rerank.MAX_DOC_CHARS for d in sent["documents"])
    assert all(d == by_id[c["host_logical_id"]][:rerank.MAX_DOC_CHARS] for d, c in zip(sent["documents"], top))
    assert sorted(tag(d) for d in sent["documents"] if len(d) == rerank.MAX_DOC_CHARS) == [20, 25]
    assert not held & {tag(d) for d in sent["documents"]}  # in-context ones are not sent

    # the 30 by score (stable), the rest as fused; each reranked entry carries its score, no other entry does
    after = eligible(trace)
    assert [c["revision_id"] for c in after] == [c["revision_id"] for c in expected]
    reranked = {c["revision_id"] for c in top}
    for c in trace["candidates"]:
        if c["revision_id"] in reranked:
            assert c["rerank"] == pytest.approx(score_of(by_id[c["host_logical_id"]]))
        else:
            assert "rerank" not in c
    opts = trace["recall_options"]
    assert opts["rerank_used"] is True
    assert isinstance(opts["rerank_ms"], (int, float)) and not isinstance(opts["rerank_ms"], bool)
    assert opts["rerank_ms"] >= 0

    # the reranker's best, which the fused packet did not place, is placed now
    assert best in {s["revision_id"] for s in trace["selected"]}


@pytest.mark.parametrize("failure", ["timeout", "status_500", "malformed", "not_json"])
def test_a_failed_rerank_leaves_the_fused_order(migrated, rerank_server, monkeypatch, failure):
    rerank_server.score = score_of
    kw: dict[str, Any] = {}
    if failure == "timeout":
        rerank_server.delay_s = 3.0
        kw["timeout_ms"] = 150
    elif failure == "status_500":
        rerank_server.status = 500
    elif failure == "malformed":
        rerank_server.raw_body = json.dumps({"results": [{"index": 0, "relevance_score": "high"}]}).encode()
    else:
        rerank_server.raw_body = b"<html>not json</html>"
    with make_client(migrated, **settings()) as client:
        chat = build(client)
        fused = ask(client, chat)
        configure(monkeypatch, reranker(rerank_server, **kw))
        trace = ask(client, chat)
    assert rerank_server.calls == 1  # it was asked, once
    assert trace["recall_options"]["rerank_used"] is False
    assert [c["revision_id"] for c in trace["candidates"]] == [c["revision_id"] for c in fused["candidates"]]
    assert all("rerank" not in c for c in trace["candidates"])
    assert [s["revision_id"] for s in trace["selected"]] == [s["revision_id"] for s in fused["selected"]]
    with db(migrated) as conn:  # its replay is the fused order too, and calls nothing
        out = audit.replay(conn, trace["id"], RecallOptions(reranker=reranker(rerank_server)))
    assert out["status"] == "ok" and out.get("reproduced") is True and rerank_server.calls == 1


def test_a_replay_of_a_reranked_request_calls_nothing_and_reproduces_its_packet(migrated, rerank_server, monkeypatch):
    rerank_server.score = score_of
    with make_client(migrated, **settings()) as client:
        chat = build(client)
        fused = ask(client, chat)
        configure(monkeypatch, reranker(rerank_server))
        trace = ask(client, chat)
    assert rerank_server.calls == 1 and trace["recall_options"]["rerank_used"] is True
    # the scores changed what was placed, so a replay in fused order could not reproduce it
    assert {s["revision_id"] for s in trace["selected"]} != {s["revision_id"] for s in fused["selected"]}
    rerank_server.score = lambda doc: -score_of(doc)  # a reranker asked again now would answer otherwise
    with db(migrated) as conn:
        for options in (RecallOptions(reranker=reranker(rerank_server)), RecallOptions()):
            out = audit.replay(conn, trace["id"], options)
            assert out["status"] == "ok" and out.get("reproduced") is True
            placed = [e["ref"] for e in out["lines"] if e["kind"] == "excerpt" and e["placed"]]
            assert placed == [e["ref"] for e in trace["lines"] if e["kind"] == "excerpt" and e["placed"]]
        out = audit.replay(conn, fused["id"], RecallOptions(reranker=reranker(rerank_server)))
        assert out["status"] == "ok" and out.get("reproduced") is True  # an unreranked request stays fused
    assert rerank_server.calls == 1  # no replay called the reranker


def test_the_key_is_in_no_trace_and_no_log_record(migrated, rerank_server, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    rerank_server.score = score_of
    with make_client(migrated, **settings()) as client:
        chat = build(client)
        configure(monkeypatch, reranker(rerank_server))
        ok = ask(client, chat)
        rerank_server.status = 500
        failed = ask(client, chat)
    assert rerank_server.auth == [f"Bearer {KEY}", f"Bearer {KEY}"]  # the key was used, twice
    assert ok["recall_options"]["rerank_used"] is True and failed["recall_options"]["rerank_used"] is False
    with db(migrated) as conn:
        rows = [r["row"] for r in conn.execute("SELECT row_to_json(t)::text AS row FROM retrieval_trace t")]
        assert len(rows) == 2
        audit.replay(conn, ok["id"], RecallOptions(reranker=reranker(rerank_server)))
    assert all(KEY not in row for row in rows)
    for record in caplog.records:
        assert KEY not in record.getMessage()
        assert KEY not in repr(record.args)
    assert KEY not in caplog.text
