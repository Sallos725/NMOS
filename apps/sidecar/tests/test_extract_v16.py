"""extract-v16 (PHASE-28 Q1–Q3): the roles in force are shown to the extractor as CURRENT ROLES, and a role the TARGET turn
ends is denied with the listed value, so ADR 0013's value match closes exactly that role. Behind NMOS_EXTRACT_COMPILER;
extract-v15 stays the default and its generation key is unchanged."""

from __future__ import annotations

import dataclasses
import re
from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import extraction
from nmos_sidecar.config import Settings
from nmos_sidecar.entities import resolve
from nmos_sidecar.facts import _versions, version_key
from nmos_sidecar.predicates import registry_prompt
from simchat import SimChat
from test_extract_v14 import SETTINGS
from test_extraction import drain, facts, filler
from test_semantics import row
from test_sidecar_integration import sync

CHAR = "character"
C = {"subject_type": CHAR, "object_type": CHAR}
CONV = UUID("01900000-0000-7000-8000-000000000064")
# extract-v15's generation key for test_extract_v14.SETTINGS, as on `main` before PHASE-28: the default must not move.
V15_KEY = "extract-f4dfd4d1c0b5a182bc19aee78f4d9f50"
V16 = dataclasses.replace(SETTINGS, extract_compiler="extract-v16")


def role(pos, subject, obj, value, **kw):
    return row(pos, subject, "role_toward", obj, value, **C, **kw)


def ctx(text: str, turn: int = 20, persona: str | None = None) -> dict:
    """A target turn whose message says `text`; the previous turns' rows are passed to role_hints apart."""
    return {"target": {"conversation_id": CONV, "host_persona_name": persona, "links": (), "splits": (), "canon": (),
                       "turn": turn},
            "context": [], "members": [{"metadata": {"role": "user"}, "content": text, "turn": turn}]}


def current(rows):
    r = resolve(CONV, rows)
    groups: dict[tuple, list] = {}
    for x in rows:
        groups.setdefault(version_key(x, r), []).append(x)
    return sorted((f["subject"], f["object"], f["value"], f["polarity"]) for h in groups.values()
                  for f in _versions(h, r))


# --- the default is untouched -----------------------------------------------------------------------------------------

def test_extract_v15_stays_the_default_with_its_key_and_prompt():
    assert extraction.COMPILER_VERSION == "extract-v15" and extraction.compiler_of(SETTINGS) == "extract-v15"
    assert extraction.PROMPTS["extract-v15"] is extraction.SYSTEM_PROMPT
    assert extraction.extractor(SETTINGS).key == V15_KEY
    assert extraction.extractor(dataclasses.replace(SETTINGS, extract_compiler="extract-v15")).key == V15_KEY
    assert "CURRENT ROLES" not in extraction.SYSTEM_PROMPT


def test_extract_v16_is_its_own_generation_by_compiler_and_prompt_only():
    v15, v16 = extraction.extractor(SETTINGS).spec, extraction.extractor(V16).spec
    assert v16["compiler"] == "extract-v16"
    assert {k for k in v15 if v15[k] != v16[k]} == {"compiler", "prompt"}
    assert extraction.extractor(V16).key != V15_KEY


def test_an_unknown_compiler_is_refused_at_startup():
    with pytest.raises(ValueError, match="NMOS_EXTRACT_COMPILER"):
        Settings(database_url="", extract_compiler="extract-v61")
    assert Settings(database_url="", extract_compiler="").extract_compiler == ""
    for name in extraction.COMPILERS:  # the settings accept exactly the extractor's compilers
        assert extraction.compiler_of(Settings(database_url="", extract_compiler=name)) == name


def test_the_v16_prompt_ends_a_listed_role_as_listed_right_after_the_role_rule():
    prompt = extraction.PROMPTS["extract-v16"].format(registry=registry_prompt())
    rule = prompt.index("- If CURRENT ROLES are listed: when the TARGET turn ends one")
    assert prompt.index('`role_toward` (하나 to 카이토, "하녀: 카이토의 저택에서 일하며 지냄").') < rule
    for phrase in ('`role_toward` with "negative" and subject, object\n  and value exactly as listed',
                   "Not when someone only goes out, travels or is away for a while",
                   "not for\n  a role that is not listed",
                   "A new role toward the same person replaces the listed one by itself"):
        assert phrase in prompt, phrase
    # the rest of the prompt is extract-v15's
    assert prompt.replace(extraction.ROLE_ENDINGS, "") == extraction.SYSTEM_PROMPT.format(registry=registry_prompt())


