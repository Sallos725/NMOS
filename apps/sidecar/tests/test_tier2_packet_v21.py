"""PHASE-63 Wave 2: `packet-v21`, every addition gated on V21_POLICIES, and `clean_text_v4` (clean-v4, unused yet).

Each test checks the packet-v21 behaviour and, beside it, that packet-v20 (and earlier) still does what it did: the
replay invariant (ADR 0027). Synthetic names and text only.
"""

from __future__ import annotations

import dataclasses
import uuid
from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import audit, packet, retrieval
from nmos_sidecar.entities import norm, resolve
from nmos_sidecar.facts import fact_entry
from nmos_sidecar.packet import (DEFAULT_POLICY, NON_ASCII, POLICIES, PRIVATE_NOTE, V21_POLICIES, Excerpt, Line,
                                 StateItem, clean_text, clean_text_v4, compile_lines)
from nmos_sidecar.retrieval import (Gathered, RecallOptions, Shown, appearances, cast_groups, closing_marks,
                                    entry_v21, fact_pool_v21, feeling_inline, gate_excerpts_v21, gate_state_v21,
                                    gone_rows, persona_threads, pinned_characters, quiet_feeling, rerank_doc,
                                    reranked_above, settled_lines, title_aliases, told_lines)
from test_semantics import row

V20 = RecallOptions(policy="packet-v20")
V21 = RecallOptions(policy="packet-v21")
C = {"subject_type": "character"}
CC = {"subject_type": "character", "object_type": "character"}


def view_of(facts=(), claims=(), other=(), threads=(), excluded=None, **more) -> dict:
    return {"facts": list(facts), "claims": list(claims), "other": list(other), "threads": list(threads),
            "excluded": excluded or {}, **more}


def res(rows, persona=("타쿠미",)):
    return resolve(uuid.UUID(int=7), list(rows), persona=list(persona))


# --- registration -----------------------------------------------------------------------------------------------------


def test_v21_joins_every_set_v20_is_in_and_the_default_stays():
    assert POLICIES[-1] == "packet-v21" and NON_ASCII["packet-v21"] == 1.2
    assert V21_POLICIES == frozenset({"packet-v21"}) and DEFAULT_POLICY == "packet-v19"
    for name in dir(packet):
        value = getattr(packet, name)
        if name.endswith("_POLICIES") and isinstance(value, frozenset) and "packet-v20" in value:
            assert "packet-v21" in value, name
    assert "packet-v21" in packet._V8


# --- packet.py: compile order -----------------------------------------------------------------------------------------


def _line(kind: str, xml: str, n: int, private: bool = False) -> Line:
    return Line(kind, xml, {"assertion": n}, n, f"H{n}: {xml}", xml[-20:], {}, private)


WALK = "하나와 카이토가 숲길을 걸었다. " * 4
SCENE = Line("summary", f'    <Summary kind="scene" turns="1-9">{WALK}</Summary>', {"summary": 1}, None, "scene", "scene")
STORY = Line("summary", f'    <Summary kind="story">{WALK}</Summary>', {"summary": 2}, None, "story", "story")
# a sim bot's status window: the state takes its share before <Story>, and lead and Private get what is left
STATUS = [StateItem(f"상태{i}", "체력 가득, 기분 좋음, 날씨 맑음", 1) for i in range(8)]
LEAD = _line("fact", '    <Fact kind="addresses" turn="3">하나 addresses 카이토: 반말, \'카이토\'라고 부름</Fact>', 3)
SECRET = _line("fact", '    <Fact kind="knows" turn="4" known_by="하나" hidden_from="카이토">하나 knows: 열쇠는 우물 속에 있다'
               '</Fact>', 4, private=True)


