"""Phase 60 S6: lines carried from an earlier chat on the memory document and the person sheet (views only).

The data side (`api.memory_data` / `api.person_data`) adds `d["carry"]` only while a link is in force, and the key
`carried` on a row that came through it; these tests build those dicts by hand. A chat without them must render
byte-identical (tests/test_phase60_views_unchanged.py keeps the goldens). Synthetic names only.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from nmos_sidecar import views
from test_inspector_timeline import PANEL_TAGS
from test_phase60_views_unchanged import CID, ENTITIES, KAITO, SERA, memory_input, person_input

SRC = "0190f3a4-1b2c-7d3e-8f40-70000000beef"
LINK = "0190f3a4-1b2c-7d3e-8f40-7000000011a0"
REV = "0190f3a4-1b2c-7d3e-8f40-7000000022b0"


def prov(turn: int | None = 7, conv: str = SRC) -> dict[str, Any]:
    return {"conversation": conv, "assertion": 41, "revision": REV, "generation": "extract-v19", "turn": turn}


def cfact(subject: str, predicate: str, obj: str | None = None, value: str | None = None, *, turn: int | None = 7,
          **kw: Any) -> dict[str, Any]:
    """A carried fact row as the view has it: before turn 0 (`turn` -1), flagged and with its provenance."""
    return {"subject": subject, "predicate": predicate, "object": obj, "value": value, "turn": -1, "position": -1,
            "polarity": "positive", "source": "carried", "carried": LINK, "carried_from": prov(turn), **kw}


def cthread(kind: str, by: str, text: str, *, to: str | None = None, turn: int | None = 9,
            **kw: Any) -> dict[str, Any]:
    return {"id": -5, "kind": kind, "by": by, "to": to, "text": text, "turn": -1, "status": "open",
            "carried": LINK, "carried_from": prov(turn), **kw}


def carry(mode: str = "continue", lines: list[dict[str, Any]] | None = None, *, names: list[str] | None = None,
          source: dict[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
    return {"source": source if source is not None else {"id": SRC, "character": "세라", "chat": "옛 항구"},
            "mode": mode, "names": names if names is not None else ([] if mode == "continue" else ["세라"]),
            "created_at": "2026-11-23T04:50:01+00:00",
            "lines": lines if lines is not None else default_lines(), **kw}


def default_lines() -> list[dict[str, Any]]:
    return [cfact("세라", "located_in", "등대", turn=7),
            cfact("카이토", "has_status", None, "지침", turn=None),
            cthread("promise", "세라", "등대에서 만나기", to="카이토", turn=12)]


def sec(html: str, key: str = "s-carry") -> str:
    """One section's HTML, from its opening to the next section (or the end)."""
    rest = html.split(f'<div class="v-sec" id="{key}">')[1]
    return rest.split('<div class="v-sec" id=')[0]


# --- pure helpers -------------------------------------------------------------------------------------------------

def test_carry_href_has_only_the_two_shapes_the_sanitizer_keeps():
    assert views.carry_href(cfact("세라", "located_in", "등대", turn=7)) == f"/inspector/c/{SRC}/t/7"
    assert views.carry_href(cfact("세라", "located_in", "등대", turn=0)) == f"/inspector/c/{SRC}/t/0"
    assert views.carry_href(cfact("세라", "located_in", "등대", turn=None)) == f"/inspector/c/{SRC}"
    # a turn the sanitizer would drop (negative, a bool, a string, too long) links to the chat instead
    for bad in (-1, True, "7", 10_000_000):
        row = cfact("세라", "located_in", "등대")
        row["carried_from"]["turn"] = bad
        assert views.carry_href(row) == f"/inspector/c/{SRC}", bad
    # no usable source id: no link at all
    for conv in ("", "not-a-uuid", f"{SRC}/../x", None):
        row = cfact("세라", "located_in", "등대")
        row["carried_from"]["conversation"] = conv
        assert views.carry_href(row) is None, conv
    assert views.carry_href({"predicate": "located_in"}) is None
    assert views.carry_href({"carried_from": None}) is None


