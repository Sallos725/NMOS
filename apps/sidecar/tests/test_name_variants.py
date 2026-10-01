"""PHASE-24 (ADR 0058): a name as the story says it — a given name alone, and a Hangul word for a romanized name.

The rows are synthetic, shaped like the measured cases (AGE-28): a character written in full as a three-syllable name
asked about by the given name, and a character a story in English stores under a romanized name asked about in Hangul.
"""

from __future__ import annotations

import uuid
from uuid import UUID

import pytest

from memeval import _sync
from nmos_sidecar import audit, variants
from nmos_sidecar.entities import resolve
from nmos_sidecar.facts import relevant_facts
from nmos_sidecar.retrieval import RecallOptions, cast_groups
from nmos_sidecar.scene import cast, private
from simchat import SimChat
from test_packet_ledger import db, extract, full  # noqa: F401  (`full` is a fixture)
from test_semantics import row

C = {"subject_type": "character"}
BASE = {"object": None, "object_type": None, "host_logical_id": "x", "known_by": None, "hidden_from": None,
        "knowledge": "public", "salience": None, "epistemic": "stated"}


def fact(position, subject, predicate, value, **extra):
    return {**BASE, "position": position, "turn": position // 2, "subject": subject, "predicate": predicate,
            "value": value, **extra}


def entity(name, *names, kind="character", persona=False):
    return {"id": name, "type": kind, "name": name, "names": [name, *names], "persona": persona}


# --- the rules (pure) ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize(("name", "given"), [("백이안", "이안"), ("이서윤", "서윤"), ("추오월", "오월"),
                                             ("마리아", None), ("이안", None), ("남궁민수", None), ("ryu ha-jin", None)])
def test_the_given_name(name, given):
    assert variants.given(name) == given


def test_a_character_goes_by_its_given_name():
    assert variants.aliases([entity("백이안")], [], "") == {"백이안": frozenset({"이안"})}


def test_a_place_and_the_persona_gain_no_given_name():
    assert variants.aliases([entity("윤슬포", kind="place"), entity("서도윤", persona=True)], ["서도윤"], "") == {}


def test_a_given_name_two_characters_share_or_another_holds_counts_for_none():
    assert variants.aliases([entity("백이안"), entity("김이안")], [], "") == {}
    assert variants.aliases([entity("백이안"), entity("이안")], [], "") == {}  # another character's own name
    # the persona's given name: 서도윤 is the persona, so 김도윤 does not go by 도윤
    assert variants.aliases([entity("김도윤"), entity("서도윤", persona=True)], ["서도윤"], "") == {}


@pytest.mark.parametrize(("latin", "text", "word"), [
    ("hajin", "하진은 어디 있어?", "하진"),
    ("ryu ha-jin", "류하진이 뭐라고 했지?", "류하진"),
    ("ryu ha-jin", "하진이는?", "하진"),  # the given name of a two-part name
    ("lee seo-yun", "이서윤한테 물어봐", "이서윤"),  # a family name's usual spelling
    ("park ji-hoon", "박지훈 씨", "박지훈"),
    ("choi min-seo", "최민서는", "최민서"),
])
def test_a_hangul_word_spells_a_romanized_name(latin, text, word):
    assert variants.aliases([entity(latin)], [], text) == {latin: frozenset({word})}


def test_a_spelling_two_characters_share_counts_for_neither():
    assert variants.aliases([entity("hajin"), entity("ha jin")], [], "하진은?") == {}


def test_a_short_key_and_a_word_without_a_match_count_for_nothing():
    assert variants.latin_keys("ian") == frozenset()  # below KEY_MIN
    assert variants.aliases([entity("hajin")], [], "오늘 날씨 어때?") == {}


def test_the_folds_meet_the_usual_spellings():
    assert variants.key("Kang Woo-seok") in variants.hangul_keys("강우석")
    assert variants.key("Seol-hee") in variants.hangul_keys("설희")
    assert variants.key("Sun-young") in variants.hangul_keys("선영")


# --- fact selection and a secret's holder addressed ----------------------------------------------------------------

def test_a_given_name_brings_its_characters_fact_with_the_aliases_only():
    f = fact(2, "백이안", "located_in", "시장")
    al = variants.aliases([entity("백이안")], [], "")
    assert relevant_facts([f], "이안은 어디 있어?", "", set(), 8) == []
    assert relevant_facts([f], "이안은 어디 있어?", "", set(), 8, aliases=al) == [f]


def test_a_hangul_spelling_brings_a_romanized_characters_fact():
    f = fact(2, "Hajin", "located_in", "harbor")
    al = variants.aliases([entity("hajin")], [], "하진은 어디 있어?")
    assert relevant_facts([f], "하진은 어디 있어?", "", set(), 8, aliases=al) == [f]


def test_a_fact_kept_from_a_character_addressed_by_the_given_name_ranks_as_addressed():
    hidden = fact(2, "카이토", "knows", "편지는 위조", knowledge="limited", known_by=["카이토"], hidden_from=["백이안"])
    other = fact(9, "카이토", "located_in", "부두")
    al = variants.aliases([entity("백이안"), entity("카이토")], [], "")
    query = "카이토, 이안이 왔어."
    assert relevant_facts([hidden, other], query, "", set(), 1) == [other]  # the newer, without the variant
    assert relevant_facts([hidden, other], query, "", set(), 1, aliases=al) == [hidden]