@pytest.mark.parametrize("budget", [520, 525])
def test_a_scene_summary_yields_to_lead_and_private_lines_under_v21_only(budget):
    v21 = compile_lines([], budget, state=STATUS, facts=[SECRET], lead=[LEAD], story=[SCENE], policy="packet-v21")
    assert "열쇠는 우물" in v21.text and "반말" in v21.text and '<Summary kind="scene"' not in v21.text
    v20 = compile_lines([], budget, state=STATUS, facts=[SECRET], lead=[LEAD], story=[SCENE], policy="packet-v20")
    assert '<Summary kind="scene"' in v20.text and "열쇠는 우물" not in v20.text  # v20: the summary starved them
    entry = next(e for e in v21.ledger if e["kind"] == "summary")
    assert not entry["placed"] and entry["why"] == "budget"  # left out for the budget: the panel's fit sees it
    # the output order is the same: <Story> first, then Facts, then Private
    roomy = compile_lines([], 4000, facts=[SECRET], lead=[LEAD], story=[SCENE], policy="packet-v21").text
    assert roomy.index("<Story>") < roomy.index("<Facts>") < roomy.index("<Private>")


def test_the_story_so_far_keeps_its_place_under_v21():
    out = compile_lines([], 520, state=STATUS, facts=[SECRET], lead=[LEAD], story=[STORY], policy="packet-v21")
    assert '<Summary kind="story"' in out.text
    assert out.text == compile_lines([], 520, state=STATUS, facts=[SECRET], lead=[LEAD], story=[STORY],
                                     policy="packet-v20").text


def _ex(n: int, text: str, **kw) -> Excerpt:
    return Excerpt(turn=n, speaker="하나", text=text, score=1.0 / (n + 1), revision_id=f"r{n}",
                   **{"short": text[:30], "position": n, **kw})


QUOTE = _ex(1, "“" + "우리는 등대 아래에서 다시 만나기로 약속했잖아, 잊지 마. " * 5 + "”", quote=True, cut_ok=False,
            short="")
NORMAL = _ex(2, "그날 밤 하나는 등대지기에게서 열쇠를 받아 품에 넣었다. 바람이 거셌다.")
FILLER = [_line("fact", f'    <Fact kind="event" turn="{n}">카이토 event: 항구에서 그물을 손질했다 {n}</Fact>', n)
          for n in range(10, 30)]


def test_a_long_quote_keeps_the_excerpt_reserve_under_v21():
    v21 = compile_lines([QUOTE, NORMAL], 420, facts=FILLER, policy="packet-v21")
    assert "열쇠를 받아" in v21.text
    v20 = compile_lines([QUOTE, NORMAL], 420, facts=FILLER, policy="packet-v20")
    assert "열쇠를 받아" not in v20.text  # v20: the quote's share collapsed the reserve to 0
    required = [e for e in v21.ledger if e["kind"] == "excerpt" and e.get("label") == "required"]
    assert [e["ref"]["revision"] for e in required] == ["r2"]


def test_a_fenced_excerpt_goes_to_private_with_its_marks_under_v21_only():
    fenced = dataclasses.replace(NORMAL, known_by=("하나",), hidden_from=("카이토",))
    out = compile_lines([fenced], 2000, policy="packet-v21").text
    private = out.split("<Private>", 1)[1].split("</Private>", 1)[0]
    assert 'known_by="하나" hidden_from="카이토"' in private and "열쇠를 받아" in private
    assert PRIVATE_NOTE in out
    plain = compile_lines([fenced], 2000, policy="packet-v20").text
    assert "<Private>" not in plain and 'hidden_from="' not in plain and "열쇠를 받아" in plain
    assert plain == compile_lines([NORMAL], 2000, policy="packet-v20").text


# --- packet.py: clean-v4 ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["<마검 발뭉>을 뽑았다.", "<신탁: 붉은 별이 떨어진다>", "<시스템: 카일 사망>",
                                  "<속삭임: 도망쳐>"])
def test_clean_v4_keeps_unicode_angle_bracket_prose(text):
    assert clean_text_v4(text) == text
    assert clean_text(text) != text  # clean-v3 is unchanged: it still drops them


def test_clean_v4_keeps_table_cells_apart():
    html = "<table><tr><th>위치</th><td>북부 성채</td></tr></table>"
    assert clean_text_v4(html) == "위치 북부 성채"
    assert clean_text(html) == "위치북부 성채"


