"""PHASE-50: notes for the author's note — markers, the fact sections, the chronicle, the API."""

from __future__ import annotations

import json
from pathlib import Path

from conftest import make_client
from nmos_sidecar import notes
from test_canon import push
from test_canon_facts import Model, canon_texts, drain, story
from test_generations import LLM
from test_sidecar_integration import sync

BLOCKS = Path(__file__).resolve().parents[3] / "fixtures/unit/note-blocks-v1.json"


def test_blocks_are_the_plugins():
    for case in json.loads(BLOCKS.read_text(encoding="utf-8"))["cases"]:
        assert notes.strip_blocks(case["note"]) == (case["text"], case["blocks"]), case["name"]


def test_a_note_without_a_block_comes_back_as_it_was():
    note = "  앞뒤 공백도\n\n\n그대로  "
    assert notes.strip_blocks(note) == (note, [])


def test_wrap_writes_what_strip_removes():
    text = notes.wrap("chronicle", "## 사건\n- 하나", "0-87", "ko", "2026-10-23")
    assert text.splitlines()[0] == "[NMOS 연대기 · t0–87 · 2026-10-23]" and text.endswith("[/NMOS 연대기]")
    assert notes.strip_blocks("메모\n\n" + text) == ("메모", [{"kind": "chronicle", "turns": "0-87"}])
    assert notes.wrap("address", "- x", "5", "en", "2026-10-23").splitlines()[0] == "[NMOS address · t5 · 2026-10-23]"


NOTE = "Hana is in the harbor town.\n\n[NMOS 연대기 · t0–1 · 2026-10-23]\nHana is a smuggler.\n[/NMOS 연대기]"


def test_canon_does_not_read_a_marked_block(migrated):
    """An older plugin sends the note whole: the canon read still leaves NMOS's block out (PHASE-50 S5)."""
    chat, model = story(), Model()
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        push(c, chat, {**canon_texts(), "note": (NOTE, {})})
        drain(migrated, model)
    note = next(u for u in model.canon_calls() if "the author's note" in u)
    assert "Hana is in the harbor town." in note and "smuggler" not in note and "NMOS" not in note


def fact(subject, predicate, *, obj=None, value=None, turn=5, history=(), knowledge=None, hidden_from=None, **kw):
    """A current fact as `memory_view` makes it (the fields these sections read)."""
    return {"subject": subject, "predicate": predicate, "object": obj, "value": value, "turn": turn, "position": turn,
            "polarity": "positive", "history": list(history), "knowledge": knowledge, "hidden_from": hidden_from,
            "claims": [], **kw}


def canon_entry(subject, predicate, *, obj=None, value=None, outcome="superseded"):
    """A history entry of a canon statement (turn -1, ADR 0047)."""
    return {"subject": subject, "predicate": predicate, "object": obj, "value": value, "polarity": "positive",
            "turn": -1, "position": -1, "outcome": outcome, "canon": "card:desc"}


def test_changed_lists_a_canon_value_the_story_replaced_and_nothing_else():
    moved = fact("Hana", "located_in", obj="old mill", turn=1,
                 history=[canon_entry("Hana", "located_in", obj="harbor town"), {"outcome": "current"}])
    same = fact("Hana", "relationship", obj="Kaito", value="sister", turn=-1, canon="card:desc")
    trait = fact("Hana", "has_trait", value="stubborn", history=[canon_entry("Hana", "has_trait", value="shy")])
    assert notes.changed_lines([moved, same, trait], "ko") == ["- Hana 위치: 설정 harbor town → 지금 old mill (t1)"]


def test_changed_leaves_out_what_is_kept_from_someone_unless_asked():
    who = fact("Hana", "identity", value="smuggler", knowledge="limited", hidden_from=["Kaito"],
               history=[canon_entry("Hana", "identity", value="lighthouse keeper")])
    assert notes.changed_lines([who], "ko") == []
    assert notes.changed_lines([who], "ko", secrets=True) == [
        "- Hana 정체: 설정 lighthouse keeper → 지금 smuggler (t5) (비밀: Kaito는 모름)"]


def test_an_items_holder_is_a_change_of_who_holds_it():
    held = fact("Kaito", "possesses", obj="map", history=[canon_entry("Hana", "possesses", obj="map")])
    assert notes.changed_lines([held], "en") == ["- map held by: setting Hana → now Kaito (t5)"]


def test_address_gives_one_line_per_pair():
    rel = fact("Hana", "relationship", obj="Kaito", value="childhood friend")
    calls = fact("Kaito", "addresses", obj="Hana", value="누나")
    feels = fact("Hana", "feels_toward", obj="Kaito", value="trust", knowledge="limited", hidden_from=["Kaito"])
    assert notes.address_lines([rel, calls, feels], "ko") == [
        "- Hana ↔ Kaito: 관계 childhood friend · Kaito→Hana 호칭 \"누나\""]
    assert "Hana→Kaito 감정 trust (비밀: Kaito는 모름)" in notes.address_lines([rel, calls, feels], "ko", secrets=True)[0]
    sister = fact("Hana", "relationship", obj="Kaito", value="sister")
    assert notes.address_lines([sister], "en") == ["- Hana ↔ Kaito: Hana→Kaito relationship sister"]
