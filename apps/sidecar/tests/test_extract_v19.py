"""extract-v19 (PHASE-60 S7, S8, ADR 0086): the `told` per-compiler extension, prompt, generation key and settings.

Synthetic names only (세라, 카이토, 하나, 유나).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from nmos_sidecar import entities, extraction as X, generations, predicates as P, secrets as S
from nmos_sidecar.config import Settings
from nmos_sidecar.facts import served_assertions
from conftest import active_generation, make_client
from test_extract_v18 import FEELING, USED, WARM, chat_of, feels
from test_extraction import drain
from test_generations import LLM, conv_id
from test_secrets import NEWEST_FIRST
from test_phase60_pins import BASE, PINNED_EXTRACT_SPEC_FIELDS
from test_sidecar_integration import sync

REGISTRY_PROMPT_SHA256 = "9cd57478151107025e53b7f29a38f5d7154ee57c66a5a92b8b3cfeb2e894084b"
REGISTRY_PROMPT_ONLY_SHA256 = "4eac87e6574ab18970f8c236a774a47c8eb9749c2699ef1a7f210c76a3d72c63"


def _told_item(**extra):
    return {
        "subject": "세라",
        "subject_type": "character",
        "predicate": "told",
        "object": "카이토",
        "object_type": "character",
        "value": "하나가 열쇠를 숨겼다는 사실",
        "with": [{"name": "하나", "type": "character"}],
        **extra,
    }


def test_told_extension_keeps_registry_and_default_prompt_unchanged():
    assert "told" not in P.REGISTRY
    assert P.EXTENSIONS == {"extract-v19": {"told": P.TOLD}}
    assert P.EXTENSION_PARTICIPANTS == {"extract-v19": frozenset({"told"})}
    assert P.registry_for(None) is P.REGISTRY
    assert P.registry_for("extract-v18") is P.REGISTRY
    assert "told" in P.registry_for("extract-v19")

    assert hashlib.sha256(P.registry_prompt().encode()).hexdigest() == REGISTRY_PROMPT_SHA256
    assert (
        hashlib.sha256(P.registry_prompt(frozenset({"has_trait", "identity"})).encode()).hexdigest()
        == REGISTRY_PROMPT_ONLY_SHA256
    )
    assert P.registry_prompt(compiler="extract-v18") == P.registry_prompt()
    assert (
        P.registry_prompt(compiler="extract-v19")
        == P.registry_prompt() + "\n- told (subject: character, object: character, value: text) — " + P.TOLD.description
    )


def test_validate_and_participants_accept_told_only_with_extension():
    item = _told_item()
    assert P.validate(item) == ("pending", "unknown predicate")
    assert P.validate(item, registry=P.registry_for("extract-v19")) == ("valid", None)
    assert P.participants(item) is None
    assert P.participants(item, also=frozenset({"told"})) == [{"name": "하나", "type": "character"}]


def test_v19_prompt_extends_v18_and_joins_only_v18_compiler_sets():
    assert X.DEFAULT_COMPILER == "extract-v16" and "extract-v19" in X.COMPILERS
    assert X.HAPPENED == {"extract-v19"}
    assert X.HAPPENED_MAX == 80 and X.CLOCK_MAX == 80
    assert X.CLOCK_LINE == "STORY CLOCK at the TARGET turn (the chat's status window): {clock}"
    v18, v19 = X.prompt_of("extract-v18"), X.prompt_of("extract-v19")
    assert X.HAPPENED_RULE not in v18 and X.TOLD_RULE not in v18 and '"when_happened"' not in v18
    assert v19 == X._v19(v18) and X.HAPPENED_RULE in v19 and X.TOLD_RULE in v19
    assert '"when_happened": "... or null (event and promised only)",' in v19
    assert v19.replace(X.HAPPENED_RULE + X.TOLD_RULE, "").replace(X._HAPPENED_ANSWER, X._FEELING_ANSWER) == v18
    assert X.FEELING_RULE + X.HAPPENED_RULE + X.TOLD_RULE + X._BECAUSE_AT in v19
    assert X.prompt_of("extract-v19", roles=False) == X.SYSTEM_V19 and X.ROLE_ENDINGS not in X.SYSTEM_V19
    assert X.SYSTEM_V19 == X._v19(X.SYSTEM_V18) and X.PROMPTS["extract-v19"] == X.SYSTEM_V19_ROLES
    assert v19.format(registry=P.registry_prompt(compiler="extract-v19"))
    assert "extract-v19" in X.ROLES & X.PARTS_APART & X.CONFIRMS & X.FEELINGS & entities.PART_EDGES
    assert "extract-v19" not in X.HORIZONS | X.SPEAKERS


def test_v19_key_keeps_v18_fields_and_differs_only_in_compiler_and_prompt():
    v18 = X.extractor(Settings(**BASE, extract_compiler="extract-v18"))
    v19 = X.extractor(Settings(**BASE, extract_compiler="extract-v19"))
    assert sorted(v19.spec) == PINNED_EXTRACT_SPEC_FIELDS["extract-v18"]
    assert {k for k in v18.spec if v18.spec[k] != v19.spec[k]} == {"compiler", "prompt"}
    assert v19.key != v18.key
    assert v19.spec["prompt"] != generations.fingerprint(X.prompt_of("extract-v19"))  # the extension is in it
    assert v18.spec["prompt"] == generations.fingerprint(X.prompt_of("extract-v18"))


def test_the_told_definition_is_in_the_v19_key_only(monkeypatch):
    settings = {c: Settings(**BASE, extract_compiler=c) for c in ("extract-v18", "extract-v19")}
    before = {c: X.extractor(s).key for c, s in settings.items()}
    reworded = dataclasses.replace(P.TOLD, description="the subject passed something on to the object")
    monkeypatch.setitem(P.EXTENSIONS, "extract-v19", {"told": reworded})
    after = {c: X.extractor(s).key for c, s in settings.items()}
    assert after["extract-v18"] == before["extract-v18"] and after["extract-v19"] != before["extract-v19"]
    monkeypatch.setitem(P.EXTENSIONS, "extract-v19", {"told": P.TOLD})
    monkeypatch.setitem(P.EXTENSION_PARTICIPANTS, "extract-v19", frozenset())
    assert X.extractor(settings["extract-v19"]).key != before["extract-v19"]


TOLD_LINE = "- told (subject: character"
ALLOWED = "Allowed predicates (anything else is rejected):"  # in every extraction system prompt


def extraction_systems(url: str, compiler: str) -> list[str]:
    """The extraction system prompts the worker sends for a short chat under `compiler` (a stub model, no call)."""
    systems: list[str] = []

    def complete(system, user):
        systems.append(system)
        return {"assertions": []}, "{}", USED

    with make_client(url, **LLM, extract_compiler=compiler) as c:
        sync(c, chat_of("세라는 카이토에게 하나가 열쇠를 숨겼다는 사실을 조용히 털어놓았다."))
        drain(url, complete)
    found = [s for s in systems if ALLOWED in s]
    assert found, "no extraction call was recorded"
    return found


def test_the_worker_formats_the_v19_registry_and_rules(migrated):
    for system in extraction_systems(migrated, "extract-v19"):
        assert TOLD_LINE in system and X.HAPPENED_RULE in system and X.TOLD_RULE in system
        assert system.count(P.TOLD.description) == 1


def test_the_worker_formats_v18_as_before(migrated):
    for system in extraction_systems(migrated, "extract-v18"):
        assert TOLD_LINE not in system and X.HAPPENED_RULE not in system and X.TOLD_RULE not in system
        assert P.registry_prompt() in system


@pytest.mark.parametrize("roles", [True, False])
def test_a7_v19_grows_the_prompt_by_at_most_15_percent(roles):
    v18, v19 = X.prompt_of("extract-v18", roles), X.prompt_of("extract-v19", roles)
    assert len(v19) <= 1.15 * len(v18)
    formatted18 = v18.format(registry=P.registry_prompt())
    formatted19 = v19.format(registry=P.registry_prompt(compiler="extract-v19"))
    assert len(formatted19) <= 1.15 * len(formatted18)


def test_when_happened_reads_a_trimmed_phrase_on_event_and_promised_only():
    def one(value, predicate="event", limit=80):
        return P.when_happened({"predicate": predicate, "when_happened": value}, limit)

    assert one("3년 전 겨울") == "3년 전 겨울" and one("  그날 밤 ") == "그날 밤"
    assert one("다음 보름날", "promised") == "다음 보름날"
    for predicate in ("knows", "feels_toward", "goal", "told", None):
        assert one("3년 전 겨울", predicate) is None
    for value in (None, "", "   ", "null", "NULL", " None ", "-", 3, 2.5, {"when": "어제"}, ["어제"]):
        assert one(value) is None
    cut = "가" * 79 + " " + "나" * 40  # a space at index 79: cut to 80, then stripped again
    assert one(cut) == "가" * 79
    assert one("가" * 120) == "가" * 80
    assert one("  어 제", limit=2) == "어"  # stripped, cut to "어 ", stripped again
    assert P.when_happened({"predicate": "event"}, 80) is None


TOLD_QUOTE = "유나가 왕녀라는 사실을 조용히 털어놓았다"
EVENT_QUOTE = "3년 전 겨울, 유나는 성을 떠났다"
SCENE = f"세라는 카이토에게 {TOLD_QUOTE}. 하나는 그 자리에 없었다. {EVENT_QUOTE}. {WARM}"
MARKS = {"knowledge": "limited", "known_by": ["세라", "카이토"], "hidden_from": ["하나"]}
ACTUAL = {"polarity": "positive", "modality": "actual", "source": "narration"}


def told_row(**extra):
    """세라 told 카이토 a secret about 유나, kept from 하나, with its quote."""
    return {"subject": "세라", "subject_type": "character", "predicate": "told", "object": "카이토",
            "object_type": "character", "value": "유나가 왕녀라는 사실", "with": [{"name": "유나", "type": "character"}],
            **MARKS, **ACTUAL, "evidence": TOLD_QUOTE, **extra}


def event_row(**extra):
    return {"subject": "유나", "subject_type": "character", "predicate": "event", "value": "성을 떠났다",
            "when_happened": "3년 전 겨울", **ACTUAL, "evidence": EVENT_QUOTE, **extra}


def happened_of(item, compiler="extract-v19"):
    [row] = X.normalize([item], SCENE, compiler=compiler)
    return row["when_happened"]


def test_a6_when_happened_is_kept_on_event_and_promised_under_v19_only():
    promised = {"subject": "세라", "subject_type": "character", "predicate": "promised", "object": "카이토",
                "object_type": "character", "value": "다시 돌아오겠다", "when_happened": "다음 보름날", **ACTUAL}
    assert happened_of(event_row()) == "3년 전 겨울" and happened_of(promised) == "다음 보름날"
    [row] = X.normalize([event_row()], SCENE, compiler="extract-v19")
    assert row["status"] == "valid" and list(row)[list(row).index("feeling") + 1] == "when_happened"
    others = [{"subject": "하나", "subject_type": "character", "predicate": "knows", "value": "유나의 비밀"},
              {**feels("고마움", None, ""), "when_happened": "3년 전 겨울"},
              {"subject": "하나", "subject_type": "character", "predicate": "goal", "value": "성으로 돌아가기"}]
    for item in others:
        assert happened_of({**item, "when_happened": "3년 전 겨울", **ACTUAL}) is None
    for compiler in ("extract-v18", "extract-v16", None):
        assert happened_of(event_row(), compiler) is None and happened_of(promised, compiler) is None
        assert "when_happened" in X.normalize([event_row()], SCENE, compiler=compiler)[0]
    for value in ("null", "", "  ", 3, {"when": "어제"}):
        assert happened_of(event_row(when_happened=value)) is None
    assert happened_of(event_row(when_happened="가" * 79 + " " + "나" * 40)) == "가" * 79
    assert happened_of(event_row(when_happened="가" * 120)) == "가" * 80
    assert happened_of(event_row(when_happened="  어젯밤  ")) == "어젯밤"


def test_told_is_valid_under_v19_only_and_keeps_its_marks():
    def one(item, compiler="extract-v19", shown=None):
        [row] = X.normalize([item], SCENE, shown=shown, compiler=compiler)
        return row

    row = one(told_row())
    assert (row["status"], row["reason"]) == ("valid", None)
    assert row["participants"] == [{"name": "유나", "type": "character"}]
    assert (row["knowledge"], row["known_by"], row["hidden_from"]) == ("limited", ["세라", "카이토"], ["하나"])
    assert row["evidence"] == TOLD_QUOTE and row["when_happened"] is None
    for compiler in ("extract-v18", None):
        row = one(told_row(), compiler)
        assert (row["status"], row["reason"]) == ("pending", "unknown predicate") and row["participants"] is None
        assert (row["knowledge"], row["known_by"], row["hidden_from"]) == ("limited", ["세라", "카이토"], ["하나"])
    for missing in ({"evidence": ""}, {"evidence": None}, {"evidence": "null"}, {"evidence": "  "}):
        row = one(told_row(**missing))
        assert (row["status"], row["reason"]) == ("pending", "told without its quote")
    no_key = told_row()
    del no_key["evidence"]
    assert (one(no_key)["status"], one(no_key)["reason"]) == ("pending", "told without its quote")
    absent = told_row(evidence="카이토는 하나에게 바다 건너 왕국의 전설을 길게 들려주었다")
    assert (one(absent, shown=SCENE)["status"], one(absent, shown=SCENE)["reason"]) == ("pending", "evidence not in the turn")
    assert one(told_row(), shown=SCENE)["status"] == "valid"
    place = one(told_row(object="왕성", object_type="place"))
    assert place["status"] == "pending" and place["reason"].startswith("object_type must be")


def test_v19_keeps_the_feeling_as_v18_does():
    item = feels("고마움", FEELING, "고마운 마음이 가득했지만")
    v18 = X.normalize([item], WARM, feelings=True, compiler="extract-v18")
    v19 = X.normalize([item], WARM, feelings=True, compiler="extract-v19")
    assert v19[0]["feeling"] == FEELING and v19 == v18


def stub(predicate="told"):
    """The model: for SCENE, the told row (as `predicate`), the event with when_happened and a feeling."""
    def complete(system, user):
        target = user.split("TARGET turn", 1)[1] if "TARGET turn" in user else ""
        if SCENE in target:
            return {"assertions": [told_row(predicate=predicate), event_row(),
                                   feels("고마움", FEELING, "고마운 마음이 가득했지만")]}, "{}", USED
        return {"assertions": []}, "{}", USED
    return complete


def stored(url: str) -> dict[str, dict]:
    """The extraction rows stored, by predicate (one each in these chats)."""
    with psycopg.connect(url, row_factory=dict_row) as conn:
        assert conn.execute("SELECT count(*) AS n FROM job WHERE last_error IS NOT NULL").fetchone()["n"] == 0
        rows = conn.execute("SELECT predicate, status, reason, knowledge, known_by, hidden_from, participants,"
                            " when_happened, feeling FROM assertion").fetchall()
    assert len(rows) == len({r["predicate"] for r in rows})
    return {r["predicate"]: r for r in rows}


@pytest.mark.parametrize("compiler", ["extract-v19", "extract-v18"])
def test_the_worker_stores_told_and_when_happened_under_v19_only(migrated, compiler):
    with make_client(migrated, **LLM, extract_compiler=compiler) as c:
        sync(c, chat_of(SCENE))
        drain(migrated, stub())
    rows = stored(migrated)
    assert set(rows) == {"told", "event", "feels_toward"}
    told = rows["told"]
    assert (told["knowledge"], told["known_by"], told["hidden_from"]) == ("limited", ["세라", "카이토"], ["하나"])
    assert rows["feels_toward"]["feeling"] == FEELING
    if compiler == "extract-v19":
        assert (told["status"], told["reason"]) == ("valid", None)
        assert told["participants"] == [{"name": "유나", "type": "character"}]
        assert rows["event"]["when_happened"] == "3년 전 겨울"
        assert told["when_happened"] is None and rows["feels_toward"]["when_happened"] is None
    else:
        assert (told["status"], told["reason"]) == ("pending", "unknown predicate")
        assert all(r["when_happened"] is None for r in rows.values())


def test_a_told_row_is_never_a_stored_secret():
    """PHASE-60 S8 (owner decision 2026-11-23): a told row keeps its marks, but no reveal check tracks it."""
    [told] = X.normalize([told_row()], SCENE, compiler="extract-v19")
    [knows] = X.normalize([told_row(predicate="knows")], SCENE, compiler="extract-v19")
    assert told["status"] == knows["status"] == "valid" and told["hidden_from"] == knows["hidden_from"] == ["하나"]
    assert not S.is_secret(told) and S.is_secret(knows)


def reveal_checks(url: str, predicate: str) -> tuple[int, int, list[dict], list[dict]]:
    """The v19 chat plus two more turns, the stub writing the secret as `predicate`. A reveal check is queued only by
    "Extract all history" (`reveals.schedule`), and only for a later turn extracted before the secret's turn could be
    listed: so the later turns are extracted first, as a first connection before Phase 30 did (`first_import`).
    (reveal jobs the POST queued, reveal jobs in the table, the served rows, `secrets.fold`'s secrets)."""
    chat = chat_of(SCENE, "세라는 창밖을 오래 바라보며 말이 없었다.", "카이토는 식은 차를 천천히 마셨다.")
    with make_client(url, **LLM, extract_compiler="extract-v19") as c:
        sync(c, chat)
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(NEWEST_FIRST, (X.FIRST_PRIORITY,))  # as `test_secrets.first_import` (Tier 1 D5)
        drain(url, stub(predicate))
        conv = conv_id(c, chat)
        queued = c.post(f"/v1/conversations/{conv}/extract-history").json()["queued"]["reveal"]
        with psycopg.connect(url, row_factory=dict_row) as conn:
            assert conn.execute("SELECT count(*) AS n FROM job WHERE kind = 'extract' AND status <> 'done'"
                                ).fetchone()["n"] == 0
            jobs = conn.execute("SELECT count(*) AS n FROM job WHERE kind = 'reveal'").fetchone()["n"]
            head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (conv,)).fetchone()
            rows = served_assertions(conn, head["head_commit_id"], active_generation(conn, "extract").key)
    return queued, jobs, rows, S.fold(rows)[0]


