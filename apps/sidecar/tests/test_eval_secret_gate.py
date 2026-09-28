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


def test_a_group_is_told_only_when_every_one_of_its_secrets_was_found_out_by_the_scene():
    """Codex review of step 6: a turn with no secret NMOS can account for keeps the group's words forbidden."""
    key = lambda n: n.casefold()  # noqa: E731 (as a resolution's key: one character, two spellings)
    def secret(turn: int, ended: int | None) -> dict:
        return {"turn": turn, "kept_from": ["Kaito"], "ended": {"kaito": {"turn": ended}} if ended is not None else {}}
    assert gate.told_group([6, 7], [secret(6, 21), secret(7, 21)], "kaito", key, 73)
    assert not gate.told_group([6, 7], [secret(6, 21)], "kaito", key, 73)  # turn 7's secret is missing
    assert not gate.told_group([6, 7], [secret(6, 21), secret(7, None)], "kaito", key, 73)  # one still kept
    assert not gate.told_group([6, 7], [secret(6, 21), secret(7, 80)], "kaito", key, 73)  # found out after the scene
    assert not gate.told_group([], [secret(6, 21)], "kaito", key, 73)  # no turns: never told
    assert not gate.told_group([6], [secret(6, 21)], "hana", key, 73)  # not kept from this character
