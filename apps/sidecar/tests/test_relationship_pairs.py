"""Relationship history per pair (PHASE-11 step 3, Q5, ADR 0038; K24). The end-to-end case is K24's own example
(`docs/KNOWN-ISSUES.md`), pinned as a strict xfail in step 2."""

from __future__ import annotations

import re
from uuid import UUID

import pytest

from conftest import make_client
from nmos_sidecar.entities import resolve
from nmos_sidecar.facts import _versions, symmetric, version_key
from simchat import SimChat
from test_extraction import drain, facts, filler
from test_semantics import row
from test_sidecar_integration import recall, sync

CHAR = "character"


def relationship(subject, obj, value):
    return {"subject": subject, "subject_type": CHAR, "predicate": "relationship", "object": obj, "object_type": CHAR,
            "value": value, "modality": "actual", "source": "narration", "knowledge": "public"}


def flipped(system, user):
    """The story makes them lovers, and extraction records it in the other direction than the old relationship."""
    target = user.split("TARGET", 1)[1]
    items = []
    if "같은 반" in target:
        items.append(relationship("유이", "카이토", "같은 반 친구"))
    if "사귀기로" in target:
        items.append(relationship("카이토", "유이", "연인"))
    return {"assertions": items}, "{}"


def test_a_symmetric_relationship_changed_in_the_other_direction_ends_the_old_one(migrated):
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake") as c:
        chat = SimChat()
        chat.user("유이와 카이토는 같은 반이다.")
        chat.reply("유이는 카이토의 옆자리에 앉았다.")
        filler(chat, 3)
        chat.user("카이토가 고백했고, 둘은 사귀기로 했다.")
        chat.reply("유이는 고개를 끄덕였다.")
        filler(chat, 5)
        sync(c, chat)
        drain(migrated, flipped)
        rows = [f for f in facts(c, chat) if f["predicate"] == "relationship"]
        packet = recall(c, chat, "유이와 카이토가 함께 하교한다.", budget=400)["packet"]["text"]
    assert {(f["subject"], f["object"], f["value"]) for f in rows} == {("카이토", "유이", "연인")}
    # packet-v5 names the relationship it replaced, the other way round, as earlier (ADR 0038)
    assert re.search(r"카이토 relationship 유이: 연인; before, turn \d+: 유이 relationship 카이토: 같은 반 친구</Fact>", packet)
    assert packet.count("같은 반 친구") == 1


CONV = UUID("01900000-0000-7000-8000-000000000038")
C = {"subject_type": CHAR, "object_type": CHAR}


def rel(pos, subject, obj, value, **kw):
    return row(pos, subject, "relationship", obj, value, **C, **kw)


def current(rows, persona=()):
    """Current facts as memory_view folds them: grouped by version key, then folded."""
    r = resolve(CONV, rows, persona=persona)
    groups: dict[tuple, list] = {}
    for x in rows:
        groups.setdefault(version_key(x, r), []).append(x)
    return sorted((f["subject"], f["object"], f["value"], f["polarity"]) for h in groups.values() for f in _versions(h, r))


@pytest.mark.parametrize("value", ["같은 반 친구", "연인", "연인 관계", "친구 사이", "소꿉친구", "남자친구", "라이벌",
                                   "동료", "형제", "쌍둥이 자매", "부부", "friends", "Lovers", "rival", "classmates"])
def test_symmetric_relationships(value):
    assert symmetric(value)


@pytest.mark.parametrize("value", ["엄마", "자녀", "이모", "조카(추정)", "친구의 동생", "짝사랑 상대", "선배", "스승",
                                   "friend of her brother", "teacher", "", None])
def test_directed_relationships(value):
    assert not symmetric(value)


def test_one_history_per_pair_in_both_directions():
    rows = [rel(1, "유이", "카이토", "같은 반 친구"), rel(3, "카이토", "유이", "연인")]
    assert current(rows) == [("카이토", "유이", "연인", "positive")]
    r = resolve(CONV, rows)
    assert version_key(rows[0], r) == version_key(rows[1], r)
    history = _versions(rows, r)[0]["history"]
    assert [(h["subject"], h["outcome"]) for h in history] == [("유이", "superseded"), ("카이토", "current")]


