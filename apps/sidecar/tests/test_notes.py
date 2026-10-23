"""PHASE-50: notes for the author's note — markers, the fact sections, the chronicle, the API."""

from __future__ import annotations

import json
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import notes
from test_canon import push
from test_canon_facts import Model, canon_texts, drain, story
from test_canon_facts import view as canon_view
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
    where = fact("Hana", "located_in", obj="smugglers' cave", knowledge="limited", hidden_from=["Kaito"],
                 history=[canon_entry("Hana", "located_in", obj="harbor town")])
    assert notes.changed_lines([where], "ko") == []
    assert notes.changed_lines([where], "ko", secrets=True) == [
        "- Hana 위치: 설정 harbor town → 지금 smugglers' cave (t5) (비밀: Kaito는 모름)"]


def test_changed_leaves_out_identity_and_says_a_line_once():
    """A card's identity told again in other words is not a change (ADR 0047 amendment 1); two canon texts saying the
    same old value give one line."""
    who = fact("Hana", "identity", value="등대지기", history=[canon_entry("Hana", "identity", value="lighthouse keeper")])
    moved = fact("Hana", "located_in", obj="old mill", turn=1,
                 history=[canon_entry("Hana", "located_in", obj="harbor town"),
                          {**canon_entry("Hana", "located_in", obj="harbor town"), "canon": "lore:hana"}])
    assert notes.changed_lines([who, moved], "ko") == ["- Hana 위치: 설정 harbor town → 지금 old mill (t1)"]


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



def scene(first, last, text, told=("smuggler",)):
    """A current scene summary; `told`: the secrets its prompt listed (`coverage.secrets`, by `secret_key`)."""
    return {"window": None, "summary": {"id": f"s{first}", "first_turn": first, "last_turn": last, "text": text,
                                        "coverage": {"secrets": list(told)}}}


def told(*scenes, story=None):
    """`summaries.current` as the chronicle reads it."""
    return {"scenes": list(scenes), "story": story}


THREADS = [
    {"kind": "promise", "by": "Hana", "to": "Kaito", "text": "meet at the lighthouse", "turn": 3, "status": "open",
     "closed_by": None, "knowledge": None, "hidden_from": None},
    {"kind": "goal", "by": "Hana", "to": None, "text": "find the bell", "turn": 1, "status": "achieved",
     "closed_by": {"turn": 9}, "knowledge": None, "hidden_from": None},
]
SECRET = {"open": ["Kaito"], "holders": ["Hana"], "text": "Hana identity: smuggler", "turn": 2, "position": 2}
OPEN_LINE = "- Hana → Kaito: meet at the lighthouse (약속, t3부터)"


class Writer:
    """A stand-in model: its replies in order, the prompts it saw."""

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, system, user):
        self.calls.append(user)
        return self.replies.pop(0), "{}"


def test_assembled_without_a_model_open_threads_from_the_store():
    notes.clear_cache()
    out = notes.chronicle(told(scene(0, 7, "Hana went to the mill."), scene(8, 15, "Hana found the bell.")),
                          THREADS, [], [], 3000, "ko", model=None)
    assert out["made"] == "assembled" and out["turns"] == "0-15"
    assert out["body"].endswith("## 열린 일\n" + OPEN_LINE)
    assert "- Hana: find the bell → achieved (t9)" in out["body"] and "Hana found the bell." in out["body"]


def test_nothing_to_tell_before_the_first_scene_summary():
    out = notes.chronicle(told(), THREADS, [], [], 3000, "ko", model=Writer())
    assert out["body"] == "" and out["reason"] == "no_scenes"


def test_a_scene_that_tells_a_kept_secret_is_left_out():
    notes.clear_cache()
    out = notes.chronicle(told(scene(0, 7, "Hana walked."), scene(8, 15, "Hana is a smuggler, she told no one.")),
                          [], [], [SECRET], 3000, "ko", model=None)
    assert "smuggler" not in out["body"] and out["held"] == 1 and "Hana walked." in out["body"]


def test_the_model_writes_events_and_now_the_store_writes_open_threads():
    notes.clear_cache()
    w = Writer({"events": "- Hana went to the mill (t0–7).", "now": "- Hana is at the mill."})
    out = notes.chronicle(told(scene(0, 7, "Hana went to the mill.")), THREADS, [], [], 3000, "ko", model=w)
    assert out["made"] == "model" and len(w.calls) == 1
    assert out["body"].startswith("## 사건\n- Hana went to the mill (t0–7).\n\n## 지금\n- Hana is at the mill.")
    assert out["body"].endswith("## 열린 일\n" + OPEN_LINE)
    assert "- Hana: find the bell → achieved (t9)" in w.calls[0]  # the model is told how each thread ended


