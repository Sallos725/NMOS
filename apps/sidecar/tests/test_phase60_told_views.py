"""Phase 60 S8: who-told-whom chains on the person sheet, the memory map and the Inspector character page."""

from __future__ import annotations

from typing import Any
import re

from nmos_sidecar import inspector, memorymap, views

CID = "0190f3a4-1b2c-7d3e-8f40-60000000c0de"
SERA, KAITO, HANA, YUNA = (f"0190f3a4-1b2c-7d3e-8f40-0000000000{i:02x}" for i in range(1, 5))
NAMES = {SERA: "세라", KAITO: "카이토", HANA: "하나", YUNA: "유나"}
ENTITIES = {name.casefold(): eid for eid, name in NAMES.items()}


def told_row(subject: str, obj: str, value: str, turn: int | None = 5, *,
             about: list[str] | tuple[str, ...] = (),
             subject_entity: dict[str, Any] | None = None,
             object_entity: dict[str, Any] | None = None,
             **kw: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "predicate": "told",
        "subject": subject,
        "subject_type": "character",
        "object": obj,
        "object_type": "character",
        "value": value,
        "turn": turn,
        "participants": tuple({"name": n, "type": "character"} for n in about) if about else None,
        "knowledge": "unknown",
        "known_by": None,
        "hidden_from": None,
    }
    if subject_entity is not None:
        row["subject_entity"] = subject_entity
    if object_entity is not None:
        row["object_entity"] = object_entity
    row.update(kw)
    return row


# --- memorymap.told_chains --------------------------------------------------------------------------------------------

def test_told_chains_empty_and_single_link():
    assert memorymap.told_chains([]) == []
    assert memorymap.told_chains(None) == []
    chains = memorymap.told_chains([told_row("세라", "카이토", "지도는 가짜다", turn=12)])
    assert chains == [[{"teller": "세라", "hearer": "카이토", "what": "지도는 가짜다", "about": [], "turn": 12}]]


def test_told_chains_three_step_chain_normalizes_value_and_resolves_entities():
    rows = [
        told_row("Sera", "카이토", "The map is fake", turn=2,
                 subject_entity={"id": SERA, "name": "세라"}, object_entity={"id": KAITO, "name": "카이토"}),
        told_row("Kaito", "하나", "  the   map  is FAKE ", turn=6,
                 subject_entity={"id": KAITO, "name": "카이토"}, object_entity={"id": HANA, "name": "하나"}),
        told_row("하나", "유나", "the map is fake", turn=11),
    ]
    chains = memorymap.told_chains(rows)
    assert len(chains) == 1
    assert [(x["teller"], x["hearer"], x["turn"]) for x in chains[0]] == [
        ("세라", "카이토", 2), ("카이토", "하나", 6), ("하나", "유나", 11)
    ]


def test_told_chains_does_not_join_different_content():
    rows = [
        told_row("세라", "카이토", "지도는 가짜다", turn=3),
        told_row("카이토", "하나", "종이 사라졌다", turn=7),
    ]
    chains = memorymap.told_chains(rows)
    assert len(chains) == 2
    assert [c[0]["what"] for c in chains] == ["지도는 가짜다", "종이 사라졌다"]


def test_told_chains_does_not_join_same_content_with_different_teller():
    rows = [
        told_row("세라", "카이토", "지도는 가짜다", turn=3),
        told_row("유나", "하나", "지도는 가짜다", turn=5),
        told_row("세라", "유나", "지도는 가짜다", turn=8),
    ]
    chains = memorymap.told_chains(rows)
    assert len(chains) == 3
    assert [(c[0]["teller"], c[0]["hearer"]) for c in chains] == [
        ("세라", "카이토"), ("유나", "하나"), ("세라", "유나")
    ]


def test_told_chains_carries_about_from_participants_and_resolved_participants():
    rows = [
        told_row("세라", "카이토", "밀수꾼이다", turn=4, about=["하나", "유나"]),
        told_row("카이토", "유나", "배가 떠났다", turn=9,
                 participant_entities=[{"name": "hana", "type": "character", "entity": {"id": HANA, "name": "하나"}}]),
    ]
    chains = memorymap.told_chains(rows)
    assert chains[0][0]["about"] == ["하나", "유나"]
    assert chains[1][0]["about"] == ["하나"]


