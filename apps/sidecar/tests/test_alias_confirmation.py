"""extract-v16's alias confirmation (PHASE-29, NMO-35): an alias whose two names are both in the turn can be given to
the wrong person (S1 turn 200: 하람 says "도도, 술 마셨지." to 도윤 and the reply writes 윤하람 → 도도). Such an alias
is asked once more about those two names alone; only a yes quoting a TARGET passage with the alias keeps it, anything
else holds it as a pending row that joins nothing, listed for the owner."""

from __future__ import annotations

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import extraction as X, llm
from nmos_sidecar.config import Settings
from simchat import SimChat
from test_extract_v16 import CHAR
from test_extraction import drain, filler
from test_sidecar_integration import sync

HINTS = [{"name": "윤하람", "type": CHAR, "also": ["하람"]}, {"name": "도윤", "type": CHAR, "also": []}]
TEASE = "하람이 코를 킁킁거렸다. \"도도, 술 마셨지.\" 도윤은 웃었다."


def alias(subject, value, **extra):
    return {"subject": subject, "subject_type": CHAR, "predicate": "also_called", "value": value,
            "modality": "actual", "source": "narration", "evidence": TEASE, **extra}


def row(turn, content, name="USER"):
    return {"turn": turn, "metadata": {"role": "user", "name": name}, "content": content}


def ctx(context, members):
    return {"context": context, "members": members, "target": {"turn": 9}}


# --- which aliases are asked (Q1) -------------------------------------------------------------------------------------

def asked(items, text=TEASE, hints=HINTS, persona=("서도윤",)):
    return [(i["subject"], i["value"]) for i, _ in X.aliases_to_confirm(items, text, hints, list(persona))]


def test_a_free_alias_whose_two_names_are_in_the_turn_is_asked_with_the_names_its_subject_goes_by():
    (item, also), = X.aliases_to_confirm([alias("윤하람", "도도")], TEASE, HINTS, ["서도윤"])
    assert (item["subject"], item["value"]) == ("윤하람", "도도") and also == ["윤하람", "하람"]


@pytest.mark.parametrize("item", [
    alias("윤하람", "도도", listed_pair=True),          # a NAME PAIRS answer, already confirmed by number (Q1, owner)
    alias("서도윤", "도도"),                            # the persona's own alias (PHASE-28 Q6)
    alias("{{user}}", "도도"),
    alias("윤하람", "하람"),                            # already one entity in KNOWN ENTITIES
    alias("윤하람", "언니"),                            # a bare person label, held anyway (ADR 0064 item 2)
    alias("윤하람", "보리"),                            # not in the turn: the presence check holds it anyway
    {**alias("나무 오리", "도도"), "subject_type": "item"},  # not a character
    {**alias("윤하람", "도도"), "predicate": "located_in"},
    alias("윤하람", "도도", held="role ending not confirmed: no"),
])
def test_other_rows_are_not_asked(item):
    assert asked([item]) == []


def test_only_the_rows_normalize_stores_are_asked():
    filler_rows = [{"subject": "도윤", "subject_type": CHAR, "predicate": "located_in", "object": "부두",
                    "object_type": "place"}] * 40
    assert asked(filler_rows + [alias("윤하람", "도도")]) == []


def test_a_missing_subject_type_is_filled_as_normalize_fills_it():
    item = alias("윤하람", "도도")
    del item["subject_type"]
    assert asked([item]) == [("윤하람", "도도")]


# --- the prompt and the answer (Q2, Q3) -------------------------------------------------------------------------------

def test_the_user_message_holds_the_two_names_the_two_preceding_turns_and_the_target_and_nothing_else():
    c = ctx([row(6, "old"), row(7, "seventh"), row(8, "eighth", "CHAR")], [row(9, TEASE)])
    text = X.alias_prompt(alias("윤하람", "도도"), ["윤하람", "하람"], c)
    assert text.startswith("NAME_A: 윤하람 (also written: 하람)\nNAME_B: 도도\n\nCONTEXT (preceding turns only):\n")
    assert "seventh" in text and "eighth" in text and "old" not in text and text.endswith(TEASE)
    assert "KNOWN ENTITIES" not in text and "ROLE:" not in text
    assert X.alias_prompt(alias("윤하람", "도도"), [], c).startswith("NAME_A: 윤하람\nNAME_B: 도도\n")


def test_the_role_confirmation_message_is_unchanged_by_the_shared_scene():
    c = ctx([row(7, "seventh")], [row(9, "target")])
    assert X.confirm_prompt({"by": "a", "to": "b", "role": "r"}, c) == (
        "ROLE: a → b: r\n\nCONTEXT (preceding turns only):\n[turn 7] USER: seventh\n\nTARGET:\nUSER: target")