def test_no_reveal_check_is_queued_for_a_told_secret(migrated):
    queued, jobs, rows, secrets = reveal_checks(migrated, "told")
    assert queued == jobs == 0
    [told] = [r for r in rows if r["predicate"] == "told"]
    assert told["hidden_from"] == ["하나"] and told["knowledge"] == "limited"
    assert [s for s in secrets if s["predicate"] == "told"] == []


def test_the_control_written_as_knows_queues_a_reveal_check(migrated):
    queued, jobs, rows, secrets = reveal_checks(migrated, "knows")
    assert queued >= 1 and jobs == queued
    [knows] = [r for r in rows if r["predicate"] == "knows"]
    assert [s["id"] for s in secrets if s["predicate"] == "knows"] == [knows["id"]]


def head_of(conn, chat) -> object:
    return conn.execute("SELECT head_commit_id FROM conversation WHERE host_chat_ref = %s",
                        (chat.id,)).fetchone()["head_commit_id"]


def observe(conn, head, position: int, key: str, value: str, rules: str = "rules-a") -> None:
    """A status-window observation stored on the head's revision at `position`, as the parser would store it."""
    inserted = conn.execute(
        "INSERT INTO state_observation (conversation_id, source_revision_id, rules_version, rule_id, key, value)"
        " SELECT so.conversation_id, am.source_revision_id, %s, 'clock', %s, %s FROM active_membership am"
        " JOIN source_revision sr ON sr.id = am.source_revision_id JOIN source_object so ON so.id = sr.source_object_id"
        " WHERE am.commit_id = %s AND am.position = %s",
        (rules, key, value, head, position))
    assert inserted.rowcount == 1, f"no membership at position {position}"