def test_told_chains_orders_oldest_first_including_turn_zero():
    rows = [
        told_row("카이토", "하나", "지도는 가짜다", turn=9),
        told_row("유나", "세라", "열쇠를 숨겼다", turn=0),
        told_row("세라", "카이토", "지도는 가짜다", turn=4),
    ]
    chains = memorymap.told_chains(rows)
    assert len(chains) == 2
    assert [(x["teller"], x["hearer"], x["turn"]) for x in chains[0]] == [("유나", "세라", 0)]
    assert [(x["teller"], x["hearer"], x["turn"]) for x in chains[1]] == [("세라", "카이토", 4), ("카이토", "하나", 9)]


# --- views.person and views.memory_map --------------------------------------------------------------------------------

def _person_data(**over: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "conv": {"id": CID, "name": "등대 마을", "character": "세라", "turns": 20},
        "entity": {"id": SERA, "name": "세라", "names": ["세라"]},
        "now": ["등대"],
        "pairs": [],
        "threads": [],
        "knows": [],
        "kept": [],
        "marks": [(2, False, "등대", "located_in")],
        "first": 0,
        "last": 20,
        "entities": ENTITIES,
    }
    data.update(over)
    return data


def _map_data(**over: Any) -> dict[str, Any]:
    v = {"facts": [], "entities": [], "excluded": {}, "assertions": [], "resolution": None}
    data: dict[str, Any] = {
        "conv": {"id": CID, "name": "등대 마을", "character": "세라", "turns": 20},
        "map": memorymap.build(v, 20, []),
        "entities": ENTITIES,
    }
    data.update(over)
    return data


def test_person_sheet_renders_told_chains_in_ko_and_en():
    rows = [
        told_row("세라", "카이토", "지도는 가짜다", turn=5, about=["유나"],
                 subject_entity={"id": SERA, "name": "세라"}, object_entity={"id": KAITO, "name": "카이토"}),
        told_row("카이토", "하나", "지도는 가짜다", turn=12,
                 subject_entity={"id": KAITO, "name": "카이토"}, object_entity={"id": HANA, "name": "하나"}),
        told_row("유나", "세라", "열쇠는 등대에 있다", turn=15),
    ]
    ko = views.person(_person_data(told=rows), "ko")
    assert re.findall(r'class="v-sec" id="(s-[a-z]+)"', ko) == [
        "s-now", "s-rels", "s-threads", "s-knows", "s-told", "s-time"
    ]
    sec_ko = ko.split('id="s-told"')[1].split('id="s-time"')[0]
    assert "누가 누구에게 들었나" in sec_ko and '<span class="v-n">2</span>' in sec_ko
    assert f'<a class="v-name" href="/views/c/{CID}/person/{SERA}">세라</a>' in sec_ko
    assert f'<a class="v-name" href="/views/c/{CID}/person/{KAITO}">카이토</a>' in sec_ko
    assert f'<a class="v-name" href="/views/c/{CID}/person/{HANA}">하나</a>' in sec_ko
    assert ": 지도는 가짜다 (t5 → t12)" in sec_ko and "유나에 대해" in sec_ko
    assert ": 열쇠는 등대에 있다 (t15)" in sec_ko
    assert "mono" not in sec_ko and "<table" not in sec_ko

    en = views.person(_person_data(told=rows), "en")
    sec_en = en.split('id="s-told"')[1].split('id="s-time"')[0]
    assert "Who told whom" in sec_en and "about 유나" in sec_en
    assert ": 지도는 가짜다 (t5 → t12)" in sec_en


def test_person_sheet_folds_more_than_three_told_chains_and_escapes_html():
    rows = [told_row("세라", "카이토", f"<b>비밀 {i}</b>", turn=i + 1, about=["<b>유나</b>"]) for i in range(4)]
    html = views.person(_person_data(told=rows), "ko")
    sec = html.split('id="s-told"')[1].split('id="s-time"')[0]
    assert '<details class="v-more">' in sec and "1개 더 보기" in sec
    assert "<b>" not in sec and "&lt;b&gt;비밀 0&lt;/b&gt;" in sec and "&lt;b&gt;유나&lt;/b&gt;" in sec


def test_person_sheet_without_told_is_unchanged():
    base_ko = views.person(_person_data(), "ko")
    base_en = views.person(_person_data(), "en")
    assert 'id="s-told"' not in base_ko and 'id="s-told"' not in base_en
    assert views.person(_person_data(told=[]), "ko") == base_ko
    assert views.person(_person_data(told=[]), "en") == base_en


