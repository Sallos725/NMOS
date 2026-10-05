"""A listed ending needs its counterpart in the shown TARGET, not only in old hints."""

import pytest

from nmos_sidecar import extraction as X
from test_extract_v16 import LISTED, make_client, moving_out, roles_of, tenancy_chat
from test_extraction import drain, filler
from test_sidecar_integration import sync


ROLE = {"by": "강세온", "to": "문채린", "role": "직원: 문채린의 식당에서 일함", "turn": 1}
PROMOTION = "류태오는 강세온을 제과실의 수석 제빵사로 승진시켰다. 화덕은 이제 강세온에게 맡긴다고 말했다."


def answer(quote):
    return {"roles_ended": [{"role": "R1", "when": "now", "evidence": quote}]}


def test_a_promotion_elsewhere_cannot_end_a_role_toward_an_absent_person():
    assert X.ended_roles(answer(PROMOTION), [], [ROLE], PROMOTION) == []


def test_the_counterpart_can_be_named_outside_the_ending_quote_by_a_known_alias():
    quote = "강세온은 식당 일을 그만두고 마지막 급료를 받았다."
    target = "문 실장이 강세온의 사직서를 받았다. " + quote
    hints = [{"name": "문채린", "type": "character", "also": ["문 실장"]}]
    assert X.ended_roles(answer(quote), [], [ROLE], target) == []
    (row,) = X.ended_roles(answer(quote), [], [ROLE], target, hints=hints)
    assert row['value'] == ROLE['role'] and row['evidence'] == quote
    # Old hints cannot make an absent name present in TARGET.
    assert X.ended_roles(answer(PROMOTION), [], [ROLE], PROMOTION, hints=hints) == []


def test_an_ambiguous_alias_or_a_name_of_another_type_does_not_supply_the_counterpart():
    target = "실장은 강세온의 사직서를 받고 식당 고용 계약을 끝냈다."
    hints = [{"name": "문채린", "type": "character", "also": ["실장"]},
             {"name": "류태오", "type": "character", "also": ["실장"]}]
    assert X.ended_roles(answer(target), [], [ROLE], target, hints=hints) == []
    assert X.ended_roles(answer(target), [], [ROLE], target, hints=[hints[0] | {"type": "place"}]) == []


def test_an_embedded_name_is_not_a_counterpart_mention():
    for other, text in [("Ann", "Joanne and Anna promoted Seon to head baker."),
                        ("이안", "백이안은 강세온을 수석 제빵사로 승진시켰다.")]:
        assert X.ended_roles(answer(text), [], [ROLE | {"to": other}], text) == []


def test_a_role_toward_the_persona_checks_the_other_person():
    quote = "강세온은 식당 고용 계약을 끝냈다고 말했다."
    reverse = ROLE | {"by": "문채린", "to": "강세온", "role": "고용주"}
    assert X.ended_roles(answer(quote), [], [reverse], quote, persona=["강세온"]) == []
    (row,) = X.ended_roles(answer(quote), [], [reverse], "문채린이 고개를 끄덕였다. " + quote, persona=["강세온"])
    assert row['subject'] == "문채린"
    assert X.ended_roles(answer(quote), [], [reverse | {"to": "{{user}}"}], quote) == []
    # Use the resolver's existing persona rule for a full Latin name too.
    quote = "Seon Hale took a new job at the bakery."
    assert X.ended_roles(answer(quote), [], [reverse | {"to": "Seon Hale"}], quote, persona=["Hale"]) == []


def test_the_counterpart_called_by_the_given_name_alone_is_named():
    """The owner's run of 7dbef46: S1 turn 233 ended both directions of an employment correctly, but the turn called
    강무진 무진 and the hints did not link them, so the guard blocked both (0/3)."""
    role = ROLE | {"to": "강무진", "role": "직원: 강무진의 공방에서 일함"}
    quote = "강세온은 공방 열쇠를 반납하고 무진에게 그만두겠다고 말했다."
    (row,) = X.ended_roles(answer(quote), [], [role], quote)
    assert row["object"] == "강무진"
    known = [{"name": "강무진", "type": "character"}, {"name": "무진", "type": "character"}]  # the split itself
    assert len(X.ended_roles(answer(quote), [], [role], quote, hints=known)) == 1
    # another known full name with the same given name: the part alone may be that person
    namesake = known + [{"name": "서무진", "type": "character"}]
    assert X.ended_roles(answer(quote), [], [role], quote, hints=namesake) == []
    assert X.ended_roles(answer(quote), [], [role], quote, persona=["무진"]) == []  # the persona's name
    reverse = {"by": "강무진", "to": "강세온", "role": "고용주"}  # toward the persona: the other party, by its part
    assert len(X.ended_roles(answer(quote), [], [reverse], quote, persona=["강세온"])) == 1
    inside = "강세온은 공방 열쇠를 반납하고 서무진에게 그만두겠다고 말했다."  # the part only inside another name
    assert X.ended_roles(answer(inside), [], [role], inside) == []
    latin = ROLE | {"to": "Mujin Kang", "role": "clerk"}
    text = "Seon handed back the keys and told Mujin she was quitting."
    assert len(X.ended_roles(answer(text), [], [latin], text)) == 1


def test_an_ending_with_a_pronoun_only_counterpart_is_conservatively_missed():
    quote = "강세온은 그녀에게 열쇠를 돌려주고 식당 일을 그만두었다."
    assert X.ended_roles(answer(quote), [], [ROLE], quote) == []


@pytest.mark.parametrize("own_alias", [False, True])
def test_a_given_name_cannot_override_another_characters_known_alias(own_alias):
    role = ROLE | {"to": "강무진", "role": "직원: 강무진의 공방에서 일함"}
    target = "강세온은 무진에게 공방 열쇠를 반납하고 고용 계약을 끝냈다."
    hints = [{"name": "강무진", "type": "character", "also": ["무진"] if own_alias else []},
             {"name": "다른 선장", "type": "character", "also": ["무진"]}]
    assert X.ended_roles(answer(target), [], [role], target, hints=hints) == []


@pytest.mark.parametrize("name_beyond_target", [False, True])
def test_worker_keeps_the_role_when_only_context_names_its_counterpart(migrated, name_beyond_target):
    chat = tenancy_chat()
    observed = []
    prompts = []

    def wrong_ending(system, user):
        target = user.split("\nTARGET turn", 1)[1].split("\n\nBefore answering", 1)[0]
        if "승진" not in target:
            return moving_out(system, user)
        listed = list(LISTED.finditer(user))
        assert listed
        observed.append(target)
        prompts.append(user)
        quote = "유이는 하나를 제과실의 수석 제빵사로 승진시켰다."
        return {"assertions": [], "roles_ended": [{"role": listed[0]['ref'], "when": "now", "evidence": quote}]}, "{}"

    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake", extract_compiler="extract-v16") as client:
        sync(client, chat)
        drain(migrated, moving_out)
        tail = "가" * X.TARGET_CHARS + " 카이토" if name_beyond_target else ""
        chat.user("유이는 하나를 제과실의 수석 제빵사로 승진시켰다." + tail)
        chat.reply("하나는 화덕 앞에서 새 작업복을 입었다.")
        filler(chat, 1, tag="after-promotion")
        sync(client, chat)
        drain(migrated, wrong_ending)
        assert observed and all("카이토" not in target for target in observed)
        assert all("Packing, a stripped bed or farewell gifts are preparations, not checkout." in p for p in prompts)
        assert roles_of(client, chat) == [("하나", "카이토", "세입자: 카이토의 집에 세 들어 삶", "positive")]
