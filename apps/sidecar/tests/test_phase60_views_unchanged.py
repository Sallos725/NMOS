"""Phase 60: the screens of a chat that uses none of the phase's new features render byte-identical to before.

PHASE-60 adds marks to the panel's memory document, the person sheet and the Inspector's chat page: lines carried
from another chat, `[happened: …; told tN]` beside an event or a promise, "who told whom" chains and pinned
characters. The owner's rule is that a chat using none of them renders exactly as it did before the phase. This file
records "before" as golden files, generated once at commit 02d161a (the base of Phase 60's panel track), and every
later change is compared with them byte for byte:

- the pure renderers `views.memory` and `views.person`, in Korean and English, from fixed synthetic inputs shaped as
  `api.memory_data` / `api.person_data` build them at 02d161a (no carried line, no `when_happened`, no `told`, no pin);
- the same screens and the Inspector's chat page through the API, on one synthetic chat extracted by the suite's
  deterministic stub, after a small explicit normalizer replaces the values that differ from run to run.

The golden files are the baseline. They must NEVER be regenerated to make a later change pass: a difference means the
change reaches a chat that does not use the new features, which the phase forbids. Regenerating is only for this
slice itself (`NMOS_WRITE_GOLDEN=1`); by default the tests only compare, and a missing golden file fails.

Synthetic names only (세라, 카이토, 하나, 유나, Rowan; Hana, Kaito, Yuna); no chat content of anyone's.
"""

from __future__ import annotations

import difflib
import os
from pathlib import Path
from typing import Any

from nmos_sidecar import views

GOLDEN = Path(__file__).parent / "golden" / "phase60"
WRITE = os.environ.get("NMOS_WRITE_GOLDEN") == "1"


def check_golden(name: str, text: str) -> None:
    """Compare `text` with the golden file `name` byte for byte; with NMOS_WRITE_GOLDEN=1, write it instead."""
    path = GOLDEN / name
    data = text.encode("utf-8")
    if WRITE:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return
    assert path.is_file(), f"golden file {path} is missing (never write it to make a test pass)"
    expected = path.read_bytes()
    if data != expected:
        at = next((i for i, (a, b) in enumerate(zip(data, expected)) if a != b), min(len(data), len(expected)))
        diff = "\n".join(list(difflib.unified_diff(
            expected.decode("utf-8", "replace").replace("><", ">\n<").splitlines(),
            text.replace("><", ">\n<").splitlines(), "golden", "now", lineterm="", n=1))[:80])
        raise AssertionError(f"{name} differs from its golden file at byte {at} "
                             f"({len(expected)} bytes before, {len(data)} now):\n{diff}")


# --- the pure renderers (no database) -----------------------------------------------------------------------------

CID = "0190f3a4-1b2c-7d3e-8f40-60000000c0de"
SERA, KAITO, HANA, YUNA, ROWAN = (f"0190f3a4-1b2c-7d3e-8f40-6000000000{i:02x}" for i in range(1, 6))
NAMES = {SERA: "세라", KAITO: "카이토", HANA: "하나", YUNA: "유나", ROWAN: "Rowan"}
ENTITIES = {name.casefold(): eid for eid, name in NAMES.items()} | {"sera": SERA, "세라짱": SERA}


def ent(eid: str) -> dict[str, str]:
    return {"id": eid, "name": NAMES[eid]}


def fact(subject: str, predicate: str, obj: str | None = None, value: str | None = None, turn: int = 3,
         **kw: Any) -> dict[str, Any]:
    """A current fact as `memory_view` gives it, with its entities."""
    out: dict[str, Any] = {"subject": NAMES[subject], "predicate": predicate, "object": NAMES.get(obj or "", obj),
                           "value": value, "turn": turn, "position": turn, "polarity": "positive",
                           "subject_entity": ent(subject)}
    if obj in NAMES:
        out["object_entity"] = ent(obj)
    return {**out, **kw}


def open_thread(i: int, kind: str, by: str, text: str, *, to: str | None = None, turn: int = 5,
                **kw: Any) -> dict[str, Any]:
    return {"id": i, "kind": kind, "by": by, "to": to, "text": text, "turn": turn, "status": "open", "restated": [],
            "knowledge": None, "hidden_from": None, **kw}


def pair(a: str, b: str, *, relationship: list[dict[str, Any]] = (), role: list[dict[str, Any]] = (),
         feels: list[dict[str, Any]] = (), speech: list[dict[str, Any]] = (), position: int = 3) -> dict[str, Any]:
    return {"ids": (a, b), "names": {a: NAMES[a], b: NAMES[b]}, "relationship": list(relationship),
            "role": list(role), "feels": list(feels), "speech": list(speech), "position": position}


FEELING = {"intensity": "strong", "valence": "positive",
           "under": {"value": "원망", "intensity": "faint", "valence": "negative"}}

PAIRS = [
    pair(SERA, KAITO, relationship=[fact(SERA, "relationship", KAITO, "소꿉친구")],
         role=[fact(SERA, "role_toward", KAITO, "보호자", turn=6)],
         feels=[fact(KAITO, "feels_toward", SERA, "그리움", turn=8, feeling=FEELING)],
         speech=[fact(KAITO, "addresses", SERA, "누나", turn=4)], position=3),
    pair(HANA, YUNA, relationship=[fact(HANA, "relationship", YUNA, "mother", turn=2)],
         feels=[fact(YUNA, "feels_toward", HANA, "angry", turn=11)], position=2),
    pair(ROWAN, YUNA, relationship=[fact(ROWAN, "relationship", YUNA, "classmate", turn=7),
                                    fact(YUNA, "relationship", ROWAN, "rival", turn=19)], position=7),
    pair(HANA, KAITO, relationship=[fact(HANA, "relationship", KAITO, "colleague", turn=9)],
         speech=[fact(HANA, "addresses", KAITO, "카이토 씨", turn=9)], position=9),
]

