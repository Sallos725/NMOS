"""PHASE-21 (ADR 0056): when the message asks how it started, the start.

The rows are synthetic, shaped like the measured cases (AGE-26): the oldest of several similar events lost its slot to
newer ones, and a pair's current form of address in the chat window took its first version with it.
"""

from __future__ import annotations

from uuid import UUID

import pytest

from memeval import _sync
from nmos_sidecar import audit
from nmos_sidecar.facts import FIRST_CUE, relevant_facts
from nmos_sidecar.retrieval import RecallOptions
from simchat import SimChat
from test_packet_ledger import db, extract, full  # noqa: F401  (`full` is a fixture)

BASE = {"object": None, "object_type": None, "host_logical_id": "x", "known_by": None, "hidden_from": None,
        "knowledge": "public", "salience": None, "epistemic": "stated"}


def fact(position, subject, predicate, value, **extra):
    return {**BASE, "position": position, "turn": position // 2, "subject": subject, "predicate": predicate,
            "value": value, **extra}


@pytest.mark.parametrize("message", ["처음에 둘이 뭐 했지?", "맨 처음 만났을 때", "최초로 간 곳", "예전에 살던 집",
                                     "옛날 얘기", "원래 뭐라고 불렀어?", "초반에 있던 일", "첫 만남 기억나?",
                                     "첫번째 선물", "첫째 날", "What did she call him at first?",
                                     "the first time we met", "Originally, who was it?", "In the beginning"])
def test_the_cue(message):
    assert FIRST_CUE.search(message)


@pytest.mark.parametrize("message", ["첫눈 왔다", "지금 뭐 해?", "마지막에 뭐라고 했지?", "최근에 무슨 일 있었어?",
                                     "first of all, hi", "the firstborn"])
def test_not_the_cue(message):
    assert not FIRST_CUE.search(message)


def baking():
    """하나's first baking with 유이 (two minor events of the first turns) and two later major events of hers."""
    first = fact(2, "하나", "event", "유이와 쿠키를 구움", salience="minor")
    gift = fact(4, "하나", "event", "유이에게 쿠키를 나눠 줌", salience="minor")
    later = [fact(200, "하나", "event", "축제 케이크를 완성함", salience="major"),
             fact(300, "하나", "event", "가게를 물려받음", salience="major")]
    return first, gift, later


def test_an_old_minor_event_comes_before_a_newer_major_one_with_the_cue():
    first, gift, later = baking()
    picked = relevant_facts([*later, gift, first], "하나는 처음에 뭘 만들었지?", "", set(), 8, 2, first_cue=True)
    assert picked == [first, gift]


def test_with_the_cue_a_mention_counts_by_whether_not_how_strongly():
    # 유이's old event is mentioned only in the previous reply, 하나's newer one in the message: the older still comes first
    old = fact(2, "유이", "event", "하나와 쿠키를 구움", salience="minor")
    new = fact(300, "하나", "event", "가게를 물려받음", salience="major")
    assert relevant_facts([new, old], "하나 처음에 뭐 했지?", "유이가 웃었다.", set(), 8, 1, first_cue=True) == [old]
    assert relevant_facts([new, old], "하나 뭐 했지?", "유이가 웃었다.", set(), 8, 1, first_cue=True) == [new]


def test_without_the_cue_or_the_option_the_major_events_keep_the_slots():
    first, gift, later = baking()
    rows = [*later, gift, first]
    today = relevant_facts(rows, "하나는 요즘 뭘 만들어?", "", set(), 8, 2, first_cue=True)
    off = relevant_facts(rows, "하나는 처음에 뭘 만들었지?", "", set(), 8, 2)
    assert today == off == [later[1], later[0]]  # the minor events miss the lexical bar (ADR 0020)


def test_a_minor_event_below_the_lexical_bar_is_kept_with_the_cue_only():
    first, _, _ = baking()
    assert relevant_facts([first], "하나는 처음에 뭐 했어?", "", set(), 8, 3) == []
    assert relevant_facts([first], "하나는 처음에 뭐 했어?", "", set(), 8, 3, first_cue=True) == [first]


def test_equal_scores_go_to_the_older_fact_with_the_cue():
    old, new = fact(10, "하나", "has_trait", "단 것을 좋아함"), fact(90, "하나", "has_trait", "짠 것을 좋아함")
    assert relevant_facts([new, old], "하나 기억나?", "", set(), 1) == [new]
    assert relevant_facts([new, old], "하나 처음 기억나?", "", set(), 1, first_cue=True) == [old]


def addressing(first_position: int, **first):
    """유이 calls 하나 '선배' at first and '언니' now; the current version's source is in the window."""
    history = [{"position": first_position, "turn": first_position // 2, "predicate": "addresses", "subject": "유이",
                "object": "하나", "value": "선배", "polarity": "positive", "knowledge": "public", "known_by": None,
                "hidden_from": None, **first},
               {"position": 120, "turn": 60, "predicate": "addresses", "subject": "유이", "object": "하나",
                "value": "언니", "polarity": "positive", "knowledge": "public", "known_by": None, "hidden_from": None}]
    return fact(120, "유이", "addresses", "언니", object="하나", object_type="character", host_logical_id="in-window",
                history=history)


