"""PHASE-60 S7: `[happened: …; told tN]` wherever a fact or a thread is listed (sidecar renderers)."""

from __future__ import annotations

import copy

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


def test_views_memory_shows_happened_mark_on_threads_and_facts_and_leaves_others_identical():
    from test_phase60_views_unchanged import memory_input

    plain = copy.deepcopy(memory_input())
    for lang in ("ko", "en"):
        base = views.memory(plain, lang)
        none_copy = copy.deepcopy(plain)
        none_copy["threads"][0] = {**none_copy["threads"][0], "when_happened": None}
        none_copy["secrets"][0] = {**none_copy["secrets"][0], "when_happened": ""}
        none_copy["changes"][0] = {**none_copy["changes"][0],
                                   "fact": {**none_copy["changes"][0]["fact"], "when_happened": None}}
        assert views.memory(none_copy, lang) == base

    dated = copy.deepcopy(plain)
    dated["threads"][0] = {**dated["threads"][0], "when_happened": "4월 11일"}
    dated["threads"][1] = {**dated["threads"][1], "when_happened": "<b>봄</b> & 밤"}
    dated["secrets"][0] = {**dated["secrets"][0], "when_happened": "the night of the fire"}
    dated["changes"][0] = {**dated["changes"][0],
                           "fact": {**dated["changes"][0]["fact"], "when_happened": "지난 주"}}
    dated["pairs"][0] = {**dated["pairs"][0],
                         "role": [{**dated["pairs"][0]["role"][0], "when_happened": "겨울"}]}

    ko = views.memory(dated, "ko")
    en = views.memory(dated, "en")
    assert "t12부터 · [일어난 때: 4월 11일; t12에 말함]" in ko
    assert "since t12 · [happened: 4월 11일; told t12]" in en
    assert "<b>" not in ko and "[일어난 때: &lt;b&gt;봄&lt;/b&gt; &amp; 밤; t3에 말함]" in ko
    assert "&amp;lt;" not in ko  # never double-escaped
    assert "t14 · [일어난 때: the night of the fire; t14에 말함]" in ko
    assert "t14 · [happened: the night of the fire; told t14]" in en
    assert "[일어난 때: 지난 주; t9에 말함]" in ko
    assert "[happened: 지난 주; told t9]" in en
    assert "[일어난 때: 겨울; t6에 말함]" in ko
    assert "[happened: 겨울; told t6]" in en


def test_views_person_shows_happened_mark_on_threads_and_timeline_events():
    from test_phase60_views_unchanged import person_input

    plain = copy.deepcopy(person_input())
    for lang in ("ko", "en"):
        base = views.person(plain, lang)
        none_copy = copy.deepcopy(plain)
        none_copy["threads"][0] = {**none_copy["threads"][0], "when_happened": None}
        none_copy["marks"][2] = (*none_copy["marks"][2], None)
        assert views.person(none_copy, lang) == base

    dated = copy.deepcopy(plain)
    dated["threads"][0] = {**dated["threads"][0], "when_happened": "4월 11일"}
    dated["marks"][2] = (*dated["marks"][2], {"when_happened": "the night of the fire", "turn": 9})
    dated["marks"][7] = (*dated["marks"][7], "<b>4월 10일</b>")

    ko = views.person(dated, "ko")
    en = views.person(dated, "en")
    assert "t12부터 · [일어난 때: 4월 11일; t12에 말함]" in ko
    assert "since t12 · [happened: 4월 11일; told t12]" in en
    assert "betrayed 카이토 [일어난 때: the night of the fire; t9에 말함]" in ko
    assert "betrayed 카이토 [happened: the night of the fire; told t9]" in en
    assert "<b>" not in ko and "the bell rang [일어난 때: &lt;b&gt;4월 10일&lt;/b&gt;; t27에 말함]" in ko

    # A 5-tuple row with explicit turn=None leaves out the told part; a 4-tuple without a row is untouched.
    no_turn = views._event((12, True, "등대 화재", "event", {"when_happened": "봄", "turn": None}), True, "en")
    assert "[happened: 봄]" in no_turn and "told" not in no_turn
    assert views._event((12, True, "등대 화재", "event", {}), True, "ko") == views._event((12, True, "등대 화재", "event"), True, "ko")


