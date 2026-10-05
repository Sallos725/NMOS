"""extract-v16 role endings after the Codex review of bcce836: an ending keeps the knowledge scope of the role it ends,
and a free negative role written under another name of a listed party cannot skip the numbered ending, `LATER` and the
confirmation. Stand-in models and throwaway databases only."""

from __future__ import annotations

from conftest import make_client
from nmos_sidecar import extraction as X
from simchat import SimChat
from test_extraction import drain, facts, filler
from test_sidecar_integration import recall, sync

CHAR = "character"


def two_turns(migrated, first, second, complete):
    chat = SimChat()
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake", extract_compiler="extract-v16") as c:
        for i, text in enumerate((first, second)):
            chat.user(text)
            chat.reply("조용히 이야기를 이어갔다.")
            filler(chat, 1, tag=f"scope-{i}")
            sync(c, chat)
            drain(migrated, complete)
        roles = [f for f in facts(c, chat) if f["predicate"] == "role_toward"]
        packet = recall(c, chat, "하나와 카이토의 역할은 무엇인가?", in_context=[])["packet"]["text"]
    return roles, packet


# --- an ending keeps the role's knowledge scope -----------------------------------------------------------------------

SECRET = "하나는 카이토의 비밀 밀정으로 일한다. 유이에게는 이 계약을 끝까지 숨기기로 했다."
QUIET_END = "하나와 카이토는 아무에게도 알리지 않은 채 비밀 밀정 계약을 끝냈다."
SPY = "밀정: 카이토를 위해 비밀리에 활동함"


def secret_story(system, user):
    if system == X.ROLE_CONFIRM_SYSTEM:
        return {"ended": "yes", "evidence": QUIET_END}, "{}"
    if system == X.ALIAS_CONFIRM_SYSTEM:
        return {"same": "no"}, "{}"
    target = user.split("TARGET turn", 1)[-1]
    if SECRET in target:
        return {"assertions": [{"subject": "하나", "subject_type": CHAR, "predicate": "role_toward", "object": "카이토",
                                "object_type": CHAR, "value": SPY, "modality": "actual", "source": "narration",
                                "knowledge": "limited", "known_by": ["하나", "카이토"], "hidden_from": ["유이"],
                                "evidence": SECRET}]}, "{}"
    if QUIET_END in target:
        return {"assertions": [], "roles_ended": [{"role": "R1", "when": "now", "evidence": QUIET_END}]}, "{}"
    return {"assertions": []}, "{}"


def test_a_secret_role_s_ending_stays_kept_from_whom_the_role_was(migrated):
    roles, packet = two_turns(migrated, SECRET, QUIET_END, secret_story)
    (ending,) = roles
    assert ending["polarity"] == "negative" and ending["knowledge"] == "limited"
    assert ending["hidden_from"] == ["유이"] and sorted(ending["known_by"]) == ["카이토", "하나"]
    fact = next(line for line in packet.splitlines() if SPY in line)
    assert 'hidden_from="유이"' in fact and 'knowledge="public"' not in fact


def test_the_listed_role_carries_its_scope_but_the_prompt_does_not_show_it():
    listed = {"by": "하나", "to": "카이토", "role": SPY, "turn": 0, "knowledge": "limited", "known_by": ["하나", "카이토"],
              "hidden_from": ["유이"]}
    assert X.roles_block([listed]) == ["CURRENT ROLES (held earlier in this story, not yet ended):",
                                       f"R1. 하나 → 카이토: {SPY} (turn 0)", ""]
    ending = X._ending(listed, QUIET_END, None)
    assert (ending["knowledge"], ending["known_by"], ending["hidden_from"]) == ("limited", ["하나", "카이토"], ["유이"])
    public = X._ending({"by": "하나", "to": "카이토", "role": "세입자", "turn": 0, "knowledge": "public",
                        "known_by": None, "hidden_from": None}, QUIET_END, None)
    assert public["knowledge"] == "public"
    assert X._ending({"by": "하나", "to": "카이토", "role": "세입자", "turn": 0}, QUIET_END, None)["knowledge"] == "public"


# --- a free negative under another name of a listed party is dropped --------------------------------------------------

MOVED_IN = "김하나가 카이토의 집에 세 들어 산다. 하나는 집주인에게 월세를 냈다."
EVE = "하나는 내일 카이토의 집에서 이사할 준비를 했다. 오늘 밤은 여기서 묵는다."
TENANT = "세입자: 카이토의 집에 세 들어 삶"


def alias_story(asked):
    def complete(system, user):
        if system == X.ALIAS_CONFIRM_SYSTEM:
            return {"same": "yes", "evidence": "하나는 집주인에게 월세를 냈다."}, "{}"
        if system == X.ROLE_CONFIRM_SYSTEM:
            asked.append(user)
            return {"ended": "no"}, "{}"
        target = user.split("TARGET turn", 1)[-1]
        if MOVED_IN in target:
            return {"assertions": [
                {"subject": "김하나", "subject_type": CHAR, "predicate": "role_toward", "object": "카이토",
                 "object_type": CHAR, "value": TENANT, "modality": "actual", "source": "narration", "evidence": MOVED_IN},
                {"subject": "김하나", "subject_type": CHAR, "predicate": "also_called", "value": "하나",
                 "modality": "actual", "source": "narration", "evidence": MOVED_IN}]}, "{}"
        if EVE in target:
            assert "김하나 → 카이토" in user  # listed under the name the role was written with
            return {"assertions": [{"subject": "하나", "subject_type": CHAR, "predicate": "role_toward",
                                    "object": "카이토", "object_type": CHAR, "value": TENANT, "polarity": "negative",
                                    "modality": "actual", "source": "narration", "evidence": EVE}],
                    "roles_ended": []}, "{}"
        return {"assertions": []}, "{}"
    return complete


def test_an_ending_written_under_a_joined_alias_does_not_skip_the_numbered_ending(migrated):
    asked: list[str] = []
    roles, _ = two_turns(migrated, MOVED_IN, EVE, alias_story(asked))
    assert [(f["subject"], f["polarity"]) for f in roles] == [("김하나", "positive")] and asked == []


def test_parties_are_the_name_the_persona_and_the_joined_aliases_shown_nothing_guessed():
    hints = [{"name": "김하나", "type": CHAR, "also": ["하나"]}, {"name": "카이토", "type": CHAR, "also": []}]
    parties = X._parties(hints, ["서도윤"])
    assert parties("하나") & parties("김하나")
    assert parties("{{user}}") == parties("서도윤") == {X.PERSONA}
    assert not parties("하나") & parties("박하나")  # not joined: no guessed join
    listed = [{"by": "김하나", "to": "카이토", "role": TENANT, "turn": 0}]
    free = {"subject": "하나", "subject_type": CHAR, "predicate": "role_toward", "object": "카이토", "object_type": CHAR,
            "value": TENANT, "polarity": "negative"}
    other = {**free, "subject": "박하나"}
    kept = X.ended_roles({"roles_ended": []}, [free, other], listed, EVE, hints=hints, persona=["서도윤"])
    assert kept == [other]
