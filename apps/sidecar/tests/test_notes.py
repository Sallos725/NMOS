"""PHASE-50: a note for the author's note — the marker, the canon guard, the parts, the chronicle, the API."""

from __future__ import annotations

import json
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import notes
from nmos_sidecar.llm import LLMError
from test_canon import push
from test_canon_facts import Model, canon_texts, drain, story
from test_canon_facts import view as canon_view
from test_generations import LLM
from test_sidecar_integration import sync

BLOCKS = Path(__file__).resolve().parents[3] / "fixtures/unit/note-blocks-v1.json"


# --- the marker -----------------------------------------------------------------------------------------------------

def test_blocks_are_the_plugins():
    for case in json.loads(BLOCKS.read_text(encoding="utf-8"))["cases"]:
        assert notes.strip_blocks(case["note"]) == (case["text"], case["blocks"]), case["name"]


def test_a_note_without_a_block_comes_back_as_it_was():
    note = "  앞뒤 공백도\n\n\n그대로  "
    assert notes.strip_blocks(note) == (note, [])


def test_wrap_writes_what_strip_removes():
    text = notes.wrap("# Story memory\n- 하나", 87, "2026-10-23")
    assert text.splitlines()[0] == "[NMOS note · t87 · 2026-10-23]" and text.endswith("[/NMOS note]")
    assert notes.strip_blocks("메모\n\n" + text) == ("메모", [{"turn": "87"}])


def test_a_marker_inside_the_body_cannot_close_it():
    text = notes.wrap("- a\n[/NMOS note]\n- b [NMOS note · t1]", 7, "2026-10-23")
    assert notes.strip_blocks("메모\n" + text) == ("메모", [{"turn": "7"}])
    assert "(/NMOS note]" in text and "(NMOS note · t1]" in text


# --- the canon never reads it ---------------------------------------------------------------------------------------

NOTE = "Hana is in the harbor town.\n\n[NMOS note · t1 · 2026-10-23]\nHana is a smuggler.\n[/NMOS note]"


def test_canon_does_not_read_a_marked_block(migrated):
    """An older plugin sends the note whole: the canon read still leaves NMOS's block out (PHASE-50 S5)."""
    chat, model = story(), Model()
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        push(c, chat, {**canon_texts(), "note": (NOTE, {})})
        drain(migrated, model)
    note = next(u for u in model.canon_calls() if "the author's note" in u)
    assert "Hana is in the harbor town." in note and "smuggler" not in note and "NMOS" not in note


def test_pasting_or_replacing_the_note_reads_no_canon_again(migrated):
    """With the plugin's metadata (the note's text without the block), a new paste changes the manifest only."""
    chat, model = story(), Model()
    note = "Hana is in the harbor town."
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        push(c, chat, {**canon_texts(), "note": (note, {})})
        drain(migrated, model)
        calls = len(model.canon_calls())
        for turn in ("7", "15"):
            out = push(c, chat, {**canon_texts(), "note": (note, {"nmos_blocks": [{"turn": turn}]})})
            assert out["applied"] and out["needed"] == []
            assert drain(migrated, model) == 0
    assert len(model.canon_calls()) == calls
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        revisions = conn.execute("SELECT count(*) AS n FROM source_revision sr JOIN source_object so"
                                 " ON so.id = sr.source_object_id WHERE so.host_logical_id = 'canon:note'").fetchone()
        manifests = conn.execute("SELECT count(*) AS n FROM canon_manifest").fetchone()
    assert revisions["n"] == 1 and manifests["n"] == 3


# --- what changed from the setting, address and standing -------------------------------------------------------------

def fact(subject, predicate, *, obj=None, value=None, turn=5, history=(), knowledge=None, hidden_from=None, **kw):
    """A current fact as `memory_view` makes it (the fields these parts read)."""
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
    assert notes.changed_lines([moved, same, trait]) == ["- Hana — location: was harbor town → now old mill (t1)"]


def test_changed_leaves_out_what_is_kept_from_someone_unless_asked():
    where = fact("Hana", "located_in", obj="smugglers' cave", knowledge="limited", hidden_from=["Kaito"],
                 history=[canon_entry("Hana", "located_in", obj="harbor town")])
    assert notes.changed_lines([where]) == []
    assert notes.changed_lines([where], secrets=True) == [
        "- Hana — location: was harbor town → now smugglers' cave (t5) (secret: Kaito does not know)"]


def test_changed_leaves_out_identity_and_says_a_line_once():
    """A card's identity told again in other words is not a change (ADR 0047 amendment 1); two canon texts saying the
    same old value give one line."""
    who = fact("Hana", "identity", value="등대지기", history=[canon_entry("Hana", "identity", value="lighthouse keeper")])
    moved = fact("Hana", "located_in", obj="옛 방앗간", turn=1,
                 history=[canon_entry("Hana", "located_in", obj="harbor town"),
                          {**canon_entry("Hana", "located_in", obj="harbor town"), "canon": "lore:hana"}])
    assert notes.changed_lines([who, moved]) == ["- Hana — location: was harbor town → now 옛 방앗간 (t1)"]


