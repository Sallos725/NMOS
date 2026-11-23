"""Phase 60 S8: who-told-whom chains on the person sheet, the memory map and the Inspector character page."""

from __future__ import annotations

from typing import Any

from nmos_sidecar import memorymap

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