QUESTION = "유이는 하나를 처음에 뭐라고 불렀지?"


def test_a_standing_fact_in_the_window_stays_when_an_earlier_version_starts_before_it():
    now = addressing(first_position=20)
    assert relevant_facts([now], QUESTION, "", {"in-window"}, 8, first_cue=True, window_start=100) == [now]
    # without the cue, or without the option, it stays out as today (the window holds the current version)
    assert relevant_facts([now], "유이는 하나를 뭐라고 불러?", "", {"in-window"}, 8, first_cue=True, window_start=100) == []
    assert relevant_facts([now], QUESTION, "", {"in-window"}, 8, window_start=100) == []


def test_a_standing_fact_whose_every_version_is_in_the_window_stays_out():
    now = addressing(first_position=110)
    assert relevant_facts([now], QUESTION, "", {"in-window"}, 8, first_cue=True, window_start=100) == []


def test_a_canon_version_counts_only_when_the_prompt_does_not_hold_it():
    # canon statements have positions below every turn; a held one is in the prompt already (ADR 0047)
    now = addressing(first_position=-3, canon="card:desc", turn=None)
    held = {"in-window", "canon:card:desc"}
    assert relevant_facts([now], QUESTION, "", held, 8, first_cue=True, window_start=100) == []
    assert relevant_facts([now], QUESTION, "", {"in-window"}, 8, first_cue=True, window_start=100) == [now]


def test_an_earlier_version_kept_from_someone_does_not_bring_the_fact_back():
    # the packet prints earlier versions under the current row's marks: one with other marks would lose its own
    now = addressing(first_position=20, knowledge="limited", hidden_from=["리아"])
    assert relevant_facts([now], QUESTION, "", {"in-window"}, 8, first_cue=True, window_start=100) == []


def test_an_event_in_the_window_stays_out_with_the_cue():
    e = fact(120, "하나", "event", "유이와 쿠키를 구움", salience="minor", host_logical_id="in-window")
    assert relevant_facts([e], "하나 처음에 뭐 했지?", "", {"in-window"}, 8, first_cue=True, window_start=100) == []


# --- through a request, and its replay ------------------------------------------------------------------------------

WINDOW = 6


def chat_with_a_start(client, url) -> SimChat:
    """Hana's chores from the start (minor events), a later betrayal (major), and a form of address that changed in the
    last messages: the window holds the current one only."""
    chat = SimChat()
    chat.reply("Welcome to the story.")
    for user in ("Hana and Kaito agree to speak informally.", "Hana did chore 1.", "Hana did chore 2.",
                 *[f"Idle chatter {i} about clouds." for i in range(6)], "Hana betrayed Kaito.",
                 "Hana goes back to formal speech with Kaito.", "Idle chatter about rain."):
        chat.user(user)
        chat.reply("Noted.")
        _sync(client, chat)
    extract(url)
    return chat


def ask_first(client, chat: SimChat, text: str) -> dict:
    chat.user(text)
    _sync(client, chat)
    return client.post("/v1/retrieve", json={"chat_id": chat.id, "query": text, "previous_ai": "",
                                             "in_context_ids": [m["chatId"] for m in chat.messages[-WINDOW:]],
                                             "budget_tokens": 1500}).json()


def test_a_request_with_the_cue_gets_the_start_and_records_the_option(full):
    client, url = full
    chat = chat_with_a_start(client, url)
    out = ask_first(client, chat, "처음에 Hana는 Kaito한테 어떻게 말했지?")
    text = out["packet"]["text"]
    assert "chore 1" in text and "chore 2" in text  # minor events, below the lexical bar
    # the current form of address is in the window; the first one is not
    assert "Hana addresses Kaito: formal speech; before, turn 1: Hana addresses Kaito: informal speech" in text
    t = client.get(f"/v1/trace/{out['trace_id']}").json()
    assert t["recall_options"]["first_cue"] is True


def test_a_trace_without_the_option_replays_as_it_was(full):
    client, url = full
    chat = chat_with_a_start(client, url)
    out = ask_first(client, chat, "처음에 Hana는 Kaito한테 어떻게 말했지?")
    with db(url) as conn:
        on = audit.replay(conn, UUID(out["trace_id"]), RecallOptions())
        conn.execute("UPDATE retrieval_trace SET recall_options = recall_options - 'first_cue' WHERE id = %s",
                     (out["trace_id"],))
        old = audit.replay(conn, UUID(out["trace_id"]), RecallOptions())
    assert on["reproduced"] is True and on["text"] == out["packet"]["text"]
    assert "chore 1" not in old["text"] and "Hana addresses Kaito" not in old["text"]
