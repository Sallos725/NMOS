"""The sampled-turn comparison tool (PHASE-19 step 4): which turns it takes, how it scores the evidence check on rows
of a generation with and without the check, and what counts as finding a ledger fact. Synthetic rows only."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

from nmos_sidecar import extraction

TOOL = Path(__file__).resolve().parents[3] / "tools/eval_extract_sample.py"
_spec = importlib.util.spec_from_file_location("eval_extract_sample", TOOL)
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)

TURN = "하나가 카이토에게 등대 열쇠를 건네주었다. 카이토는 고개를 끄덕였다."


def row(evidence: str | None, status: str = "valid", reason: str | None = None, **extra) -> dict:
    return {"subject": "하나", "predicate": "event", "object": None, "value": "등대 열쇠를 건넴", "evidence": evidence,
            "status": status, "reason": reason, **extra}


def test_the_tool_uses_the_extractors_evidence_test():
    assert (tool.QUOTE_MIN, tool.QUOTE_MIN_CHARS) == (extraction.EVIDENCE_MIN, extraction.EVIDENCE_MIN_CHARS)
    assert tool.in_turn("하나가 카이토에게 등대 열쇠를", TURN) is True
    assert tool.in_turn("유이는 어젯밤 항구의 창고에서", TURN) is False
    assert tool.in_turn("등대 열쇠", TURN) is None and tool.in_turn(None, TURN) is None  # not checked


def test_ledger_turns_are_nmos_turns(tmp_path):
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps([{"must_appear_in_turn": 1}, {"must_appear_in_turn": 5}, {"must_appear_in_turn": None},
                                  {"must_appear_in_turn": 5}]))
    assert tool.ledger_turns(ledger) == {0, 4}


def test_a_ledger_fact_is_found_by_a_row_that_names_its_character_and_overlaps_it():
    fact = {"subject": "하나-카이토", "statement": "하나가 카이토에게 등대 열쇠를 건넨다", "kind": "event"}
    assert tool.hit(row(None), fact, "타쿠미")
    assert not tool.hit({**row(None), "subject": "유이"}, fact, "타쿠미")  # no character of the fact named
    assert not tool.hit({**row(None), "value": "항구로 떠남"}, fact, "타쿠미")  # another fact
    persona = {"subject": "{{user}}-카이토", "statement": "타쿠미가 카이토를 도와준다", "kind": "event"}
    assert tool.hit({**row(None), "subject": "{{user}}", "value": "카이토를 도와준다"}, persona, "타쿠미")


def test_score_counts_the_check_the_same_way_with_and_without_it(tmp_path, capsys):
    # Today's rows are valid and only marked; extract-v14 parks the same row itself.
    today = {"turn": 4, "usage": {"input": 900, "output": 90}, "assertions": [
        row("하나가 카이토에게 등대 열쇠를", quote_in_turn=True),
        row("유이는 어젯밤 항구의 창고에서", quote_in_turn=False),
        row("열쇠", quote_in_turn=None)]}
    v14 = {"turn": 4, "usage": {"input": 700, "output": 95}, "assertions": [
        row("하나가 카이토에게 등대 열쇠를", quote_in_turn=True),
        row("유이는 어젯밤 항구의 창고에서", "pending", "evidence not in the turn", quote_in_turn=False),
        row("?", "invalid", "unknown predicate", quote_in_turn=None)]}
    for label, data in (("v13", today), ("v14", v14)):
        path = tmp_path / label / "1" / "synth-4.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(data, ensure_ascii=False))
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps([{"must_appear_in_turn": 5, "subject": "하나", "statement": "하나가 등대 열쇠를 건넴",
                                   "kind": "event"}], ensure_ascii=False))
    tool.score(argparse.Namespace(out=tmp_path, labels="v13,v14", name="synth", ledger=ledger, persona=""))
    lines = [x for x in capsys.readouterr().out.splitlines() if x.startswith("| v1")]
    assert lines[0].startswith("| v13 | 1 | 1 | 3 | 1 | 1 | 33.3 % | 1/1 | 1/1 | 0 | 0 | 1k | 90 |")
    assert lines[1].startswith("| v14 | 1 | 1 | 2 | 0 | 1 | 50.0 % | 1/1 | 1/1 | 0 | 0 | 1k | 95 |")