def test_clean_v4_drops_more_reasoning_and_ooc_blocks():
    assert clean_text_v4("<reasoning>plan</reasoning>그가 웃었다. <ooc>잠깐 쉴게요</ooc>") == "그가 웃었다."
    assert clean_text_v4("<scratchpad>x</scratchpad><cot>y</cot>끝.") == "끝."
    assert clean_text_v4("<think>a</think>이야기") == "이야기"


def test_clean_v4_unclosed_leading_reasoning_is_cut_only_to_a_blank_line():
    assert clean_text_v4("<think>먼저 상황을 정리하자\n둘째 줄\n\n하나가 문을 열었다.") == "하나가 문을 열었다."
    assert clean_text_v4("<thinking>닫히지 않은 한 덩어리") == "닫히지 않은 한 덩어리"  # no blank line: tag only
    assert clean_text_v4("하나가 말했다. <think> 그리고\n\n계속") == "하나가 말했다. 그리고\n계속"  # not at the start


def test_clean_v4_drops_more_of_nmos_markup():
    assert clean_text_v4('<Summary kind="scene">요약</Summary>뒤') == "뒤"
    assert clean_text_v4('<Secret holders="하나">x</Secret><Quote turn="2">말</Quote>뒤') == "뒤"
    assert clean_text_v4('<StateHistory key="HP"><At turn="1">30</At></StateHistory>뒤') == "뒤"
    assert clean_text_v4('<Regression remembered_by="하나">    <Fact kind="x">y</Fact></Regression>뒤') == "뒤"
    assert clean_text('<StateHistory key="HP"><At turn="1">30</At></StateHistory>뒤') == "30뒤"  # v3 as it was


# --- fact lines: feeling, secret clauses ------------------------------------------------------------------------------


FEEL = row(5, "하나", "feels_toward", "카이토", "애틋함", **CC,
           feeling={"intensity": "strong", "valence": "positive",
                    "under": {"value": "원망", "intensity": "faint", "valence": "negative"}})


def test_the_feeling_detail_is_inline_under_v21_only():
    assert feeling_inline(FEEL) == " [strong, positive; under: 원망 (faint, negative)]"
    assert feeling_inline({**FEEL, "feeling": {"intensity": "loud", "valence": None}}) == ""
    assert feeling_inline({**FEEL, "predicate": "relationship"}) == ""
    line = entry_v21(FEEL, False, True, True, False, Shown())
    assert line.xml.endswith("하나 feels toward 카이토: 애틋함 [strong, positive; under: 원망 (faint, negative)]</Fact>")
    plain = fact_entry(FEEL, False, True, True, False)
    assert (line.text, line.content, line.ref) == (plain.text, plain.content, plain.ref)
    assert entry_v21(FEEL, False, True, True, False, None) == plain


SECRETS = [{"holders": ["하나"], "open": ["카이토"], "text": "하나 knows: 열쇠는 우물 속에 숨겨져 있다"}]


def test_a_public_line_drops_a_cause_that_says_a_secret_to_someone_present():
    f = row(6, "하나", "has_status", None, "초조함", **C, because="열쇠는 우물 속에 숨겨져 있다")
    present = frozenset({"카이토", "하나"})
    assert "because" not in entry_v21(f, False, False, True, False, Shown(SECRETS, present)).xml
    assert "because: 열쇠는" in entry_v21(f, False, False, True, False, Shown(SECRETS, frozenset({"하나"}))).xml
    assert "because: 열쇠는" in entry_v21(f, True, False, True, False, Shown(SECRETS, present)).xml  # private: kept
    assert "because: 열쇠는" in fact_entry(f, False, False, True, False).xml  # v20 as it was


def test_a_disputed_clause_that_says_a_secret_is_dropped_too():
    against = row(7, "하나", "located_in", "열쇠는 우물 속에 숨겨져 있다", None, **C)
    f = row(8, "하나", "located_in", "광장", None, **C, disputed_by=against)
    out = entry_v21(f, False, False, False, False, Shown(SECRETS, frozenset({"카이토"}))).xml
    assert "but turn" not in out and "disputed" not in out


# --- <Cast> -------------------------------------------------------------------------------------------------------------


