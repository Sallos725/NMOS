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
