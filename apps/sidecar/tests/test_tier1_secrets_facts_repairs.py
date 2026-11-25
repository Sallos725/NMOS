"""Tier 1 wave 1: secrets, facts folding, threads, dropped facts, owner repairs and the scene cast.

Each test pins one bug the Tier 1 review found (C1, C3–C5, C7, A3, A7, D6, D7, F2) and the behavior that must not move
with its fix. Synthetic names only.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from nmos_sidecar import dropped, repairs, scene, variants
from nmos_sidecar.entities import resolve
from nmos_sidecar.facts import memory_view, symmetric
from nmos_sidecar.secrets import _split, fold as fold_secrets, matches, secret_text
from nmos_sidecar.threads import fold as fold_threads
from test_semantics import row

C = {"subject_type": "character"}


def kept(pos: int, subject: str, predicate: str, obj: str | None = None, value: str | None = None, *,
         hidden=("노엘",), holders=None, **kw) -> dict:
    """A fact kept from someone: a secret."""
    return row(pos, subject, predicate, obj, value, **C, knowledge="limited",
               known_by=list(holders or (subject,)), hidden_from=list(hidden), **kw)


def learned(pos: int, text: str, who: str = "노엘", **kw) -> dict:
    return row(pos, who, "learned", None, text, **C, **kw)


def secrets_of(rows: list[dict]) -> tuple[dict[str, list[str]], list[dict]]:
    """({secret text: who it is still kept from}, unmatched reveals)."""
    got, unmatched, _ = fold_secrets(rows, resolve(uuid.uuid4(), rows))
    return {s["text"]: s["open"] for s in got}, unmatched


# --- secrets (C1, C5) --------------------------------------------------------------------------------------------------

def test_a_line_without_a_value_splits_its_object_off_as_the_content():
    poison = kept(5, "김하나", "possesses", "독약", object_type="item")
    assert secret_text(poison) == "김하나 possesses 독약"  # the listed and stored format is unchanged
    assert _split("김하나 possesses 독약") == (None, "김하나 possesses", "독약")
    assert _split("[turn 5] 김하나 member of 그림자 길드") == (5, "김하나 member of", "그림자 길드")
    assert _split("[turn 2] 하나 located in 옛 등대") == (2, "하나 located in", "옛 등대")
    assert _split("하나 relationship 카이토: 연인") == (None, "하나 relationship 카이토", "연인")  # with a value: as before
    assert _split("엄마 몰래 수업 보기") == (None, None, "엄마 몰래 수업 보기")  # content alone: as before
    assert _split("[turn -1] 세라 knows: 열쇠") == (-1, "세라 knows", "열쇠")  # a carried secret's turn


def test_revealing_one_belonging_never_reveals_the_others():
    """C1: "김하나 possesses 금고열쇠" and "김하나 possesses 독약" shared 82 % of their text, so one reveal ended both."""
    assert not matches("김하나 possesses 독약", "[turn 3] 김하나 possesses 금고열쇠")
    rows = [kept(3, "김하나", "possesses", "금고열쇠", object_type="item"),
            kept(5, "김하나", "possesses", "독약", object_type="item"),
            kept(5, "김하나", "member_of", "그림자 길드", object_type="group"),
            learned(9, "[turn 3] 김하나 possesses 금고열쇠")]
    got, unmatched = secrets_of(rows)
    assert got == {"김하나 possesses 금고열쇠": [], "김하나 possesses 독약": ["노엘"],
                   "김하나 member of 그림자 길드": ["노엘"]} and unmatched == []


def test_two_belongings_of_one_turn_are_told_apart_by_rule_1():
    rows = [kept(5, "김하나", "possesses", "금고열쇠", object_type="item"),
            kept(5, "김하나", "possesses", "독약", object_type="item"),
            learned(9, "[turn 5] 김하나 possesses 독약")]
    assert secrets_of(rows)[0] == {"김하나 possesses 금고열쇠": ["노엘"], "김하나 possesses 독약": []}


def test_a_belonging_the_reextraction_dropped_ends_no_other_one():
    """Rule 1 floor for a head without a value: the content is an item, so 0.0 is another item, not a rewording."""
    poison = kept(5, "김하나", "possesses", "독약", object_type="item")
    got, unmatched = secrets_of([poison, learned(9, "[turn 5] 김하나 possesses 금고열쇠")])
    assert got == {"김하나 possesses 독약": ["노엘"]} and [u["turn"] for u in unmatched] == [9]
    # the same item worded a little otherwise by a re-extraction is still that item
    got, unmatched = secrets_of([poison, learned(9, "[turn 5] 김하나 possesses 독약병")])
    assert got == {"김하나 possesses 독약": []} and unmatched == []


def test_a_dropped_secret_of_a_turn_with_two_others_ends_neither():
    """C5: with no floor, a reveal sharing nothing with the turn's secrets tied them all at 0.0 and ended every one."""
    rows = [kept(7, "루카", "goal", None, "쿠키를 서랍에 숨기기"), kept(7, "루카", "goal", None, "다이아몬드 훔치기"),
            learned(21, "[turn 7] 루카 goal: 엄마 몰래 강의실 뒤에서 수업을 보기")]
    got, unmatched = secrets_of(rows)
    assert got == {"루카 goal: 쿠키를 서랍에 숨기기": ["노엘"], "루카 goal: 다이아몬드 훔치기": ["노엘"]}
    assert [u["turn"] for u in unmatched] == [21]
    # ADR 0033: the one secret of the turn with that head still ends, however it is worded now
    got, _ = secrets_of([kept(7, "루카", "goal", None, "노엘 모르게 강의 듣기"),
                         learned(21, "[turn 7] 루카 goal: 엄마 몰래 강의실 뒤에서 수업을 보기")])
    assert got == {"루카 goal: 노엘 모르게 강의 듣기": []}


