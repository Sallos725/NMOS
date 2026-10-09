"""PHASE-34 Q8 b: the sequential replay's overuse numbers on a sequence of packets. Pure."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
from replay_sequence import overuse  # noqa: E402


def test_repeat_share_streaks_and_stale_tokens():
    a, b, c, d = ("fact", "1"), ("fact", "2"), ("excerpt", "r"), ("fact", "3")
    packets = [{a: 10, b: 5}, {a: 10, c: 20}, {a: 10, c: 20}, {a: 10, c: 20, d: 5}, {a: 10, d: 5}]
    out = overuse(packets)
    assert out["requests"] == 5
    assert out["repeat_share"] == round((1 / 2 + 2 / 2 + 2 / 3 + 2 / 2) / 4, 3)
    assert out["streak_max"] == 5  # a, placed in every request
    # request 4 (index 3): a was placed in each of the three before (10 of 35 tokens); request 5: a again (10 of 15)
    assert out["stale_token_share"] == round((10 / 35 + 10 / 15) / 2, 3)


def test_an_empty_sequence_reports_nothing():
    assert overuse([])["repeat_share"] is None and overuse([])["stale_token_share"] is None