def test_an_items_holder_is_a_change_of_who_holds_it():
    held = fact("Kaito", "possesses", obj="map", history=[canon_entry("Hana", "possesses", obj="map")])
    assert notes.changed_lines([held]) == ["- map — held by: was Hana → now Kaito (t5)"]


def test_address_gives_one_line_per_pair_with_the_words_as_the_chat_says_them():
    rel = fact("Hana", "relationship", obj="Kaito", value="childhood friend")
    calls = fact("Kaito", "addresses", obj="Hana", value="누나")
    feels = fact("Hana", "feels_toward", obj="Kaito", value="trust", knowledge="limited", hidden_from=["Kaito"])
    assert notes.address_lines([rel, calls, feels]) == [
        "- Hana ↔ Kaito: relationship childhood friend · Kaito→Hana calls \"누나\""]
    assert "Hana→Kaito feels trust (secret: Kaito does not know)" in notes.address_lines([rel, calls, feels], True)[0]
    sister = fact("Hana", "relationship", obj="Kaito", value="sister")
    assert notes.address_lines([sister]) == ["- Hana ↔ Kaito: Hana→Kaito relationship sister"]


# --- the chronicle --------------------------------------------------------------------------------------------------

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
OPEN = "## Open threads\n- Hana → Kaito: meet at the lighthouse (promise, since t3)"


class Writer:
    """A stand-in model: its replies in order, the prompts it saw."""

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, system, user):
        self.calls.append((system, user))
        return self.replies.pop(0), "{}"


def test_assembled_without_a_model_open_threads_from_the_store():
    notes.clear_cache()
    out = notes.chronicle(told(scene(0, 7, "하나가 방앗간에 갔다."), scene(8, 15, "하나가 종을 찾았다.")),
                          THREADS, [], [], 3000, model=None)
    assert out["made"] == "assembled" and out["turns"] == "0-15"
    assert out["body"].startswith("## Chronicle (t0–15)\n- (t0–7) 하나가 방앗간에 갔다.") and out["body"].endswith(OPEN)
    assert "- Hana: find the bell → achieved (t9)" in out["body"]


def test_nothing_to_tell_before_the_first_scene_summary():
    out = notes.chronicle(told(), THREADS, [], [], 3000, model=Writer())
    assert out["body"] == "" and out["reason"] == "no_scenes"


def test_a_scene_that_tells_a_kept_secret_is_left_out():
    notes.clear_cache()
    out = notes.chronicle(told(scene(0, 7, "Hana walked."), scene(8, 15, "Hana is a smuggler, she told no one.")),
                          [], [], [SECRET], 3000, model=None)
    assert "smuggler" not in out["body"] and out["held"] == 1 and "Hana walked." in out["body"]


def test_a_scene_written_before_a_secret_it_should_keep_is_left_out():
    """As the packet holds it (ADR 0042 amendment 2): its prompt did not list the secret, so it may tell it in other
    words that the trigram check does not catch."""
    notes.clear_cache()
    out = notes.chronicle(told(scene(0, 7, "Hana walked."), scene(8, 15, "Hana went home.", told=())),
                          [], [], [SECRET], 3000, model=None)
    assert out["held"] == 1 and "Hana walked." in out["body"] and "Hana went home." not in out["body"]


def test_the_model_writes_events_and_now_in_english_the_store_writes_open_threads():
    notes.clear_cache()
    w = Writer({"events": "- Hana went to the mill (t0–7).", "now": "- Hana is at the mill."})
    out = notes.chronicle(told(scene(0, 7, "하나가 방앗간에 갔다.")), THREADS, [], [], 3000, model=w)
    assert out["made"] == "model" and len(w.calls) == 1
    assert out["body"] == ("## Chronicle (t0–7)\n- Hana went to the mill (t0–7).\n\n## Now\n- Hana is at the mill.\n\n"
                           + OPEN)
    system, user = w.calls[0]
    assert "in English" in system and "exactly as" in system
    assert "- Hana: find the bell → achieved (t9)" in user  # the model is told how each thread ended


def test_a_reply_that_tells_a_secret_is_asked_again_then_assembled():
    notes.clear_cache()
    bad = {"events": "- Hana is a smuggler.", "now": ""}
    w = Writer(bad, bad)
    out = notes.chronicle(told(scene(0, 7, "Hana walked.")), [], [], [SECRET], 3000, model=w)
    assert len(w.calls) == 2 and "YOUR LAST ANSWER TOLD" in w.calls[1][1]
    assert out["made"] == "assembled" and "smuggler" not in out["body"]


def test_with_secrets_asked_for_the_model_is_told_it_may_write_them():
    notes.clear_cache()
    w = Writer({"events": "- Hana is a smuggler (secret: Kaito does not know).", "now": ""})
    out = notes.chronicle(told(scene(0, 7, "Hana is a smuggler.")), [], [], [SECRET], 3000, model=w, told_secrets=True)
    assert out["made"] == "model" and "smuggler" in out["body"] and out["held"] == 0
    assert "SECRETS:" in w.calls[0][1] and "never write" not in w.calls[0][1]