def test_two_characters_whose_names_differ_by_a_syllable_have_different_heads():
    """C5: "김서연 feels toward 박도윤" and "김서윤 feels toward 박도윤" were 0.86 alike, above HEAD_MIN."""
    rows = [kept(3, "김서연", "feels_toward", "박도윤", "몰래 좋아함", object_type="character"),
            kept(4, "김서윤", "feels_toward", "박도윤", "몰래 미워함", object_type="character"),
            learned(9, "김서윤 feels toward 박도윤: 몰래 좋아함")]
    got, _ = secrets_of(rows)
    assert got["김서연 feels toward 박도윤: 몰래 좋아함"] == ["노엘"]
    # the subject spelled with a space, or an object one entity with its alias, is still the same head
    assert matches("김서연 feels toward 박도윤: 몰래 좋아함", "김 서연 feels toward 박도윤: 몰래 좋아함")
    alias = [row(1, "박도윤", "also_called", None, "도윤", **C)]
    r = resolve(uuid.uuid4(), alias)
    assert matches("김서연 feels toward 박도윤: 몰래 좋아함", "김서연 feels toward 도윤: 몰래 좋아함", r)
    assert not matches("김서연 feels toward 박도윤: 몰래 좋아함", "김서연 feels toward 도윤: 몰래 좋아함")


# --- facts: symmetric relationships (A3) -------------------------------------------------------------------------------

def test_a_korean_adjective_ending_in_jeok_is_not_an_enemy():
    for one_way in ("일방적 관계", "적대적 관계", "계약적", "복종적 사이", "의존적", "보호적"):
        assert not symmetric(one_way), one_way
    for enemy in ("적", "숙적", "오랜 적", "적 관계", "친구", "연인 사이"):
        assert symmetric(enemy), enemy


def test_an_english_possessive_or_a_one_way_modifier_is_not_symmetric():
    for one_way in ("friend's brother", "partner’s boss", "ex-partner", "former friends", "fake friend",
                    "unrequited lover", "one-sided rival", "friend of her brother"):
        assert not symmetric(one_way), one_way
    for both in ("friends", "close friend", "rivals", "married couple", "childhood friends (since school)"):
        assert symmetric(both), both