def test_carry_text_reads_facts_and_threads_in_plain_words():
    assert views.carry_text(cfact("세라", "located_in", "등대"), "ko") == "세라 위치 등대"
    assert views.carry_text(cfact("세라", "located_in", "등대"), "en") == "세라 location 등대"
    assert views.carry_text(cfact("카이토", "has_status", None, "지침"), "ko") == "카이토 상태 지침"
    assert views.carry_text(cfact("세라", "relationship", "카이토", "소꿉친구"), "ko") == "세라 → 카이토 관계 소꿉친구"
    assert views.carry_text(cfact("세라", "member_of", "등대지기회"), "ko") == "세라 소속 등대지기회"
    assert views.carry_text(cfact("세라", "also_called", None, "세라짱"), "ko") == "세라 다른 이름 세라짱"
    assert views.carry_text(cfact("세라", "also_called", None, "세라짱"), "en") == "세라 also called 세라짱"
    assert views.carry_text(cfact("세라", "located_in", "등대", polarity="negative"), "ko") == "세라 위치 등대 (아님)"
    assert views.carry_text(cfact("세라", "located_in", "등대", polarity="negative"), "en") == "세라 location 등대 (not)"
    # the resolved name when the row has one
    assert views.carry_text(cfact("sera", "located_in", "등대", subject_entity={"id": SERA, "name": "세라"}),
                            "ko") == "세라 위치 등대"
    assert views.carry_text(cthread("promise", "세라", "등대에서 만나기", to="카이토"), "ko") == "세라 → 카이토: 등대에서 만나기"
    assert views.carry_text(cthread("goal", "세라", "종 찾기"), "en") == "세라: 종 찾기"
    # a regression row says which it is; a thread without "line" is told apart by by/text without a predicate
    assert views.carry_text({**cthread("goal", "세라", "종 찾기"), "line": "thread"}, "ko") == "세라: 종 찾기"
    assert views.carry_text({**cfact("세라", "located_in", "등대"), "line": "fact"}, "ko") == "세라 위치 등대"


def test_carry_head_says_where_from_in_words():
    assert views.carry_head(carry(), "ko") == "세라 · 옛 항구에서 이어받음 · 이 채팅의 턴이 아님"
    assert views.carry_head(carry(), "en") == "Carried from 세라 · 옛 항구 · not this chat's own turns"
    only_chat = carry(source={"id": SRC, "character": None, "chat": "옛 항구"})
    assert views.carry_head(only_chat, "ko") == "옛 항구에서 이어받음 · 이 채팅의 턴이 아님"
    neither = carry(source={"id": SRC, "character": None, "chat": None})
    assert views.carry_head(neither, "en") == "Carried from 0190f3a4 · not this chat's own turns"
    assert views.carry_head(carry(cutoff_turn=30), "ko") == "세라 · 옛 항구에서 이어받음 · 이 채팅의 턴이 아님 · t30까지"
    assert views.carry_head(carry(cutoff_turn=30), "en").endswith(" · up to t30")
    reg = carry("regression", names=["세라", "카이토"])
    assert views.carry_head(reg, "ko") == "이전 타임라인 · 세라, 카이토만 기억"
    assert views.carry_head(reg, "en") == "Earlier timeline · remembered only by 세라, 카이토"


# --- the panel's sanitizer ---------------------------------------------------------------------------------------

UUID_RE = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
TURN_RE = "/t/(?:0|[1-9][0-9]{0,6})"


def panel_safe(html: str) -> None:
    """Only the tags and link shapes the plugin's sanitizer keeps (adapters/pocketrisu-plugin/src/inspector.ts)."""
    assert "style=" not in html and "<script" not in html and "<svg" not in html and "<table" not in html
    assert set(re.findall(r"<([a-z0-9]+)", html)) <= PANEL_TAGS - {"table", "thead", "tbody", "tr", "th", "td"}
    for href in re.findall(r'href="([^"]*)"', html):
        assert re.fullmatch(rf"/inspector/c/{UUID_RE}(?:/e/{UUID_RE}|{TURN_RE})?(?:#s-[a-z]+)?"
                            rf"|/views/c/{UUID_RE}/(?:memory|map|person/{UUID_RE})|#s-[a-z]+", href), href
    assert "mono" not in html


def without_section(html: str, key: str, nxt: str) -> str:
    """`html` with the section `key` (followed by the section `nxt`) and its contents chip taken out."""
    head, rest = html.split(f'<div class="v-sec" id="{key}">')
    rest = f'<div class="v-sec" id="{nxt}">' + rest.split(f'<div class="v-sec" id="{nxt}">', 1)[1]
    return re.sub(rf'<a href="#{key}">.*?</a>', "", head) + rest


# --- the memory document ------------------------------------------------------------------------------------------

