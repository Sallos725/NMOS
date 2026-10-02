"""The independent probe must detect wrong closures/joins and never call on a dry run."""
import argparse
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "eval_story_probe", Path(__file__).resolve().parents[3] / "tools" / "eval_story_probe.py")
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)


def cases():
    return {c["id"]: c for c in tool.load_cases(tool.DEFAULT_CASES)["cases"]}


def ending(case, role="R1", when="now"):
    return {"assertions": [], "roles_ended": [{"role": role, "when": when,
                                               "evidence": case["target"].split(".")[0] + "."}]}


def alias(left, right, evidence):
    return {"subject": left, "subject_type": "character", "predicate": "also_called", "value": right,
            "modality": "actual", "source": "narration", "evidence": evidence, "knowledge": "public",
            "epistemic": "stated"}


def test_new_job_does_not_end_mentorship_but_a_false_ending_fails_the_probe():
    case = cases()["mentor-new-job"]
    assert tool.grade(case, {"assertions": []}, "extract-v16")["passed"]
    result = tool.grade(case, ending(case), "extract-v16")
    assert not result["passed"]
    assert result["checks"][0]["actual"] is False


def test_a_required_ending_must_actually_close_the_seeded_role():
    case = cases()["checkout-complete"]
    assert tool.grade(case, ending(case), "extract-v16")["passed"]
    assert not tool.grade(case, {"assertions": []}, "extract-v16")["passed"]
    assert not tool.grade(case, ending(case, when="planned"), "extract-v16")["passed"]
    assert not tool.grade(case, ending(case, role="R1. descriptive text"), "extract-v16")["passed"]


def test_only_the_correct_pair_ends():
    case = cases()["end-job-keep-mentor"]
    assert tool.grade(case, ending(case, role="R2"), "extract-v16")["passed"]
    assert not tool.grade(case, ending(case, role="R1"), "extract-v16")["passed"]


def test_alias_check_uses_real_resolution_and_rejects_a_namesake_join():
    case = cases()["full-and-given-name"]
    parsed = {"assertions": [alias("강세온", "세온", case["target"])]}
    assert tool.grade(case, parsed, "extract-v16")["passed"]
    assert not tool.grade(case, {"assertions": []}, "extract-v16")["passed"]
    case = cases()["two-people-same-given-name"]
    assert tool.grade(case, {"assertions": []}, "extract-v16")["passed"]
    parsed = {"assertions": [alias("문채린", "채린", case["target"])]}
    assert not tool.grade(case, parsed, "extract-v16")["passed"]


def test_full_name_alone_does_not_prove_a_short_alias():
    case = cases()["full-name-only"]
    result = tool.grade(case, {"assertions": [alias("강세온", "세온", case["target"])]}, "extract-v16")
    assert result["passed"]
    assert result["assertions"][0]["status"] == "pending"


def test_an_ending_under_a_proven_alias_is_not_an_unexpected_other_person():
    case = cases()["alias-and-ending-together"]
    parsed = {"assertions": [alias("강세온", "세온", case["target"]),
        {"subject": "세온", "subject_type": "character", "predicate": "role_toward", "object": "백도겸",
         "object_type": "character", "value": case["roles"][0]["role"], "polarity": "negative",
         "modality": "actual", "source": "narration", "knowledge": "public", "epistemic": "stated",
         "evidence": "백도겸은 숙박 계약을 종료했다."}]}
    assert tool.grade(case, parsed, "extract-v15")["passed"]


def args(tmp_path, execute=False):
    return argparse.Namespace(cases=tool.DEFAULT_CASES, out=tmp_path / "result", runs=3,
                              compiler="extract-v16", execute=execute, url="http://unused.invalid/v1", model="fake")


def test_dry_run_contains_no_gold_and_makes_no_calls(tmp_path, monkeypatch):
    def forbidden(*a, **kw):
        pytest.fail("dry-run instantiated a network client")
    monkeypatch.setattr(tool, "ChatModel", forbidden)
    options = args(tmp_path)
    assert tool.run(options) == 0
    manifest = json.loads((options.out / "manifest.json").read_text())
    assert manifest["planned_calls"] == 42 and manifest["estimated_input_tokens"] > 0
    prompts = json.loads((options.out / "prompts.json").read_text())
    assert all("expected_ended" not in p and "forbidden_aliases" not in p for p in prompts.values())
    assert not (options.out / "calls.jsonl").exists()
    with pytest.raises(FileExistsError):
        tool.run(options)


def test_live_run_stops_at_first_failure_and_preserves_raw_reply(tmp_path, monkeypatch):
    class Fake:
        calls = 0

        def __init__(self, *a, **kw):
            pass

        def complete_metered(self, system, user):
            Fake.calls += 1
            return ending(cases()["mentor-new-job"]), "fixture raw", {"input": 123, "output": 45}

    monkeypatch.setattr(tool, "ChatModel", Fake)
    options = args(tmp_path, execute=True)
    assert tool.run(options) == 1
    assert Fake.calls == 1
    result = json.loads((options.out / "summary.json").read_text())
    assert result["completed"] == 1 and result["passed"] == 0 and result["input_tokens"] == 123
    assert json.loads((options.out / "mentor-new-job-1-raw.json").read_text())["raw"] == "fixture raw"


def test_invalid_seed_and_unsafe_case_id_are_rejected_before_output(tmp_path):
    data = tool.load_cases(tool.DEFAULT_CASES)
    data["cases"][0]["roles"][0]["turn"] = 1
    source = tmp_path / "cases.json"
    tool.save(source, data)
    with pytest.raises(ValueError, match="earlier"):
        tool.load_cases(source)
    data["cases"][0]["roles"][0]["turn"] = 0
    data["cases"][0]["id"] = "../outside"
    tool.save(source, data)
    with pytest.raises(ValueError, match="filenames"):
        tool.load_cases(source)
