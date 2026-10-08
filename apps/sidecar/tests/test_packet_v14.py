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


# --- the Inspector (Q7) --------------------------------------------------------------------------------------------

def test_placement_numbers_on_the_whole_packet_and_on_supportive_lines():
    from nmos_sidecar.overuse import placement

    def line(n, label, tok=10):
        return {"kind": "fact", "ref": {"assertion": n}, "placed": True, "tok": tok, "label": label}

    ledgers = [[line(1, "required"), line(2, "supportive")], [line(1, "required"), line(3, "supportive")],
               [line(1, "required"), line(3, "supportive")], [line(1, "required"), line(3, "supportive")]]
    out = placement(ledgers)
    assert out["requests"] == 4
    assert out["repeat_share"] == round((1 / 2 + 2 / 2 + 2 / 2) / 3, 3)
    assert out["supportive_repeat_share"] == round((0 + 1 + 1) / 3, 3)
    assert out["stale_token_share"] == 0.5 and out["supportive_stale_token_share"] == 0.0  # 3 was new in request 2
    assert "supportive_repeat_share" not in placement([[{"kind": "fact", "ref": {"assertion": 1}, "placed": True}]])


def test_the_inspector_shows_labels_rest_counts_and_repetition(v14):
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
    for i in range(4):
        chat.user(f"Hana, the map? ({i})")
        _sync(client, chat)
        client.post("/v1/retrieve", json={"chat_id": chat.id, "query": f"Hana, the map? ({i})", "previous_ai": "",
                                          "budget_tokens": 600,
                                          "in_context_ids": [m["chatId"] for m in chat.messages[-RECENT:]]})
        chat.reply("Quiet waves.")
        _sync(client, chat)
    conv = client.get("/v1/conversations").json()[0]["id"]
    page = client.get(f"/inspector/c/{conv}").text
    assert 'title="required">필수</span>' in page
    assert "쉬느라 빠진 보조 줄" in page
    assert "반복 (최근 요청 4개)" in page and "직전 요청에도 들어간 줄의 비율" in page


# --- Codex review on #278 ----------------------------------------------------------------------------------------

def test_the_reserved_first_excerpt_never_rests(migrated):
    """P1: a vector-only best hit, the request's only memory, was left out on the third request: the rest ran before
    the compiler chose the reserved (required) excerpt."""
    from test_sidecar_integration import recall
    from test_vectors import FakeEmbedder, drain_embeddings
    with make_client(migrated, embedder=FakeEmbedder(), packet_policy="packet-v14", embed_url="http://fake/v1",
                     embed_model="fake-embed") as client:
        chat = SimChat()
        chat.reply("Welcome to the story.")
        chat.user("하나는 은빛 열쇠를 등대 지하에 숨겼다.")
        chat.reply("Noted.")
        _sync(client, chat)
        drain_embeddings(migrated)
        lines = []
        for _ in range(3):
            chat.user("Where is the key at the lighthouse?")
            _sync(client, chat)
            out = recall(client, chat, "Where is the key at the lighthouse?",  # all but the source in the prompt
                         in_context=[m["chatId"] for m in chat.messages[3:]])
            lines.append(client.get(f"/v1/trace/{out['trace_id']}").json()["lines"])
            chat.reply("Quiet waves.")
            _sync(client, chat)
        placed = [[e for e in ls if e["kind"] == "excerpt" and e.get("placed") and "열쇠" in e["text"]] for ls in lines]
        assert all(placed), [len(p) for p in placed]
        assert placed[2][0]["label"] == "required"


def test_a_replay_reads_only_the_replies_written_before_its_request(v14):
    """P2: a reply appended after the replayed request counted as an echo of the requests before it and changed what
    it rested."""
    client, url = v14
    chat = SimChat()
    chat.reply("Welcome to the story.")
    chat.user("Hana is a cartographer.")
    chat.reply("Noted.")
    for i in range(RECENT + 2):
        chat.user(f"Idle chatter {i} about clouds.")
        chat.reply("Noted.")
    _sync(client, chat)
    extract(url)
    chat.user("What now?")
    _sync(client, chat)
    traces = [client.post("/v1/retrieve", json={"chat_id": chat.id, "query": "What now?", "previous_ai": "Hana smiled.",
                                                "budget_tokens": 600,
                                                "in_context_ids": [m["chatId"] for m in chat.messages[-RECENT:]]}
                          ).json()["trace_id"] for _ in range(3)]  # retried before any reply was shown
    rested = client.get(f"/v1/trace/{traces[2]}").json()
    assert rested["latency_ms"]["rested"] >= 1, [e["text"] for e in rested["lines"] if e.get("placed")]
    first = client.get(f"/v1/trace/{traces[2]}/replay").json()
    assert first["status"] == "ok" and first["reproduced"] is True
    gone = [e for e in client.get(f"/v1/trace/{traces[0]}").json()["lines"] if e.get("placed")
            and not any(x.get("placed") and x["kind"] == e["kind"] and x.get("ref") == e.get("ref")
                        for x in rested["lines"])]
    assert gone  # the supportive identity fact, placed twice and never used, rests
    chat.reply(f"{gone[0].get('content') or gone[0]['text']}, she said.")  # written after all three: echoes the rested line
    _sync(client, chat)
    again = client.get(f"/v1/trace/{traces[2]}/replay").json()
    assert again["status"] == "ok" and again["reproduced"] is True, again.get("notes")


def test_an_unused_scene_summary_rests(migrated):
    """P2: a scene summary was labeled supportive but never passed through the rest; the story so far stays."""
    from test_summaries import ON, drain, story_chat
    with make_client(migrated, **ON, packet_policy="packet-v14") as client:
        chat = story_chat(30)
        _sync(client, chat)
        drain(migrated)
        traces = []
        for _ in range(3):
            chat.user("Turn 1 begins.")
            _sync(client, chat)
            out = client.post("/v1/retrieve", json={"chat_id": chat.id, "query": "Turn 1 begins.", "previous_ai": "",
                                                    "budget_tokens": 2000,
                                                    "in_context_ids": [m["chatId"] for m in chat.messages[-6:]]}).json()
            traces.append(client.get(f"/v1/trace/{out['trace_id']}").json())
            chat.reply("Quiet waves.")
            _sync(client, chat)

    def summaries(trace, label):
        return {str(e["ref"]) for e in trace["lines"] if e["kind"] == "summary" and e.get("placed")
                and e.get("label") == label}
    scene = summaries(traces[0], "supportive") & summaries(traces[1], "supportive")
    assert scene and not scene & summaries(traces[2], "supportive")
    assert summaries(traces[2], "required")  # the story so far never rests
    assert traces[2]["latency_ms"]["rested"] >= 1


def test_a_risky_line_is_offered_after_an_ordinary_supportive_one():
    """P2: a disputed fact first in relevance order took the room an ordinary supportive fact needed."""
    disputed, ordinary = _line("fact", 1), _line("fact", 2)
    out = compile_lines([], 150, facts=[disputed, ordinary], policy="packet-v14", risky=frozenset({"1"}))
    placed = {(e.get("ref") or {}).get("assertion"): e.get("placed") for e in out.ledger if e["kind"] == "fact"}
    assert placed[2] is True
    assert placed[1] is False or out.ledger.index(next(e for e in out.ledger if (e.get("ref") or {}).get("assertion") == 1)) \
        > out.ledger.index(next(e for e in out.ledger if (e.get("ref") or {}).get("assertion") == 2))
