"""PHASE-60 S6 / S7: carried rows keep `when_happened` across snapshot and target_rows.

Pure tests (no database); synthetic names only (세라, 카이토, 도현)."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from nmos_sidecar import carry
from nmos_sidecar.entities import resolve
from nmos_sidecar.facts import _annotate

SRC_ID = UUID("01960000-0000-7000-8000-000000000011")
LINK_CONTINUE = UUID("01960000-0000-7000-8000-000000000012")
LINK_REGRESSION = UUID("01960000-0000-7000-8000-000000000013")
REV_1 = UUID("01960000-0000-7000-8000-000000000111")
REV_2 = UUID("01960000-0000-7000-8000-000000000112")
WHEN = "4월 11일"


def _row(
    aid: int,
    subject: str,
    predicate: str,
    *,
    value: str | None = None,
    turn: int = 1,
    position: int = 1,
    compiler: str = "extract-v19",
    **extra: Any,
) -> dict[str, Any]:
    return {
        "id": aid,
        "subject": subject,
        "subject_type": "character",
        "predicate": predicate,
        "object": None,
        "object_type": None,
        "value": value,
        "epistemic": "stated",
        "confidence": 0.9,
        "evidence": f"evidence-{aid}",
        "knowledge": "unknown",
        "known_by": None,
        "hidden_from": None,
        "polarity": "positive",
        "modality": "actual",
        "source": "narration",
        "asserted_by": None,
        "salience": "major" if predicate == "event" else None,
        "participants": None,
        "outcome": None,
        "because": None,
        "turn": turn,
        "position": position,
        "generation": "extract:v19-gen-1",
        "compiler": compiler,
        "host_logical_id": f"m-{position}",
        "turn_hash": f"th-{turn}",
        **extra,
    }


def _make_view(facts: list[dict[str, Any]]) -> dict[str, Any]:
    r = resolve(SRC_ID, facts, persona=("도현",))
    for row in facts:
        _annotate(row, r)
    return {
        "facts": sorted(facts, key=lambda f: f["position"], reverse=True),
        "threads": [],
        "assertions": list(facts),
        "resolution": r,
        "entities": r.entities(),
        "excluded": {},
        "secrets": [],
    }


def _source_facts() -> list[dict[str, Any]]:
    dated_event = _row(
        1, "세라", "event",
        value="항구에서 오래된 편지를 발견했다",
        turn=2, position=4,
        when_happened=WHEN,
    )
    # No `when_happened` key, matching `facts.served_assertions` when the column is NULL.
    undated_event = _row(
        2, "세라", "event",
        value="등대 문을 잠갔다",
        turn=3, position=6,
    )
    return [dated_event, undated_event]


def _link(link_id: UUID, snap: dict[str, Any], *, mode: str, names: list[str]) -> dict[str, Any]:
    return {
        "id": link_id,
        "source_conversation_id": SRC_ID,
        "mode": mode,
        "entity_names": names,
        "snapshot": snap,
    }


def test_snapshot_of_keeps_when_happened_and_omits_it_when_absent() -> None:
    """`snapshot_of` stores `when_happened` when present on a source fact and never invents it when absent."""
    view = _make_view(_source_facts())
    revs = {1: REV_1, 2: REV_2}

    cont = carry.snapshot_of(view, None, "continue", [], SRC_ID, revs)
    cont_by_id = {f["from"]["assertion"]: f for f in cont["facts"]}
    assert cont_by_id[1]["when_happened"] == WHEN
    assert "when_happened" not in cont_by_id[2]
    assert json.loads(json.dumps(cont, ensure_ascii=False)) == cont

    reg = carry.snapshot_of(view, None, "regression", ["세라"], SRC_ID, revs)
    reg_by_id = {f["from"]["assertion"]: f for f in reg["facts"]}
    assert reg_by_id[1]["when_happened"] == WHEN
    assert "when_happened" not in reg_by_id[2]
    assert json.loads(json.dumps(reg, ensure_ascii=False)) == reg


def test_target_rows_preserves_when_happened_for_continue_and_regression() -> None:
    """`target_rows` keeps `when_happened` unchanged on continue rows and regression copies without inventing it."""
    view = _make_view(_source_facts())
    revs = {1: REV_1, 2: REV_2}

    cont_snap = carry.snapshot_of(view, None, "continue", [], SRC_ID, revs)
    carried_cont = carry.target_rows(_link(LINK_CONTINUE, cont_snap, mode="continue", names=[]))
    assert carried_cont.mode == "continue"
    assert carried_cont.regression == ()
    cont_rows = {r["carried_from"]["assertion"]: r for r in carried_cont.rows}
    assert cont_rows[1]["when_happened"] == WHEN
    assert cont_rows[1]["carried"] == str(LINK_CONTINUE)
    assert cont_rows[1]["turn"] == -1
    assert "when_happened" not in cont_rows[2]

    reg_snap = carry.snapshot_of(view, None, "regression", ["세라"], SRC_ID, revs)
    carried_reg = carry.target_rows(_link(LINK_REGRESSION, reg_snap, mode="regression", names=["세라"]))
    assert carried_reg.mode == "regression"
    assert carried_reg.rows == ()
    reg_rows = {r["carried_from"]["assertion"]: r for r in carried_reg.regression}
    assert reg_rows[1]["line"] == "fact"
    assert reg_rows[1]["when_happened"] == WHEN
    assert reg_rows[1]["carried"] == str(LINK_REGRESSION)
    assert "when_happened" not in reg_rows[2]