THREADS = [
    open_thread(1, "promise", "세라", "등대에서 만나기", to="카이토", turn=12, horizon="arc"),
    open_thread(2, "goal", "하나", "잃어버린 종 찾기", turn=3, horizon="lasting"),
    open_thread(3, "threat", "Rowan", "the <sealed> letter & the key", to="유나", turn=20, horizon="scene"),
    open_thread(4, "question", "유나", "누가 지도를 바꿨는가", turn=25),
    open_thread(5, "debt", "Rowan", "a favour at the old mill", to="유나", turn=30),
]

SECRETS = [
    {"id": 11, "text": "세라 knows: 지도는 가짜다", "holders": ["세라"], "open": ["카이토"], "turn": 14},
    {"id": 12, "text": "하나 identity: 밀수꾼", "holders": ["하나", "유나"], "open": ["세라", "Rowan"], "turn": 2},
    {"id": 13, "text": "Rowan knows: the bell was never lost", "holders": ["Rowan"], "open": [], "turn": 21},
    {"id": 14, "text": "the tide hides the cave", "holders": [], "open": ["유나"], "turn": 26},
]


def memory_input() -> dict[str, Any]:
    """`api.memory_data` at 02d161a for a chat that uses no Phase 60 feature, filled in every section."""
    moved = fact(SERA, "located_in", None, None, turn=9, object="old mill")
    status = fact(KAITO, "has_status", None, "지침", turn=17)
    return {"conv": {"id": CID, "name": "등대 마을 & <harbor>", "character": "세라", "turns": 42},
            "now": [{"name": "세라", "entity": SERA, "said": ["등대", "젖은 외투"]},
                    {"name": "카이토", "entity": KAITO, "said": ["부두"]},
                    {"name": "Rowan", "entity": ROWAN, "said": ["the old mill", "tired"]},
                    {"name": "유나", "entity": YUNA, "said": ["시장"]}],
            "threads": THREADS, "stale": 2, "pairs": PAIRS,
            "story": {"first_turn": 0, "last_turn": 30, "text": "세라와 카이토는 등대에서 다시 만났다. Rowan owes Yuna."},
            "scenes": [{"first_turn": 21, "last_turn": 30, "text": "시장에서의 추격."},
                       {"first_turn": 0, "last_turn": 20, "text": "Scene one: the harbor at night."}],
            "secrets": SECRETS,
            "changes": [{"fact": moved, "old": "harbor town", "new": "old mill"},
                        {"fact": status, "old": "건강함", "new": "지침"}],
            "facts": 138, "attention": 3, "entities": ENTITIES}


def person_input() -> dict[str, Any]:
    """`api.person_data` at 02d161a for 세라: aliases, relationships, open threads, what she knows and does not,
    and a timeline whose marks are of every kind the sheet shows (4-tuples with their predicate)."""
    marks = [(2, False, "등대지기", "identity"), (5, False, "등대", "located_in"), (9, True, "betrayed 카이토", "event"),
             (12, False, "카이토 → 등대에서 만나기", "promised"), (15, True, "카이토 → 연인", "relationship"),
             (20, False, "old mill", "located_in"), (24, False, "chore 1", "event"), (27, True, "the bell rang", "event"),
             (31, False, "카이토 → 보호자", "role_toward"), (38, False, "지침", "has_status")]
    return {"conv": {"id": CID, "name": "등대 마을 & <harbor>", "character": "세라", "turns": 42},
            "entity": {"id": SERA, "name": "세라", "names": ["세라", "세라짱", "Sera"], "persona": False,
                       "excluded": None, "pinned": None},
            "now": ["등대", "젖은 외투"],
            "pairs": [p for p in PAIRS if SERA in p["ids"]] + [
                pair(SERA, YUNA, relationship=[fact(SERA, "relationship", YUNA, "teacher of", turn=13)]),
                pair(SERA, ROWAN, feels=[fact(SERA, "feels_toward", ROWAN, "의심", turn=22)]),
                pair(SERA, HANA, relationship=[fact(HANA, "relationship", SERA, "friend", turn=4)])],
            "threads": [THREADS[0], open_thread(6, "goal", "세라", "종지기 찾기", turn=8, horizon="arc"),
                        open_thread(7, "promise", "카이토", "배를 고치기", to="세라", turn=16),
                        open_thread(8, "question", "세라", "Rowan은 무엇을 숨기나", turn=33)],
            "knows": [SECRETS[0]], "kept": [SECRETS[1]],
            "marks": marks, "first": 0, "last": 42, "entities": ENTITIES}


def test_the_memory_document_renders_as_before():
    for lang in ("ko", "en"):
        check_golden(f"memory.{lang}.html", views.memory(memory_input(), lang))


def test_a_persons_sheet_renders_as_before():
    for lang in ("ko", "en"):
        check_golden(f"person.{lang}.html", views.person(person_input(), lang))
