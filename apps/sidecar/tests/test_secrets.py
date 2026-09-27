"""Phase 10 (docs/phases/PHASE-10.md): secrets at read time and OPEN SECRETS for extraction (ADR 0033)."""

from __future__ import annotations

import uuid

from nmos_sidecar import extraction
from nmos_sidecar.entities import resolve
from nmos_sidecar.predicates import REGISTRY, registry_prompt, validate
from nmos_sidecar.facts import served_assertions
from nmos_sidecar.secrets import fold, is_secret, secret_text
from test_semantics import row

PLAN = "엄마 몰래 강의실 뒤에서 수업을 보기"


def secret(pos: int, holders=("엘피", "{{user}}"), kept=("블랑",), value=PLAN, **kw):
    """A goal kept from someone, as extract-v12 stores one."""
    return row(pos, "엘피", "goal", None, value, subject_type="character", knowledge="limited",
               known_by=list(holders), hidden_from=list(kept), **kw)


def learned(pos: int, who: str = "블랑", text: str = f"엘피 goal: {PLAN}", **kw):
    return row(pos, who, "learned", None, text, subject_type="character", **kw)


def secrets(rows):
    return fold(rows, resolve(uuid.uuid4(), rows))


def test_a_fact_kept_from_someone_is_a_secret():
    assert is_secret(secret(1))
    assert not is_secret(secret(1, kept=()))  # limited without hidden_from: only who knows
    assert not is_secret(row(1, "엘피", "goal", None, PLAN, subject_type="character", knowledge="public"))
    assert not is_secret(secret(1, modality="dreamed"))
    (s,), unmatched, used = secrets([secret(7)])
    assert (s["text"], s["kept_from"], s["open"], s["ended"]) == (f"엘피 goal: {PLAN}", ["블랑"], ["블랑"], {})
    assert unmatched == [] and used == set()


def test_learned_ends_the_secret_for_that_character_only():
    (s,), unmatched, used = secrets([secret(7, kept=("블랑", "라디아")), learned(21)])
    assert s["open"] == ["라디아"] and s["ended"]["블랑"]["turn"] == 21 and unmatched == [] and used == {21}


def test_a_reworded_reveal_ends_every_restated_copy_but_not_another_secret():
    rows = [secret(7), secret(8, value="강의실 뒤에서 몰래 엄마 수업 보기 작전"), secret(9, value="쿠키 굽기"),
            learned(21, text=f"엘피 goal: {PLAN}")]
    got, unmatched, _ = secrets(rows)
    assert {s["turn"]: s["open"] for s in got} == {7: [], 8: [], 9: ["블랑"]} and unmatched == []
    # The content alone, without the head, matches too; a different head does not.
    assert secrets([secret(7), learned(21, text="엄마 몰래 수업 보기")])[0][0]["open"] == []
    assert secrets([secret(7), learned(21, text=f"라디아 goal: {PLAN}")])[0][0]["open"] == ["블랑"]


def test_a_reveal_of_a_listed_turn_survives_that_turn_being_extracted_again_in_other_words():
    # Listed as "엘피 goal: {PLAN}" from turn 7; turn 7 was extracted again later and reads differently now.
    reworded = secret(7, value="블랑 모르게 강의 듣기")
    (s,), unmatched, _ = secrets([reworded, learned(21, text=f"[turn 7] 엘피 goal: {PLAN}")])
    assert s["open"] == [] and unmatched == []
    # Two secrets of that turn with the head: the closer one ends; a secret of another turn does not.
    other = secret(7, value="쿠키를 서랍에 숨기기")
    got, _, _ = secrets([reworded, other, secret(9, value="쿠키 굽기"), learned(21, text=f"[turn 7] 엘피 goal: {PLAN}")])
    assert {s["text"][9:]: s["open"] for s in got} == {"블랑 모르게 강의 듣기": [], "쿠키를 서랍에 숨기기": ["블랑"],
                                                       "쿠키 굽기": ["블랑"]}