def test_memory_map_renders_told_chains_and_stays_panel_safe():
    from test_memorymap import panel_safe

    rows = [
        told_row("세라", "카이토", "<b>지도는 가짜다</b>", turn=12, about=["유나"]),
    ]
    ko = views.memory_map(_map_data(told=rows), "ko")
    assert 'id="s-told"' in ko and 'href="#s-told"' in ko
    assert "누가 누구에게 들었나" in ko and "&lt;b&gt;지도는 가짜다&lt;/b&gt; (t12)" in ko and "<b>" not in ko
    assert f'href="/views/c/{CID}/person/{SERA}"' in ko
    assert "유나에 대해" in ko
    # verify panel sanitizer constraints (same tag/href allowlist as test_memorymap.panel_safe)
    assert "<table" not in ko and "<svg" not in ko and "style=" not in ko
    en = views.memory_map(_map_data(told=rows), "en")
    assert "Who told whom" in en and "about 유나" in en
    # use test_memorymap's fixture CID for panel_safe's href regex check
    from test_memorymap import map_data as make_map_data
    d_map = make_map_data()
    d_map["told"] = rows
    panel_safe(views.memory_map(d_map, "ko"))


def test_memory_map_without_told_is_unchanged():
    base_ko = views.memory_map(_map_data(), "ko")
    base_en = views.memory_map(_map_data(), "en")
    assert 'id="s-told"' not in base_ko and 'id="s-told"' not in base_en
    assert views.memory_map(_map_data(told=[]), "ko") == base_ko
    assert views.memory_map(_map_data(told=[]), "en") == base_en


# --- inspector.told_section and inspector.character -------------------------------------------------------------------

def test_inspector_told_section_empty_lines_turn_links_and_escaping():
    assert inspector.told_section([], "ko") == ""
    assert inspector.told_section(None, "en") == ""

    rows = [
        told_row("세라", "카이토", "<b>지도는 가짜다</b>", turn=5, about=["<b>유나</b>"]),
        told_row("카이토", "하나", "<b>지도는 가짜다</b>", turn=12),
    ]
    with inspector.turn_links(CID, None, "ko"):
        ko = inspector.told_section(rows, "ko")
    assert "<th>누가 누구에게</th><th>내용</th><th>관련 인물</th><th>턴</th>" in ko
    assert "세라 → 카이토 → 하나" in ko
    assert "&lt;b&gt;지도는 가짜다&lt;/b&gt;" in ko and "<b>" not in ko
    assert "&lt;b&gt;유나&lt;/b&gt;" in ko
    assert f'<a href="/inspector/c/{CID}/t/5">5</a> → <a href="/inspector/c/{CID}/t/12">12</a>' in ko
    assert "mono" not in ko

    with inspector.turn_links(CID, "tok", "en"):
        en = inspector.told_section(rows, "en")
    assert "<th>Who to whom</th><th>What</th><th>About</th><th>Turn</th>" in en
    assert f'<a href="/inspector/c/{CID}/t/5?token=tok&lang=en">5</a>' in en


def test_inspector_character_page_includes_told_section_only_when_present():
    conv = {"id": CID, "host_chat_ref": "chat-1", "head_commit_id": "head-1",
            "host_character_name": "세라", "host_chat_name": "등대"}
    base_view: dict[str, Any] = {
        "entities": [
            {"id": SERA, "type": "character", "name": "세라", "names": ["세라"], "mentions": 3,
             "aliases": [], "links": [], "persona": False},
            {"id": KAITO, "type": "character", "name": "카이토", "names": ["카이토"], "mentions": 2,
             "aliases": [], "links": [], "persona": False},
        ],
        "facts": [], "claims": [], "other": [], "conflicts": [], "threads": [], "secrets": [],
    }
    rows = [told_row("세라", "카이토", "종이 사라졌다", turn=8, about=["하나"])]
    with inspector.turn_links(CID, None, "ko"):
        without = inspector.character(conv, SERA, base_view, None, lang="ko", embed=True)
        empty = inspector.character(conv, SERA, {**base_view, "told": []}, None, lang="ko", embed=True)
        shown = inspector.character(conv, SERA, {**base_view, "told": rows}, None, lang="ko", embed=True)
    assert 'id="s-told"' not in without and empty == without
    assert 'id="s-told"' in shown and 'href="#s-told"' in shown
    assert "누가 누구에게 들었나" in shown and "세라 → 카이토" in shown and "종이 사라졌다" in shown
    assert f'<a href="/inspector/c/{CID}/t/8">8</a>' in shown

    with inspector.turn_links(CID, None, "en"):
        shown_en = inspector.character(conv, SERA, {**base_view, "told": rows}, None, lang="en", embed=True)
    assert "Who told whom" in shown_en and f'<a href="/inspector/c/{CID}/t/8?lang=en">8</a>' in shown_en
