"""PHASE-60 S6 (ADR 0085): a target chat's read folds the rows its link carries (`carry.target_rows`,
`facts.memory_view(carried=…)`).

`continue` folds the carried rows like canon: before turn 0, after the target's canon, superseded by the target's story.
`regression` keeps them apart, as memory only. Stub extractor and canon extractor only; synthetic names 세라, 카이토,
하나, 유나, 도현, 유찬."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from nmos_sidecar import canonfacts, carry

LINK = str(uuid4())
SOURCE = str(uuid4())


def _from(aid: int, gen: str = "extract-test") -> dict[str, Any]:
    return {"conversation": SOURCE, "assertion": aid, "revision": str(uuid4()), "generation": gen, "repair": None}


def _snapshot(mode: str = "continue") -> dict[str, Any]:
    """A stored shape-2 snapshot: facts newest first, as `carry.snapshot_of` stores them."""
    facts = [
        {"predicate": "has_status", "subject": "세라", "subject_type": "character", "value": "피곤함",
         "polarity": "positive", "turn": 3, "position": 7, "compiler": "c1", "known_by": None, "hidden_from": None,
         "participants": [{"name": "카이토", "type": "character"}], "from": _from(12)},
        {"predicate": "located_in", "subject": "세라", "subject_type": "character", "object": "등대",
         "object_type": "place", "value": None, "polarity": "positive", "modality": "actual", "source": "narration",
         "turn": 0, "position": 1, "from": _from(10)},
    ]
    threads = [
        {"kind": "promise", "by": "세라", "to": "카이토", "text": "열쇠를 찾아주기", "status": "open", "turn": 1,
         "position": 3, "names": ["세라", "카이토"], "closed_turn": None,
         "opening": {"predicate": "promised", "subject": "세라", "subject_type": "character", "object": "카이토",
                     "object_type": "character", "value": "열쇠를 찾아주기", "polarity": "positive",
                     "modality": "actual", "source": "narration", "turn": 1, "position": 3, "compiler": "c1"},
         "from": _from(11)},
        {"kind": "goal", "by": "세라", "to": None, "text": "등대를 고치기", "status": "open", "turn": 2,
         "position": 5, "names": ["세라"], "closed_turn": None, "opening": None, "from": _from(13)},
    ]
    aliases = [{"entity_type": "character", "name": "세라", "alias": "세짱", "turn": 1, "from": _from(14)}]
    story = {"text": "세라는 등대에 있었다.", "first_turn": 0, "last_turn": 3,
             "from": {"conversation": SOURCE, "summary": str(uuid4()), "generation": "sum-test"}}
    if mode == "regression":
        for row in (*facts, *threads):
            row.update(knowledge="limited", known_by=["세라"], orig_knowledge=None, orig_known_by=None)
        aliases, story = [], None
    return {"shape": 2, "mode": mode, "names": ["세라"] if mode == "regression" else [], "facts": facts,
            "aliases": aliases, "threads": threads, "story": story, "story_left_out": None, "characters": ["세라"]}


def _link(mode: str = "continue") -> dict[str, Any]:
    from uuid import UUID
    return {"id": UUID(LINK), "source_conversation_id": UUID(SOURCE), "mode": mode,
            "entity_names": ["세라"] if mode == "regression" else [], "snapshot": _snapshot(mode)}


# --- pure: carry.target_rows ------------------------------------------------------------------------------------

def test_continue_rows_are_facts_oldest_first_then_openings_then_aliases() -> None:
    got = carry.target_rows(_link())
    assert got.link == LINK and got.source == SOURCE and got.mode == "continue" and got.names == ()
    assert [(r["predicate"], r.get("value") or r.get("object")) for r in got.rows] == [
        ("located_in", "등대"), ("has_status", "피곤함"), ("promised", "열쇠를 찾아주기"), ("also_called", "세짱")]
    assert got.regression == ()
    assert got.story is not None and got.story["text"] == "세라는 등대에 있었다."


def test_continue_rows_carry_the_flag_and_sort_after_canon_before_turn_0() -> None:
    rows = carry.target_rows(_link()).rows
    positions = [r["position"] for r in rows]
    assert positions == sorted(positions) and len(set(positions)) == len(positions)
    assert all(canonfacts.POSITION_BASE < p < 0 for p in positions)
    assert positions[0] == carry.CARRY_BASE
    for r in rows:
        assert r["carried"] == LINK
        assert r["turn"] == -1
        assert r["turn_hash"] == r["host_logical_id"] == f"carried:{LINK}"
        assert r["listed_hash"] is None and r["evidence"] == ""
        assert r["modality"] == "actual" and r["source"] == "narration" and r["polarity"] == "positive"
        assert isinstance(r["id"], int) and r["id"] < 0
    place, status, opening, alias = rows
    assert status["generation"] == "extract-test" and status["compiler"] == "c1"
    assert place["compiler"] is None
    assert status["participants"] == ({"name": "카이토", "type": "character"},)
    assert place["participants"] is None
    assert status["carried_from"]["assertion"] == 12
    assert opening["carried_from"]["assertion"] == 11  # a thread opening's provenance is its thread's
    assert alias == {**alias, "subject": "세라", "subject_type": "character", "value": "세짱",
                     "predicate": "also_called", "object": None, "object_type": None}
    assert alias["carried_from"]["assertion"] == 14


def test_ids_are_negative_unique_and_stable() -> None:
    a, b = carry.target_rows(_link()), carry.target_rows(_link())
    ids = [r["id"] for r in a.rows]
    assert ids == [r["id"] for r in b.rows]
    assert len(set(ids)) == len(ids) and all(i < 0 for i in ids)
    other = dict(_link(), id=uuid4())
    assert not set(ids) & {r["id"] for r in carry.target_rows(other).rows}


def test_target_rows_never_changes_the_stored_snapshot() -> None:
    link = _link()
    before = repr(link["snapshot"])
    got = carry.target_rows(link)
    got.rows[0]["subject"] = "바뀜"
    assert repr(link["snapshot"]) == before


def test_regression_keeps_every_stored_row_apart_with_its_line() -> None:
    got = carry.target_rows(_link("regression"))
    assert got.mode == "regression" and got.names == ("세라",) and got.rows == () and got.story is None
    assert [(r["line"], r.get("predicate") or r.get("kind")) for r in got.regression] == [
        ("fact", "has_status"), ("fact", "located_in"), ("thread", "promise"), ("thread", "goal")]
    for r in got.regression:
        assert r["carried"] == LINK and r["carried_from"]["conversation"] == SOURCE
        assert r["knowledge"] == "limited" and r["known_by"] == ["세라"]