def test_a_reveal_whose_listed_turn_was_edited_matches_by_content_only():
    """ADR 0033 amendment 2: the listed turn's hash when the reveal was extracted, against the turn's now."""
    listed = f"[turn 7] 엘피 goal: {PLAN}"
    other = secret(7, value="다이아몬드 훔치기", turn_hash="h2")
    (s,), unmatched, _ = secrets([other, learned(21, text=listed, listed_hash="h1")])
    assert s["open"] == ["블랑"] and [u["value"] for u in unmatched] == [listed]
    for unchanged in ("h2", None):  # the same turn, or a reveal extracted before hashes were recorded: rule 1
        (s,), unmatched, _ = secrets([other, learned(21, text=listed, listed_hash=unchanged)])
        assert s["open"] == [] and unmatched == []
    (s,), unmatched, _ = secrets([secret(7, turn_hash="h2"), learned(21, text=listed, listed_hash="h1")])  # rule 2
    assert s["open"] == [] and unmatched == []


def test_a_second_reveal_of_the_same_secret_is_no_mismatch():
    (s,), unmatched, used = secrets([secret(7), learned(21), learned(30)])
    assert s["ended"]["블랑"]["turn"] == 21 and unmatched == [] and used == {21, 30}


def test_a_reveal_matching_nothing_ends_nothing():
    (s,), unmatched, _ = secrets([secret(7), learned(21, text="라디아 identity: 연구원")])
    assert s["open"] == ["블랑"] and [u["turn"] for u in unmatched] == [21]
    # Someone the secret was not kept from cannot end it.
    (s,), unmatched, _ = secrets([secret(7), learned(21, who="라디아")])
    assert s["open"] == ["블랑"] and len(unmatched) == 1


def test_a_reveal_before_the_secret_or_not_actual_ends_nothing():
    (s,), _, _ = secrets([learned(3), secret(7)])
    assert s["open"] == ["블랑"]
    (s,), _, used = secrets([secret(7), learned(21, modality="hypothetical")])
    assert s["open"] == ["블랑"] and used == set()
    (s,), _, _ = secrets([secret(7), learned(21, polarity="negative")])
    assert s["open"] == ["블랑"]


def test_learned_is_registered_for_characters():
    assert "learned" in REGISTRY
    assert validate({"subject": "블랑", "subject_type": "character", "predicate": "learned", "value": "x"}) == ("valid", None)
    assert validate({"subject": "블랑", "subject_type": "character", "predicate": "learned"})[0] == "pending"


def test_open_secrets_are_listed_for_named_people_and_leave_when_found_out():
    ctx = {"target": {"conversation_id": uuid.uuid4(), "turn": 30},
           "context": [{"turn": 29, "metadata": {"role": "user"}, "content": "아침이 밝았다."}],
           "members": [{"turn": 30, "metadata": {"role": "char"}, "content": "조용한 부엌."}]}
    rows = [secret(7)]
    assert extraction.secret_hints(ctx, rows) == []  # nobody it concerns is named
    ctx["members"][0]["content"] = "블랑이 커피를 마셨다."
    assert extraction.secret_hints(ctx, rows) == [
        {"text": f"엘피 goal: {PLAN}", "holders": ["엘피", "{{user}}"], "kept_from": ["블랑"], "turn": 7, "turn_hash": None}]
    assert extraction.secret_hints(ctx, [secret(7), learned(21)]) == []  # found out: no longer open