def at(head, position: int) -> dict:
    """The fields of an extraction context `story_clock` reads: the target's commit and its members' positions."""
    return {"target": {"commit_id": head}, "members": [{"position": position - 1}, {"position": position}]}


def test_story_clock_reads_the_latest_unambiguous_field_as_of_the_target(migrated):
    chat = chat_of("세라는 문을 열었다.", "카이토는 창가에 앉았다.", "하나는 차를 끓였다.")
    with make_client(migrated) as c:
        sync(c, chat)
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        head = head_of(conn, chat)
        assert X.story_clock(conn, at(head, 5)) is None  # no observation: no clock
        observe(conn, head, 1, "날짜", "4월 12일")
        observe(conn, head, 1, "시간", "오후 3시")
        observe(conn, head, 1, "기분", "맑음")  # not a clock key
        observe(conn, head, 5, "날짜", "4월 13일")
        assert X.story_clock(conn, at(head, 1)) == "날짜: 4월 12일; 시간: 오후 3시"
        assert X.story_clock(conn, at(head, 3)) == "날짜: 4월 12일; 시간: 오후 3시"
        # each field its own latest, but never one of a turn long before (Tier 1 G2: turn 2's date and turn 0's time
        # were one clock)
        assert X.story_clock(conn, at(head, 5)) == "날짜: 4월 13일"
        observe(conn, head, 5, "date", "April 13")  # two date keys at the latest position: ambiguous
        assert X.story_clock(conn, at(head, 5)) == "시간: 오후 3시"
        assert X.story_clock(conn, at(head, 3)) == "날짜: 4월 12일; 시간: 오후 3시"
        conn.execute("DELETE FROM state_observation WHERE key = 'date'")
        observe(conn, head, 3, " Time ", "가" * 81)  # too long: the field is left out, not an earlier one
        assert X.story_clock(conn, at(head, 3)) == "날짜: 4월 12일"
        conn.execute("UPDATE state_observation SET value = %s WHERE key = ' Time '", ("가" * 80,))
        assert X.story_clock(conn, at(head, 3)) == "날짜: 4월 12일;  Time : " + "가" * 80  # as stored
        conn.execute("UPDATE state_observation SET value = '   ' WHERE key = ' Time '")
        assert X.story_clock(conn, at(head, 3)) == "날짜: 4월 12일"
        conn.execute("DELETE FROM state_observation WHERE key = ' Time '")
        observe(conn, head, 3, "시각", "저녁", rules="rules-b")  # two rule sets: no clock
        assert X.story_clock(conn, at(head, 3)) is None
        assert X.story_clock(conn, at(head, 1)) == "날짜: 4월 12일; 시간: 오후 3시"  # rules-b is after turn 0
        conn.execute("DELETE FROM state_observation WHERE rules_version = 'rules-b'")
        assert X.story_clock(conn, at(head, 3)) == "날짜: 4월 12일; 시간: 오후 3시"
        assert X.story_clock(conn, at(uuid4(), 3)) is None  # another commit's membership
        conn.execute("DELETE FROM state_observation")
    chat.disable(3)  # turn 1's reply
    with make_client(migrated) as c:
        sync(c, chat)
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        head = head_of(conn, chat)
        observe(conn, head, 1, "날짜", "4월 12일")
        observe(conn, head, 3, "날짜", "4월 20일")  # on the disabled message: ignored
        assert X.story_clock(conn, at(head, 5)) == "날짜: 4월 12일"