def test_cast_holds_peer_feelings_addresses_and_the_persona_under_v21():
    rows = [row(1, "하나", "feels_toward", "카이토", "질투", **CC), row(2, "하나", "addresses", "{{user}}", "존댓말", **CC),
            row(3, "하나", "located_in", "광장", None, **C, object_type="place"),
            row(4, "{{user}}", "has_status", None, "다리 부상", **C), row(5, "{{user}}", "possesses", "가면", None, **C,
                                                                     object_type="item")]
    r = res(rows)
    cast = {r.key("character", n): n for n in ("하나", "카이토", "{{user}}")}
    v21, used21 = cast_groups(view_of(rows), cast, r, "", V21, shown_v21=Shown())
    v20, used20 = cast_groups(view_of(rows), cast, r, "", V20)
    groups = dict(v21)
    assert [line.ref["assertion"] for line in groups["하나"]] == [3, 1, 2]
    persona_group = [g for name, g in v21 if name not in ("하나", "카이토")]
    assert [[line.ref["assertion"] for line in g] for g in persona_group] == [[4, 5]]
    assert [line.ref["assertion"] for line in dict(v20)["하나"]] == [3]  # v20: place only, no persona group
    assert used20 == {3} and used21 == {1, 2, 3, 4, 5}


# --- gone and appearances ------------------------------------------------------------------------------------------------


def chosen(rows, now=20, policy_v21=True, **more):
    view = view_of(rows, **more)
    r = res(view["facts"] + view["claims"] + view["other"])
    return [f["subject"] for f in (gone_rows(view, r, now, v21=True) if policy_v21 else gone_rows(view, r, now))]


DEAD = row(10, "세라", "has_status", None, "사망", **C)


def test_a_mourners_feeling_or_a_dream_does_not_bring_the_dead_back_under_v21():
    mourning = row(18, "카이토", "feels_toward", "세라", "그리움", **CC)
    assert chosen([DEAD, mourning]) == ["세라"]
    assert chosen([DEAD, mourning], policy_v21=False) == []  # v20: the object row brought her back
    dream = row(19, "세라", "event", None, "꿈에 나타났다", **C, modality="dreamed")
    assert chosen([DEAD], other=[dream]) == ["세라"]
    flashback = row(19, "세라", "event", None, "웃었다", **C, when_happened="3년 전")
    assert chosen([DEAD, flashback]) == ["세라"]


def test_a_return_long_ago_still_holds_under_v21():
    back = row(12, "세라", "event", None, "되살아나 일어섰다", **C)
    assert chosen([DEAD, back], now=30) == []
    assert chosen([DEAD, back], now=30, policy_v21=False) == ["세라"]  # v20: outside the two-turn window, dead again


def test_a_carried_death_stays_pinned_under_v21_only():
    carried = {**row(-5, "세라", "has_status", None, "사망", **C), "turn": -1, "carried": "link-1"}
    assert chosen([carried]) == ["세라"]
    assert chosen([carried], policy_v21=False) == []


def test_a_rumour_is_no_appearance_under_v21():
    rows = [row(2, "세라", "located_in", "광장", None, **C, object_type="place"),
            row(15, "카이토", "event", None, "세라 얘기를 했다", **C,
                participants=[{"name": "세라", "type": "character"}])]
    view = view_of(rows)
    r = res(rows)
    k = r.key("character", "세라")
    assert appearances(view, r, v21=True)[k] == [2]
    assert appearances(view, r)[k] == [2, 15]


# --- threads: settled, persona, told ------------------------------------------------------------------------------------


def _thread(n, by, to, status="open", kind="promise", **kw):
    return {"id": 100 + n, "position": n, "turn": n, "host_logical_id": f"t{n}", "kind": kind, "by": by, "to": to,
            "text": "등대에서 만나기", "status": status, "closed_by": None, "knowledge": None, "known_by": None,
            "hidden_from": None, **kw}


