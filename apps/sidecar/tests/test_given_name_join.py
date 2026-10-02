"""`given_name_join` (PHASE-28 Q4, ADR 0064, proposed): a recorded recall option that reads a full name and its given name
as one character when the story mentions both in the same turns and nothing says they are two. Off by default; a trace
without it replays with it off. Its known false join (two people, one named in full, one only by the same given name)
is pinned here as a measured limit."""

from __future__ import annotations

from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import audit
from nmos_sidecar.entities import GIVEN_JOIN_TURNS, resolve
from nmos_sidecar.retrieval import RECORDED, RecallOptions
from simchat import SimChat
from test_extraction import drain, filler
from test_semantics import row
from test_sidecar_integration import recall, sync

CHAR = "character"
CONV = UUID("01900000-0000-7000-8000-000000000065")


def c(turn, subject, predicate="has_status", obj=None, value="깨어 있음", **kw):
    """One character row of `turn` (position = turn)."""
    extra = {"object_type": "place" if predicate == "located_in" else CHAR} if obj else {}
    return row(turn, subject, predicate, obj, value, subject_type=CHAR, **extra, **kw)


# Two turns that mention 백이안 and 이안 in separate assertions: the shape a narration calling one person both ways has.
BOTH = [c(1, "백이안", "has_trait", value="키가 크다"), c(1, "이안"), c(2, "백이안", "has_trait", value="안경을 쓴다"),
        c(2, "이안", value="피곤함")]


def same(r, a="백이안", b="이안"):
    return r.entity(CHAR, a)["id"] == r.entity(CHAR, b)["id"]


def test_off_by_default_the_two_names_stay_two_entities():
    assert not same(resolve(CONV, BOTH))
    assert resolve(CONV, BOTH).given_joins == []


def test_on_a_full_name_and_its_given_name_mentioned_in_two_turns_are_one():
    r = resolve(CONV, BOTH, given_joins=True)
    assert same(r) and GIVEN_JOIN_TURNS == 2
    e = r.entity(CHAR, "이안")
    assert e["name"] == "백이안" and set(e["names"]) == {"백이안", "이안"}
    assert {"name": "백이안", "other": "이안", "turn": None, "given_name": True} in e["aliases"]  # what the option joined


def test_one_turn_together_is_not_enough():
    assert not same(resolve(CONV, BOTH[:2] + [c(3, "이안")], given_joins=True))


def test_one_assertion_naming_both_says_they_are_two():
    related = BOTH + [c(3, "백이안", "relationship", "이안", "형제")]
    assert not same(resolve(CONV, related, given_joins=True))
    together = BOTH + [c(3, "카이토", "event", value="회의", participants=[{"type": CHAR, "name": "백이안"},
                                                                       {"type": CHAR, "name": "이안"}])]
    assert not same(resolve(CONV, together, given_joins=True))
    crowd = BOTH + [c(3, "카이토", "event", value="회의", participants=[{"type": CHAR, "name": n}
                                                                     for n in ("백이안", "이안", "김하람", "하람")])]
    assert not same(resolve(CONV, crowd, given_joins=True))  # any two of an assertion's names are two people


def test_two_values_of_one_single_valued_predicate_in_a_turn_say_they_are_two():
    apart = BOTH + [c(3, "백이안", "located_in", "부엌", None), c(3, "이안", "located_in", "정원", None)]
    assert not same(resolve(CONV, apart, given_joins=True))
    alike = BOTH + [c(3, "백이안", "located_in", "부엌", None), c(3, "이안", "located_in", "부엌", None)]
    assert same(resolve(CONV, alike, given_joins=True))  # the same place: nothing says two
    moved = BOTH + [c(3, "백이안", "located_in", "부엌", None), c(4, "이안", "located_in", "정원", None)]
    assert same(resolve(CONV, moved, given_joins=True))  # another turn: a move, not two people


def test_a_given_name_two_full_names_share_joins_neither():
    shared = BOTH + [c(1, "김이안"), c(2, "김이안")]
    r = resolve(CONV, shared, given_joins=True)
    assert not same(r) and not same(r, "김이안", "이안")