# --- the scene ------------------------------------------------------------------------------------------------------

def test_a_character_addressed_by_a_variant_is_in_the_scene_and_its_secret_is_private():
    rows = [row(1, "백이안", "located_in", None, "시장", **C), row(9, "카이토", "has_status", None, "졸림", **C)]
    r = resolve(uuid.uuid4(), rows)
    al = variants.aliases(r.entities(), r.persona_names, "이안이 들어왔다.")
    secret = {"knowledge": "limited", "known_by": ["카이토", "{{user}}"], "hidden_from": ["백이안"]}
    without = cast(rows, r, "이안이 들어왔다.")
    with_variants = cast(rows, r, "이안이 들어왔다.", aliases=al)
    assert "백이안" not in without.values() and "백이안" in with_variants.values()
    assert not private(secret, without, r) and private(secret, with_variants, r)


def test_a_name_only_in_knowledge_marks_counts_by_its_given_name():
    rows = [row(9, "카이토", "knows", None, "편지는 위조", **C, knowledge="limited", known_by=["카이토"],
                hidden_from=["백이안"])]
    r = resolve(uuid.uuid4(), rows)
    assert "백이안" not in variants.aliases(r.entities(), r.persona_names, "")  # not an entity: named only in the mark
    al = variants.aliases(r.entities(), r.persona_names, "", marked=["백이안"])
    assert al == {"백이안": frozenset({"이안"})}
    assert "백이안" in cast(rows, r, "이안이 문을 열었다.", aliases=al).values()


# --- through a request, and its replay ------------------------------------------------------------------------------

WINDOW = 4


def story(client, url, lines) -> SimChat:
    chat = SimChat()
    chat.reply("Welcome to the story.")
    for user in (*lines, *[f"Idle chatter {i} about clouds." for i in range(4)]):
        chat.user(user)
        chat.reply("Noted.")
        _sync(client, chat)
    extract(url)
    return chat


def ask(client, chat: SimChat, text: str) -> dict:
    chat.user(text)
    _sync(client, chat)
    return client.post("/v1/retrieve", json={"chat_id": chat.id, "query": text, "previous_ai": "",
                                             "in_context_ids": [m["chatId"] for m in chat.messages[-WINDOW:]],
                                             "budget_tokens": 1500}).json()


def test_a_request_by_the_given_name_gets_the_fact_and_records_the_option(full):
    client, url = full
    chat = story(client, url, ["백이안 is in the 시장."])
    out = ask(client, chat, "이안은 지금 어디 있지?")
    assert "백이안 located in 시장" in out["packet"]["text"]
    assert client.get(f"/v1/trace/{out['trace_id']}").json()["recall_options"]["name_variants"] is True


def test_a_request_in_hangul_gets_a_romanized_characters_fact(full):
    client, url = full
    chat = story(client, url, ["Hajin is in the harbor."])
    out = ask(client, chat, "하진은 지금 어디 있지?")
    assert "Hajin located in harbor" in out["packet"]["text"]


def test_a_secret_kept_from_a_character_addressed_by_the_given_name_is_private(full):
    client, url = full
    chat = story(client, url, ["카이토 keeps a secret from 백이안: the letter is forged."])
    text = ask(client, chat, "카이토, 이안이 편지 얘기를 물어봐.")["packet"]["text"]
    assert "<Private>" in text and "the letter is forged" in text.split("<Private>", 1)[1]


def test_a_trace_without_the_option_replays_as_it_was(full):
    client, url = full
    chat = story(client, url, ["백이안 is in the 시장."])
    out = ask(client, chat, "이안은 지금 어디 있지?")
    with db(url) as conn:
        on = audit.replay(conn, UUID(out["trace_id"]), RecallOptions())
        conn.execute("UPDATE retrieval_trace SET recall_options = recall_options - 'name_variants' WHERE id = %s",
                     (out["trace_id"],))
        old = audit.replay(conn, UUID(out["trace_id"]), RecallOptions())
    assert on["reproduced"] is True and on["text"] == out["packet"]["text"]
    assert "백이안 located in 시장" not in old["text"]


def test_with_the_option_the_character_the_message_names_keeps_its_cast_group():
    # five characters in the scene, four groups: the one asked about by full name was the fifth, behind characters a
    # given name in the previous reply brought in
    people = ["백이안", "강무진", "윤하람", "추오월", "곽은비"]
    rows = [row(10 + i, p, "located_in", f"장소{i}", None, **C, object_type="place", knowledge="public",
                known_by=None, hidden_from=None, salience=None)
            for i, p in enumerate(people)]
    rows = [{**x, "turn": 9} for x in rows]
    r = resolve(uuid.uuid4(), rows)
    view = {"facts": rows, "threads": []}
    scene_now = cast(rows, r, "곽은비는 지금 어디 있어?")
    groups = lambda al: [name for name, _ in cast_groups(view, scene_now, r, "곽은비는 지금 어디 있어?",  # noqa: E731
                                                         RecallOptions(), set(), al)[0]]
    assert "곽은비" not in groups(None)  # without the option: the cast's order, as recorded requests had it
    assert groups({})[0] == "곽은비"