def test_the_prompt_lists_open_secrets_and_the_rules():
    ctx = {"target": {"turn": 30}, "context": [],
           "members": [{"turn": 30, "metadata": {"role": "char"}, "content": "블랑이 문 앞에 섰다."}]}
    listed = [{"text": f"엘피 goal: {PLAN}", "holders": ["엘피", "{{user}}"], "kept_from": ["블랑"], "turn": 7}]
    prompt = extraction.build_prompt(ctx, None, None, listed)
    assert "OPEN SECRETS (kept from someone earlier in this story, not yet found out):" in prompt
    assert f"S1. 엘피 goal: {PLAN} (known by: 엘피, {{{{user}}}}; kept from: 블랑; turn 7)" in prompt
    assert "decide for each OPEN SECRET (S1–S1)" in prompt
    assert "OPEN SECRETS" not in extraction.build_prompt(ctx, None, None, [])
    system = extraction.SYSTEM_PROMPT.format(registry=registry_prompt())
    assert "Someone who was simply not there is not `hidden_from`" in system
    assert "report in `secrets` each one" in system and '"secrets": [{"secret": "S1"' in system
    assert "- learned" not in system  # filled from `secrets`, never asked for directly
    assert extraction.COMPILER_VERSION == "extract-v12"


def test_the_secrets_check_becomes_learned_only_with_a_kept_name_and_quoted_evidence():
    listed = [{"text": f"엘피 goal: {PLAN}", "holders": ["엘피"], "kept_from": ["블랑"], "turn": 7},
              {"text": "하나 identity: 공주", "holders": ["하나"], "kept_from": ["유이", "카이토"], "turn": 3}]
    turn = "블랑이 창문 너머로 엘피의 귀를 보았다. 강의실 뒤에 숨어 있던 엘피가 들킨 것이다."
    answer = {"secrets": [{"secret": "S1", "found_out_by": ["블랑", "라디아"], "evidence": "엘피의 귀를 보았다"},
                          {"secret": "s2", "found_out_by": ["유이"], "evidence": "공주라는 말을 들었다"},  # not in the turn
                          {"secret": "S9", "found_out_by": ["블랑"], "evidence": "엘피의 귀를 보았다"},  # no such line
                          "S1"]}
    got = extraction.revealed(answer, listed, turn)
    assert [(a["subject"], a["predicate"], a["value"]) for a in got] == [("블랑", "learned", f"[turn 7] 엘피 goal: {PLAN}")]
    assert extraction.revealed({"secrets": "S1"}, listed, turn) == [] and extraction.revealed({}, listed, turn) == []


def test_secret_text_is_the_fact_line():
    assert secret_text(secret(7)) == f"엘피 goal: {PLAN}"
    assert secret_text(row(1, "하나", "relationship", "카이토", "연인", subject_type="character")) == "하나 relationship 카이토: 연인"


# --- end to end: the worker lists open secrets, a reveal ends one, deleting the reveal restores it ----------------

import re  # noqa: E402

import pytest  # noqa: E402

from conftest import active_generation, make_client  # noqa: E402
from simchat import SimChat  # noqa: E402
from test_extraction import drain, facts  # noqa: E402
from test_generations import LLM  # noqa: E402
from test_hints import Recorder, step  # noqa: E402
from test_sidecar_integration import sync  # noqa: E402

KEPT = re.compile(r"(?P<who>[A-Z]\w+) secretly plans to (?P<what>[^,]+), hidden from (?P<from>[A-Z]\w+)\.")
FOUND = re.compile(r"(?P<who>[A-Z]\w+) found out: (?P<what>[^.]+)\.")  # → the `secrets` check on S1


class SecretRecorder(Recorder):
    """Also: 'X secretly plans to Y, hidden from Z.' → a goal kept from Z; 'Z found out: T.' → learned."""

    def __call__(self, system: str, user: str) -> tuple[dict, str]:
        out, raw = super().__call__(system, user)
        target = user.split("TARGET", 1)[1]
        out["assertions"] += [{"subject": m["who"], "subject_type": "character", "predicate": "goal",
                               "value": m["what"], "modality": "actual", "knowledge": "limited",
                               "known_by": [m["who"], "{{user}}"], "hidden_from": [m["from"]]}
                              for m in KEPT.finditer(target)]
        listed = [line.split(". ", 1)[0] for line in user.split("TARGET", 1)[0].splitlines() if line[:1] == "S"]
        out["secrets"] = [{"secret": listed[0], "found_out_by": [m["who"]], "evidence": m.group(0)}
                          for m in FOUND.finditer(target) if listed]
        return out, raw


