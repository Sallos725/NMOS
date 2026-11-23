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