def test_a_promise_broken_in_secret_is_private_under_v21():
    t = _thread(5, "하나", "카이토", "broken",
                closed_by={"turn": 9, "position": 9, "knowledge": "limited", "known_by": ["하나"],
                           "hidden_from": ["카이토"]})
    assert closing_marks(t)["hidden_from"] == ["카이토"] and closing_marks(t)["knowledge"] == "limited"
    assert closing_marks(_thread(5, "하나", "카이토")) == _thread(5, "하나", "카이토")
    r = res([row(1, "하나", "event", None, "x", **C), row(2, "카이토", "event", None, "y", **C)])
    g = Gathered()
    g.cast = {r.key("character", n): n for n in ("하나", "카이토")}
    [v21] = settled_lines(g, view_of(threads=[t]), r, "", 10, frozenset(), V21)
    [v20] = settled_lines(g, view_of(threads=[t]), r, "", 10, frozenset(), V20)
    assert v21.private and 'hidden_from="카이토"' in v21.xml
    assert not v20.private and "hidden_from" not in v20.xml


def test_the_personas_settled_and_open_threads_are_included_under_v21():
    r = res([row(1, "하나", "event", None, "x", **C)])
    goal = _thread(6, "{{user}}", None, "kept", kind="goal",
                   closed_by={"turn": 9, "position": 9, "knowledge": None, "known_by": None, "hidden_from": None})
    g = Gathered()
    assert len(settled_lines(g, view_of(threads=[goal]), r, "", 10, frozenset(), V21)) == 1
    assert settled_lines(g, view_of(threads=[goal]), r, "", 10, frozenset(), V20) == []
    open_goal = _thread(7, "{{user}}", None, kind="goal", text="왕국을 되찾는다")
    assert persona_threads([open_goal], r, "내 목표가 뭐였지?", set(), [], set()) == [open_goal]
    assert persona_threads([open_goal], r, "하나는 어디 있어?", set(), [], set()) == []


def test_told_counts_whom_it_is_about_and_gates_only_for_someone_present():
    told = {**row(8, "하나", "told", "레오", "열쇠는 우물 속에 숨겨져 있다", **CC), "evidence": "",
            "participants": [{"name": "세라", "type": "character"}]}
    r = res([told, row(1, "세라", "event", None, "x", **C), row(2, "카이토", "event", None, "x", **C)])
    view = view_of(told=[told], secrets=SECRETS)
    g = Gathered()
    g.cast = {r.key("character", "세라"): "세라"}  # only the one it is about is here
    assert len(told_lines(g, view, r, "", "", set(), V21)) == 1
    assert told_lines(Gathered(cast=dict(g.cast)), view, r, "", "", set(), V20) == []  # v20: not involved
    g = Gathered()
    g.cast = {r.key("character", "카이토"): "카이토", r.key("character", "하나"): "하나"}  # the one kept from is here
    assert told_lines(g, view, r, "", "", set(), V21) == []
    alone = Gathered()
    alone.cast = {r.key("character", "하나"): "하나", r.key("character", "레오"): "레오"}
    assert len(told_lines(alone, view, r, "", "", set(), V21)) == 1  # holders alone: told
    assert told_lines(Gathered(cast=dict(alone.cast)), view, r, "", "", set(), V20) == []  # v20 self-censored


# --- strict mode: a quiet feeling stays readable -------------------------------------------------------------------------


def test_strict_mode_keeps_an_unspoken_feeling_readable_under_v21_only():
    quiet = row(9, "하나", "feels_toward", "카이토", "짝사랑", **CC, knowledge="limited", known_by=["하나"])
    plotted = {**quiet, "id": 10, "hidden_from": ["카이토"]}
    assert quiet_feeling(quiet) and not quiet_feeling(plotted) and not quiet_feeling({**quiet, "timeline": "previous"})
    r = res([quiet])
    cast = {r.key("character", n): n for n in ("하나", "카이토")}
    for opts, readable in ((dataclasses.replace(V21, strict=True), True), (dataclasses.replace(V20, strict=True), False)):
        g = Gathered()
        g.cast = dict(cast)
        out = retrieval._moded([fact_entry(quiet, True)], [quiet], g, r, opts)
        assert (out[0].kind == "fact") is readable
        g = Gathered()
        g.cast = dict(cast)
        assert retrieval._moded([fact_entry(plotted, True)], [plotted], g, r, opts)[0].kind == "secret"


# --- names: titles, pins ------------------------------------------------------------------------------------------------