def test_timeline_shows_happened_mark_in_existing_attributes_and_card_only():
    import re
    from test_inspector_timeline import CONV, HANA, fact, panel_safe, step, view

    plain_state = fact(10, HANA, "has_status", [step(2, "건강함", "superseded", closed_turn=7),
                                                step(7, "부상", "current")], value="부상", turn=7)
    plain_event = fact(12, HANA, "event", None, value="등대 화재", turn=9, salience="major")
    plain_thread = {"id": 14, "kind": "promise", "by": "Hana", "to": "Kaito", "text": "등대에서 만나기",
                    "turn": 5, "position": 5, "status": "open", "closed_by": None, "restated": []}

    dated_state = fact(10, HANA, "has_status", [step(2, "건강함", "superseded", closed_turn=7),
                                                step(7, "부상", "current", when_happened="4월 11일")],
                       value="부상", turn=7)
    dated_event = fact(12, HANA, "event", None, value="등대 화재", turn=9, salience="major",
                       when_happened="the night of the fire")
    dated_thread = {**plain_thread, "when_happened": "<b>4월 12일</b>"}

    plain_view = view([plain_state, plain_event], [plain_thread])
    none_view = view(
        [fact(10, HANA, "has_status", [step(2, "건강함", "superseded", closed_turn=7),
                                       step(7, "부상", "current", when_happened=None)], value="부상", turn=7),
         fact(12, HANA, "event", None, value="등대 화재", turn=9, salience="major", when_happened="")],
        [{**plain_thread, "when_happened": None}],
    )
    dated_view = view([dated_state, dated_event], [dated_thread])

    for lang in ("ko", "en"):
        base_browser = inspector.character(CONV, "e1", plain_view, None, lang=lang, now=12)
        base_panel = inspector.character_timeline(CONV, "e1", plain_view, lang, now=12)
        assert inspector.character(CONV, "e1", none_view, None, lang=lang, now=12) == base_browser
        assert inspector.character_timeline(CONV, "e1", none_view, lang, now=12) == base_panel

        browser = inspector.character(CONV, "e1", dated_view, None, lang=lang, now=12)
        panel = inspector.character_timeline(CONV, "e1", dated_view, lang, now=12)
        panel_safe(panel)  # fixed MARK_TEXT allowlist: no new data-* attribute

        state_mark = "[일어난 때: 4월 11일; t7에 말함]" if lang == "ko" else "[happened: 4월 11일; told t7]"
        event_mark = ("[일어난 때: the night of the fire; t9에 말함]" if lang == "ko"
                      else "[happened: the night of the fire; told t9]")
        thread_mark = ("[일어난 때: &lt;b&gt;4월 12일&lt;/b&gt;; t5에 말함]" if lang == "ko"
                       else "[happened: &lt;b&gt;4월 12일&lt;/b&gt;; told t5]")
        now_word = "현재" if lang == "ko" else "now"

        # Selected state bar card + data-s
        card = browser.split('class="tl-card"', 1)[1].split("</div>", 1)[0]
        assert f"t7 – {now_word} · {state_mark}" in card
        assert f'data-s="t7 – {now_word} · {state_mark}"' in browser
        assert f'data-s="t7 – {now_word} · {state_mark}"' in panel

        # Event dot data-s
        assert f'data-s="t9 · {event_mark}"' in browser
        assert f'data-s="t9 · {event_mark}"' in panel

        # Thread bar data-s (escaped)
        assert "<b>4월 12일</b>" not in browser and "<b>4월 12일</b>" not in panel
        assert f'data-s="t5 – {now_word} · {thread_mark}"' in browser
        assert f'data-s="t5 – {now_word} · {thread_mark}"' in panel

    # Oversized when_happened in data-s stays within DATA_MAX so the panel sanitizer never drops it.
    long_ev = fact(13, HANA, "event", None, value="화재", turn=9, when_happened="가" * 500)
    long_panel = inspector.character_timeline(CONV, "e1", view([long_ev]), "ko", now=12)
    panel_safe(long_panel)
    data_s = re.search(r'data-s="([^"]+)"', long_panel).group(1)
    assert len(data_s) <= 300