# --- which roles are listed (Q2) --------------------------------------------------------------------------------------

def test_the_roles_in_force_are_listed_newest_first_and_ended_or_replaced_ones_are_not():
    rows = [role(1, "하나", "카이토", "세입자: 카이토의 집에 세 들어 삶"),
            role(2, "카이토", "하나", "집주인"),
            role(3, "유이", "카이토", "제자"), role(6, "유이", "카이토", "조수"),  # replaced: only the new one
            role(4, "미나", "카이토", "하녀"), role(7, "미나", "카이토", "하녀", polarity="negative"),  # ended as listed
            role(5, "하나", "카이토", "친구의 오빠", source="character_claim", asserted_by="하나"),  # a claim: not a fact
            role(8, "하나", "유이", "선생님", modality="hypothetical")]  # considered only
    listed = extraction.role_hints(ctx("카이토가 하나와 유이를 불렀다."), rows)
    assert [(x["by"], x["to"], x["role"], x["turn"]) for x in listed] == [
        ("유이", "카이토", "조수", 6), ("카이토", "하나", "집주인", 2), ("하나", "카이토", "세입자: 카이토의 집에 세 들어 삶", 1)]


def test_a_role_whose_parties_the_prompt_does_not_name_is_listed_only_when_it_is_the_personas():
    rows = [role(1, "{{user}}", "카이토", "손님: 카이토의 여관 3호실에 묵음"), role(2, "유이", "미나", "제자")]
    listed = extraction.role_hints(ctx("짐을 챙겨 방을 나섰다."), rows)
    assert [(x["by"], x["to"]) for x in listed] == [("{{user}}", "카이토")]  # the persona is in every scene
    named = extraction.role_hints(ctx("미나가 짐을 챙겨 방을 나섰다."), rows)
    assert [(x["by"], x["to"]) for x in named] == [("유이", "미나"), ("{{user}}", "카이토")]  # named first
    assert extraction.role_hints(ctx("미나"), rows, limit=1) == named[:1]
    assert extraction.role_hints(ctx("미나"), rows, limit=0) == []
    assert extraction.role_hints(ctx("미나"), [row(1, "미나", "located_in", "부엌")]) == []


def test_the_block_lists_each_role_with_its_turn_and_only_when_there_is_one():
    roles = [{"by": "하나", "to": "카이토", "role": "세입자", "turn": 3}]
    assert extraction.roles_block(roles) == ["CURRENT ROLES (held earlier in this story, not yet ended):",
                                             "- 하나 → 카이토: 세입자 (turn 3)", ""]
    c = {**ctx("하나는 이사했다."), "context": []}
    assert "CURRENT ROLES" in extraction.build_prompt(c, roles=roles)
    assert "CURRENT ROLES" not in extraction.build_prompt(c) and "CURRENT ROLES" not in extraction.build_prompt(c, roles=[])


# --- what an ending as listed does (ADR 0013, unchanged) ---------------------------------------------------------------

def test_an_ending_as_listed_closes_exactly_that_role_and_keeps_it_in_history():
    tenancy = role(1, "하나", "카이토", "세입자: 카이토의 집에 세 들어 삶")
    landlord = role(1, "카이토", "하나", "집주인")
    ended = role(5, "하나", "카이토", "세입자: 카이토의 집에 세 들어 삶", polarity="negative")
    assert current([tenancy, landlord, ended]) == [
        ("카이토", "하나", "집주인", "positive"),  # the reverse direction is its own role
        ("하나", "카이토", "세입자: 카이토의 집에 세 들어 삶", "negative")]
    (fact,) = [f for f in _versions([tenancy, ended], resolve(CONV, [tenancy, ended]))]
    assert [h["outcome"] for h in fact["history"]] == ["ended", "current"]  # a past question still sees it
    # in other words (the AGE-24 defect extract-v16 avoids by listing the value): the role stays current
    worded = role(5, "하나", "카이토", "세입자였음", polarity="negative")
    assert ("하나", "카이토", "세입자: 카이토의 집에 세 들어 삶", "positive") in current([tenancy, worded])
    # leaving the place is another predicate: it does not end the role
    left = row(5, "하나", "located_in", "카이토의 집", polarity="negative", subject_type=CHAR, object_type="place")
    assert ("하나", "카이토", "세입자: 카이토의 집에 세 들어 삶", "positive") in current([tenancy, left])


# --- through the worker ------------------------------------------------------------------------------------------------