def test_the_persona_and_its_given_name_are_never_joined():
    r = resolve(CONV, BOTH, ["김이안"], given_joins=True)  # the persona's given name is 이안
    assert not same(r)
    persona = [c(1, "{{user}}"), c(1, "이안"), c(2, "{{user}}"), c(2, "이안")]
    assert not resolve(CONV, persona, ["백이안"], given_joins=True).given_joins  # the persona is 백이안


def test_an_ambiguous_name_and_an_owner_split_are_left_as_they_are():
    nick = BOTH + [c(3, "이안", "also_called", value="하나"), c(3, "이안", "also_called", value="유이")]
    r = resolve(CONV, nick, given_joins=True)
    assert r.status(CHAR, "이안") == "ambiguous" and not r.given_joins
    split = [{"id": "s1", "entity_type": CHAR, "name": "백이안", "other": "이안", "created_at": None}]
    assert not same(resolve(CONV, BOTH, splits=split, given_joins=True))


def test_names_the_story_already_joined_need_nothing_more():
    aliased = BOTH + [c(3, "백이안", "also_called", value="이안")]
    r = resolve(CONV, aliased, given_joins=True)
    assert same(r) and r.given_joins == []


def test_the_known_false_join_two_people_in_separate_assertions_of_the_same_turns():
    """PHASE-28 Q4's measured limit: 백이안 and another person called only 이안, each in assertions of their own in the
    same two turns ("백이안이 들어왔다. 이안이 앉았다."), read exactly as one person called both ways. The option joins
    them; only the owner's measurement of every join it makes can find such a pair."""
    two_people = [c(1, "백이안", "event", value="들어왔다"), c(1, "이안", "event", value="앉았다"),
                  c(2, "백이안", "event", value="나갔다"), c(2, "이안", "event", value="남았다")]
    assert same(resolve(CONV, two_people, given_joins=True))


def test_the_option_is_recorded_and_off_unless_asked():
    assert "given_name_join" in RECORDED and RecallOptions().given_name_join is False


# --- through the request path -----------------------------------------------------------------------------------------

def cafe(system, user):
    """One character, written in full and by the given name: 이안 in the cafe early on, 백이안 at home later."""
    target = user.split("TARGET", 1)[1]
    items = []

    def say(subject, predicate, value=None, obj=None):
        items.append({"subject": subject, "subject_type": CHAR, "predicate": predicate, "value": value, "object": obj,
                      "object_type": "place" if obj else None, "modality": "actual", "source": "narration",
                      "knowledge": "public"})

    if "들어왔다" in target:
        say("백이안", "has_trait", "키가 크다")
        say("이안", "located_in", obj="카페")
    if "창가" in target:
        say("백이안", "has_trait", "안경을 쓴다")
        say("이안", "has_status", "피곤함")
    if "집으로" in target:
        say("백이안", "located_in", obj="집")
    return {"assertions": items}, "{}"


def cafe_chat() -> SimChat:
    chat = SimChat()
    chat.user("백이안이 카페에 들어왔다. 이안은 커피를 주문했다.")
    chat.reply("점원이 고개를 끄덕였다.")
    chat.user("백이안은 창가에 앉았다. 이안은 피곤해 보였다.")
    chat.reply("햇빛이 들었다.")
    filler(chat, 2)
    chat.user("저녁이 되자 백이안은 집으로 돌아갔다.")
    chat.reply("거리는 조용했다.")
    filler(chat, 2, tag="b")
    return chat


QUESTION = "이안은 지금 어디 있어?"