# --- threads (C3, C7) --------------------------------------------------------------------------------------------------

def threads(rows: list[dict]) -> tuple[list[dict], list[dict], set[int]]:
    return fold_threads(rows, resolve(uuid.uuid4(), rows))


def test_a_short_aim_said_again_word_for_word_is_one_thread_its_end_closes():
    """C3: below RESTATE_MIN_CHARS a goal was never a restatement: two open "복수" threads, and every resolution tied."""
    rows = [row(1, "하나", "goal", None, "복수", **C), row(2, "하나", "goal", None, "복수", **C),
            row(3, "하나", "resolved", None, "복수", **C, outcome="achieved")]
    (t,), unmatched, _ = threads(rows)
    assert (t["status"], [x["turn"] for x in t["restated"]], unmatched) == ("achieved", [2], [])
    # a different short aim is its own thread
    got, _, _ = threads([row(1, "하나", "goal", None, "복수", **C), row(2, "하나", "goal", None, "탈출", **C)])
    assert sorted(t["text"] for t in got) == ["복수", "탈출"]


def promise(**kw) -> dict:
    return row(1, "세라", "promised", "카이토", "등대 앞에서 만나기", **C, object_type="character", **kw)


def said(pos: int, subject: str, predicate: str, value: str, by: str, **kw) -> dict:
    return row(pos, subject, predicate, None, value, **C, source="character_claim", asserted_by=by, **kw)


def test_the_counterpart_closes_a_thread_in_dialogue():
    """C7: `fulfilled` and `resolved` take no object, so the counterpart's own words named nobody and closed nothing."""
    (t,), _, used = threads([promise(), said(5, "세라", "fulfilled", "등대 앞에서 만나기", "카이토")])
    assert t["status"] == "kept" and 5 in used
    debt = row(1, "카일", "owes", "상인", "금화 열 닢", **C, object_type="character")
    (t,), _, _ = threads([debt, said(4, "카일", "resolved", "금화 열 닢", "상인", outcome="paid")])
    assert t["status"] == "paid"
    question = row(1, "루카", "question", None, "범인은 누구인가", **C)
    (t,), _, _ = threads([question, said(4, "루카", "resolved", "범인은 누구인가", "노엘", outcome="answered")])
    assert t["status"] == "answered"


def test_someone_elses_report_still_closes_nothing_and_stays_a_claim():
    for closing in (said(5, "세라", "fulfilled", "등대 앞에서 만나기", "유나"),
                    said(5, "세라", "promised", "등대 앞에서 만나기", "유나", polarity="negative")):
        (t,), unmatched, used = threads([promise(), closing])
        assert (t["status"], unmatched, 5 in used) == ("open", [], False)
    goal = row(1, "하나", "goal", None, "등대지기를 찾기", **C)
    (t,), _, used = threads([goal, said(4, "하나", "resolved", "등대지기를 찾기", "유나", outcome="achieved")])
    assert t["status"] == "open" and 4 not in used
    question = row(1, "루카", "question", None, "범인은 누구인가", **C)  # only an answer closes a question by another
    (t,), _, used = threads([question, said(4, "루카", "resolved", "범인은 누구인가", "노엘", outcome="abandoned")])
    assert t["status"] == "open" and 4 not in used
    # a claim by the counterpart that matches no thread is a claim, as before (no unmatched resolution)
    _, unmatched, used = threads([promise(), said(5, "세라", "fulfilled", "편지를 태우기", "카이토")])
    assert unmatched == [] and 5 not in used


def test_a_close_keeps_the_closing_rows_knowledge_marks():
    broken = row(6, "세라", "promised", "카이토", "등대 앞에서 만나기", **C, object_type="character", polarity="negative",
                 knowledge="limited", known_by=["세라", "유나"], hidden_from=["카이토"])
    (t,), _, _ = threads([promise(), broken])
    assert t["status"] == "broken"
    assert {k: t["closed_by"][k] for k in ("knowledge", "known_by", "hidden_from")} == {
        "knowledge": "limited", "known_by": ["세라", "유나"], "hidden_from": ["카이토"]}