def test_a_title_the_persona_uses_points_to_one_character_under_v21():
    rows = [row(1, "{{user}}", "addresses", "백이안", "존댓말, '선배'라고 부름", **CC),
            row(2, "하나", "role_toward", "{{user}}", "사장: 가게 주인", **CC),
            row(3, "{{user}}", "addresses", "카이토", "반말, '카이토'라고 부름", **CC)]
    r = res(rows)
    assert title_aliases(view_of(rows), r) == {"선배": "백이안", "사장": "하나"}  # a name is no title
    shared = rows + [row(4, "{{user}}", "addresses", "레오", "존댓말, '선배'라고 부름", **CC)]
    assert "선배" not in title_aliases(view_of(shared), res(shared))
    v21 = retrieval._aliases(r, "선배, 아까 그 일 어떻게 됐어?", "", V21, view_of(rows), {})
    v20 = retrieval._aliases(r, "선배, 아까 그 일 어떻게 됐어?", "", V20, view_of(rows), {})
    assert "선배" in v21[norm("백이안")] and "선배" not in (v20 or {}).get(norm("백이안"), frozenset())


def test_an_at_mention_of_a_variant_pins_under_v21():
    rows = [row(1, "백이안", "event", None, "x", **C)]
    r = res(rows)
    aliases = {norm("백이안"): frozenset({"이안"})}
    opts21 = dataclasses.replace(V21, pin_at_mentions=True)
    assert [p["name"] for p in pinned_characters(view_of(rows), r, "@이안 왔어?", opts21, None, aliases)] == ["백이안"]
    opts20 = dataclasses.replace(V20, pin_at_mentions=True)
    assert pinned_characters(view_of(rows), r, "@이안 왔어?", opts20) == []


# --- facts: when it happened, the history cue ----------------------------------------------------------------------------


def test_when_happened_and_history_stand_ins():
    winter = row(4, "하나", "event", None, "성을 떠났다", **C, when_happened="3년 전 겨울")
    pool, back = fact_pool_v21([winter], "3년 전 겨울에 무슨 일이 있었어?", set(), None, False)
    assert "3년 전 겨울" in pool[0]["value"] and back[id(pool[0])] is winter and winter["value"] == "성을 떠났다"
    pool, back = fact_pool_v21([winter], "하나 뭐 해?", set(), None, False)
    assert pool == [winter] and back == {}


# --- rerank -------------------------------------------------------------------------------------------------------------


def test_the_reranker_reads_the_matched_chunk_and_its_top_clears_the_floor():
    text = "가" * 2000 + "등대의 열쇠" + "나" * 2000
    c = {"clean": text, "text_start": 2000, "text_end": 2006}
    doc = rerank_doc(c)
    assert "등대의 열쇠" in doc and len(doc) <= 1000
    assert rerank_doc({"clean": text}) == text[:1000]
    assert reranked_above([{"id": 1, "rerank": 0.9}, {"id": 2, "rerank": 0.5}, {"id": 3, "rerank": 0.1}]) \
        == frozenset({"1", "2"})
    assert reranked_above([{"id": 1, "rerank": 3.0}, {"id": 2, "rerank": -1.0}]) == frozenset({"1"})
    assert reranked_above([{"id": 1}]) == frozenset()


# --- secret gates on excerpts and state -----------------------------------------------------------------------------------


LEAKY = _ex(3, "하나는 열쇠는 우물 속에 숨겨져 있다고 혼잣말을 했다.")


def test_an_excerpt_that_says_a_secret_is_fenced_or_withheld_by_mode():
    present = frozenset({"하나", "카이토"})
    g = Gathered(ranked=[LEAKY, NORMAL])
    gate_excerpts_v21(g, SECRETS, present, set(), V21)
    assert g.ranked[0].hidden_from == ("카이토",) and g.ranked[0].known_by == ("하나",) and g.excerpts_fenced == 1
    assert g.ranked[1].hidden_from == ()
    for mode in ({"strict": True}, {"narrator": "하나"}):
        g = Gathered(ranked=[LEAKY, NORMAL])
        gate_excerpts_v21(g, SECRETS, present, set(), dataclasses.replace(V21, **mode))
        assert [e.revision_id for e in g.ranked] == ["r2"] and g.excerpts_withheld == 1
        assert g.hidden_entries[0]["why"] == "secret_gate"
    g = Gathered(ranked=[LEAKY])
    gate_excerpts_v21(g, SECRETS, frozenset({"하나"}), set(), V21)  # the one it is kept from is not here
    assert g.ranked[0].hidden_from == ()