def test_the_clock_line_goes_between_context_and_the_target_only_when_given():
    ctx = {"target": {"turn": 2},
           "context": [{"turn": 1, "metadata": {"name": "세라"}, "content": "세라는 문을 열었다."}],
           "members": [{"metadata": {"name": "카이토"}, "content": "카이토는 창가에 앉았다."}]}
    plain = X.build_prompt(ctx, compiler="extract-v19")
    assert X.build_prompt(ctx, compiler="extract-v19", clock=None) == plain and "STORY CLOCK" not in plain
    shown = X.build_prompt(ctx, compiler="extract-v19", clock="날짜: 4월 12일")
    line = X.CLOCK_LINE.format(clock="날짜: 4월 12일")
    head, tail = plain.split("\n\nTARGET turn 2:\n")
    assert shown == head + "\n\n" + line + "\n\nTARGET turn 2:\n" + tail
    empty = dict(ctx, context=[])
    assert X.build_prompt(empty, clock="시간: 밤") == "CONTEXT:\n(none)\n\n" + X.CLOCK_LINE.format(clock="시간: 밤") + (
        "\n\nTARGET turn 2:\n카이토: 카이토는 창가에 앉았다.")


CLOCKED = ("세라는 성문 앞에서 카이토를 기다렸다.",
           "카이토가 늦게 도착했다.\n☆ [날짜: 4월 12일 | 시간: 오후 3시]",
           "두 사람은 말없이 성벽을 따라 걸었다.",
           "다음 날 아침 하나가 성문을 두드렸다.\n☆ [날짜: 4월 13일 | 시간: 아침]")
