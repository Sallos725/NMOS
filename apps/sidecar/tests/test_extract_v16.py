"""extract-v16 (PHASE-28 Q1–Q4): the roles in force are shown to the extractor as CURRENT ROLES, and a role the TARGET turn
ends is denied with the listed value, so ADR 0013's value match closes exactly that role; and a character written in full
and by part of the name is one entity through `also_called`. Behind NMOS_EXTRACT_COMPILER; extract-v15 stays the default
and its generation key is unchanged."""

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


def test_the_v16_prompt_names_a_listed_role_that_ends_right_after_the_role_rule():
    prompt = extraction.PROMPTS["extract-v16"].format(registry=registry_prompt())
    rule = prompt.index("- If CURRENT ROLES are listed (R1, R2, …), report in `roles_ended` each one the TARGET")
    assert prompt.index('`role_toward` (하나 to 카이토, "하녀: 카이토의 저택에서 일하며 지냄").') < rule
    for phrase in ('`when`: "now" when it is over by the end of the TARGET turn',
                   '"planned" when the TARGET turn only plans, arranges, announces or prepares',
                   "even when it is decided in this\n  turn: the role holds until a later turn ends it",
                   'A sentence about tomorrow or later is never "now".',
                   "`evidence`: the TARGET turn's own words for what happens in it that ends the role",
                   "A reason, an arrangement or a plan in\n  CONTEXT is not evidence",
                   "A listed role is between its two people, not just a job title",
                   "a new job does not end a mentorship; a promotion does not end employment or being colleagues",
                   # the owner's run of 073b7a1: a promotion at the bakery ended the role toward the inn's owner (2/3)
                   "A new role, job or promotion toward someone else (another employer, another workplace) never ends a\n"
                   "  listed role toward a different person",
                   'never join two passages with "..."',
                   "Not when someone only goes out, travels\n  or is away for a while",
                   "Do not write the ending as a `role_toward` yourself",
                   "A new role toward the same\n  person replaces the listed one by itself",
                   'Most turns end none: then\n  "roles_ended": [].',
                   '"roles_ended": [{"role": "R1", "when": "now|planned", "evidence": "..."}],'):
        assert phrase in prompt, phrase
    # the rest of the prompt is extract-v15's, but for the alias rule (below)
    v16 = extraction.PROMPTS["extract-v16"].replace(extraction.ROLE_ENDINGS, "").replace(
        extraction.ALIAS_PARTS, extraction.V15_ALIAS).replace(extraction.ANSWER_ROLES, extraction._ANSWER_END)
    assert v16 == extraction.SYSTEM_PROMPT


def test_the_v16_prompt_links_a_full_name_and_a_part_of_it_with_its_limits():
    v15, v16 = (extraction.PROMPTS[c].format(registry=registry_prompt()) for c in ("extract-v15", "extract-v16"))
    assert extraction.V15_ALIAS in v15 and extraction.V15_ALIAS not in v16 and extraction.ALIAS_PARTS in v16
    for phrase in ("writes a character by a full\n  name and, for the same character, by part of it",
                   "the given name alone; in a story in English, the\n  first or the last name alone",
                   'e.g. "윤하나가 문을 열었다. 하나는 웃었다.": subject the full name, value\n  the part',
                   "Not when the two could be different people: they speak to or act on each other",
                   "named side by side as two, or the story has another character with that name"):
        assert phrase in v16, phrase
    # the alias still needs both names in the turn it comes from (ADR 0012), and under extract-v16 the part on its own:
    # inside the full name it is not said a second time
    both = {"subject": "윤하나", "subject_type": CHAR, "predicate": "also_called", "value": "하나"}
    for apart in (False, True):
        assert extraction.alias_evidenced(both, "윤하나가 문을 열었다. 하나는 웃었다.", apart=apart)
        assert not extraction.alias_evidenced(both, "하나는 웃었다.", apart=apart)
        assert extraction.alias_evidenced({**both, "subject": "하나", "value": "윤하나"},
                                          "윤하나가 문을 열었다. 하나는 웃었다.", apart=apart)  # either way round
    assert extraction.alias_evidenced(both, "윤하나가 문을 열었다.")  # extract-v15's check, as it was
    assert not extraction.alias_evidenced(both, "윤하나가 문을 열었다.", apart=True)
    listed = [{"name": "윤하나", "type": CHAR}]
    assert extraction.alias_evidenced(both, "하나는 웃었다.", listed)  # extract-v15: a known name stands in (ADR 0024)
    assert not extraction.alias_evidenced(both, "하나는 웃었다.", listed, apart=True)  # a part alone may be another's
    assert extraction.alias_evidenced({**both, "value": "Hana"}, "윤하나(Hana)", apart=True)  # not nested: as before
    rows = extraction.normalize([{**both, "modality": "actual", "source": "narration"}], "윤하나가 문을 열었다.",
                                apart=True)
    assert (rows[0]["status"], rows[0]["reason"]) == ("pending", "alias not stated in the turn")


