"""PHASE-34 Q1: packet-v14 labels every ledger line (required, supportive, risky) and, at step 2, places what
packet-v13 places."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from conftest import make_client
from memeval import RECENT, _sync, settings_for
from nmos_sidecar.packet import Excerpt, Line, StateItem, compile_lines
from simchat import SimChat
from test_packet_ledger import extract, fact


def _line(kind: str, n: int, private: bool = False) -> Line:
    return Line(kind, f'    <Fact turn="{n}">line {n}</Fact>', {"assertion": n}, n, f"line {n}", f"words {n}",
                private=private)


def _excerpt(n: int, quote: bool = False) -> Excerpt:
    return Excerpt(turn=n, speaker="user", text=f"excerpt words number {n} about the harbour", score=0.1,
                   revision_id=f"r{n}", quote=quote)


def test_the_labels_follow_the_rules():
    out = compile_lines([_excerpt(1), _excerpt(2), _excerpt(3, quote=True)], 4000,
                        state=[StateItem("HP", "80/100", 9)],
                        facts=[_line("fact", 10), _line("fact", 11), _line("fact", 12), _line("fact", 13, private=True)],
                        threads=[_line("thread", 20), _line("thread", 21)],
                        story=[Line("summary", '    <Summary kind="story" turns="0–9">so far</Summary>', {"summary": "s1"},
                                    None, "story 0–9: so far", "so far"),
                               Line("summary", '    <Summary kind="scene" turns="8–9">a scene</Summary>', {"summary": "s2"},
                                    9, "scene 8–9: a scene", "a scene")],
                        cast=[("Hana", [_line("fact", 30)])],
                        policy="packet-v14", named=frozenset({"10", "21"}), risky=frozenset({"11"}))
    by = {(e["kind"], str((e.get("ref") or {}).get("assertion") or (e.get("ref") or {}).get("revision")
                         or (e.get("ref") or {}).get("summary") or (e.get("ref") or {}).get("key") or "")): e["label"]
          for e in out.ledger}
    assert by[("state", "HP")] == "required"
    assert by[("summary", "s1")] == "required" and by[("summary", "s2")] == "supportive"  # the story so far; a scene
    assert by[("fact", "30")] == "required"  # the cast
    assert by[("fact", "10")] == "required" and by[("thread", "21")] == "required"  # the question names them
    assert by[("fact", "11")] == "risky"
    assert by[("fact", "12")] == "supportive" and by[("thread", "20")] == "supportive"
    assert by[("fact", "13")] == "required"  # private: a knowledge boundary
    assert by[("excerpt", "r1")] == "required" and by[("excerpt", "r2")] == "supportive"  # the first excerpt
    assert by[("quote", "r3")] == "required"


def test_step_2_places_what_packet_v13_places_and_labels_nothing_else():
    lines = [fact(i) for i in range(10)]
    args = ([_excerpt(1), _excerpt(2)], 600)
    v13 = compile_lines(*args, facts=lines, policy="packet-v13", named=frozenset({"1"}))
    v14 = compile_lines(*args, facts=lines, policy="packet-v14", named=frozenset({"1"}))
    assert v13.text == v14.text
    assert not any("label" in e for e in v13.ledger) and all("label" in e for e in v14.ledger)


@pytest.fixture
def v14(migrated: str) -> Iterator[tuple]:
    settings = ({k: v for k, v in settings_for("full").items() if not k.startswith("embed_")}
                | {"embed_backfill": 0, "packet_policy": "packet-v14"})
    with make_client(migrated, **settings) as c:
        yield c, migrated


def test_every_line_of_a_v14_request_is_labeled_and_what_the_question_names_is_required(v14):
    """The question names Hana and the compass: both facts are required (an item the question names is what it asks
    about); the excerpt after the first is supportive."""
    client, url = v14
    chat = SimChat()
    chat.reply("Welcome to the story.")
    chat.user("Hana has the map.")
    chat.reply("Noted.")
    chat.user("Kaito has the compass.")
    chat.reply("Noted.")
    for i in range(RECENT):
        chat.user(f"Idle chatter {i} about clouds.")
        chat.reply("Noted.")
    _sync(client, chat)
    extract(url)
    question = "Hana, the compass?"
    chat.user(question)
    _sync(client, chat)
    out = client.post("/v1/retrieve", json={"chat_id": chat.id, "query": question, "previous_ai": "",
                                            "budget_tokens": 600,
                                            "in_context_ids": [m["chatId"] for m in chat.messages[-RECENT:]]}).json()
    trace = client.get(f"/v1/trace/{out['trace_id']}").json()
    assert trace["policy"] == "packet-v14" and all(e.get("label") for e in trace["lines"])
    facts = {e["text"]: e["label"] for e in trace["lines"] if e["kind"] == "fact"}
    assert facts.get("Hana possesses map") == "required" and facts.get("Kaito possesses compass") == "required"
    kept = [e["label"] for e in trace["lines"] if e["kind"] == "excerpt" and e["why"] != "repeats"]
    assert kept[:1] == ["required"] and set(kept[1:]) <= {"supportive"}  # the first kept excerpt is the reserved one


# --- the rest (Q2, Q3) ---------------------------------------------------------------------------------------------

from nmos_sidecar.overuse import Recent, key, tired  # noqa: E402
from nmos_sidecar.retrieval import Gathered, _rested  # noqa: E402

A, B = key("fact", {"assertion": 1}), key("excerpt", {"revision": "r9"})


def placed(*keys, echoed=()) -> Recent:
    return Recent(frozenset(keys), frozenset(echoed))


def test_a_line_placed_twice_in_a_row_and_never_used_rests():
    assert tired([placed(A, B), placed(A, B)]) == {A, B}
    assert tired([placed(A, B), placed(A, B, echoed=[B])]) == {A}  # a reply used B: it is not tired
    assert tired([placed(A), placed(B)]) == frozenset()  # not in a row
    assert tired([placed(A, B)]) == frozenset()  # one request is no run
    assert tired([placed(A), placed(A)], rest_after=3) == frozenset()
    assert tired([placed(A), placed(A), placed(A)], rest_after=3) == {A}


def test_a_resting_line_is_left_out_for_two_requests():
    assert tired([placed(), placed(A), placed(A)]) == {A}  # left out once: still resting
    assert tired([placed(), placed(), placed(A), placed(A)]) == frozenset()  # left out twice: a candidate again


def test_what_the_question_names_or_its_words_found_never_rests():
    g = Gathered()
    g.named = {"2"}
    rows = [{"id": 1}, {"id": 2}, {"id": 3}]
    assert _rested(rows, "fact", frozenset({("fact", "1"), ("fact", "2")}), g) == [{"id": 2}, {"id": 3}]
    assert g.rested == 1
    secret = [{"id": 4, "hidden_from": ["Kaito"]}, {"id": 5, "known_by": ["Hana"]}]
    assert _rested(secret, "fact", frozenset({("fact", "4"), ("fact", "5")}), Gathered()) == secret  # boundaries stay
    excerpts = [{"id": "r1", "user_score": 0.6}, {"id": "r2", "sim": 0.5}]
    rest = frozenset({("excerpt", "r1"), ("excerpt", "r2")})
    kept = _rested(excerpts, "excerpt", rest, Gathered(), ident=lambda c: c["id"],
                   hit=lambda c: bool(c.get("user_score") or c.get("keyword_score")))
    assert kept == [{"id": "r1", "user_score": 0.6}]  # the question's words found r1; r2 came by vector alone


def test_a_request_records_how_many_lines_rested_and_a_question_about_the_past_rests_nothing(v14):
    client, url = v14
    chat = SimChat()
    chat.reply("Welcome to the story.")
    chat.user("Hana has the map.")
    chat.reply("Noted.")
    for i in range(RECENT + 2):
        chat.user(f"Idle chatter {i} about clouds.")
        chat.reply("Noted.")
    _sync(client, chat)
    extract(url)

    def ask(question: str) -> dict:
        chat.user(question)
        _sync(client, chat)
        out = client.post("/v1/retrieve", json={"chat_id": chat.id, "query": question, "previous_ai": "",
                                                "budget_tokens": 600,
                                                "in_context_ids": [m["chatId"] for m in chat.messages[-RECENT:]]}).json()
        chat.reply("Quiet waves.")  # a reply that uses nothing the packet held
        _sync(client, chat)
        return client.get(f"/v1/trace/{out['trace_id']}").json()

    for _ in range(2):
        first = ask("Tell me about the map")
    assert "rested" in first["latency_ms"]
    then = ask("What was the map like at first?")  # a question about how it started: old memory is the answer
    assert then["latency_ms"]["rested"] == 0