CLOCK_12 = "날짜: 4월 12일; 시간: 오후 3시"
CLOCK_13 = "날짜: 4월 13일; 시간: 아침"


@pytest.fixture
def clock_rules(tmp_path):
    """A parser rules file whose status window (bound to the card 'Clock test') carries 날짜 and 시간."""
    path = tmp_path / "clock.json"
    path.write_text(json.dumps({"rules": [{"id": "clock", "card": "Clock test", "kind": "block", "role": "char",
                                           "start": r"☆ \[", "end": r"\]\s*$", "separator": "|"}]}))
    return str(path)


def recording(prompts: dict[int, str]):
    """A stub model that answers nothing and keeps each extraction call's user prompt by its TARGET turn."""
    def complete(system, user):
        if ALLOWED in system:
            found = re.search(r"^TARGET turn (\d+):$", user, re.M)
            assert found and int(found.group(1)) not in prompts
            prompts[int(found.group(1))] = user
        return {"assertions": []}, "{}", USED
    return complete


def extracted(url: str, chat) -> dict[int, dict]:
    """The chat's extraction rows by the turn they extract."""
    with psycopg.connect(url, row_factory=dict_row) as conn:
        assert conn.execute("SELECT count(*) AS n FROM job WHERE last_error IS NOT NULL").fetchone()["n"] == 0
        rows = conn.execute(
            "SELECT am.turn, e.source_revision_id, e.window_hash, e.extractor_key, e.compiler_version, e.story_clock"
            " FROM extraction e JOIN active_membership am ON am.source_revision_id = e.source_revision_id"
            " AND am.commit_id = (SELECT head_commit_id FROM conversation WHERE host_chat_ref = %s)", (chat.id,)
        ).fetchall()
    assert len(rows) == len({r["turn"] for r in rows})
    return {r["turn"]: r for r in rows}