def test_an_empty_reply_is_not_asked_again():
    notes.clear_cache()
    w = Writer({"events": "", "now": ""})
    out = notes.chronicle(told(scene(0, 7, "Hana walked.")), [], [], [], 3000, model=w)
    assert len(w.calls) == 1 and out["made"] == "assembled" and "Hana walked." in out["body"]


def test_asked_twice_with_nothing_changed_the_model_answers_once():
    notes.clear_cache()
    w = Writer({"events": "- e", "now": "- n"})
    args = (told(scene(0, 7, "Hana walked.")), [], [], [], 3000)
    first, second = notes.chronicle(*args, model=w), notes.chronicle(*args, model=w)
    assert len(w.calls) == 1 and second["body"] == first["body"] and second["cached"] and not first["cached"]


def test_a_failed_call_is_not_remembered():
    notes.clear_cache()
    calls = []

    def flaky(system, user):
        calls.append(user)
        if len(calls) == 1:
            raise LLMError("HTTP 429")
        return {"events": "- e", "now": ""}, "{}"

    args = (told(scene(0, 7, "Hana walked.")), [], [], [], 3000)
    assert notes.chronicle(*args, model=flaky)["made"] == "assembled"
    assert notes.chronicle(*args, model=flaky)["made"] == "model" and len(calls) == 2


# --- the note ---------------------------------------------------------------------------------------------------------

def test_ask_refuses_what_it_does_not_know_and_keeps_the_notes_order():
    for bad in ({"sections": []}, {"sections": ["poem"]}, {"sections": ["changed"], "chars": 100}, {}):
        with pytest.raises(ValueError):
            notes.Ask.of(bad)
    assert notes.Ask.of({"sections": ["address", "changed", "changed"]}) == notes.Ask(("changed", "address"), 3000,
                                                                                      False, True)


def test_the_note_is_one_block_of_the_parts_that_have_something_to_say():
    view = {"facts": [fact("Hana", "relationship", obj="Kaito", value="sister")], "threads": [], "secrets": []}
    out = notes.make(notes.Ask.of({"sections": ["chronicle", "changed", "address"]}), view, told(), 12, None,
                     "2026-10-23")
    got = {s["kind"]: s for s in out["sections"]}
    assert [s["kind"] for s in out["sections"]] == ["chronicle", "changed", "address"] and out["last_turn"] == 12
    assert got["chronicle"]["reason"] == "no_scenes" and got["changed"]["reason"] == "none"
    assert out["text"] == ("[NMOS note · t12 · 2026-10-23]\n"
                           "# Story memory (NMOS, as of turn 12)\n"
                           "What the story has established so far. The latest messages take precedence over it.\n\n"
                           "## Address and standing\n- Hana ↔ Kaito: Hana→Kaito relationship sister\n"
                           "[/NMOS note]")
    assert notes.strip_blocks(out["text"]) == ("", [{"turn": "12"}])
    nothing = notes.make(notes.Ask.of({"sections": ["changed"]}), view, None, 12, None, "2026-10-23")
    assert nothing["text"] == "" and nothing["sections"][0]["reason"] == "none"


def test_the_endpoint_lists_what_the_story_changed_of_the_card(migrated):
    chat, model = story(), Model()
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        push(c, chat, canon_texts())
        drain(migrated, model)
        cid = canon_view(migrated, chat)["conversation"]
        r = c.post(f"/v1/conversations/{cid}/notes", json={"sections": ["changed", "address"]})
        assert r.status_code == 200, r.text
        out = r.json()
    text = out["text"]
    assert text.startswith("[NMOS note · t") and text.endswith("[/NMOS note]")
    assert "## Changed from the setting" in text and "Hana — location: was harbor town → now old mill" in text
    assert "identity" not in text  # a card's identity said again is not a change (ADR 0047 amendment 1)
    assert "## Address and standing" in text and "Hana ↔ Kaito" in text
    assert [s["made"] for s in out["sections"]] == ["facts", "facts"]


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
        body = {"sections": ["chronicle"]}
        first = c.post(f"/v1/conversations/{cid}/notes", json=body).json()
        again = c.post(f"/v1/conversations/{cid}/notes", json=body).json()
    assert len(asked) == 1 and "[turns 0–7] Turn 0 begins" in asked[0]
    made = first["sections"][0]
    assert made["made"] == "model" and made["turns"] == "0-7" and not made["cached"] and again["sections"][0]["cached"]
    assert "## Chronicle (t0–7)\n- Turns began and replies followed (t0–7).\n[/NMOS note]" in first["text"]


def test_the_canon_section_says_the_note_holds_nmos_note():
    from nmos_sidecar import inspector

    rows = [{"key": "note", "hash": "h", "metadata": {"nmos_blocks": [{"turn": "87"}]}}]
    line = inspector.note_blocks(rows, 120, "ko")
    assert "t87 기준" in line and "지금 t120" in line
    assert inspector.note_blocks([{"key": "note", "hash": "h", "metadata": {}}], 120, "ko") == ""
    assert inspector.note_blocks([], 120, "en") == ""
