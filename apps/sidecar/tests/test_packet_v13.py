"""PHASE-33 (ADR 0067): packet-v13's lines. Quotes and the excerpts of turns extraction has not reached (Q5) are raw
evidence: never dropped for restating a fact. packet-v12 compiles as before."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from memeval import RECENT, _sync, settings_for
from nmos_sidecar import audit
from nmos_sidecar.packet import Excerpt, compile_lines
from nmos_sidecar.retrieval import RecallOptions
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
    extract(url)  # every turn is extracted now; a replay reads the request as it was
    with psycopg.connect(url, row_factory=dict_row) as conn:
        again = audit.replay(conn, UUID(out["trace_id"]), RecallOptions())
    assert again["status"] == "ok" and again["reproduced"] is True
    assert [e.get("marks") for e in again["lines"] if "silver map" in e["text"]][:1] == [{"unextracted": True}]


def test_a_quote_only_the_quote_route_found_keeps_a_secret_as_a_keyword_only_excerpt_does(v13):
    """ADR 0052's rule for raw text no other route would place holds for the quote route's own messages (ADR 0067)."""
    client, url = v13
    chat = SimChat()
    chat.reply("Welcome to the story.")
    chat.user("Hana keeps a secret from Kaito: the letter is forged.")
    chat.reply("Noted.")
    chat.user('Hana whispered "burn it, the letter is forged".')  # turn 2: nothing the question says
    chat.reply("Noted.")
    for i in range(RECENT + 2):
        chat.user(f"Idle chatter {i} about clouds.")
        chat.reply("Noted.")
    _sync(client, chat)
    extract(url)
    question = "Kaito here. What was said on turn 2?"
    chat.user(question)
    _sync(client, chat)
    out = client.post("/v1/retrieve", json={"chat_id": chat.id, "query": question, "previous_ai": "", "budget_tokens": 600,
                                            "in_context_ids": [m["chatId"] for m in chat.messages[-RECENT:]]}).json()
    trace = client.get(f"/v1/trace/{out['trace_id']}").json()
    assert trace["latency_ms"]["path"] == "forensic"
    assert not any("forged" in line for line in out["packet"]["text"].splitlines() if "<Quote" in line)
    assert trace["latency_ms"]["quote_withheld"] >= 1  # found by the route alone: no keyword or lexical candidate


def test_a_turn_edited_since_its_extraction_is_unextracted_again(v13):
    """An extraction of the turn as it was before an edit does not count (its window changed, ADR 0008)."""
    client, url = v13
    chat = SimChat()
    chat.reply("Welcome to the story.")
    chat.user("Hana hid the silver map in the attic.")
    chat.reply("Noted.")
    chat.user("Hana smiles.")
    chat.reply("Noted.")
    _sync(client, chat)
    extract(url)
    chat.edit(1, "Hana hid the silver map under the lighthouse stairs.")  # turn 1, after its extraction
    for i in range(RECENT):
        chat.user(f"Idle chatter {i} about clouds.")
        chat.reply("Noted.")
    _sync(client, chat)
    chat.user("Where did Hana hide the silver map?")
    _sync(client, chat)
    out = client.post("/v1/retrieve", json={"chat_id": chat.id, "query": "Where did Hana hide the silver map?",
                                            "previous_ai": "", "budget_tokens": 600,
                                            "in_context_ids": [m["chatId"] for m in chat.messages[-RECENT:]]}).json()
    lines = client.get(f"/v1/trace/{out['trace_id']}").json()["lines"]
    hit = [e for e in lines if e["kind"] == "excerpt" and "lighthouse stairs" in e["text"]]
    assert hit and hit[0]["marks"] == {"unextracted": True}


def test_the_trace_records_the_route_s_time_apart_from_the_quotes_placed(v13):
    client, url = v13
    chat = SimChat()
    chat.reply('Welcome. Hana said "the lighthouse opens at dawn".')
    for i in range(RECENT + 2):
        chat.user(f"Idle chatter {i} about clouds.")
        chat.reply("Noted.")
    _sync(client, chat)
    question = "What did Hana say about the lighthouse?"
    chat.user(question)
    _sync(client, chat)
    out = client.post("/v1/retrieve", json={"chat_id": chat.id, "query": question, "previous_ai": "", "budget_tokens": 600,
                                            "in_context_ids": [m["chatId"] for m in chat.messages[-RECENT:]]}).json()
    lat = client.get(f"/v1/trace/{out['trace_id']}").json()["latency_ms"]
    assert lat["path"] == "forensic" and isinstance(lat["quotes"], int) and isinstance(lat["quote_route"], float)


def test_a_quote_before_an_allbefore_cut_never_reaches_the_packet(v13):
    """Invariant 7 (Codex review, #274): what the host hides behind an `allBefore` cut is no memory. The quote route's
    own searches (the words, a named turn, a first cue) stop at the cut as lexical and vector recall do."""
    client, url = v13
    chat = SimChat()
    chat.reply("Welcome to the story.")
    chat.user('Hana said "The ruby is kept in the lighthouse." to Kaito.')
    chat.reply("Noted.")
    chat.user("A new start.")
    chat.disable(-1, "allBefore")
    chat.reply("Noted.")
    for i in range(RECENT + 2):
        chat.user(f"Idle chatter {i} about clouds.")
        chat.reply("Noted.")
    _sync(client, chat)
    for question in ("What did Hana say about the ruby?", "What was said on turn 1?",
                     "What did Hana say the first time she met Kaito?"):
        chat.user(question)
        _sync(client, chat)
        out = client.post("/v1/retrieve", json={"chat_id": chat.id, "query": question, "previous_ai": "",
                                                "budget_tokens": 600,
                                                "in_context_ids": [m["chatId"] for m in chat.messages[-RECENT:]]}).json()
        assert "lighthouse" not in out["packet"]["text"], question
        chat.reply("Noted.")
        _sync(client, chat)