# --- NAME PAIRS (Q4, the owner's run of 27c7658) ----------------------------------------------------------------------

def test_the_v16_prompt_asks_for_listed_name_pairs_by_number():
    """The owner's run of 27c7658: the free alias rule gave no `also_called` on any of 27 turns that write a known full
    name and its part apart, 3 runs each. Known full names whose part the turn writes are listed (N1, …) and the model
    answers by number, as CURRENT ROLES are."""
    v15, v16 = (extraction.PROMPTS[c].format(registry=registry_prompt()) for c in ("extract-v15", "extract-v16"))
    for phrase in ("If NAME PAIRS are listed (N1, N2, …)", "Report in `same_names` each pair the TARGET turn uses for one"
                   " character", 'with `pair`: its number as listed ("N1"), never the names',
                   "Do not also write that `also_called` yourself", '"same_names": []',
                   '"same_names": [{"pair": "N1", "evidence": "..."}]'):
        assert phrase not in v15 and phrase in v16.replace("\n  ", " "), phrase


def test_name_parts_are_the_given_name_of_a_hangul_name_and_the_first_or_last_word_of_a_latin_one():
    assert extraction.name_parts("윤하나") == ["하나"] and extraction.name_parts("남궁하나") == ["하나"]
    assert extraction.name_parts("Hana Yoon") == ["Hana", "Yoon"]
    assert extraction.name_parts("Mary Anne Smith") == ["Mary", "Smith"]
    for name in ("하나", "윤하나나나나", "?검은 망토의 남자", "Hana", "윤 하나", "검은 고양이"):
        assert extraction.name_parts(name) == [], name
    assert extraction.name_parts("카이토") == ["이토"]  # a candidate only: the turn must write 이토 apart, and the model confirm


def known(*names, also=None):
    return [{"name": n, "type": CHAR, **({"also": also[n]} if also and n in also else {})} for n in names]


TWO_WAYS = "윤하나는 의자에 앉았다. 하나는 차를 마셨다."


def test_a_known_full_name_is_paired_with_its_part_only_when_the_turn_writes_the_part_apart():
    assert extraction.name_pairs(known("윤하나", "하나"), TWO_WAYS) == [{"full": "윤하나", "part": "하나"}]
    assert extraction.name_pairs(known("윤하나"), TWO_WAYS) == [{"full": "윤하나", "part": "하나"}]  # part not yet known
    assert extraction.name_pairs(known("윤하나"), "윤하나는 의자에 앉았다.") == []  # only inside the full name
    assert extraction.name_pairs(known("윤하나"), "하나는 차를 마셨다.") == []  # the full name is not in the turn
    assert extraction.name_pairs(known("윤하나", also={"윤하나": ["하나"]}), TWO_WAYS) == []  # already one character
    assert extraction.name_pairs(known("윤하나", "김하나"), TWO_WAYS) == []  # two known full names share the part
    assert extraction.name_pairs(known("윤하나"), TWO_WAYS, persona=["윤하나"]) == []  # the persona (Q6)
    assert extraction.name_pairs(known("윤하나"), TWO_WAYS, persona=["하나"]) == []
    assert extraction.name_pairs([{"name": "윤하나", "type": "place"}], TWO_WAYS) == []
    assert extraction.name_pairs(None, TWO_WAYS) == []
    latin = "Hana Yoon opened the door. Hana smiled."
    assert extraction.name_pairs(known("Hana Yoon"), latin) == [{"full": "Hana Yoon", "part": "Hana"}]
    many = known(*(f"윤{g}람" for g in "가나다라마바사아자차"))
    text = " ".join(f"윤{g}람이 왔다. {g}람은 웃었다." for g in "가나다라마바사아자차")
    assert len(extraction.name_pairs(many, text)) == extraction.NAME_PAIRS