def clock_shown(prompt: str) -> str | None:
    lines = [line for line in prompt.splitlines() if line.startswith("STORY CLOCK")]
    assert len(lines) <= 1
    return lines[0].removeprefix(X.CLOCK_LINE.format(clock="")) if lines else None


def test_without_a_tracked_clock_the_v19_prompt_is_v18s(migrated):
    prompts: dict[str, dict[int, str]] = {}
    chats = {}
    for compiler in ("extract-v19", "extract-v18"):
        prompts[compiler], chats[compiler] = {}, chat_of(*CLOCKED[::2], "카이토는 성벽 위에서 별을 세었다.")
        with make_client(migrated, **LLM, extract_compiler=compiler) as c:
            sync(c, chats[compiler], character_name="Clock test")
            drain(migrated, recording(prompts[compiler]))
    v19, v18 = prompts["extract-v19"], prompts["extract-v18"]
    assert len(v19) >= 3 and set(v19) == set(v18)
    for turn, prompt in v19.items():
        assert "STORY CLOCK" not in prompt and prompt == v18[turn]
    rows = extracted(migrated, chats["extract-v19"])
    assert set(v19) <= set(rows) and all(r["story_clock"] is None for r in rows.values())
    assert {r["compiler_version"] for r in rows.values()} == {"extract-v19"}