def test_a_reply_that_tells_a_secret_is_asked_again_then_assembled():
    notes.clear_cache()
    bad = {"events": "- Hana is a smuggler.", "now": ""}
    w = Writer(bad, bad)
    out = notes.chronicle(told(scene(0, 7, "Hana walked.")), [], [], [SECRET], 3000, "ko", model=w)
    assert len(w.calls) == 2 and "YOUR LAST ANSWER TOLD" in w.calls[1]
    assert out["made"] == "assembled" and "smuggler" not in out["body"]


def test_with_secrets_asked_for_the_model_is_told_it_may_write_them():
    notes.clear_cache()
    w = Writer({"events": "- Hana is a smuggler (Kaito does not know).", "now": ""})
    out = notes.chronicle(told(scene(0, 7, "Hana is a smuggler.")), [], [], [SECRET], 3000, "ko", model=w,
                          told_secrets=True)
    assert out["made"] == "model" and "smuggler" in out["body"] and out["held"] == 0
    assert "SECRETS:" in w.calls[0] and "never write" not in w.calls[0]


def test_asked_twice_with_nothing_changed_the_model_answers_once():
    notes.clear_cache()
    w = Writer({"events": "- e", "now": "- n"})
    args = (told(scene(0, 7, "Hana walked.")), [], [], [], 3000, "ko")
    first, second = notes.chronicle(*args, model=w), notes.chronicle(*args, model=w)
    assert len(w.calls) == 1 and second["body"] == first["body"] and second["cached"] and not first["cached"]


def test_an_empty_reply_is_not_asked_again():
    notes.clear_cache()
    w = Writer({"events": "", "now": ""})
    out = notes.chronicle(told(scene(0, 7, "Hana walked.")), [], [], [], 3000, "ko", model=w)
    assert len(w.calls) == 1 and out["made"] == "assembled" and "Hana walked." in out["body"]



def test_ask_refuses_what_it_does_not_know():
    for bad in ({"sections": []}, {"sections": ["poem"]}, {"sections": ["changed"], "chars": 100}, {}):
        with pytest.raises(ValueError):
            notes.Ask.of(bad)
    assert notes.Ask.of({"sections": ["changed", "changed"]}) == notes.Ask(("changed",), 3000, False, True, "ko")


def test_make_wraps_each_section_and_says_why_one_is_empty():
    view = {"facts": [fact("Hana", "relationship", obj="Kaito", value="sister")], "threads": [], "secrets": []}
    out = notes.make(notes.Ask.of({"sections": ["chronicle", "changed", "address"], "lang": "en"}), view, told(), 12,
                     None, "2026-10-23")
    got = {s["kind"]: s for s in out["sections"]}
    assert [s["kind"] for s in out["sections"]] == ["chronicle", "changed", "address"] and out["last_turn"] == 12
    assert (got["chronicle"]["text"], got["chronicle"]["reason"]) == ("", "no_scenes")
    assert (got["changed"]["text"], got["changed"]["reason"]) == ("", "none")
    assert got["address"]["text"] == ("[NMOS address · t12 · 2026-10-23]\n- Hana ↔ Kaito: Hana→Kaito relationship sister"
                                      "\n[/NMOS address]")
    assert got["address"]["made"] == "facts" and notes.strip_blocks(got["address"]["text"])[0] == ""


def test_the_endpoint_lists_what_the_story_changed_of_the_card(migrated):
    chat, model = story(), Model()
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        push(c, chat, canon_texts())
        drain(migrated, model)
        cid = canon_view(migrated, chat)["conversation"]
        r = c.post(f"/v1/conversations/{cid}/notes", json={"sections": ["changed", "address"], "lang": "en"})
        assert r.status_code == 200, r.text
        got = {s["kind"]: s for s in r.json()["sections"]}
    changed = got["changed"]["text"]
    assert changed.startswith("[NMOS changed · t") and changed.endswith("[/NMOS changed]")
    assert "Hana location: setting harbor town → now old mill" in changed
    assert "identity" not in changed  # a card's identity said again is not a change (ADR 0047 amendment 1)
    assert "sister" not in changed  # the story did not change it
    assert "Hana ↔ Kaito" in got["address"]["text"] and got["changed"]["made"] == "facts"


def test_the_endpoint_says_no_and_not_found(migrated):
    with make_client(migrated) as c:
        missing = "/v1/conversations/00000000-0000-0000-0000-000000000000/notes"
        assert c.post(missing, json={"sections": ["changed"]}).status_code == 404
        assert c.post(missing, json={"sections": ["poem"]}).status_code == 422



