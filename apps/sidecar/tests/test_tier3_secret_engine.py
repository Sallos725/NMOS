"""PHASE-66 part 4 (Tier 3, Wave 4): the secret engine reads extract-v21's knowledge marks.

`secrets.fold` (a fact known by its holders alone, a group in a mark, a forgetting, a belief), `threads.fold` (a
promise's `condition`) and `scene` (`public_except`, a character the story says is gone). A row of every earlier
generation reads exactly as before: the differential run of `w4-secrets-epistemic-REPORT.md`, and the controls below.
Synthetic names only."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from nmos_sidecar import scene, threads
from nmos_sidecar.entities import resolve
from nmos_sidecar.secrets import fold, kept_from_others, reveal_value
from test_semantics import row

C = "character"


def v21(pos: int, subject: str, predicate: str, obj: str | None = None, value: str | None = None, *,
        scope: str = "public", **kw: Any) -> dict[str, Any]:
    """A row as extract-v21 stores one: `knowledge_scope` on every row."""
    return row(pos, subject, predicate, obj, value, subject_type=C, knowledge_scope=scope,
               compiler="extract-v21", **kw)


def solo(pos: int = 1, holders=("루카",), value: str = "노엘을 짝사랑한다", **kw: Any) -> dict[str, Any]:
    """A fact its holders alone know (extract-v21): limited, `known_by` only."""
    return v21(pos, "루카", "goal", None, value, scope="limited", knowledge="limited", known_by=list(holders), **kw)


def kept(pos: int, hidden=("노엘",), value: str = "몰래 성을 떠난다", *, scope: str | None = "public_except",
         known=("루카",), **kw: Any) -> dict[str, Any]:
    """A secret kept from someone; `scope=None`: as extract-v20 stores one (no `knowledge_scope`)."""
    base = row(pos, "루카", "goal", None, value, subject_type=C, knowledge="limited", known_by=list(known),
               hidden_from=list(hidden), **kw)
    if scope is not None:
        base.update(knowledge_scope=scope, compiler="extract-v21")
    return base


def here(pos: int, who: str, place: str = "정원", **kw: Any) -> dict[str, Any]:
    return row(pos, who, "located_in", place, None, subject_type=C, object_type="place", **kw)


def learned(pos: int, who: str, listed: dict[str, Any], **kw: Any) -> dict[str, Any]:
    from nmos_sidecar.secrets import secret_text
    return row(pos, who, "learned", None, reveal_value({"turn": listed["turn"], "text": secret_text(listed)}),
               subject_type=C, **kw)


def member(pos: int, who: str, group: str = "기사단", polarity: str = "positive") -> dict[str, Any]:
    return row(pos, who, "member_of", group, None, subject_type=C, object_type="group", polarity=polarity)


def forgot(pos: int, who: str, value: str) -> dict[str, Any]:
    return v21(pos, who, "forgot", None, value)


def secrets_of(rows: list[dict[str, Any]], persona: tuple[str, ...] = ()) -> tuple[list, list, set]:
    return fold(rows, resolve(uuid.uuid4(), rows, persona))


def only(rows: list[dict[str, Any]]) -> dict[str, Any]:
    (s,), _, _ = secrets_of(rows)
    return s


# --- 1. a fact known by its holders alone ------------------------------------------------------------------------------

def test_a_fact_its_holders_alone_know_is_a_secret_kept_from_everyone_else_newcomers_included():
    rows = [here(0, "노엘"), solo(1), here(2, "아델라"), here(5, "미라")]  # 미라 first appears after it
    s = only(rows)
    assert s["solo"] is True and s["holders"] == ["루카"]
    assert set(s["open"]) == {"노엘", "아델라", "미라", "{{user}}"} and "루카" not in s["kept_from"]
    assert kept_from_others(solo(1))
    # its learned row (the worker's reveal of the listed line) matches: it ends for that character only, and stays
    # kept from everyone else, so it is still listed for them
    s = only(rows + [learned(6, "아델라", solo(1))])
    assert set(s["ended"]) == {"아델라"} and set(s["open"]) == {"노엘", "미라", "{{user}}"}
    # a newcomer the read meets only in the reveal itself is ended too
    s = only([solo(1), learned(6, "세라", solo(1))])
    assert "세라" in s["ended"] and "세라" not in s["open"]


def test_a_holders_own_learned_row_is_unmatched_and_ends_nothing():
    (s,), unmatched, used = secrets_of([here(0, "노엘"), solo(1), learned(6, "루카", solo(1))])
    assert s["ended"] == {} and [u["subject"] for u in unmatched] == ["루카"] and used == {6}


def test_an_earlier_generations_known_by_only_fact_is_still_no_secret():
    earlier = {k: v for k, v in solo(1).items() if k not in ("knowledge_scope", "compiler")}
    assert not kept_from_others(earlier)
    assert secrets_of([here(0, "노엘"), earlier, learned(6, "노엘", earlier)])[0] == []
    # extract-v21's public fact and its unknown one are no secrets either
    assert secrets_of([v21(1, "루카", "goal", None, "x", scope="unknown", knowledge="unknown")])[0] == []


def test_a_revealed_solo_secrets_row_gets_a_list_the_view_can_drop_the_name_from():
    rows = [here(0, "노엘"), solo(1), learned(6, "노엘", solo(1))]
    secrets_of(rows)
    assert rows[1]["hidden_from"] == []  # facts.memory_view iterates it; an unrevealed one is left as stored
    rows = [here(0, "노엘"), solo(1)]
    secrets_of(rows)
    assert "hidden_from" not in rows[1]


# --- 2. public_except --------------------------------------------------------------------------------------------------

def test_public_except_is_kept_from_those_named_alone_never_from_a_newcomer():
    s = only([here(0, "노엘"), kept(1, known=()), here(4, "미라")])
    assert s["kept_from"] == ["노엘"] and s["open"] == ["노엘"] and "solo" not in s


# --- 3. groups ---------------------------------------------------------------------------------------------------------

def test_a_group_kept_from_is_its_members_over_the_secrets_time():
    rows = [member(0, "노엘"), member(0, "미라"), member(1, "미라", polarity="negative"),  # 미라 left before it
            kept(2, hidden=("기사단",)), member(4, "아델라"),  # 아델라 joins after: covered from then on
            member(5, "노엘", polarity="negative")]  # 노엘 leaves after: never told
    s = only(rows)
    assert s["kept_from"] == ["기사단", "노엘", "아델라"] and "미라" not in s["open"]
    s = only(rows + [learned(6, "아델라", kept(2, hidden=("기사단",)))])
    assert set(s["ended"]) == {"아델라"} and s["open"] == ["기사단", "노엘"]
    # the holder the mark names is never kept from by the group it belongs to
    s = only([member(0, "루카"), member(0, "노엘"), kept(2, hidden=("기사단",))])
    assert s["kept_from"] == ["기사단", "노엘"]


def test_a_group_known_by_makes_its_members_holders_and_leaving_does_not_untell():
    rows = [member(0, "노엘"), solo(2, holders=("기사단",)), member(3, "아델라"), member(4, "노엘", polarity="negative"),
            here(5, "미라")]
    s = only(rows)
    assert s["holders"] == ["기사단", "노엘", "아델라"] and set(s["open"]) == {"루카", "미라", "{{user}}"}  # 루카: not named


def test_a_name_that_is_both_a_group_and_a_character_is_not_read_as_holders():
    rows = [member(0, "노엘", "그림자"), here(0, "그림자"), solo(2, holders=("그림자",))]
    assert only(rows)["holders"] == ["그림자"] and "노엘" in only(rows)["open"]


def test_an_earlier_generations_group_mark_is_read_as_a_name_as_before():
    s = only([member(0, "노엘"), kept(2, hidden=("기사단",), scope=None)])
    assert s["kept_from"] == ["기사단"] and s["open"] == ["기사단"]


# --- 4. forgetting reopens ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("scope", ["public_except", None])  # an earlier generation's secret too, in a mixed chat
def test_forgetting_keeps_a_revealed_secret_from_them_again_until_they_learn_it_again(scope):
    secret = kept(1, scope=scope)
    s = only([secret, learned(3, "노엘", secret), forgot(5, "노엘", "all")])
    assert s["open"] == ["노엘"] and s["ended"] == {} and s["reopened"][0]["to"] == "노엘"
    assert s["reopened"][0]["ended"]["turn"] == 3 and s["reopened"][0]["forgot"]["turn"] == 5
    s = only([secret, learned(3, "노엘", secret), forgot(5, "노엘", "all"), learned(7, "노엘", secret)])
    assert s["open"] == [] and s["ended"]["노엘"]["turn"] == 7


def test_a_forgetting_reaches_only_its_scope_and_its_subject():
    secret = kept(1, hidden=("노엘", "아델라"))
    base = [secret, learned(3, "노엘", secret), learned(3, "아델라", secret)]
    assert only(base + [forgot(5, "노엘", "since turn 3")])["open"] == ["노엘"]
    assert only(base + [forgot(5, "노엘", "since turn 4")])["open"] == []  # learned before turn 4
    assert only(base + [forgot(5, "노엘", "몰래 성을 떠난다")])["open"] == ["노엘"]  # the matter
    assert only(base + [forgot(5, "노엘", "어린 시절의 기억")])["open"] == []  # another matter
    assert only(base + [forgot(2, "노엘", "all")])["open"] == []  # before the reveal: it stands
    assert "reopened" not in only(base)


def test_a_holder_who_forgets_a_fact_only_they_knew_no_longer_knows_it():
    s = only([here(0, "노엘"), solo(1), forgot(4, "루카", "all")])
    assert s["holders"] == [] and "루카" in s["open"] and s["reopened"][0]["held"] is True


# --- 5. beliefs are not knowledge --------------------------------------------------------------------------------------

def test_a_belief_is_never_a_secret_never_ends_one_and_never_counts_as_knowing():
    secret = kept(1)
    belief = v21(3, "노엘", "believes", None, "루카 goal: 몰래 성을 떠난다", scope="public_except",
                 knowledge="limited", hidden_from=["루카"])
    (s,), unmatched, used = secrets_of([secret, belief])
    assert s["open"] == ["노엘"] and unmatched == [] and used == set()  # the belief is no secret of its own
    believed = {**belief, "predicate": "learned", "id": 4, "position": 4}  # only a learned row ends it
    assert only([secret, believed])["open"] == []
    assert secrets_of([v21(1, "노엘", "forgot", None, "x", scope="limited", knowledge="limited",
                           known_by=["노엘"])])[0] == []


# --- carried secrets (review F7) ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("compiler", [f"extract-v{n}" for n in range(15, 22)])
def test_a_carried_secret_ends_when_its_learned_row_arrives_under_every_compiler(compiler):
    carried = kept(-1, scope="public_except" if compiler == "extract-v21" else None, compiler=compiler,
                   carried=True, turn=-1)
    carried["position"] = -1
    s = only([carried, learned(4, "노엘", carried, compiler=compiler)])
    assert s["turn"] == -1 and s["open"] == [] and s["ended"]["노엘"]["turn"] == 4