def test_end_to_end_when_happened_reaches_inspector_and_views(migrated):
    """A stub-extracted event with `when_happened` set in SQL reaches the Inspector chat/character pages and timeline."""
    import psycopg
    from conftest import make_client
    from memeval import stub_extractor
    from simchat import SimChat
    from test_extraction import drain
    from test_generations import LLM
    from test_sidecar_integration import sync

    chat = SimChat("phase60-happened-e2e")
    for line in ("Hana is in the harbor.", "Hana betrayed Kaito.",
                 'Hana says to Kaito: "I promise to meet you at the lighthouse."'):
        chat.user(line)
        chat.reply("Noted.")
    chat.user("next")

    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        drain(migrated, stub_extractor)
        with psycopg.connect(migrated, autocommit=True) as conn:
            row = conn.execute(
                "UPDATE assertion SET when_happened = %s WHERE predicate = 'event' RETURNING id",
                ("4월 11일",),
            ).fetchone()
            assert row is not None
        cid = c.get("/v1/views/hub", params={"chat": chat.id}).json()["conversation"]
        hana = next(e["id"] for e in c.get(f"/v1/conversations/{cid}/entities").json() if e["name"] == "Hana")

        for lang, want in (("ko", "[일어난 때: 4월 11일; t1에 말함]"), ("en", "[happened: 4월 11일; told t1]")):
            mem = c.get(f"/v1/views/c/{cid}/memory", params={"lang": lang})
            assert mem.status_code == 200 and 'id="s-open"' in mem.json()["html"]
            insp = c.get(f"/v1/inspector/c/{cid}", params={"lang": lang})
            assert insp.status_code == 200 and want in insp.json()["html"]
            char = c.get(f"/inspector/c/{cid}/e/{hana}", params={"lang": lang})
            assert char.status_code == 200
            assert want in char.text and f'data-s="t1 · {want}"' in char.text


def test_person_sheet_timeline_event_shows_happened_mark_through_person_data(migrated):
    """The person sheet built by the real `person_data` carries `when_happened` to its timeline event lines; an event
    without one shows no mark."""
    import re

    import psycopg
    from conftest import make_client
    from memeval import stub_extractor
    from simchat import SimChat
    from test_extraction import drain
    from test_generations import LLM
    from test_sidecar_integration import sync

    chat = SimChat("phase60-happened-person")
    for line in ("Hana is in the harbor.", "Hana betrayed Kaito.", "Hana betrayed Yuna."):
        chat.user(line)
        chat.reply("Noted.")
    chat.user("next")

    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        drain(migrated, stub_extractor)
        with psycopg.connect(migrated, autocommit=True) as conn:
            rows = conn.execute("SELECT id, value FROM assertion WHERE predicate = 'event' ORDER BY id").fetchall()
            dated = next(r for r in rows if "Kaito" in str(r[1]))
            assert any("Yuna" in str(r[1]) for r in rows)
            conn.execute("UPDATE assertion SET when_happened = %s WHERE id = %s", ("4월 11일", dated[0]))
        cid = c.get("/v1/views/hub", params={"chat": chat.id}).json()["conversation"]
        hana = next(e["id"] for e in c.get(f"/v1/conversations/{cid}/entities").json() if e["name"] == "Hana")

        for lang, mark, word in (("ko", "[일어난 때: 4월 11일; t", "[일어난 때:"), ("en", "[happened: 4월 11일; told t", "[happened:")):
            person = c.get(f"/v1/views/c/{cid}/person/{hana}", params={"lang": lang})
            assert person.status_code == 200
            events = re.findall(r'<div class="v-ev[^"]*">.*?</div>', person.json()["html"])
            kaito = [e for e in events if "betrayed Kaito" in e]
            yuna = [e for e in events if "betrayed Yuna" in e]
            assert kaito and yuna
            assert all(mark in e for e in kaito)
            assert not any(word in e for e in yuna)