def test_the_block_and_the_nudge_list_the_pairs_only_when_there_is_one():
    pairs = [{"full": "윤하나", "part": "하나"}]
    user = extraction.build_prompt(ctx(TWO_WAYS), known("윤하나"), pairs=pairs)
    assert "NAME PAIRS (a known full name, and part of it written on its own in the TARGET turn):\nN1. 윤하나 / 하나" in user
    assert "Before answering, decide for each NAME PAIR (N1–N1) whether the TARGET turn uses the two names for one" in user
    # the owner's run of 0abb2fd: 46 of 63 answers named the pair ("윤하람 / 하람") instead of its number, and were refused
    assert ('list only those in `same_names` by their number, not their names (for N1, 윤하나 / 하나: {"pair": "N1",'
            ' "evidence": "..."}), each quoting the TARGET turn.') in user
    assert "NAME PAIRS" not in extraction.build_prompt(ctx(TWO_WAYS), known("윤하나"))


PAIRS = [{"full": "윤하나", "part": "하나"}, {"full": "Hana Yoon", "part": "Yoon"}]


def test_a_confirmed_pair_is_written_as_the_alias_the_turn_check_keeps():
    (row,) = extraction.same_names({"same_names": [{"pair": "N1", "evidence": TWO_WAYS}]}, [], PAIRS, TWO_WAYS)
    assert (row["subject"], row["predicate"], row["value"], row["evidence"]) == ("윤하나", "also_called", "하나", TWO_WAYS)
    (kept,) = extraction.normalize([row], TWO_WAYS, known("윤하나", "하나"), TWO_WAYS, apart=True)
    assert (kept["status"], kept["modality"], kept["source"]) == ("valid", "actual", "narration")


def test_an_unknown_number_a_quote_not_in_the_turn_and_a_repeat_give_nothing_more():
    answer = {"same_names": [{"pair": "N3", "evidence": TWO_WAYS},
                             {"pair": "윤하나 / 하나", "evidence": TWO_WAYS},  # the names, not the number: refused
                             {"pair": "N1", "evidence": "카이토는 창밖을 내다보며 오래 생각에 잠겼다."},
                             {"pair": "n1", "evidence": TWO_WAYS}, {"pair": "N1", "evidence": TWO_WAYS}, "N1"]}
    assert [r["value"] for r in extraction.same_names(answer, [], PAIRS, TWO_WAYS)] == ["하나"]
    assert extraction.same_names({"same_names": "N1"}, [], PAIRS, TWO_WAYS) == []
    assert extraction.same_names({}, [], PAIRS, TWO_WAYS) == []


def test_a_free_alias_between_a_listed_pair_is_dropped_and_others_are_kept():
    free = {"subject": "하나", "subject_type": CHAR, "predicate": "also_called", "value": "윤하나"}
    other = {"subject": "카이토", "subject_type": CHAR, "predicate": "also_called", "value": "Kaito"}
    place = {"subject": "윤하나", "subject_type": CHAR, "predicate": "located_in", "object": "거실"}
    assert extraction.same_names({"same_names": []}, [free, other, place], PAIRS, TWO_WAYS) == [other, place]
    assert extraction.same_names({}, [free], [], TWO_WAYS) == [free]  # no pairs listed: the free rule, as before


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
                                             "R1. 하나 → 카이토: 세입자 (turn 3)", ""]
    c = {**ctx("하나는 이사했다."), "context": []}
    assert "CURRENT ROLES" in extraction.build_prompt(c, roles=roles)
    assert extraction.build_prompt(c, roles=roles).endswith(
        "Before answering, decide for each CURRENT ROLE (R1–R1) whether the TARGET turn ends it between its own two people"
        " (a new role or promotion toward someone else does not), and whether it is over by"
        ' the end of the TARGET turn ("now") or only planned or prepared ("planned"); list only those in `roles_ended`,'
        ' each quoting the TARGET turn (the text after "TARGET turn 20:"), not CONTEXT.')
    assert "CURRENT ROLES" not in extraction.build_prompt(c) and "CURRENT ROLES" not in extraction.build_prompt(c, roles=[])


# --- the model names an ending, the listed role is written (Q1) --------------------------------------------------------