LISTED = re.compile(r"^- (?P<by>.+?) → (?P<to>.+?): (?P<role>.+) \(turn \d+\)$", re.M)


def moving_out(system, user):
    """The model as the prompt allows it: the tenancy when the story states it, the leaving as a place, and under
    extract-v16 the ending of the listed role, copied from CURRENT ROLES."""
    target = user.split("TARGET", 1)[1]
    items = []
    if "세 들어" in target:
        items.append({"subject": "하나", "subject_type": CHAR, "predicate": "role_toward", "object": "카이토",
                      "object_type": CHAR, "value": "세입자: 카이토의 집에 세 들어 삶", "modality": "actual",
                      "source": "narration", "knowledge": "public"})
    if "이사" in target:
        items.append({"subject": "하나", "subject_type": CHAR, "predicate": "located_in", "object": "카이토의 집",
                      "object_type": "place", "polarity": "negative", "modality": "actual", "source": "narration",
                      "knowledge": "public"})
        if "CURRENT ROLES" in user:
            for m in LISTED.finditer(user.split("CURRENT ROLES", 1)[1].split("\n\n", 1)[0]):
                items.append({"subject": m["by"], "subject_type": CHAR, "predicate": "role_toward", "object": m["to"],
                              "object_type": CHAR, "value": m["role"], "polarity": "negative", "modality": "actual",
                              "source": "narration", "knowledge": "public"})
    return {"assertions": items}, "{}"


def tenancy_chat() -> SimChat:
    chat = SimChat()
    chat.user("하나는 카이토의 집에 세 들어 산다.")
    chat.reply("카이토는 월세 봉투를 받아 들었다.")
    filler(chat, 3)
    return chat


def move_out(chat: SimChat) -> None:
    chat.user("하나는 짐을 싸서 카이토의 집을 떠나 이사했다.")
    chat.reply("카이토는 빈 다락방을 정리했다.")
    filler(chat, 1, tag="after")  # a turn is extracted once the story has moved past it


def roles_of(c, chat):
    return [(f["subject"], f["object"], f["value"], f["polarity"]) for f in facts(c, chat)
            if f["predicate"] == "role_toward"]


def test_under_extract_v16_the_story_ends_the_role_it_listed(migrated):
    chat = tenancy_chat()
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake", extract_compiler="extract-v16") as c:
        sync(c, chat)
        drain(migrated, moving_out)
        move_out(chat)
        sync(c, chat)
        drain(migrated, moving_out)
        roles = roles_of(c, chat)
    assert roles == [("하나", "카이토", "세입자: 카이토의 집에 세 들어 삶", "negative")]
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        rows = conn.execute("SELECT compiler_version, hints FROM extraction ORDER BY created_at").fetchall()
    assert {r["compiler_version"] for r in rows} == {"extract-v16"}
    listed = [r["hints"]["roles"] for r in rows if r["hints"] and r["hints"].get("roles")]
    # every turn after the tenancy whose prompt names 하나 (its context does) lists it, the moving out included
    assert listed and all(x == [{"by": "하나", "to": "카이토", "role": "세입자: 카이토의 집에 세 들어 삶", "turn": 0}]
                          for x in listed)


def test_under_extract_v15_the_same_story_keeps_the_role_and_stores_no_roles(migrated):
    chat = tenancy_chat()
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake") as c:
        sync(c, chat)
        drain(migrated, moving_out)
        move_out(chat)
        sync(c, chat)
        drain(migrated, moving_out)
        roles = roles_of(c, chat)
    assert roles == [("하나", "카이토", "세입자: 카이토의 집에 세 들어 삶", "positive")]  # the AGE-24 defect
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        rows = conn.execute("SELECT compiler_version, hints FROM extraction").fetchall()
    assert {r["compiler_version"] for r in rows} == {"extract-v15"}
    assert not any(r["hints"] and "roles" in r["hints"] for r in rows)


def test_a_first_connection_extracts_the_ending_before_the_role_and_lists_nothing(migrated):
    """Q2's measured limit: first-sight work runs newest first, so the turn that ends the role is extracted before the
    turn that set it up, and its list is empty; the role stays current. A generation's backfill runs oldest first."""
    chat = tenancy_chat()
    move_out(chat)
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake", extract_compiler="extract-v16") as c:
        sync(c, chat)
        drain(migrated, moving_out)
        roles = roles_of(c, chat)
    assert roles == [("하나", "카이토", "세입자: 카이토의 집에 세 들어 삶", "positive")]