def test_a_directed_relationship_keeps_both_directions():
    rows = [rel(1, "노엘", "루카", "엄마"), rel(2, "루카", "노엘", "자녀")]
    assert current(rows) == [("노엘", "루카", "엄마", "positive"), ("루카", "노엘", "자녀", "positive")]


def test_a_symmetric_one_ends_a_directed_one_the_other_way_and_the_same_direction_is_replaced_as_before():
    assert current([rel(1, "하나", "카이토", "선생님"), rel(2, "카이토", "하나", "연인")]) == [("카이토", "하나", "연인", "positive")]
    assert current([rel(1, "하나", "카이토", "라이벌"), rel(2, "카이토", "하나", "제자")]) == [("카이토", "하나", "제자", "positive")]
    assert current([rel(1, "하나", "카이토", "선생님"), rel(2, "하나", "카이토", "연인")]) == [("하나", "카이토", "연인", "positive")]


def test_a_breakup_said_either_way_ends_a_symmetric_relationship():
    rows = [rel(1, "카이토", "유이", "연인"), rel(2, "유이", "카이토", "연인", polarity="negative")]
    assert current(rows) == [("유이", "카이토", "연인", "negative")]
    # A denial of another relation stands beside it, as for any predicate (ADR 0013).
    other = [rel(1, "카이토", "유이", "연인"), rel(2, "유이", "카이토", "라이벌", polarity="negative")]
    assert current(other) == [("유이", "카이토", "라이벌", "negative"), ("카이토", "유이", "연인", "positive")]


def test_feelings_stay_per_direction():
    rows = [row(1, "유이", "feels_toward", "카이토", "화남", **C), row(2, "카이토", "feels_toward", "유이", "미안함", **C)]
    assert current(rows) == [("유이", "카이토", "화남", "positive"), ("카이토", "유이", "미안함", "positive")]


def test_the_persona_under_two_names_is_one_side_of_the_pair():
    rows = [rel(1, "노엘", "타쿠미", "동료"), rel(2, "아오키 타쿠미", "노엘", "연인")]
    assert current(rows, persona=["타쿠미"]) == [("아오키 타쿠미", "노엘", "연인", "positive")]


def test_packet_v5_names_what_a_standing_fact_replaced():
    from nmos_sidecar.facts import earlier, fact_line

    rows = [rel(1, "유이", "카이토", "같은 반 친구"), rel(3, "카이토", "유이", "연인")]
    r = resolve(CONV, rows)
    (f,) = _versions(rows, r)
    assert earlier(f)["value"] == "같은 반 친구"
    assert fact_line(f).endswith(">카이토 relationship 유이: 연인</Fact>")  # packet-v4 and earlier: as before
    assert fact_line(f, before=True).endswith(">카이토 relationship 유이: 연인; before, turn 1: 유이 relationship 카이토: 같은 반 친구</Fact>")
    # only another value counts, a denial is not what it was, and facts that are not standing name nothing
    same = _versions([rel(1, "유이", "카이토", "연인"), rel(3, "카이토", "유이", "연인")], r)[0]
    assert earlier(same) is None
    denied = _versions([rel(1, "유이", "카이토", "라이벌", polarity="negative"), rel(3, "유이", "카이토", "연인")], r)
    assert all(earlier(x) is None for x in denied)
    trait = _versions([row(1, "유이", "has_status", None, "아픔", subject_type=CHAR),
                       row(2, "유이", "has_status", None, "회복함", subject_type=CHAR)])[0]
    assert earlier(trait) is None and "before" not in fact_line(trait, before=True)


def test_packet_v5_names_how_it_started_when_that_is_not_what_it_replaced():
    from nmos_sidecar.facts import fact_line

    speech = [row(20, "타쿠미", "addresses", "아델라", "하십시오체", **C), row(39, "타쿠미", "addresses", "아델라", "반말, '아델라 누나'", **C),
              row(64, "타쿠미", "addresses", "아델라", "반말, '누나'", **C)]
    (f,) = _versions(speech)
    assert fact_line(f, before=True).endswith(">타쿠미 addresses 아델라: 반말, '누나'; before, turn 39: 타쿠미 addresses 아델라:"
                                              " 반말, '아델라 누나'; first, turn 20: 타쿠미 addresses 아델라: 하십시오체</Fact>")
    (two,) = _versions(speech[1:])
    assert "first" not in fact_line(two, before=True)  # what it replaced is how it started