ROLES = [{"by": "하나", "to": "카이토", "role": "세입자: 카이토의 집에 세 들어 삶", "turn": 1},
         {"by": "{{user}}", "to": "유이", "role": "손님: 유이의 여관 3호실에 묵음", "turn": 2}]
MOVED = "하나는 짐을 싸서 카이토의 집을 떠나 이사했다."


def test_a_named_ending_is_written_with_the_listed_subject_object_and_value():
    (row,) = extraction.ended_roles({"roles_ended": [{"role": "R1", "when": "now", "evidence": MOVED}]}, [], ROLES, MOVED)
    assert (row["subject"], row["object"], row["value"], row["polarity"]) == (
        "하나", "카이토", "세입자: 카이토의 집에 세 들어 삶", "negative")
    assert (row["predicate"], row["modality"], row["source"]) == ("role_toward", "actual", "narration")
    (valid,) = extraction.normalize([row], MOVED, shown=MOVED)
    assert valid["status"] == "valid"


def test_an_unknown_number_a_quote_not_in_the_turn_and_a_repeat_give_nothing_more():
    named = [{"role": "R9", "when": "now", "evidence": MOVED},
             {"role": "R2", "when": "now", "evidence": "유이는 어젯밤 항구의 창고에서 지도를 찾았다."},
             {"role": "r1", "when": "NOW", "evidence": MOVED}, {"role": "R1", "when": "now", "evidence": MOVED}, "R2",
             {"role": "R1", "when": "now"}]
    rows = extraction.ended_roles({"roles_ended": named}, [], ROLES, MOVED)
    assert [(r["subject"], r["value"]) for r in rows] == [("하나", "세입자: 카이토의 집에 세 들어 삶")]
    assert extraction.ended_roles({"roles_ended": "R1"}, [], ROLES, MOVED) == []
    assert extraction.ended_roles({}, [], [], MOVED) == []


def test_an_ending_only_planned_or_without_its_time_closes_nothing_yet():
    """The owner's run of 4a7c11c: on the eve of the move, packing, the model ended the stay three times out of three on a
    sentence about tomorrow. Only an ending over in the target turn is written."""
    eve = "하나는 내일 이사할 짐을 쌌다. 내일부터 겨울 내내 다른 집에서 지내기로 했다."
    for when in ("planned", "", None, "later"):
        entry = {"role": "R1", "evidence": eve, **({"when": when} if when is not None else {})}
        assert extraction.ended_roles({"roles_ended": [entry]}, [], ROLES, eve) == []
    (row,) = extraction.ended_roles({"roles_ended": [{"role": "R1", "when": "planned", "evidence": eve},
                                                     {"role": "R1", "when": "now", "evidence": MOVED}]}, [], ROLES, MOVED)
    assert row["value"] == "세입자: 카이토의 집에 세 들어 삶"  # a planned report does not use up the number


EVE = "그날 저녁 하나는 다락방에서 짐을 쌌다. 내일부터는 다른 집에서 지내기로 되어 있었다."


def test_a_quote_that_places_the_change_later_closes_nothing_even_when_said_now():
    """The owner's run of 2e4ccfd: on the eve of the move the model answered "now" once in three, quoting "내일부터 겨울
    내내 …", a sentence in the target turn about the next day. A quote with a time word that places the change later
    closes nothing; an ending told as done still does."""
    for quote in ("내일부터 겨울 내내 다른 집에서 지내기로 했다.", "다음 날 아침에 이사하기로 했다.", "다음 주에 짐을 옮길 예정이다.",
                  "She will move out of Kaito's house tomorrow.", "From next week she rents a room elsewhere.",
                  "Hana is going to leave the inn."):
        assert extraction.ended_roles({"roles_ended": [{"role": "R1", "when": "now", "evidence": quote}]}, [], ROLES,
                                      quote) == [], quote
    for quote in (MOVED, "하나는 오늘 아침 카이토의 집을 떠나 새 집으로 이사했다.", "Hana moved out of Kaito's house this morning."):
        (row,) = extraction.ended_roles({"roles_ended": [{"role": "R1", "when": "now", "evidence": quote}]}, [], ROLES,
                                        quote, hints=known("카이토", also={"카이토": ["Kaito"]}))
        assert row["polarity"] == "negative", quote