def test_memory_document_shows_continue_lines_after_now_in_ko_and_en():
    d = {**memory_input(), "carry": carry()}
    ko = views.memory(d, "ko")
    assert re.findall(r'class="v-sec" id="(s-[a-z]+)"', ko) == [
        "s-now", "s-carry", "s-open", "s-people", "s-sofar", "s-secrets", "s-changed"]
    assert re.findall(r'<a href="#(s-[a-z]+)">', ko)[:2] == ["s-now", "s-carry"]
    assert '<a href="#s-carry"><span>이전 채팅에서 이어받은 기억</span><span class="v-chip-n">3</span></a>' in ko
    s = sec(ko)
    assert '<h2 class="v-h2">이전 채팅에서 이어받은 기억<span class="v-n">3</span></h2>' in s
    assert '<p class="v-text">세라 · 옛 항구에서 이어받음 · 이 채팅의 턴이 아님</p>' in s
    assert f'<a class="v-src" href="/inspector/c/{SRC}/t/7">세라 위치 등대</a>' in s
    assert f'<a class="v-src" href="/inspector/c/{SRC}">카이토 상태 지침</a>' in s  # turn null: the chat
    assert (f'<span class="v-tag k-promise">약속</span><a class="v-src" href="/inspector/c/{SRC}/t/12">'
            f'세라 → 카이토: 등대에서 만나기</a>') in s
    assert "이전 채팅 t7" in s and "t-1" not in s
    panel_safe(ko)

    en = views.memory(d, "en")
    s = sec(en)
    assert "Carried from an earlier chat" in s
    assert '<p class="v-text">Carried from 세라 · 옛 항구 · not this chat&#x27;s own turns</p>' in s
    assert f'<a class="v-src" href="/inspector/c/{SRC}/t/7">세라 location 등대</a>' in s
    assert "earlier chat t7" in s
    panel_safe(en)


def test_memory_document_with_carry_only_adds_its_section_and_chip():
    for lang in ("ko", "en"):
        base = views.memory(memory_input(), lang)
        shown = views.memory({**memory_input(), "carry": carry()}, lang)
        assert without_section(shown, "s-carry", "s-open") == base


def test_memory_document_regression_head_names_who_remembers():
    lines = [{**cfact("세라", "located_in", "등대"), "line": "fact"},
             {**cthread("goal", "세라", "종 찾기"), "line": "thread"}]
    d = {**memory_input(), "carry": carry("regression", lines, names=["세라", "카이토"])}
    s = sec(views.memory(d, "ko"))
    assert '<p class="v-text">이전 타임라인 · 세라, 카이토만 기억</p>' in s
    assert "세라 위치 등대" in s and "세라: 종 찾기" in s
    assert "Earlier timeline · remembered only by 세라, 카이토" in sec(views.memory(d, "en"))


def test_memory_document_with_a_link_and_no_lines_still_says_where_from():
    d = {**memory_input(), "carry": carry(lines=[])}
    s = sec(views.memory(d, "ko"))
    assert "세라 · 옛 항구에서 이어받음" in s and "아직 없어요" in s and 'class="v-n"' not in s
    assert '<a href="#s-carry"><span>이전 채팅에서 이어받은 기억</span></a>' in views.memory(d, "ko")


def test_memory_document_shows_fifty_lines_and_counts_the_rest():
    lines = [cfact("세라", "has_status", None, f"상태 {i}", turn=i) for i in range(60)]
    for lang, left in (("ko", "외 10줄"), ("en", "10 more")):
        s = sec(views.memory({**memory_input(), "carry": carry(lines=lines)}, lang))
        assert s.count('class="v-line"') == 50
        assert "상태 49<" in s and "상태 50<" not in s
        assert f'<span class="v-n">60</span>' in s
        assert f'<p class="v-note"><a class="v-src" href="/inspector/c/{SRC}">{left}</a></p>' in s
        assert '<details class="v-more">' in s  # the 50 fold as the other lists do
    s = sec(views.memory({**memory_input(), "carry": carry(lines=lines[:50])}, "en"))
    assert s.count('class="v-line"') == 50 and "v-note" not in s


def test_memory_document_carried_line_shows_when_it_happened_without_a_turn_of_this_chat():
    lines = [cfact("세라", "event", None, "종이 울렸다", when_happened="어제"),
             cthread("promise", "세라", "등대에서 만나기", to="카이토", when_happened="4월 12일")]
    s = sec(views.memory({**memory_input(), "carry": carry(lines=lines)}, "ko"))
    assert "</a> [일어난 때: 어제]" in s and "</a> [일어난 때: 4월 12일]" in s and "t-1" not in s


def test_memory_document_escapes_carried_values_and_source_names():
    lines = [cfact("세라", "has_status", None, "<b>지침</b>"), cthread("goal", "<b>세라</b>", "<b>종</b>")]
    d = {**memory_input(), "carry": carry(lines=lines, source={"id": SRC, "character": "<b>세라</b>",
                                                                "chat": "<b>옛 항구</b>"})}
    for lang in ("ko", "en"):
        s = sec(views.memory(d, lang))
        assert "<b>" not in s
        assert "&lt;b&gt;세라&lt;/b&gt; · &lt;b&gt;옛 항구&lt;/b&gt;" in s and "&lt;b&gt;지침&lt;/b&gt;" in s
        assert "&lt;b&gt;세라&lt;/b&gt;: &lt;b&gt;종&lt;/b&gt;" in s
    reg = {**memory_input(), "carry": carry("regression", [], names=["<b>세라</b>"])}
    assert "<b>" not in sec(views.memory(reg, "ko")) and "&lt;b&gt;세라&lt;/b&gt;만 기억" in sec(views.memory(reg, "ko"))