@pytest.mark.parametrize("compiler", ["extract-v19", "extract-v18"])
def test_the_clock_as_of_each_target_turn_is_shown_and_recorded(migrated, clock_rules, compiler):
    prompts: dict[int, str] = {}
    chat = chat_of(*CLOCKED)
    with make_client(migrated, **LLM, extract_compiler=compiler, parsers_file=clock_rules) as c:
        sync(c, chat, character_name="Clock test")  # the head already holds the 13th when turn 2 is extracted
        drain(migrated, recording(prompts))
    rows = extracted(migrated, chat)
    assert {0, 1, 2, 3} <= set(prompts) <= set(rows)
    if compiler != "extract-v19":
        assert all(clock_shown(p) is None for p in prompts.values())
        assert all(r["story_clock"] is None for r in rows.values())
        return
    assert {t: clock_shown(prompts[t]) for t in (0, 1, 2, 3)} == {0: None, 1: CLOCK_12, 2: CLOCK_12, 3: CLOCK_13}
    for turn, row in rows.items():
        assert row["story_clock"] == (clock_shown(prompts[turn]) if turn in prompts else None)
    line = X.CLOCK_LINE.format(clock=CLOCK_12)
    assert "\n\n" + line + "\n\nTARGET turn 2:\n" in prompts[2]


