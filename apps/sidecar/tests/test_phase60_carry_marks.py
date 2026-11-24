"""PHASE-60 S6 (ADR 0085): a person's sheet draws its timeline marks from the chat's own turns only. A carried fact
is before this chat's story (turn -1): it is listed in the sheet's `carry` lines, never as a mark on the timeline.
Synthetic names only."""

from __future__ import annotations

import pytest

from conftest import make_client
from test_phase60_carry_data import Seen, _entity_id, _person, _setup
from test_phase60_carry_take import ON


def test_a_carried_fact_makes_no_timeline_mark_on_a_person_sheet(migrated: str, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = Seen(monkeypatch)
    with make_client(migrated, **ON) as c:
        src, tgt = _setup(c, migrated)
        sera = _entity_id(c, tgt, "세라")
        before, _, _ = _person(c, seen, tgt, sera)
        made = c.post(f"/v1/conversations/{tgt}/carry", json={"source_conversation_id": src, "mode": "continue"})
        assert made.status_code == 200, made.text
        after, _, _ = _person(c, seen, tgt, sera)
    assert after["carry"]["lines"], "the sheet lists 세라's carried lines"
    assert all(m[0] >= 0 for m in after["marks"]), after["marks"]
    assert after["marks"] == before["marks"]