def test_a_state_value_that_says_a_secret_is_withheld():
    g = Gathered(state=[StateItem("메모", "열쇠는 우물 속에 숨겨져 있다", 3), StateItem("HP", "30", 3)])
    gate_state_v21(g, SECRETS, frozenset({"카이토"}), V21)
    assert [i.key for i in g.state] == ["HP"] and g.state_withheld == 1


# --- end to end (stub model, test database) --------------------------------------------------------------------------


def test_speakers_of_an_earlier_generation_are_read_under_v21(migrated):
    from test_extract_v17 import extracted
    extracted(migrated, "extract-v17")
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        x = conn.execute("SELECT members, extractor_key FROM extraction WHERE speakers IS NOT NULL").fetchone()
        ids = list(x["members"])
        assert retrieval._quote_speakers(conn, ids, "extract-other") == {}  # v20: another generation in use, none
        got = retrieval._quote_speakers(conn, ids, "extract-other", any_generation=True)
        assert got[norm("알았어, 늦지 마.")] == "카이토"
        assert got == retrieval._quote_speakers(conn, ids, x["extractor_key"])


@pytest.mark.parametrize("policy", ["packet-v21", "packet-v20"])
def test_a_v21_request_runs_end_to_end_and_records_its_gates(migrated, policy):
    from test_phase60_gone import ask, story
    from test_generations import LLM
    with make_client(migrated, packet_policy=policy, **LLM) as c:
        chat = story(c, migrated, "세라의 상태: 전투 중 전사.")
        out = ask(c, migrated, chat, "오늘은 날씨가 맑네.")
        text = out["packet"]["text"]
        trace = c.get(f"/v1/trace/{out['trace_id']}").json()
    assert trace["policy"] == policy and 'gone="true"' in text
    assert ("secret_gate" in trace["recall_options"]) is (policy == "packet-v21")
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        again = audit.replay(conn, UUID(out["trace_id"]), RecallOptions(), policy=None)
    assert again["status"] == "ok" and again["text"] == text


# --- review follow-ups: more of each item ----------------------------------------------------------------------------


def test_a_death_confirmed_later_or_a_negated_presence_keeps_the_pin_under_v21():
    confirmed = row(14, "세라", "vital_status", None, "사망", **C)
    assert chosen([DEAD, confirmed], now=30) == ["세라"]
    destroyed = row(15, "세라", "destroyed", None, None, **C)
    assert chosen([DEAD, destroyed], now=30) == ["세라"]
    absent = row(16, "세라", "located_in", "광장", None, **C, object_type="place", polarity="negative")
    assert chosen([DEAD, absent], now=30) == ["세라"]


def test_a_replaced_value_counts_only_in_an_excerpt_about_its_subject_under_v21():
    old = row(3, "하나", "has_status", None, "감기", **C, outcome="superseded")
    now = row(10, "하나", "has_status", None, "회복함", **C, history=[old])
    r = res([now, row(2, "카이토", "event", None, "x", **C)])
    view = view_of([now], resolution=r)
    for opts, other_dropped in ((V21, False), (V20, True)):
        stale = retrieval._replaced_judge(view, [now], "오늘 뭐 해?", "", opts, {})
        assert stale("하나는 감기에 걸려 누워 있었다.", 5)
        assert stale("카이토는 감기에 걸려 누워 있었다.", 5) is other_dropped


def test_the_history_cue_keeps_a_standing_fact_whose_history_is_before_the_window():
    was = row(2, "하나", "addresses", "카이토", "존댓말", **CC)
    f = {**row(20, "하나", "addresses", "카이토", "반말", **CC), "history": [was]}
    pool, back = fact_pool_v21([f], "전에 하나가 카이토를 어떻게 불렀어?", {"m20"}, 15, False)
    assert pool[0]["host_logical_id"] is None and back[id(pool[0])] is f
    pool, _ = fact_pool_v21([f], "전에 하나가 카이토를 어떻게 불렀어?", {"m20"}, 1, False)  # history in the window
    assert pool == [f]


