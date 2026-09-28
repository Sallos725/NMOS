"""The secret gate tool (tools/eval_secret_gate.py): a case's words by secret, and the words of a secret the character
found out by the scene told rather than forbidden (Phase 13 step 6, the owner's decision)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

TOOL = Path(__file__).resolve().parents[3] / "tools/eval_secret_gate.py"
_spec = importlib.util.spec_from_file_location("eval_secret_gate", TOOL)
gate = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(gate)


def test_a_case_without_groups_forbids_every_word():
    case = {"forbidden": ["편지", "등대"]}
    assert gate.groups(case) == [{"turns": [], "forbidden": ["편지", "등대"]}]
    assert gate.words(case, [False]) == (["편지", "등대"], [])


def test_the_words_of_a_secret_found_out_by_the_scene_are_told_not_forbidden():
    case = {"forbidden": ["편지", "등대"], "groups": [{"turns": [6, 7], "forbidden": ["편지"]},
                                                     {"turns": [9], "forbidden": ["등대"]}]}
    assert gate.words(case, [True, False]) == (["등대"], ["편지"])
    assert gate.words(case, [False, False]) == (["편지", "등대"], [])
    assert gate.hits("하나는 카이토의 편지를 서랍에 숨겼다", ["편지", "등대"]) == ["편지"]