def test_next_week_and_next_month_are_nouns_not_the_verbs_that_contain_them():
    """The owner's probe on 27c7658: "과제를 내주었다" (gave an assignment) matched 내주 (next week). 내주다 (hand over)
    and 내달리다 (dash) tell what happens now; the nouns still place the change later."""
    for quote in ("하나는 카이토에게 열쇠를 내주고 짐을 들고 나왔다.", "하나는 짐을 메고 문밖으로 내달려 집을 떠났다."):
        assert extraction.LATER.search(quote) is None, quote
        target = "카이토는 문 옆에 서 있었다. " + quote
        (row,) = extraction.ended_roles({"roles_ended": [{"role": "R1", "when": "now", "evidence": quote}]}, [], ROLES,
                                        target)
        assert row["polarity"] == "negative", quote
    for quote in ("하나는 내주에 카이토의 집을 떠난다.", "내달부터 다른 집에 세 들기로 했다.", "하나는 내주 월요일에 이사한다.",
                  "이사는 내달.", "내주의 일정대로 집을 비운다.", "이사를 내달로 미뤘다."):
        assert extraction.LATER.search(quote), quote


def test_a_quote_joining_context_and_target_counts_by_its_passage_in_the_target_turn():
    """The owner's run of 37af724: on the turn of the move the model named the stay and "now", and quoted a sentence of
    the previous turn and one of the target joined by "...", three times out of three; the whole quote missed the bar.
    The passage found in the target turn is the evidence, at the same bar; the previous turn's never counts."""
    joined = EVE.split(". ")[1] + " ... " + MOVED
    assert extraction.quoted_in(MOVED, MOVED) == MOVED  # a whole quote, as before
    assert extraction.quoted_in(joined, MOVED) == MOVED
    assert extraction.quoted_in(EVE.split(". ")[1] + "…" + MOVED, MOVED) == MOVED
    assert extraction.quoted_in(EVE.replace(". ", " ... "), MOVED) is None  # every passage from CONTEXT
    assert extraction.quoted_in(EVE.split(". ")[1] + " ... 이사했다.", MOVED) is None  # too short to tell
    assert extraction.quoted_in("", MOVED) is None
    (row,) = extraction.ended_roles({"roles_ended": [{"role": "R1", "when": "now", "evidence": joined}]}, [], ROLES,
                                    MOVED)
    assert row["evidence"] == MOVED and row["value"] == "세입자: 카이토의 집에 세 들어 삶"


def test_a_free_ending_between_a_listed_pair_is_dropped_and_others_are_kept():
    """On the owner's run the model wrote the ending itself with the role's name only, which matched nothing and would
    stand beside the role as a fact of its own (#251)."""
    free = {"subject": "하나", "subject_type": CHAR, "predicate": "role_toward", "object": "카이토", "object_type": CHAR,
            "value": "세입자", "polarity": "negative"}
    other = {**free, "object": "유이"}  # not a listed pair
    new = {**free, "value": "친구의 집에 얹혀 삶", "polarity": "positive"}  # a new role toward the same person
    place = {"subject": "하나", "predicate": "located_in", "object": "카이토의 집", "polarity": "negative"}
    assert extraction.ended_roles({}, [free, other, new, place], ROLES, MOVED) == [other, new, place]


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


def test_a_new_job_toward_another_person_keeps_the_existing_mentorship():
    mentorship = role(1, "하나", "카이토", "제자: 카이토에게 지도를 배우는 조수")
    hired = role(2, "하나", "유이", "직원: 유이의 측량 사무소에서 일함")
    assert current([mentorship, hired]) == [
        ("하나", "유이", "직원: 유이의 측량 사무소에서 일함", "positive"),
        ("하나", "카이토", "제자: 카이토에게 지도를 배우는 조수", "positive")]


# --- through the worker ------------------------------------------------------------------------------------------------

LISTED = re.compile(r"^(?P<ref>R\d+)\. (?P<by>.+?) → (?P<to>.+?): (?P<role>.+) \(turn \d+\)$", re.M)


def moving_out(system, user):
    """The model as the prompt allows it: the tenancy when the story states it, the leaving as a place, and under
    extract-v16 the listed role it ends (by number), with a free ending in the role's name only besides, as the owner's
    run saw the model write one (#251)."""
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
            listed = list(LISTED.finditer(user.split("CURRENT ROLES", 1)[1].split("\n\n", 1)[0]))
            items += [{"subject": m["by"], "subject_type": CHAR, "predicate": "role_toward", "object": m["to"],
                       "object_type": CHAR, "value": m["role"].split(":")[0], "polarity": "negative",
                       "modality": "actual", "source": "narration", "knowledge": "public"} for m in listed]
            return {"assertions": items, "roles_ended": [{"role": m["ref"], "when": "now",
                                                          "evidence": "하나는 짐을 싸서 카이토의 집을 떠나 이사했다."}
                                                         for m in listed]}, "{}"
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


