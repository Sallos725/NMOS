"""PHASE-33 (ADR 0067): packet-v13's lines. Quotes and the excerpts of turns extraction has not reached (Q5) are raw
evidence: never dropped for restating a fact. packet-v12 compiles as before."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from conftest import make_client
from memeval import RECENT, _sync, settings_for
from nmos_sidecar.packet import Excerpt, compile_lines
from simchat import SimChat
from test_packet_ledger import extract, fact

SAME = "하나의 특징: 등대 꼭대기에서 바다를 오래 바라보는 버릇이 있다 1."


def _excerpt(**kw) -> Excerpt:
    return Excerpt(turn=9, speaker="user", text=SAME, score=0.05, revision_id="r-trait", short=SAME, **kw)


@pytest.mark.parametrize("kind", ["unextracted", "quote"])
def test_raw_evidence_is_not_dropped_for_restating_a_fact(kind):
    item = _excerpt(**{kind: True})
    out = compile_lines([item], 600, facts=[fact(i) for i in range(4)], policy="packet-v13")
    [entry] = [e for e in out.ledger if e["kind"] in ("excerpt", "quote")]
    assert entry["placed"] and entry["why"] == "placed"
    assert entry.get("marks") == ({"unextracted": True} if kind == "unextracted" else None)


def test_an_extracted_excerpt_that_restates_a_fact_is_still_dropped():
    for policy in ("packet-v12", "packet-v13"):
        out = compile_lines([_excerpt()], 600, facts=[fact(i) for i in range(4)], policy=policy)
        [entry] = [e for e in out.ledger if e["kind"] == "excerpt"]
        assert not entry["placed"] and entry["why"] == "repeats"


@pytest.fixture
def v13(migrated: str) -> Iterator[tuple]:
    settings = ({k: v for k, v in settings_for("full").items() if not k.startswith("embed_")}
                | {"embed_backfill": 0, "packet_policy": "packet-v13"})
    with make_client(migrated, **settings) as c:
        yield c, migrated


def test_a_turn_extraction_has_not_reached_is_marked_in_the_ledger(v13):
    client, url = v13
    chat = SimChat()
    chat.reply("Welcome to the story.")
    chat.user("Hana keeps the brass key in her coat.")
    chat.reply("Noted.")
    chat.user("Hana smiles.")
    chat.reply("Noted.")
    _sync(client, chat)
    extract(url)  # the turns before the newest are extracted; the ones below are not
    chat.user("Hana hid the silver map under the lighthouse stairs.")
    chat.reply("Noted.")
    for i in range(RECENT):
        chat.user(f"Idle chatter {i} about clouds.")
        chat.reply("Noted.")
    _sync(client, chat)
    chat.user("Where did Hana hide the silver map?")
    _sync(client, chat)
    out = client.post("/v1/retrieve", json={"chat_id": chat.id, "query": "Where did Hana hide the silver map?",
                                            "previous_ai": "", "budget_tokens": 600,
                                            "in_context_ids": [m["chatId"] for m in chat.messages[-RECENT:]]}).json()
    trace = client.get(f"/v1/trace/{out['trace_id']}").json()
    assert trace["policy"] == "packet-v13"
    hit = [e for e in trace["lines"] if e["kind"] == "excerpt" and "silver map" in e["text"]]
    assert hit and hit[0]["marks"] == {"unextracted": True}
    assert not any((e.get("marks") or {}).get("unextracted") for e in trace["lines"] if "brass key" in e["text"])