# --- the scene cast (D6) -----------------------------------------------------------------------------------------------

def test_an_entity_marked_not_a_character_is_never_in_the_cast():
    rows = [row(9, "시스템", "has_status", None, "작동 중", **C), row(9, "노엘", "event", None, "출근", **C)]
    r = resolve(uuid.uuid4(), rows)
    system = str(r.entity("character", "시스템")["id"])
    assert "시스템" in scene.cast(rows, r).values()  # without `excluded`: as before
    got = scene.cast(rows, r, "시스템 메시지가 떴다.", excluded={system})
    assert "시스템" not in got.values() and "노엘" in got.values()
    secret = {"knowledge": "limited", "known_by": ["노엘", "{{user}}"]}
    assert scene.private(secret, scene.cast(rows, r), r) and not scene.private(secret, got, r)


def test_a_latin_name_is_said_only_as_a_whole_word():
    rows = [row(1, "Ren", "goal", None, "find the key", **C)]
    r = resolve(uuid.uuid4(), rows)
    assert "Ren" not in scene.cast(rows, r, "That's different from the current plan.", now=10).values()
    assert "Ren" in scene.cast(rows, r, "Ren, come here.", now=10).values()
    assert "Ren" in scene.cast(rows, r, "", "Where is REN?", now=10).values()
    # a name only in knowledge marks, too
    marks = [kept(1, "노엘", "knows", None, "편지는 위조", hidden=("Ren",))]
    r = resolve(uuid.uuid4(), marks)
    assert "Ren" not in scene.cast(marks, r, "Apparently it's different.", now=10).values()
    assert "Ren" in scene.cast(marks, r, "Ren walks in.", now=10).values()
    # Korean names still match with a particle joined
    assert "노엘" in scene.cast(marks, r, "노엘이 왔다.", now=10).values()


def test_a_mark_spelling_a_characters_given_name_is_that_character():
    """D6: "이안" in a mark beside the entity "백이안" made two cast members: holders="백이안" not_known_by="이안"."""
    rows = [kept(9, "카이토", "knows", None, "편지는 위조", hidden=("이안",), holders=("카이토", "백이안")),
            row(1, "백이안", "located_in", None, "시장", **C)]
    r = resolve(uuid.uuid4(), rows)
    query = "이안이 왔어."
    al = variants.aliases(r.entities(), r.persona_names, query)
    assert al == {"백이안": frozenset({"이안"})}
    got = scene.cast(rows, r, query, now=10, aliases=al)
    assert sorted(got.values()) == ["{{user}}", "백이안", "카이토"] and "text:이안" not in got


# --- owner repairs (D7, F2) --------------------------------------------------------------------------------------------

def test_an_exclusion_never_hides_the_persona():
    rows = [row(1, "타쿠미", "located_in", None, "집", **C), row(2, "타쿠미", "also_called", None, "선배", **C)]
    r = resolve(uuid.uuid4(), rows, persona=["타쿠미"])
    for name in ("타쿠미", "선배"):  # the persona itself, or a name the story later joins to it
        rep = {"id": "x", "kind": "entity_exclude", "target": {"entity_type": "character", "name": name, "scope": "memory"}}
        assert repairs.exclusions([rep], r) == {}
    rep = {"id": "y", "kind": "entity_exclude", "target": {"entity_type": "character", "name": "시스템", "scope": "cast"}}
    other = rows + [row(3, "시스템", "has_status", None, "작동 중", **C)]
    assert list(repairs.exclusions([rep], resolve(uuid.uuid4(), other, persona=["타쿠미"]))) != []


def before_story(kind: str, value: str, **kw) -> dict:
    return row(-1, "세라", "located_in", None, value, **C, turn=-1, **kw) | {"position": -100 if kind == "canon" else -50}