def test_the_clock_is_not_part_of_validity(migrated, clock_rules):
    chat = chat_of(*CLOCKED)
    with make_client(migrated, **LLM, extract_compiler="extract-v19", parsers_file=clock_rules) as c:
        sync(c, chat, character_name="Clock test")
        drain(migrated, recording({}))
        row = extracted(migrated, chat)[2]
        assert row["story_clock"] == CLOCK_12
        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            head = head_of(conn, chat)
            [rules] = [r["rules_version"] for r in
                       conn.execute("SELECT DISTINCT rules_version FROM state_observation").fetchall()]
            queued = "SELECT count(*) AS n FROM job WHERE kind = 'extract' AND status = 'queued'"
            before = conn.execute(queued).fetchone()["n"]
            position = conn.execute("SELECT max(position) AS p FROM active_membership WHERE commit_id = %s AND turn = 2",
                                    (head,)).fetchone()["p"]
            observe(conn, head, position, "날짜", "4월 30일", rules=rules)  # turn 2's clock source changes
            ctx = X.load_context(conn, row["source_revision_id"], row["window_hash"], 3, row["extractor_key"])
            assert X.story_clock(conn, ctx) == "날짜: 4월 30일; 시간: 오후 3시" != row["story_clock"]
            assert ctx["done"]
        sync(c, chat, character_name="Clock test")
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            assert conn.execute(queued).fetchone()["n"] == before
    assert extracted(migrated, chat)[2]["story_clock"] == CLOCK_12


def test_settings_accept_v19_and_refuse_a_later_name():
    assert Settings(database_url="", extract_compiler="extract-v19").extract_compiler == "extract-v19"
    with pytest.raises(ValueError, match="extract-v19"):
        Settings(database_url="", extract_compiler="extract-v20")