def secrets_of(prompt: str) -> list[str]:
    if "OPEN SECRETS" not in prompt:
        return []
    block = prompt.split("OPEN SECRETS", 1)[1].split("\n\n", 1)[0]
    return [line.split(". ", 1)[1] for line in block.splitlines() if line[:1] == "S" and ". " in line]


def test_a_reveal_ends_the_secret_until_its_turn_is_deleted(migrated, db):
    model, chat = SecretRecorder(), SimChat()
    with make_client(migrated, **LLM) as c:
        step(c, migrated, chat, model, "Elpi secretly plans to watch the lecture, hidden from Blanc.")
        step(c, migrated, chat, model, "Blanc drinks coffee.")
        step(c, migrated, chat, model, "Blanc found out: Elpi goal: watch the lecture.")
        step(c, migrated, chat, model, "Blanc smiles.")
        step(c, migrated, chat, model, "next")
        listed = "Elpi goal: watch the lecture (known by: Elpi, {{user}}; kept from: Blanc; turn 0)"  # S1
        assert secrets_of(model.prompts[1]) == [listed]  # Blanc is named: the secret is shown
        assert secrets_of(model.prompts[3]) == []  # found out in turn 2
        stored = db.execute("SELECT hints FROM extraction e JOIN active_membership am"
                            " ON am.source_revision_id = e.source_revision_id WHERE am.turn = 1 LIMIT 1").fetchone()
        assert stored["hints"]["secrets"][0]["kept_from"] == ["Blanc"]
        view = facts(c, chat)
        goal = next(f for f in view if f["predicate"] == "goal")
        assert not goal.get("hidden_from") and goal["known_by"] == ["Elpi", "{{user}}", "Blanc"]  # amendment 1
        assert [r["to"] for r in goal["revealed"]] == ["Blanc"]
        assert not [f for f in view if f["predicate"] == "learned"]  # a reveal is not a fact itself
        # The Inspector lists the secret and when Blanc found it out (step 6), also on Blanc's own page.
        conv = next(x for x in c.get("/v1/conversations").json() if x["host_chat_ref"] == chat.id)["id"]
        page = c.get(f"/inspector/c/{conv}", params={"lang": "en"}).text
        assert "Secrets (kept from whom" in page and "Elpi goal: watch the lecture" in page
        assert "Blanc: found out in turn 2" in page and "Reveals that matched no open secret" not in page
        blanc = next(e for e in c.get(f"/v1/conversations/{conv}/entities").json() if e["name"] == "Blanc")
        assert "Secrets this character found out" in c.get(f"/inspector/c/{conv}/e/{blanc['id']}",
                                                          params={"lang": "en"}).text
        chat.delete(4)  # the revealing turn's user message (turns are user + reply)
        step(c, migrated, chat, model, "again")
        goal = next(f for f in facts(c, chat) if f["predicate"] == "goal")
        assert goal["hidden_from"] == ["Blanc"] and not goal.get("revealed") and goal["known_by"] == ["Elpi", "{{user}}"]
        page = c.get(f"/inspector/c/{conv}", params={"lang": "en"}).text
        assert "Blanc: <span class=\"warn\">does not know yet</span>" in page


# --- findings of the 2026-09-27 audit (docs/proposals/ORIGINAL-VISION-TO-STABLE-2026-09-27.md) ----------------------


def goal_of(c, chat) -> dict:
    return next(f for f in facts(c, chat) if f["predicate"] == "goal")


def served(db) -> list[dict]:
    head = db.execute("SELECT head_commit_id FROM conversation").fetchone()["head_commit_id"]
    return served_assertions(db, head, active_generation(db, "extract").key)


def reveal_rows(db) -> list[dict]:
    return [r for r in served(db) if r["predicate"] == "learned"]


def goal_row(db) -> dict:
    return next(r for r in served(db) if r["predicate"] == "goal")


