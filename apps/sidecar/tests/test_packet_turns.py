"""packet-v7 (ADR 0041): one numbering for `turn` in the packet. Facts, claims and threads carry the turn index
(ADR 0008); before packet-v7 an excerpt's `turn` and a state item's `as_of_turn` were the message's head position."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import ExitStack

import pytest

from conftest import make_client
from memeval import settings_for
from test_sidecar_integration import sync as _sync
from nmos_sidecar.packet import Excerpt, StateItem, compile_lines, excerpt_line, state_block
from simchat import SimChat
from test_packet_ledger import extract

RULES = {"rules": [{"card": "Status test", "id": "status", "kind": "block", "start": r"```status", "end": r"```", "role": "char"}]}
STATUS = "The vault password is violet-seven.\n```status\n장소: 폐허가 된 성당\n```"


@pytest.fixture
def client_for(migrated: str, tmp_path) -> Iterator:
    """A client for a policy: stub extraction and parser state, no vectors."""
    rules = tmp_path / "rules.json"
    rules.write_text(json.dumps(RULES), encoding="utf-8")
    settings = {k: v for k, v in settings_for("full").items() if not k.startswith("embed_")} | {
        "embed_backfill": 0, "parsers_file": str(rules)}
    with ExitStack() as stack:
        yield lambda policy: stack.enter_context(make_client(migrated, **(settings | {"packet_policy": policy})))


def story(client, url: str) -> SimChat:
    """Turn 1 is a user message (position 1) and its reply (position 2); four idle turns follow."""
    chat = SimChat()
    chat.reply("Welcome to the story.")  # position 0, turn 0
    chat.user("Akari is in the chapel.")  # position 1, turn 1
    chat.reply(STATUS)  # position 2, turn 1
    for i in range(4):  # positions 3-10, turns 2-5
        chat.user(f"Idle chatter {i} about clouds.")
        chat.reply(f"Idle reply {i} about the weather.")
    _sync(client, chat, character_name="Status test")
    extract(url)
    return chat


def ask(client, chat: SimChat, text: str) -> dict:
    chat.user(text)
    _sync(client, chat, character_name="Status test")
    recent = chat.messages[-4:]
    return client.post("/v1/retrieve", json={"chat_id": chat.id, "query": text, "previous_ai": "",
                                             "in_context_ids": [m["chatId"] for m in recent],
                                             "budget_tokens": 800}).json()


QUERY = "Akari, what was the vault password?"


def test_packet_v6_numbers_an_excerpt_by_its_position_and_a_fact_by_its_turn(client_for, migrated):
    """The inconsistency seen in the Phase 11 real-host smoke, kept by packet-v6 so its traces replay."""
    client = client_for("packet-v6")
    text = ask(client, story(client, migrated), QUERY)["packet"]["text"]
    assert '<Fact kind="located_in" turn="1">Akari located in chapel</Fact>' in text
    assert '<Excerpt turn="2" speaker="character">' in text  # the reply of turn 1, at position 2
    assert '<Item key="장소" as_of_turn="2">폐허가 된 성당</Item>' in text


def test_packet_v7_numbers_excerpts_and_state_by_the_turn_of_their_message(client_for, migrated):
    client = client_for("packet-v7")
    out = ask(client, story(client, migrated), QUERY)
    text = out["packet"]["text"]
    assert '<Fact kind="located_in" turn="1">Akari located in chapel</Fact>' in text
    assert '<Excerpt turn="1" speaker="character">' in text
    assert '<Item key="장소" as_of_turn="1">폐허가 된 성당</Item>' in text
    trace = client.get(f"/v1/trace/{out['trace_id']}").json()
    assert trace["policy"] == "packet-v7"
    turns = {e["kind"]: e["turn"] for e in trace["lines"] if e["placed"]}
    assert turns == {"state": 1, "fact": 1, "excerpt": 1}  # the ledger says what the packet says
    assert [s["turn"] for s in trace["selected"]] == [1]


def test_the_inspector_shows_the_turn_a_state_item_is_as_of(client_for, migrated):
    """Its column says "As of turn", as the fact tables do (ADR 0008); it showed the position."""
    client = client_for("packet-v6")
    story(client, migrated)
    conv = client.get("/v1/conversations").json()[0]["id"]
    page = client.get(f"/inspector/c/{conv}", params={"lang": "en"}).text
    assert "<td>장소</td><td>폐허가 된 성당</td><td>1</td><td>status</td>" in page
    state = client.get(f"/v1/conversations/{conv}/state").json()
    assert [(s["turn"], s["position"]) for s in state] == [(1, 2)]


def test_each_trace_replays_under_its_own_policy(client_for, migrated):
    """ADR 0027: a recorded packet compiles again exactly under the policy that built it."""
    client = client_for("packet-v6")
    chat = story(client, migrated)
    v6 = ask(client, chat, QUERY)
    again = client.get(f"/v1/trace/{v6['trace_id']}/replay").json()
    assert again["reproduced"] is True and again["text"] == v6["packet"]["text"]
    moved = client.get(f"/v1/trace/{v6['trace_id']}/replay", params={"policy": "packet-v7"}).json()
    assert '<Excerpt turn="1" ' in moved["text"] and '<Excerpt turn="2" ' not in moved["text"]
    v7_client = client_for("packet-v7")
    chat.reply("Noted.")
    v7 = ask(v7_client, chat, QUERY)
    again = v7_client.get(f"/v1/trace/{v7['trace_id']}/replay").json()
    assert again["policy"] == "packet-v7" and again["reproduced"] is True and again["text"] == v7["packet"]["text"]


def test_excerpts_of_one_turn_stay_in_story_order():
    """Two messages of one turn share its number; the packet still lists them as the story has them."""
    reply = Excerpt(turn=4, speaker="Hana", text="She nods.", score=0.02, revision_id="r2", position=8)
    user = Excerpt(turn=4, speaker="user", text="Hana, open the door.", score=0.03, revision_id="r1", position=7)
    early = Excerpt(turn=1, speaker="Hana", text="The door is locked.", score=0.01, revision_id="r0", position=2)
    text = compile_lines([reply, early, user], 800, policy="packet-v7").text
    assert text.index("The door is locked.") < text.index("Hana, open the door.") < text.index("She nods.")


def test_a_message_without_a_turn_has_no_turn_in_the_packet():
    """Comments and disabled messages belong to no turn (ADR 0008). A state item from one says no turn rather
    than a number of another scale."""
    assert state_block([StateItem("HP", "42/100", None)]) == ["  <State>", '    <Item key="HP">42/100</Item>', "  </State>"]
    assert excerpt_line(Excerpt(None, "Hana", "…", 0.0, "r")) == '  <Excerpt speaker="Hana">…</Excerpt>'
