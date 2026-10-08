"""PHASE-36: under packet-v16 a message that only names a character makes required (never resting) how the character
stands now or with another, and its knowledge boundaries; its other facts are supportive unless the message's words
point at them."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from conftest import make_client
from memeval import RECENT, _sync, settings_for
from nmos_sidecar.packet import NAMED_POLICIES, POLICIES
from simchat import SimChat
from test_packet_ledger import extract


def test_packet_v16_is_a_policy():
    assert "packet-v16" in POLICIES and NAMED_POLICIES == {"packet-v16"}


def client_for(url: str, policy: str):
    settings = ({k: v for k, v in settings_for("full").items() if not k.startswith("embed_")}
                | {"embed_backfill": 0, "packet_policy": policy, "facts_limit": 12})
    return make_client(url, **settings)


@pytest.fixture
def story(migrated: str) -> Iterator[str]:
    yield migrated


def labels(url: str, policy: str, question: str) -> dict[str, str]:
    with client_for(url, policy) as client:
        chat = SimChat()
        chat.reply("Welcome to the story.")
        chat.user("Hana is a knight.")
        chat.reply("Noted.")
        chat.user("Hana has the map.")
        chat.reply("Noted.")
        chat.user("Hana and Kaito agree to speak informally.")
        chat.reply("Noted.")
        chat.user("Hana betrayed Kaito.")
        chat.reply("Noted.")
        for i in range(RECENT):
            chat.user(f"Idle chatter {i} about clouds.")
            chat.reply("Noted.")
        _sync(client, chat)
        extract(url)
        chat.user(question)
        _sync(client, chat)
        out = client.post("/v1/retrieve", json={"chat_id": chat.id, "query": question, "previous_ai": "",
                                                "budget_tokens": 1200,
                                                "in_context_ids": [m["chatId"] for m in chat.messages[-RECENT:]]}).json()
        trace = client.get(f"/v1/trace/{out['trace_id']}").json()
    return {e["text"]: e["label"] for e in trace["lines"] if e["kind"] == "fact"}


def test_a_name_alone_names_how_a_character_stands_not_everything_about_it(story):
    v15 = labels(story, "packet-v15", "Hana, are you there?")
    v16 = labels(story, "packet-v16", "Hana, are you there?")
    knight = next(t for t in v16 if "knight" in t)
    event = next(t for t in v16 if "betray" in t)
    informal = next(t for t in v16 if "informal" in t or "반말" in t or "addresses" in t)
    assert v15[knight] == "required" and v15[event] == "required"  # packet-v15: the name made all of them required
    assert v16[knight] == "supportive" and v16[event] == "supportive"  # a past event and a trait: they may rest
    assert v16[informal] == "required"  # how two characters speak stays required
    assert all(label == "required" for text, label in v16.items() if "map" in text)  # what she carries now


def test_the_messages_own_words_still_name_a_fact(story):
    v16 = labels(story, "packet-v16", "Hana, are you a knight?")
    assert v16[next(t for t in v16 if "knight" in t)] == "required"