@pytest.mark.parametrize("answer, outcome", [
    ({"same": "yes", "evidence": "\"도도, 술 마셨지.\""}, "yes"),
    ({"same": " YES ", "evidence": "도도, 술 마셨지."}, "yes"),
    ({"same": "no", "evidence": "도도, 술 마셨지."}, "no"),
    ({"same": "yes", "evidence": "하람이 코를 킁킁거렸다."}, "quote without the name"),
    ({"same": "yes", "evidence": "도도는 부두에서 잤다."}, "quote not in the turn"),
    ({"same": "yes"}, "quote not in the turn"),
    ({"same": "maybe", "evidence": "도도, 술 마셨지."}, "invalid answer"),
    ({"same": True, "evidence": "도도, 술 마셨지."}, "invalid answer"),
    ({"ended": "yes", "evidence": "도도, 술 마셨지."}, "invalid answer"),
    (["yes"], "invalid answer"),
])
def test_only_a_yes_quoting_a_target_passage_with_the_alias_keeps_it(answer, outcome):
    got, quote = X.alias_confirmed(answer, TEASE, "도도")
    assert got == outcome and (quote is not None) == (outcome == "yes")


# --- held or kept (Q4) ------------------------------------------------------------------------------------------------

def confirm(reply, items=None):
    items = items if items is not None else [alias("윤하람", "도도")]
    calls = []

    def complete(system, user):
        calls.append((system, user))
        if isinstance(reply, BaseException):
            raise reply
        return reply, "raw reply", {"calls": 1, "input": 4000, "output": 20}
    record, usage = X.confirm_aliases(complete, items, ctx([], [row(9, TEASE)]), TEASE, TEASE, HINTS, ["서도윤"])
    return items, record, usage, calls


def test_a_no_holds_the_alias_with_its_reason_and_the_record_keeps_every_answer():
    items, record, usage, calls = confirm({"same": "no", "evidence": "도도, 술 마셨지."})
    assert items[0]["held"] == "alias not confirmed: no" and calls[0][0] == X.ALIAS_CONFIRM_SYSTEM
    (r,) = record
    assert (r["subject"], r["value"], r["outcome"], r["quote"]) == ("윤하람", "도도", "no", None)
    assert r["reply"] == "raw reply" and r["also"] == ["윤하람", "하람"] and usage == {"calls": 1, "input": 4000, "output": 20}
    stored, = X.normalize(items, TEASE, HINTS, TEASE, True)
    assert (stored["status"], stored["reason"]) == ("pending", "alias not confirmed: no")


def test_a_yes_keeps_the_alias_valid():
    items, record, _, _ = confirm({"same": "yes", "evidence": "도도, 술 마셨지."})
    assert "held" not in items[0] and record[0]["quote"] == "도도, 술 마셨지."
    stored, = X.normalize(items, TEASE, HINTS, TEASE, True)
    assert stored["status"] == "valid"


def test_a_failed_call_holds_the_alias_and_keeps_what_came_back():
    items, record, usage, _ = confirm(llm.ReplyError("invalid JSON in model reply: x", "not json", {"calls": 1, "input": 9}))
    assert items[0]["held"] == "alias not confirmed: unusable reply" and record[0]["reply"] == "not json"
    assert usage == {"calls": 1, "input": 9}
    items, record, usage, _ = confirm(TimeoutError("slow"))
    assert items[0]["held"] == "alias not confirmed: call failed: TimeoutError" and usage is None
    assert record[0]["error"] == "TimeoutError: slow"


def test_a_stop_of_the_run_is_not_swallowed():
    with pytest.raises(KeyboardInterrupt):
        confirm(KeyboardInterrupt())


def test_a_copied_row_is_held_where_normalize_reads_it():
    item = alias("윤하람", "도도")
    del item["subject_type"]  # fill_types copies it
    items, _, _, _ = confirm({"same": "no"}, [item])
    assert items[0]["held"] == "alias not confirmed: no"


def test_a_repeated_alias_is_asked_once_and_every_copy_is_held():
    items, record, _, calls = confirm({"same": "no"}, [alias("윤하람", "도도"), alias("윤하람", "도도")])
    assert len(calls) == 1 and len(record) == 1 and all(i["held"] == "alias not confirmed: no" for i in items)


def test_nothing_asked_costs_nothing():
    items, record, usage, calls = confirm({"same": "no"}, [alias("윤하람", "하람")])
    assert (record, usage, calls) == ([], None, []) and "held" not in items[0]


def test_usages_add_up():
    assert X.summed(None, None) is None
    assert X.summed({"calls": 1, "input": 5, "model": "m"}, None, {"calls": 2, "input": 1}) == {
        "calls": 3, "input": 6, "model": "m"}