def test_a_request_with_the_option_reads_one_history_and_replays_as_recorded(migrated):
    chat = cafe_chat()
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake") as c:
        sync(c, chat)
        drain(migrated, cafe)
        off = recall(c, chat, QUESTION, budget=600)
        off_trace = c.get(f"/v1/trace/{off['trace_id']}").json()
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake", given_name_join=True) as c:
        on = recall(c, chat, QUESTION, budget=600)
        trace = c.get(f"/v1/trace/{on['trace_id']}").json()
        again = c.get(f"/v1/trace/{on['trace_id']}/replay").json()
    # off: 이안 is its own character, still in the cafe, beside 백이안 at home; its given name belongs to no one
    # (ADR 0058 item 3), so the scene holds both
    assert off_trace["recall_options"]["given_name_join"] is False
    assert '<Character name="이안">' in off["packet"]["text"] and "이안 located in 카페" in off["packet"]["text"]
    # on: one character, in its later place
    assert trace["recall_options"]["given_name_join"] is True
    assert '<Character name="이안">' not in on["packet"]["text"] and "located in 카페" not in on["packet"]["text"]
    assert "백이안 located in 집" in on["packet"]["text"] and "이안 has status: 피곤함" in on["packet"]["text"]
    assert again["status"] == "ok" and again["reproduced"] is True
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        assert audit.replay(conn, off["trace_id"], RecallOptions())["text"] == off["packet"]["text"]
        # a trace from before the option records nothing: it replays with the option off
        conn.execute("UPDATE retrieval_trace SET recall_options = recall_options - 'given_name_join' WHERE id = %s",
                     (on["trace_id"],))
        legacy = audit.replay(conn, on["trace_id"], RecallOptions())
    assert legacy["text"] == off["packet"]["text"]


def secret(system, user):
    """cafe's story, and a secret of 하나's kept from 이안."""
    parsed, raw = cafe(system, user)
    if "비밀" in user.split("TARGET", 1)[1]:
        parsed["assertions"].append({"subject": "하나", "subject_type": CHAR, "predicate": "identity",
                                     "value": "사실은 왕국의 공주", "modality": "actual", "source": "narration",
                                     "knowledge": "limited", "known_by": ["하나"], "hidden_from": ["이안"]})
    return parsed, raw


def test_a_secret_kept_from_one_spelling_is_kept_from_the_joined_character(migrated):
    chat = cafe_chat()
    chat.user("하나에게는 비밀이 있다. 하나는 그것을 이안에게 숨겼다.")
    chat.reply("하나는 미소만 지었다.")
    filler(chat, 2, tag="c")
    question = "백이안은 하나에 대해 뭘 알아?"
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake") as c:
        sync(c, chat)
        drain(migrated, secret)
        off = recall(c, chat, question, budget=800)["packet"]["text"]
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake", given_name_join=True) as c:
        on = recall(c, chat, question, budget=800)["packet"]["text"]
    secret_line = "하나 identity: 사실은 왕국의 공주"
    for text in (off, on):
        private, facts = text.split("<Private>", 1)[1], text.split("<Facts>", 1)[1].split("</Facts>", 1)[0]
        assert secret_line in private and secret_line not in facts
    # on: the scene holds one character, the one the secret is kept from under its given name
    assert '<Character name="이안">' not in on and '<Character name="백이안">' in on


def test_the_evaluation_replays_with_the_option_and_lists_every_join(migrated):
    """`tools/eval_rp.py --given-name-join --show-joins` (PHASE-28 Q5 (b)): the same recorded requests with the option,
    and every join it makes, for the owner to check."""
    import importlib.util
    from pathlib import Path

    tool = Path(__file__).resolve().parents[3] / "tools/eval_rp.py"
    spec = importlib.util.spec_from_file_location("eval_rp", tool)
    eval_rp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(eval_rp)
    chat = cafe_chat()
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake") as c:
        sync(c, chat)
        drain(migrated, cafe)
        trace = recall(c, chat, QUESTION, budget=600)["trace_id"]
    cases = [{"name": "where", "category": "state", "trace": trace, "gold": ["located in 집"],
              "forbidden": ["located in 카페"]}]
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        off = eval_rp.evaluate(conn, cases, RecallOptions())
        on = eval_rp.evaluate(conn, cases, RecallOptions(), given_name_join=True)
        joins = eval_rp.given_joins(conn, cases)
    assert off["summary"]["all"]["passed"] == 0 and on["summary"]["all"]["passed"] == 1
    assert joins == {trace: [["백이안", "이안"]]}
