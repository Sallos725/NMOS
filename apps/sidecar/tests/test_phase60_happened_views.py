"""PHASE-60 S7: `[happened: …; told tN]` wherever a fact or a thread is listed (sidecar renderers)."""

from __future__ import annotations

from nmos_sidecar import inspector, views


def test_happened_mark_formats_ko_and_en_with_and_without_turn():
    row = {"when_happened": "4월 11일", "turn": 12}
    assert inspector.happened_mark(row, "ko") == "[일어난 때: 4월 11일; t12에 말함]"
    assert inspector.happened_mark(row, "en") == "[happened: 4월 11일; told t12]"
    assert views.happened_mark(row, "ko") == inspector.happened_mark(row, "ko")

    en_row = {"when_happened": "the night of the fire", "turn": 0}
    assert inspector.happened_mark(en_row, "ko") == "[일어난 때: the night of the fire; t0에 말함]"
    assert inspector.happened_mark(en_row, "en") == "[happened: the night of the fire; told t0]"

    # No integer turn (carried, canon, or missing): leave the "told" part out.
    for no_turn in (
        {"when_happened": "4월 11일"},
        {"when_happened": "4월 11일", "turn": None},
        {"when_happened": "4월 11일", "turn": 5, "canon": "card"},
        {"when_happened": "4월 11일", "turn": True},
    ):
        assert inspector.happened_mark(no_turn, "ko") == "[일어난 때: 4월 11일]"
        assert inspector.happened_mark(no_turn, "en") == "[happened: 4월 11일]"


def test_happened_mark_escapes_html_and_ignores_empty():
    evil = {"when_happened": '<b>4월 11일</b> & "밤"', "turn": 7}
    ko = inspector.happened_mark(evil, "ko")
    en = inspector.happened_mark(evil, "en")
    assert "<b>" not in ko and "&lt;b&gt;4월 11일&lt;/b&gt; &amp; &quot;밤&quot;" in ko
    assert "<b>" not in en and "&lt;b&gt;4월 11일&lt;/b&gt; &amp; &quot;밤&quot;" in en

    for empty in ({}, {"turn": 5}, {"when_happened": None, "turn": 5}, {"when_happened": "", "turn": 5},
                  {"when_happened": "   ", "turn": 5}):
        assert inspector.happened_mark(empty, "ko") == ""
        assert inspector.happened_mark(empty, "en") == ""
