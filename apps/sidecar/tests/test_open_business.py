"""Phase 11 (docs/phases/PHASE-11.md, ADR 0039): goals, questions, threats and debts as threads that end (Q2, Q3).

The fold is pure: rows as the fact read serves them. Only extract-v13 or later reports how these end, so rows of an
earlier generation (`compiler`) stay facts."""

from __future__ import annotations

import uuid

from nmos_sidecar.entities import resolve
from nmos_sidecar.predicates import OUTCOMES, because, outcome, validate
from nmos_sidecar.threads import fold
from test_semantics import row
from test_threads import kept, promise

C = {"subject_type": "character"}
GOAL = "목요일마다 노엘에게 도시락을 챙겨주는 것"


def goal(pos, who="루카", text=GOAL, **kw):
    return row(pos, who, "goal", None, text, **C, **kw)


def resolved(pos, who="루카", text=GOAL, how="achieved", **kw):
    return row(pos, who, "resolved", None, text, **{**C, **kw}, outcome=how)


def status(rows):
    r = resolve(uuid.uuid4(), rows)
    return [(t["kind"], t["by"], t["text"], t["status"]) for t in fold(rows, r)[0]]


def test_a_goal_is_a_thread_until_the_story_ends_it():
    assert status([goal(26)]) == [("goal", "루카", GOAL, "open")]
    for how in ("achieved", "abandoned", "failed"):
        assert status([goal(26), resolved(40, how=how)]) == [("goal", "루카", GOAL, how)]
    # a plan is labelled hypothetical as often as not: the aim is held now
    assert status([goal(26, modality="hypothetical")]) == [("goal", "루카", GOAL, "open")]
    assert status([goal(26, modality="dreamed")]) == []


def test_each_kind_opens_and_ends():
    rows = [row(10, "하나", "question", None, "등대지기가 왜 사라졌는지", **C),
            row(11, "마을", "threat", None, "산적의 습격", subject_type="place"),
            row(12, "카이토", "owes", "하나", "빌린 은화 세 닢", **C, object_type="character"),
            resolved(20, "하나", "등대지기가 왜 사라졌는지", "answered"),
            resolved(21, "마을", "산적의 습격", "averted", subject_type="place"),
            resolved(22, "카이토", "빌린 은화 세 닢", "paid")]
    assert sorted(status(rows)) == [("debt", "카이토", "빌린 은화 세 닢", "paid"),
                                    ("question", "하나", "등대지기가 왜 사라졌는지", "answered"),
                                    ("threat", "마을", "산적의 습격", "averted")]


def test_who_may_open_one():
    said = {"source": "character_claim"}
    assert status([goal(26, asserted_by="루카", **said)]) == [("goal", "루카", GOAL, "open")]
    assert status([goal(26, asserted_by="노엘", **said)]) == []  # someone else's report stays a claim
    threat = row(5, "하나", "threat", None, "내일 밤 너를 끝장내겠다", **C, asserted_by="산적 두목", **said)
    assert status([threat]) == [("threat", "하나", "내일 밤 너를 끝장내겠다", "open")]  # the one who threatens says it
    debt = dict(C, object_type="character")
    assert status([row(5, "카이토", "owes", "하나", "은화", **debt, asserted_by="하나", **said)])[0][3] == "open"
    assert status([row(5, "카이토", "owes", "하나", "은화", **debt, asserted_by="유이", **said)]) == []


def test_a_resolution_matches_its_own_kind_and_owner_only():
    assert status([promise(10), resolved(40, "하나", "비가 그치면 내일 아침 등대 앞에서 만나기로 함")])[0][3] == "open"
    assert status([goal(26), resolved(40, "노엘")]) == [("goal", "루카", GOAL, "open")]
    _, unmatched, _ = fold([goal(26), resolved(40, "노엘")], resolve(uuid.uuid4(), [goal(26)]))
    assert unmatched and unmatched[0]["outcome"] == "achieved"