def test_a_carried_fact_can_be_named_by_a_repair_and_never_crosses_with_canon():
    """F2: a carried fact has turn -1 as canon does, so a repair of it looked for canon and found nothing."""
    canon = before_story("canon", "등대", canon="card", turn_hash="canon:card")
    carried = before_story("carried", "항구", carried="link-1", turn_hash="carried:link-1", id=-7)
    rows = [canon, carried]
    r = resolve(uuid.uuid4(), rows)
    assert repairs.fact_target(carried)["carried"] == "link-1" and "canon" not in repairs.fact_target(carried)
    assert repairs.fact_target(canon)["canon"] == "card" and "carried" not in repairs.fact_target(canon)
    assert repairs.match_fact(repairs.fact_target(carried), rows, r) is carried
    assert repairs.match_fact(repairs.fact_target(canon), rows, r) is canon
    legacy = {k: v for k, v in repairs.fact_target(canon).items() if k not in ("canon", "turn_hash")}
    assert repairs.match_fact(legacy, rows, r) is canon  # a lock stored before: turn -1 alone is canon's
    # by its hash alone, too (a target stored without the flag)
    hashed = {k: v for k, v in repairs.fact_target(carried).items() if k != "carried"}
    assert repairs.match_fact(hashed, rows, r) is carried
    applied: dict = {}
    out, gone = repairs.apply_facts(rows, [{"id": "r1", "kind": "fact_retract", "target": repairs.fact_target(carried),
                                            "value": {}, "note": None}], r, applied)
    assert out == [canon] and gone["r1"] is carried and applied == {"r1": "-7"}


def test_a_denial_does_not_restate_the_fact_it_denies():
    role = row(3, "하나", "role_toward", "카이토", "호위", **C, object_type="character")
    denied = {**role, "id": 30, "polarity": "negative"}
    assert repairs.restated([denied], [role], None) == {}
    assert repairs.restated([role], [denied], None) == {}
    assert set(repairs.restated([role], [{**role, "id": 31}], None)) == {0}


def test_two_different_events_of_one_character_do_not_restate_each_other():
    murder = row(3, "카일", "event", None, "왕을 암살함", **C)
    left = row(3, "카일", "event", None, "성을 떠남", **C, id=31)
    assert repairs.restated([murder], [left], None) == {}
    assert set(repairs.restated([murder], [{**left, "value": "왕을 몰래 암살함"}], None)) == {0}  # similar: level 2


# --- dropped facts (D7) ------------------------------------------------------------------------------------------------

OLD, NEW = uuid.uuid4(), uuid.uuid4()


def stored(i: int, extraction: uuid.UUID, subject: str, predicate: str, obj: str | None = None, value: str | None = None,
           **kw) -> dict:
    """An assertion as `dropped.ROWS` reads it."""
    return {"id": i, "extraction_id": extraction, "subject": subject, "subject_type": "character", "predicate": predicate,
            "object": obj, "object_type": "character" if obj else None, "value": value, "epistemic": "stated",
            "confidence": 0.9, "evidence": f"{subject}의 장면 {i}", "knowledge": None, "known_by": None,
            "hidden_from": None, "polarity": "positive", "modality": "actual", "source": "narration", "asserted_by": None,
            "salience": None, "participants": None, "outcome": None, "because": None, "when_happened": None,
            "feeling": None, **kw}


class Conn:
    """The two reads `dropped.find` makes."""

    def __init__(self, rows: list[dict]):
        self.rows = rows

    def execute(self, sql: str, params=None):
        if sql is dropped.PAIRS:
            return SimpleNamespace(fetchall=lambda: [{"turn": 3, "turn_hash": "h3", "new": NEW, "old": OLD}])
        assert "feeling::text AS feeling" in sql
        return SimpleNamespace(fetchall=lambda: [dict(x) for x in self.rows])


