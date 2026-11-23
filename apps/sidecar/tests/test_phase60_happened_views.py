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


def _fact_row(**extra):
    return {"id": 10, "subject": "세라", "predicate": "event", "object": None, "value": "등대 화재",
            "turn": 12, "position": 12, "polarity": "positive", "knowledge": "public", "source": "story",
            "salience": "major", "versions": 1, **extra}


def _thread_row(**extra):
    return {"id": 20, "kind": "promise", "by": "세라", "to": "카이토", "text": "등대에서 만나기",
            "turn": 12, "position": 12, "status": "open", "closed_by": None, "restated": [], **extra}


def test_inspector_facts_rows_show_happened_mark_and_leave_others_identical():
    plain = _fact_row()
    dated = _fact_row(when_happened="4월 11일")
    evil = _fact_row(when_happened="<b>4월 11일</b>")
    carried = _fact_row(turn=None, when_happened="지난 겨울")

    for lang, want in (("ko", "[일어난 때: 4월 11일; t12에 말함]"), ("en", "[happened: 4월 11일; told t12]")):
        html = inspector._facts_rows([dated], None, lang)
        assert want in html
        assert "mono" not in html
        base = inspector._facts_rows([plain], None, lang)
        assert want not in base
        assert inspector._facts_rows([_fact_row(when_happened=None)], None, lang) == base
        assert inspector._facts_rows([_fact_row(when_happened="")], None, lang) == base

    esc = inspector._facts_rows([evil], None, "en")
    assert "<b>" not in esc and "[happened: &lt;b&gt;4월 11일&lt;/b&gt;; told t12]" in esc

    assert "[일어난 때: 지난 겨울]" in inspector._facts_rows([carried], None, "ko")
    assert "말함" not in inspector._facts_rows([carried], None, "ko")
    assert "[happened: 지난 겨울]" in inspector._facts_rows([carried], None, "en")
    assert "told" not in inspector._facts_rows([carried], None, "en")


def test_inspector_history_step_shows_happened_mark_and_leaves_others_identical():
    plain = {"predicate": "possesses", "subject": "하나", "object": "나침반", "value": None,
             "turn": 5, "position": 5, "polarity": "positive", "outcome": "current"}
    dated = {**plain, "when_happened": "the night of the fire"}
    evil = {**plain, "when_happened": "<i>어제</i>"}

    for lang, want in (("ko", "[일어난 때: the night of the fire; t5에 말함]"),
                       ("en", "[happened: the night of the fire; told t5]")):
        html = inspector._step(dated, lang)
        assert want in html and "mono" not in html
        base = inspector._step(plain, lang)
        assert want not in base
        assert inspector._step({**plain, "when_happened": None}, lang) == base
        assert inspector._step({**plain, "when_happened": ""}, lang) == base

    esc = inspector._step(evil, "ko")
    assert "<i>" not in esc and "[일어난 때: &lt;i&gt;어제&lt;/i&gt;; t5에 말함]" in esc


def test_inspector_threads_table_shows_happened_mark_and_leaves_others_identical():
    plain = _thread_row()
    dated = _thread_row(when_happened="4월 11일")
    evil = _thread_row(when_happened="<b>내일</b>")
    carried = _thread_row(turn=None, when_happened="봄")

    for lang, want in (("ko", "[일어난 때: 4월 11일; t12에 말함]"), ("en", "[happened: 4월 11일; told t12]")):
        html = inspector._threads_table([dated], lang)
        assert want in html and "mono" not in html
        base = inspector._threads_table([plain], lang)
        assert want not in base
        assert inspector._threads_table([_thread_row(when_happened=None)], lang) == base
        assert inspector._threads_table([_thread_row(when_happened="")], lang) == base

    esc = inspector._threads_table([evil], "en")
    assert "<b>" not in esc and "[happened: &lt;b&gt;내일&lt;/b&gt;; told t12]" in esc

    assert "[일어난 때: 봄]" in inspector._threads_table([carried], "ko")
    assert "[happened: 봄]" in inspector._threads_table([carried], "en")
    assert "told" not in inspector._threads_table([carried], "en")