def test_the_same_aim_in_other_words_is_one_thread():
    rows = [goal(0, text="엄마를 위해 버터 쿠키를 만드는 것"), goal(0, text="엄마를 위해 더 달게 만든 버터 쿠키를 굽는 것")]
    (t,) = fold(rows, resolve(uuid.uuid4(), rows))[0]
    assert t["text"] == "엄마를 위해 버터 쿠키를 만드는 것" and len(t["restated"]) == 1
    two = [goal(0, text="노엘의 수업을 몰래 보는 것"), goal(1, text="목요일마다 도시락을 싸는 것")]
    assert len(fold(two, resolve(uuid.uuid4(), two))[0]) == 2


def test_an_earlier_generation_never_opens_one():
    old = goal(26, compiler="extract-v12")
    r = resolve(uuid.uuid4(), [old])
    threads, _, used = fold([old], r)
    assert threads == [] and used == set()  # it stays a fact, as before
    assert status([goal(26, compiler="extract-v13")]) == [("goal", "루카", GOAL, "open")]
    assert status([promise(10, compiler="extract-v7")])[0][3] == "open"  # promises are unchanged


def test_outcome_and_because_are_kept_only_where_they_belong():
    base = {"subject": "루카", "subject_type": "character", "value": GOAL}
    assert [outcome({**base, "predicate": "resolved", "outcome": o}) for o in OUTCOMES] == list(OUTCOMES)
    assert outcome({**base, "predicate": "resolved", "outcome": "done"}) is None
    assert outcome({**base, "predicate": "goal", "outcome": "achieved"}) is None
    assert because({**base, "predicate": "feels_toward", "because": " 손등에 입맞춤해서 "}) == "손등에 입맞춤해서"
    assert because({**base, "predicate": "feels_toward", "because": "null"}) is None
    assert because({**base, "predicate": "located_in", "because": "x"}) is None
    assert validate({**base, "predicate": "resolved"}) == ("valid", None)
    assert validate({"subject": "카이토", "subject_type": "character", "predicate": "owes", "value": "은화"})[0] == "pending"


def test_models_fill_in_an_object_or_say_fulfilled_and_the_goal_still_ends():
    """Seen on the owner's chat re-extracted with extract-v13 (M0): a `resolved` with its owner as `object`, and
    `fulfilled` for a goal. Both matched nothing before."""
    with_object = row(40, "루카", "resolved", "루카", GOAL, **C, object_type="character", outcome="achieved")
    assert status([goal(26), with_object]) == [("goal", "루카", GOAL, "achieved")]
    assert status([goal(26), kept(40, "루카", GOAL)]) == [("goal", "루카", GOAL, "achieved")]
    # a promise of the same words still wins `fulfilled`
    both = [promise(10, "루카", "{{user}}", GOAL), goal(26), kept(40, "루카", GOAL)]
    assert sorted(t[3] for t in status(both)) == ["kept", "open"]
    # goals are one owner's: the same aim with a stray object is a restatement
    stray = row(27, "루카", "goal", "노엘", GOAL, **C, object_type="character")
    assert len(status([goal(26), stray])) == 1


def test_the_extractor_sees_an_old_thread_the_target_turn_is_about():
    """OPEN THREADS lists what the target turn is about before the newest named threads: an old goal the story comes
    back to can only be ended while it is listed (M0: most of the owner's goals were never listed again)."""
    from nmos_sidecar import extraction

    rows = [goal(i, text=f"하나의 {i}번째 소원 이루기 {'가나다라마바사'[i % 7] * 3}") for i in range(12)]
    rows.append(goal(13, text="목요일마다 노엘에게 도시락을 챙겨주는 것"))
    rows += [goal(20 + i, text=f"새로운 계획 {i} {'아자차카타파하'[i] * 3}") for i in range(7)]
    ctx = {"target": {"conversation_id": uuid.uuid4(), "turn": 40},
           "context": [{"turn": 39, "metadata": {"role": "user"}, "content": "루카가 부엌에 있다."}],
           "members": [{"turn": 40, "metadata": {"role": "char"},
                        "content": "루카는 목요일 아침, 노엘에게 도시락을 챙겨주는 것을 잊지 않았다."}]}
    listed = extraction.thread_hints(ctx, rows)
    assert listed[0]["text"] == "목요일마다 노엘에게 도시락을 챙겨주는 것"
    assert len(listed) == 8 and listed[1]["turn"] == 26  # then the newest named ones