# --- generation (Q6) --------------------------------------------------------------------------------------------------

def test_the_alias_confirmation_is_in_the_v16_fingerprint_and_not_in_v15(monkeypatch):
    s16 = Settings(llm_url="http://x/v1", llm_model="m", extract_compiler="extract-v16")
    s15 = Settings(llm_url="http://x/v1", llm_model="m")
    before16, before15 = X.extractor(s16).key, X.extractor(s15).key
    monkeypatch.setattr(X, "ALIAS_CONFIRM_SYSTEM", X.ALIAS_CONFIRM_SYSTEM + " ")
    assert X.extractor(s16).key != before16 and X.extractor(s15).key == before15


# --- through the worker and the Inspector (Q4, Q5) --------------------------------------------------------------------

INTRO = "윤하람이 빵집 문을 열었다. 하람은 반죽을 치댔다."
USED = {"calls": 1, "input": 100, "output": 10}


def story(answer):
    """윤하람 / 하람 joined at the first turn (a NAME PAIRS-free alias the confirmation keeps), then the tease: the reply
    writes 윤하람 → 도도 and the confirmation answers `answer` about it."""
    asked = []

    def complete(system, user):
        if system == X.ALIAS_CONFIRM_SYSTEM:
            asked.append(user)
            if "NAME_B: 하람" in user:
                return {"same": "yes", "evidence": "하람은 반죽을 치댔다."}, "{}", USED
            return {"same": answer, "evidence": "\"도도, 술 마셨지.\""}, "{}", USED
        shown = user.split("TARGET turn", 1)[-1]
        if INTRO in shown:
            return {"assertions": [{**alias("윤하람", "하람"), "evidence": INTRO}]}, "{}", USED
        if "도도, 술 마셨지" in shown:
            return {"assertions": [alias("윤하람", "도도")]}, "{}", USED
        return {"assertions": []}, "{}", USED
    return complete, asked


def run(migrated, compiler, answer):
    complete, asked = story(answer)
    chat = SimChat()
    settings = {"extract_compiler": compiler} if compiler else {}
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake", **settings) as c:
        for i, text in enumerate([INTRO, TEASE]):  # in story order: the tease's extraction knows 윤하람 / 하람
            chat.user(text)
            chat.reply("가게 안은 따뜻했다.")
            filler(chat, 1, tag=str(i))
            sync(c, chat)
            drain(migrated, complete)
        conv = next(x["id"] for x in c.get("/v1/conversations").json() if x["host_chat_ref"] == chat.id)
        entities = c.get(f"/v1/conversations/{conv}/entities").json()
        page = c.get(f"/inspector/c/{conv}", params={"lang": "en"}).text
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:  # a fresh connection: stored state
        rows = conn.execute("SELECT a.value, a.status, a.reason, x.raw, x.usage FROM assertion a JOIN extraction x"
                            " ON x.id = a.extraction_id WHERE a.predicate = 'also_called' ORDER BY a.id").fetchall()
        failed = conn.execute("SELECT count(*) AS n FROM job WHERE status <> 'done'").fetchone()["n"]
    return asked, entities, page, rows, failed


def names(entities):
    return [set(e["names"]) for e in entities]


def test_a_wrong_alias_the_confirmation_rejects_is_held_joins_nothing_and_is_listed(migrated):
    asked, entities, page, rows, failed = run(migrated, "extract-v16", "no")
    assert len(asked) == 2 and failed == 0
    tease = next(r for r in rows if r["value"] == "도도")
    assert (tease["status"], tease["reason"]) == ("pending", "alias not confirmed: no")
    (record,) = tease["raw"]["alias_confirmations"]
    assert (record["subject"], record["value"], record["outcome"]) == ("윤하람", "도도", "no")
    assert tease["usage"]["confirm"]["calls"] == 1 and tease["usage"]["calls"] == 2
    assert {"윤하람", "하람"} in names(entities) and not any("도도" in n and "하람" in n for n in names(entities))
    assert "an alias held, not confirmed: no (not linked)" in page and "윤하람 = 도도" in page


def test_a_confirmed_alias_is_served_and_not_listed(migrated):
    asked, entities, page, rows, failed = run(migrated, "extract-v16", "yes")
    assert all(r["status"] == "valid" for r in rows) and failed == 0
    assert "an alias held" not in page


def test_extract_v15_never_asks(migrated):
    asked, _, page, rows, failed = run(migrated, None, "no")
    assert asked == [] and failed == 0 and "an alias held" not in page
    assert all("alias_confirmations" not in r["raw"] for r in rows)
