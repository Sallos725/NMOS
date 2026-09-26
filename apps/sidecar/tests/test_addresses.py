"""extract-v10: `addresses`, how one character speaks to and calls another (ADR 0028)."""

from __future__ import annotations

from conftest import make_client
from nmos_sidecar.extraction import SYSTEM_PROMPT
from nmos_sidecar.facts import STANDING
from nmos_sidecar.predicates import REGISTRY, registry_prompt, validate
from simchat import SimChat
from test_extraction import drain, facts, filler
from test_sidecar_integration import recall, sync

CHAR = "character"


def addresses(subject, obj, value, **extra):
    return {"subject": subject, "subject_type": CHAR, "predicate": "addresses", "object": obj, "object_type": CHAR,
            "value": value, "modality": "actual", "source": "narration", "knowledge": "public", **extra}


def test_addresses_is_single_per_direction_and_standing():
    p = REGISTRY["addresses"]
    assert (p.cardinality, p.per_object, p.subject_types, p.object_types) == ("single", True, (CHAR,), (CHAR,))
    assert "- addresses (subject: character, object: character, value: text)" in registry_prompt()
    assert "addresses" in STANDING
    assert validate(addresses("라디아", "유우마", "반말")) == ("valid", None)
    assert validate({**addresses("라디아", "유우마", "반말"), "object": None})[0] == "pending"


def test_the_prompt_asks_for_settled_speech_not_slips():
    prompt = SYSTEM_PROMPT.format(registry=registry_prompt())
    for phrase in ("`addresses` when the TARGET turn settles how one character speaks to or calls another",
                   "One assertion per direction", "It is narration when the TARGET\n  turn shows it",
                   "a slip is not a change", "A change back is a new\n  `addresses`",
                   "Record the turning point as an `event` as well"):
        assert phrase in prompt, phrase


def speech_complete(system, user):
    target = user.split("TARGET", 1)[1]
    items = []
    if "말 편하게" in target:
        items += [addresses("라디아", "{{user}}", "반말, '유우마'라고 부름"),
                  addresses("{{user}}", "라디아", "반말, '누나'라고 부름")]
    if "다시 존댓말" in target:
        items.append(addresses("라디아", "{{user}}", "존댓말(해요체), '유우마 씨'라고 부름"))
    return {"assertions": items}, "{}"


def test_a_change_back_replaces_one_direction_only(migrated):
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake") as c:
        chat = SimChat()
        chat.user("누나, 이제 말 편하게 해.")
        chat.reply("라디아는 웃었다. \"알았어, 유우마.\"")
        filler(chat, 3)
        chat.user("라디아가 다시 존댓말을 쓰기로 한다.")
        chat.reply("\"……유우마 씨, 역시 이게 편해요.\"")
        filler(chat, 5)
        sync(c, chat)
        drain(migrated, speech_complete)
        rows = [f for f in facts(c, chat) if f["predicate"] == "addresses"]
        packet = recall(c, chat, "라디아가 문을 열고 들어왔다.", budget=400)["packet"]["text"]
    current = {(f["subject"], f["value"]) for f in rows}
    assert current == {("라디아", "존댓말(해요체), '유우마 씨'라고 부름"), ("{{user}}", "반말, '누나'라고 부름")}
    radia = next(f for f in rows if f["subject"] == "라디아")
    assert radia["versions"] == 2  # the earlier 반말 stays as history
    assert "라디아 addresses {{user}}: 존댓말(해요체), '유우마 씨'라고 부름" in packet
    assert "반말, '유우마'라고 부름" not in packet
