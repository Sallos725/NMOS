"""PHASE-46: packet-v19 adds no fact or claim slots for a question that names no one and shares no fact's words."""
from __future__ import annotations

import pytest

from conftest import make_client
from memeval import _sync, settings_for
from nmos_sidecar import packet
from nmos_sidecar.retrieval import unrelated_question
from test_packet_fill import secrets_chat


def test_v19_inherits_v18_and_is_not_the_default():
    assert packet.DEFAULT_POLICY == "packet-v18" and "packet-v19" in packet.POLICIES
    for name, policies in vars(packet).items():
        if name.endswith("_POLICIES") and "packet-v18" in policies:
            assert "packet-v19" in policies, name
    assert packet.RELATED_FILL_POLICIES == {"packet-v19"}
    assert packet.NON_ASCII["packet-v19"] == packet.NON_ASCII["packet-v18"]
    assert packet.fill(8000, "packet-v19") == packet.fill(8000, "packet-v18")  # the budget still grows excerpts


@pytest.mark.parametrize("query,named,expected", [
    ("내일 날씨 어떨까?", set(), True),
    ("What will the weather be tomorrow?", set(), True),
    ("고개를 끄덕인다.", set(), False),  # narration without a name keeps the fill (14 of 80 real requests changed)
    ("Hana는 뭐 가지고 있어?", {"1"}, False),  # a question that names someone
    ("Who possesses the key?", set(), False),  # shares a fact's words
])
def test_an_unrelated_question(query, named, expected):
    facts = [{"subject": "Hana", "predicate": "possesses", "object": "the key", "value": None}]
    assert unrelated_question(query, named, facts) is expected


def ask(client, chat, text: str, budget: int) -> str:
    return client.post("/v1/retrieve", json={"chat_id": chat.id, "query": text, "previous_ai": "Hana smiled at Kaito.",
                                             "in_context_ids": [m["chatId"] for m in chat.messages[-4:]],
                                             "budget_tokens": budget}).json()["packet"]["text"]


def keys(text: str) -> int:
    return sum(f"has the key{i}" in text or f"possesses key{i}" in text for i in range(12))


@pytest.mark.parametrize("policy,query,grows", [
    ("packet-v18", "What will the weather be tomorrow?", True),
    ("packet-v19", "What will the weather be tomorrow?", False),
    ("packet-v19", "Kaito, what does Hana have?", True),
])
def test_the_added_fact_slots_need_a_related_message(migrated, policy, query, grows):
    settings = {k: v for k, v in settings_for("full").items() if not k.startswith("embed_")} | {"embed_backfill": 0}
    with make_client(migrated, **(settings | {"packet_policy": policy})) as client:
        chat = secrets_chat(client, migrated)
        chat.user(query)
        _sync(client, chat)
        small, large = ask(client, chat, query, 2000), ask(client, chat, query, 8000)
        assert keys(small) > 0  # the previous reply names Hana: her facts are candidates either way
        assert (keys(large) > keys(small)) is grows
