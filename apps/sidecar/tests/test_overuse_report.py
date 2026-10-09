"""PHASE-33 Q8: the overuse report's line identity and percentile helpers."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("overuse_report", Path(__file__).parents[3] / "tools/overuse_report.py")
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def test_a_line_is_its_kind_and_ref_or_its_text():
    assert report.line_key({"kind": "fact", "ref": 12, "text": "a"}) == ("fact", "12")
    a = report.line_key({"kind": "excerpt", "text": "the harbor at dawn"})
    assert a[0] == "excerpt" and a[1].startswith("t:") and a == report.line_key({"kind": "excerpt", "content": "the harbor at dawn"})


def test_percentiles():
    assert report.pct([], 0.5) is None
    assert report.pct([1, 1, 2, 3, 9], 0.5) == 2 and report.pct([1, 1, 2, 3, 9], 0.9) == 9