def test_standing_facts_and_settled_threads_never_rest_under_v21():
    standing = row(5, "하나", "addresses", "카이토", "반말", **CC)
    event = row(6, "하나", "event", None, "걸었다", **C)
    rest = frozenset({("fact", "5"), ("fact", "6"), ("thread", "105")})
    assert retrieval._rested([standing, event], "fact", rest, Gathered(), v21=True) == [standing]
    assert retrieval._rested([standing, event], "fact", rest, Gathered()) == []
    t = _thread(5, "하나", "카이토", "kept")
    assert retrieval._rested([t], "thread", rest, Gathered(), v21=True, settled=True) == [t]
    assert retrieval._rested([t], "thread", rest, Gathered(), v21=True) == []


def test_the_v21_scene_reads_four_turns_and_never_an_excluded_entity():
    rows = [row(16, "하나", "event", None, "x", **C), row(18, "카이토", "event", None, "y", **C),
            row(19, "등대", "event", None, "z", **C)]
    r = res(rows)
    view = view_of(rows, excluded={str(r.key("character", "등대")): {"scope": "cast"}})
    v21 = set(retrieval._scene_cast(view, r, "", "", 20, None, V21).values())
    v20 = set(retrieval._scene_cast(view, r, "", "", 20, None, V20).values())
    assert "하나" in v21 and "카이토" in v21 and "등대" not in v21
    assert "하나" not in v20 and "등대" in v20


def test_a_closed_regression_thread_is_remembered_under_v21_only():
    kept = {**_thread(3, "하나", "카이토", "kept"), "line": "thread", "names": ["하나", "카이토"],
            "known_by": ["하나"], "knowledge": "limited"}
    r = res([row(1, "하나", "event", None, "x", **C)])
    view = view_of(regression=[kept])
    g = Gathered()
    assert len(retrieval.regression_lines(g, view, r, "하나랑 한 약속 기억나?", "", set(), V21)) == 1
    assert retrieval.regression_lines(Gathered(), view, r, "하나랑 한 약속 기억나?", "", set(), V20) == []


def test_a_title_names_the_facts_so_the_question_is_not_small_talk():
    from nmos_sidecar.facts import relevant_facts
    rows = [row(1, "{{user}}", "addresses", "백이안", "존댓말, '선배'라고 부름", **CC),
            row(2, "백이안", "event", None, "서류를 정리했다", **C)]
    r = res(rows)
    q = "선배, 아까 그 일 어떻게 됐어?"
    for opts, small_talk in ((V21, False), (V20, True)):
        aliases = retrieval._aliases(r, q, "", opts, view_of(rows), {})
        named: set[str] = set()
        relevant_facts(rows, q, "", set(), 8, aliases=aliases, named=named)
        assert retrieval.unrelated_question(q, named, rows) is small_talk


def test_a_v21_request_hands_its_options_to_the_v21_readers(migrated, monkeypatch):
    from test_phase60_gone import ask, story
    from test_generations import LLM
    from nmos_sidecar import overuse
    seen: dict[str, list] = {"keywords": [], "recent": []}
    real_keywords, real_recent = retrieval.keywords, overuse.recent
    monkeypatch.setattr(retrieval, "keywords", lambda q, **kw: seen["keywords"].append(kw) or real_keywords(q, **kw))
    monkeypatch.setattr(overuse, "recent", lambda *a, **kw: seen["recent"].append(kw) or real_recent(*a, **kw))
    with make_client(migrated, packet_policy="packet-v21", **LLM) as c:
        chat = story(c, migrated, "세라의 상태: 전투 중 전사.")
        ask(c, migrated, chat, "세라는 어디 있지?")
    assert seen["keywords"] and all(kw == {"v21": True} for kw in seen["keywords"])
    assert seen["recent"] and seen["recent"][-1]["dedupe_positions"] is True
    assert seen["recent"][-1]["exclude_position"] is not None