def test_a_dropped_event_shows_though_its_character_has_another_event():
    old = [stored(1, OLD, "카일", "event", value="왕을 암살함"), stored(2, OLD, "카일", "has_status", value="지침"),
           stored(3, OLD, "카일", "event", value="성을 떠남")]
    view_rows = [row(9, "카일", "event", None, "성을 떠남", **C), row(9, "카일", "has_status", None, "졸림", **C, id=10)]
    view = {"resolution": resolve(uuid.uuid4(), view_rows), "assertions": view_rows}
    got = dropped.find(Conn(old), uuid.uuid4(), "extract", view)
    # the murder is dropped (another event does not hold it); the status is held by the newer status, as before; the
    # event memory still holds word for word is not dropped
    assert [(d["predicate"], d["value"]) for d in got] == [("event", "왕을 암살함")]


def test_a_dropped_fact_held_only_as_its_denial_is_dropped():
    old = [stored(1, OLD, "하나", "role_toward", "카이토", "호위")]
    denial = row(9, "하나", "role_toward", "카이토", "호위", **C, object_type="character", polarity="negative")
    view = {"resolution": resolve(uuid.uuid4(), [denial]), "assertions": [denial]}
    assert [d["value"] for d in dropped.find(Conn(old), uuid.uuid4(), "extract", view)] == ["호위"]


def test_a_dropped_feeling_keeps_how_it_felt_for_its_restore():
    feeling = {"intensity": "strong", "shades": ["그리움"]}
    old = [stored(1, OLD, "하나", "feels_toward", "카이토", "그리움", feeling=json.dumps(feeling, ensure_ascii=False))]
    view = {"resolution": resolve(uuid.uuid4(), []), "assertions": []}
    (d,) = dropped.find(Conn(old), uuid.uuid4(), "extract", view)
    assert d["feeling"] == feeling and repairs.restore_target(d)["fact"]["feeling"] == feeling


# --- through a read of the head ----------------------------------------------------------------------------------------

from conftest import active_generation, alias_yes, make_client  # noqa: E402
from nmos_sidecar.extraction import ALIAS_CONFIRM_SYSTEM  # noqa: E402
from simchat import SimChat  # noqa: E402
from test_extraction import drain  # noqa: E402
from test_generations import LLM  # noqa: E402
from test_sidecar_integration import sync  # noqa: E402


def scripted(script: dict[str, list[dict]], reveals: dict[str, tuple[str, str]] | None = None):
    """An extractor that states `script[marker]` for a turn whose text has the marker, and reports `reveals[marker]`
    (who found out, words of the listed secret) on the open secrets the prompt lists."""
    def complete(system: str, user: str) -> tuple[dict, str]:
        if system == ALIAS_CONFIRM_SYSTEM:  # extract-v16 confirms an alias whose two names are in the turn
            return alias_yes(user)
        before, target = user.split("TARGET", 1)
        items = [{"modality": "actual", "source": "narration", "epistemic": "stated", "confidence": 0.9,
                  "evidence": marker, "object": None, "object_type": None, **a}
                 for marker, said in script.items() if marker in target for a in said]
        listed = [line.split(". ", 1) for line in before.splitlines() if re.match(r"S\d+\. ", line)]
        found = [{"secret": n, "found_out_by": [who], "evidence": marker}
                 for marker, (who, what) in (reveals or {}).items() if marker in target
                 for n, text in listed if what in text]
        return {"assertions": items, "secrets": found}, "{}"
    return complete


def view_of(db, **kw) -> dict:
    head = db.execute("SELECT head_commit_id FROM conversation").fetchone()["head_commit_id"]
    return memory_view(db, head, active_generation(db, "extract").key, **kw)


def story(c, migrated, lines: list[str], complete) -> SimChat:
    chat = SimChat()
    for line in lines:
        chat.user(line)
        chat.reply("Noted.")
    chat.user("Go on.")  # the last turn is extracted once the user continues from it (ADR 0008)
    sync(c, chat)
    drain(migrated, complete)
    return chat


ALIASES = "Scene zero: 김하나 is also 하나, 백이안 is also 이안, and 카이토 forged the letter."
SLEEPY = "Scene one: 백이안 says 카이토 looks sleepy."
TIRED = "Scene two: 이안 says 카이토 looks tired now."
FOUND = "Scene three: 김하나 found out that the letter was forged."