def test_a_reveal_does_not_carry_over_to_a_different_secret_after_its_turn_is_edited(migrated, db):
    """Audit G1: linked by turn and head, a reveal used to end whatever secret its listed turn held after an
    edit. It ends one there only while that turn reads as it did (ADR 0033 amendment 2)."""
    model, chat = SecretRecorder(), SimChat()
    with make_client(migrated, **LLM) as c:
        step(c, migrated, chat, model, "Elpi secretly plans to watch the lecture, hidden from Blanc.")
        for i in range(4):  # the reveal falls outside the edited turn's context (extract_turns = 3)
            step(c, migrated, chat, model, f"Blanc reads chapter {i}.")
        step(c, migrated, chat, model, "Blanc found out: Elpi goal: watch the lecture.")
        step(c, migrated, chat, model, "next")
        assert [r["to"] for r in goal_of(c, chat)["revealed"]] == ["Blanc"]
        (listed,) = [r["listed_hash"] for r in reveal_rows(db)]
        assert listed is not None
        conv = next(x for x in c.get("/v1/conversations").json() if x["host_chat_ref"] == chat.id)["id"]
        assert c.post(f"/v1/conversations/{conv}/extract-history").json()["queued"]["extract"] == 0  # in order
        chat.edit(0, "Elpi secretly plans to steal the diamond, hidden from Blanc.")
        sync(c, chat)
        drain(migrated, model)
        goal = goal_of(c, chat)
        assert goal["value"] == "steal the diamond"
        assert goal["hidden_from"] == ["Blanc"] and not goal.get("revealed")  # Blanc learned of the lecture only
        assert [r["listed_hash"] for r in reveal_rows(db)] == [listed] and goal_row(db)["turn_hash"] != listed
        page = c.get(f"/inspector/c/{conv}", params={"lang": "en"}).text
        assert "Reveals that matched no open secret" in page


FIRST_IMPORT = ("Elpi secretly plans to watch the lecture, hidden from Blanc.", "Blanc drinks coffee.",
                "Blanc found out: Elpi goal: watch the lecture.", "Blanc smiles.")


def first_import(c, migrated, model) -> tuple[SimChat, str]:
    """K29: four complete turns seen at once; the reveal is extracted before the secret and matches nothing."""
    chat = SimChat()
    for line in FIRST_IMPORT:
        chat.user(line)
        chat.reply("Noted.")
    sync(c, chat)
    drain(migrated, model)
    assert goal_of(c, chat)["hidden_from"] == ["Blanc"]
    conv = next(x for x in c.get("/v1/conversations").json() if x["host_chat_ref"] == chat.id)["id"]
    return chat, conv


def test_extract_all_history_recovers_a_reveal_missed_on_first_import(migrated, db):
    """Audit G2: Extract all history used to skip every compiled turn, so K29's workaround did nothing. It now
    extracts again the turns extracted before an earlier turn's secret, oldest first, and only those."""
    model = SecretRecorder()
    with make_client(migrated, **LLM) as c:
        chat, conv = first_import(c, migrated, model)
        out = c.post(f"/v1/conversations/{conv}/extract-history").json()
        assert out["queued"]["extract"] == 2  # turns 1 and 2; turn 0 holds the secret
        drain(migrated, model)
        goal = goal_of(c, chat)
        assert not goal.get("hidden_from") and [r["to"] for r in goal["revealed"]] == ["Blanc"]
        assert c.post(f"/v1/conversations/{conv}/extract-history").json()["queued"]["extract"] == 0  # settled


def test_rebuild_recovers_a_reveal_missed_on_first_import(migrated, db):
    """K29's workaround: Rebuild re-extracts every turn, and one worker takes them oldest first."""
    model = SecretRecorder()
    with make_client(migrated, **LLM) as c:
        chat, conv = first_import(c, migrated, model)
        out = c.post(f"/v1/conversations/{conv}/rebuild").json()
        assert out["discarded"] == out["queued"]["extract"] > 0
        drain(migrated, model)
        goal = goal_of(c, chat)
        assert not goal.get("hidden_from") and [r["to"] for r in goal["revealed"]] == ["Blanc"]