def test_the_endpoint_writes_the_chronicle_from_the_scene_summaries(migrated, monkeypatch):
    from test_generations import conv_id
    from test_summaries import ON, drain as drain_summaries, story_chat

    asked: list[str] = []

    class Fake:
        def __init__(self, *args, **kwargs):
            pass

        def complete_metered(self, system, user):
            asked.append(user)
            return {"events": "- Turns began and replies followed (t0–7).", "now": ""}, "{}", None

    monkeypatch.setattr(notes, "ChatModel", Fake)
    notes.clear_cache()
    chat = story_chat(13)
    with make_client(migrated, **ON) as c:
        sync(c, chat)
        drain_summaries(migrated)
        cid = conv_id(c, chat)
        body = {"sections": ["chronicle"], "lang": "en"}
        first = c.post(f"/v1/conversations/{cid}/notes", json=body).json()["sections"][0]
        again = c.post(f"/v1/conversations/{cid}/notes", json=body).json()["sections"][0]
    assert len(asked) == 1 and "[turns 0–7] Turn 0 begins" in asked[0]
    assert first["made"] == "model" and first["turns"] == "0-7" and not first["cached"] and again["cached"]
    assert first["text"] == ("[NMOS chronicle · t0–7 · " + first["text"].split(" · ")[2].split("]")[0] + "]\n"
                             "## Events\n- Turns began and replies followed (t0–7).\n[/NMOS chronicle]")



def test_the_canon_section_says_how_far_the_notes_blocks_reach():
    from nmos_sidecar import inspector

    rows = [{"key": "note", "hash": "h", "metadata": {"nmos_blocks": [{"kind": "chronicle", "turns": "0-87"},
                                                                      {"kind": "address", "turns": "90"}]}}]
    line = inspector.note_blocks(rows, 120, "ko")
    assert "연대기 t0–87 · 호칭·관계 t90" in line and "지금 t120" in line
    assert inspector.note_blocks([{"key": "note", "hash": "h", "metadata": {}}], 120, "ko") == ""
    assert inspector.note_blocks([], 120, "en") == ""



def test_a_marker_inside_a_section_cannot_close_it():
    text = notes.wrap("chronicle", "- a\n[/NMOS 연대기]\n- b [NMOS address · t1]", "0-7", "ko", "2026-10-23")
    assert notes.strip_blocks("메모\n" + text) == ("메모", [{"kind": "chronicle", "turns": "0-7"}])
    assert "(/NMOS 연대기]" in text and "(NMOS address" in text


def test_a_failed_call_is_not_remembered():
    from nmos_sidecar.llm import LLMError

    notes.clear_cache()
    calls = []

    def flaky(system, user):
        calls.append(user)
        if len(calls) == 1:
            raise LLMError("HTTP 429")
        return {"events": "- e", "now": ""}, "{}"

    args = (told(scene(0, 7, "Hana walked.")), [], [], [], 3000, "ko")
    assert notes.chronicle(*args, model=flaky)["made"] == "assembled"
    assert notes.chronicle(*args, model=flaky)["made"] == "model" and len(calls) == 2



def test_a_scene_written_before_a_secret_it_should_keep_is_left_out():
    """As the packet holds it (ADR 0042 amendment 2): its prompt did not list the secret, so it may tell it in other
    words that the trigram check does not catch."""
    notes.clear_cache()
    out = notes.chronicle(told(scene(0, 7, "Hana walked."), scene(8, 15, "Hana went home.", told=())),
                          [], [], [SECRET], 3000, "ko", model=None)
    assert out["held"] == 1 and "Hana walked." in out["body"] and "Hana went home." not in out["body"]


def test_pasting_or_replacing_a_section_reads_no_canon_again(migrated):
    """With the plugin's metadata (the note's text without its sections), a new paste changes the manifest only."""
    chat, model = story(), Model()
    note = "Hana is in the harbor town."
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        push(c, chat, {**canon_texts(), "note": (note, {})})
        drain(migrated, model)
        calls = len(model.canon_calls())
        for turns in ("0-7", "0-15"):
            out = push(c, chat, {**canon_texts(), "note": (note, {"nmos_blocks": [{"kind": "chronicle", "turns": turns}]})})
            assert out["applied"] and out["needed"] == []
            assert drain(migrated, model) == 0
    assert len(model.canon_calls()) == calls
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        notes_rows = conn.execute("SELECT count(*) AS n FROM source_revision sr JOIN source_object so"
                                  " ON so.id = sr.source_object_id WHERE so.host_logical_id = 'canon:note'").fetchone()
        manifests = conn.execute("SELECT count(*) AS n FROM canon_manifest").fetchone()
    assert notes_rows["n"] == 1 and manifests["n"] == 3