# --- a name said two ways, through the worker (Q4) ---------------------------------------------------------------------

def two_ways(system, user):
    """The model as each prompt allows it: under extract-v16 the turn that writes 윤하나 and then 하나 links them."""
    target = user.split("TARGET", 1)[1]
    items = []

    def say(**item):
        items.append({"subject_type": CHAR, "modality": "actual", "source": "narration", "knowledge": "public", **item})

    if "문을 열었다" in target:
        say(subject="윤하나", predicate="located_in", object="현관", object_type="place")
        if extraction.ALIAS_PARTS in system:
            say(subject="윤하나", predicate="also_called", value="하나")
    if "정원으로" in target:
        say(subject="하나", predicate="located_in", object="정원", object_type="place")
    return {"assertions": items}, "{}"


def two_ways_chat() -> SimChat:
    chat = SimChat()
    chat.user("윤하나가 문을 열었다. 하나는 웃었다.")
    chat.reply("바람이 들어왔다.")
    filler(chat, 2)
    chat.user("하나는 정원으로 나갔다.")
    chat.reply("꽃이 피어 있었다.")
    filler(chat, 2, tag="b")
    return chat


def pairs_named(system, user):
    """The model as the prompt allows it: each turn's place; under extract-v16, a listed NAME PAIR confirmed by number,
    and no free alias (the owner's run of 27c7658 saw none)."""
    target = user.split("TARGET", 1)[1]
    items = []
    for name, place, where in (("윤하나", "현관", "문을 열었다"), ("하나", "정원", "정원으로"), ("윤하나", "거실", "의자에")):
        if where in target:
            items.append({"subject": name, "subject_type": CHAR, "predicate": "located_in", "object": place,
                          "object_type": "place", "modality": "actual", "source": "narration", "knowledge": "public"})
    if "N1. 윤하나 / 하나" in user:
        return {"assertions": items, "same_names": [{"pair": "N1", "evidence": TWO_WAYS}]}, "{}"
    return {"assertions": items}, "{}"


@pytest.mark.parametrize("compiler, places", [
    ("extract-v15", [("윤하나", "거실"), ("하나", "정원")]),  # two entities, each with a current place (the defect)
    ("extract-v16", [("윤하나", "거실")]),  # one character, in its latest place
])
def test_a_known_full_name_and_its_part_written_apart_are_one_character_under_extract_v16(migrated, compiler, places):
    chat = SimChat()
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake", extract_compiler=compiler) as c:
        for text in ("윤하나가 문을 열었다.", "하나는 정원으로 나갔다.", TWO_WAYS):  # in story order, as a live chat
            chat.user(text)
            chat.reply("바람이 불었다.")
            filler(chat, 1, tag=str(len(chat.messages)))
            sync(c, chat)
            drain(migrated, pairs_named)
        current = sorted((f["subject"], f["object"]) for f in facts(c, chat)
                         if f["predicate"] == "located_in" and f.get("polarity") != "negative")
    assert current == sorted(places)
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        rows = conn.execute("SELECT hints FROM extraction").fetchall()
    listed = [r["hints"]["names"] for r in rows if r["hints"] and r["hints"].get("names")]
    assert listed == ([[{"full": "윤하나", "part": "하나"}]] if compiler == "extract-v16" else [])


@pytest.mark.parametrize("compiler, places", [
    ("extract-v15", [("윤하나", "현관"), ("하나", "정원")]),  # two entities, each with a current place (the defect)
    ("extract-v16", [("하나", "정원")]),  # one character, in its later place
])
def test_a_name_and_its_part_are_one_character_under_extract_v16(migrated, compiler, places):
    chat = two_ways_chat()
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake", extract_compiler=compiler) as c:
        sync(c, chat)
        drain(migrated, two_ways)
        current = sorted((f["subject"], f["object"]) for f in facts(c, chat)
                         if f["predicate"] == "located_in" and f.get("polarity") != "negative")
    assert current == sorted(places)