def test_a_reveal_ends_the_secret_under_every_name_and_one_speaker_has_one_claim(migrated, db):
    """C4: a reveal to "김하나" left "하나" in hidden_from; A7: claims by "백이안" and "이안" were two speakers."""
    complete = scripted({
        ALIASES: [{"subject": "김하나", "subject_type": "character", "predicate": "also_called", "value": "하나"},
                  {"subject": "백이안", "subject_type": "character", "predicate": "also_called", "value": "이안"},
                  {"subject": "카이토", "subject_type": "character", "predicate": "knows", "value": "편지는 위조",
                   "knowledge": "limited", "known_by": ["카이토"], "hidden_from": ["김하나", "하나"]}],
        SLEEPY: [{"subject": "카이토", "subject_type": "character", "predicate": "has_status", "value": "졸림",
                  "source": "character_claim", "asserted_by": "백이안"}],
        TIRED: [{"subject": "카이토", "subject_type": "character", "predicate": "has_status", "value": "지침",
                 "source": "character_claim", "asserted_by": "이안"}],
    }, {FOUND: ("김하나", "편지는 위조")})
    with make_client(migrated, **LLM) as c:
        story(c, migrated, [ALIASES, SLEEPY, TIRED, FOUND], complete)
        view = view_of(db)
    (s,) = view["secrets"]
    assert s["open"] == [] and list(s["ended"]) == ["김하나"]
    knows = next(a for a in view["assertions"] if a["predicate"] == "knows")
    assert knows["hidden_from"] is None and "김하나" in knows["known_by"]
    status = [c for c in view["claims"] if c["predicate"] == "has_status" and c["subject"] == "카이토"]
    assert [(c["asserted_by"], c["value"]) for c in status] == [("이안", "지침")]


AIM = "Scene zero: 하나 wants to find the lighthouse keeper."
HARBOR = "Scene one: 카이토 waits at the harbor."


def test_a_retracted_or_restored_opening_is_folded_as_the_repairs_left_it(migrated, db):
    """Item 4.5: the threads folded the rows from before the owner's repairs, so a retracted goal stayed open and a
    restored one was a fact instead of a thread."""
    complete = scripted({
        AIM: [{"subject": "하나", "subject_type": "character", "predicate": "goal", "value": "등대지기를 찾기"}],
        HARBOR: [{"subject": "카이토", "subject_type": "character", "predicate": "located_in", "object": "항구",
                  "object_type": "place"}],
    })
    with make_client(migrated, **LLM) as c:
        story(c, migrated, [AIM, HARBOR], complete)
        view = view_of(db)
        assert [(t["text"], t["status"]) for t in view["threads"]] == [("등대지기를 찾기", "open")]
        goal = next(a for a in view["assertions"] if a["predicate"] == "goal")
        now = datetime.now(timezone.utc)
        retract = {"id": uuid.uuid4(), "kind": "fact_retract", "target": repairs.fact_target(goal), "value": {},
                   "note": None, "created_at": now}
        assert view_of(db, what_if={"add_repairs": [retract]})["threads"] == []
        harbor = next(a for a in view["assertions"] if a["predicate"] == "located_in")
        lost = {**{k: None for k in repairs.RESTORED}, "subject": "하나", "subject_type": "character", "predicate": "goal",
                "value": "비밀 통로를 찾기", "modality": "actual", "source": "narration", "polarity": "positive",
                "evidence": HARBOR, "turn": harbor["turn"], "turn_hash": harbor["turn_hash"], "text": "하나 goal: 비밀 통로를 찾기"}
        restore = {"id": uuid.uuid4(), "kind": "fact_restore", "target": repairs.restore_target(lost), "value": {},
                   "note": None, "created_at": now}
        after = view_of(db, what_if={"add_repairs": [restore]})
        assert sorted((t["text"], t["status"]) for t in after["threads"]) == [
            ("등대지기를 찾기", "open"), ("비밀 통로를 찾기", "open")]
        assert not [f for f in after["facts"] if f["predicate"] == "goal"]
