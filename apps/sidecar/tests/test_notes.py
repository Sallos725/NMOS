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
    assert notes.Ask.of({"sections": ["address", "diverged", "changed"]}).sections == ("diverged", "address")


def test_the_note_is_one_block_of_the_parts_that_have_something_to_say():
    view = {"facts": [fact("Hana", "relationship", obj="Kaito", value="sister")], "threads": [], "secrets": []}
    out = notes.make(notes.Ask.of({"sections": ["chronicle", "changed", "address"]}), view, told(), 12, None,
                     "2026-10-23")
    got = {s["kind"]: s for s in out["sections"]}
    assert [s["kind"] for s in out["sections"]] == ["chronicle", "changed", "address"] and out["last_turn"] == 12
    assert got["chronicle"]["reason"] == "no_scenes" and got["changed"]["reason"] == "none"
    assert out["text"] == ("[NMOS note · t12 · 2026-10-23]\n"
                           "# Story memory (NMOS, as of turn 12)\n"
                           "What the story has established so far. The latest messages take precedence over it.\n"
                           "The character card and lorebook were written before the story began: where they disagree"
                           " with this note, this note is true now.\n\n"
                           "## Address and standing\n- Hana ↔ Kaito: Hana→Kaito relationship sister\n"
                           "[/NMOS note]")
    assert notes.strip_blocks(out["text"]) == ("", [{"turn": "12"}])
    nothing = notes.make(notes.Ask.of({"sections": ["changed"]}), view, None, 12, None, "2026-10-23")
    assert nothing["text"] == "" and nothing["sections"][0]["reason"] == "none"


def test_diverged_comes_first_and_falls_back_to_what_changed():
    notes.clear_cache()
    hist = [canon_entry("Hana", "located_in", obj="harbor town")]
    view = {"facts": [fact("Hana", "located_in", obj="old mill", turn=7, history=hist)], "threads": [], "secrets": [],
            "entities": []}
    out = notes.make(notes.Ask.of({"sections": ["address", "diverged"]}), view, told(), 12, None, "2026-11-01",
                     canon=[])
    assert [s["kind"] for s in out["sections"]] == ["diverged", "address"]
    assert out["sections"][0]["made"] == "facts" and out["sections"][0]["lines"] == 1
    assert "## Diverged from the setting\n- Hana — location: was harbor town → now old mill (t7)" in out["text"]


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


def test_the_endpoint_compares_the_setting_with_the_story(migrated, monkeypatch):
    import re

    asked: list[str] = []

    class Fake:
        def __init__(self, *args, **kwargs):
            pass

        def complete_metered(self, system, user):
            asked.append(user)
            turn = int(re.search(r"\[t(\d+)\] Hana located in old mill", user)[1])
            return {"diverged": [{"key": "card:desc", "quote": "Hana is in the harbor town", "subject": "Hana",
                                  "now": "in the old mill", "turns": [turn], "kind": "world"}]}, "{}", None

    monkeypatch.setattr(notes, "ChatModel", Fake)
    notes.clear_cache()
    chat, model = story(), Model()
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        push(c, chat, canon_texts())
        drain(migrated, model)
        cid = canon_view(migrated, chat)["conversation"]
        out = c.post(f"/v1/conversations/{cid}/notes", json={"sections": ["diverged"]}).json()
    assert len(asked) == 1 and "[key: card:desc] (card)\nHana is a lighthouse keeper." in asked[0]
    assert "lore:mira" not in asked[0]  # Mira is in no story fact or scene
    part = out["sections"][0]
    assert part["kind"] == "diverged" and part["made"] == "model" and part["lines"] == 1
    assert '- Hana (card): the setting says "Hana is in the harbor town" → now in the old mill (t' in out["text"]


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



def test_an_open_thread_not_said_again_for_30_turns_is_left_out_and_counted():
    """As the Inspector's "needs a look" (PHASE-13 Q6): from the note's Open threads and from the model's input."""
    notes.clear_cache()
    old = {**THREADS[0], "text": "fight at four", "turn": 2, "restated": []}
    kept_alive = {**THREADS[0], "text": "pay the debt", "turn": 6, "restated": [{"turn": 40, "position": 40}]}
    w = Writer({"events": "- e", "now": ""})
    out = notes.chronicle(told(scene(0, 7, "Hana walked.")), [old, kept_alive], [], [], 3000, model=w, last_turn=50)
    assert out["stale"] == 1 and "fight at four" not in out["body"] and "fight at four" not in w.calls[0][1]
    assert "- Hana → Kaito: pay the debt (promise, since t6)" in out["body"]


# --- the custom part (PHASE-56) ---------------------------------------------------------------------------------------

def setting_entry(key, text, **metadata):
    return {"key": key, "hash": "h", "metadata": metadata, "content": text, "revision_id": None}


def test_ask_takes_the_custom_prompt_only_with_the_custom_part():
    for bad in ({"sections": ["custom"]}, {"sections": ["custom"], "custom_prompt": "   "},
                {"sections": ["custom"], "custom_prompt": 7},
                {"sections": ["custom"], "custom_prompt": "x" * (notes.PROMPT_MAX + 1)}):
        with pytest.raises(ValueError):
            notes.Ask.of(bad)
    ask = notes.Ask.of({"sections": ["custom", "chronicle"], "custom_prompt": "  List outfits.  ",
                        "custom_setting": True})
    assert ask.sections == ("chronicle", "custom") and ask.custom_prompt == "List outfits." and ask.custom_setting
    # an older plugin's request is what it was, whatever else it sends
    older = notes.Ask.of({"sections": ["chronicle"], "custom_prompt": "ignored", "custom_setting": True})
    assert older == notes.Ask(("chronicle",), 3000, False, True)


def test_the_custom_part_writes_what_the_prompt_asks_inside_the_frame():
    notes.clear_cache()
    w = Writer({"text": "### Outfits\n- Hana: a grey coat (t7)."})
    out = notes.custom("List each character's outfit. {not a field}", told(scene(0, 7, "하나가 회색 코트를 입었다.")),
                       THREADS, [], [], 3000, model=w)
    assert out["made"] == "model" and out["turns"] == "0-7" and out["reason"] == ""
    assert out["body"] == "## Custom (owner's prompt)\n### Outfits\n- Hana: a grey coat (t7)."
    system, user = w.calls[0]
    # the owner's words verbatim, then the frame's rules, which the prompt cannot come after
    assert "List each character's outfit. {not a field}" in system
    assert system.index("{not a field}") < system.index("from the input only") < system.index("OPEN SECRETS")
    assert system.rstrip().endswith('{"text": "..."}') and "SETTING" not in system
    assert "[turns 0–7] 하나가 회색 코트를 입었다." in user and "- Hana: find the bell → achieved (t9)" in user


def test_the_custom_part_has_no_fallback():
    notes.clear_cache()
    args = ("Anything.", told(scene(0, 7, "Hana walked.")), [], [], [], 3000)
    assert notes.custom(*args, model=None)["reason"] == "no_model"
    assert notes.custom("Anything.", told(), [], [], [], 3000, model=Writer())["reason"] == "no_scenes"

    def broken(system, user):
        raise LLMError("not a JSON object")

    out = notes.custom(*args, model=broken)
    assert out["made"] == "none" and out["reason"] == "failed" and out["body"] == ""
    w = Writer({"text": 3}, {"answer": "x"})
    assert notes.custom(*args, model=w)["reason"] == "failed" and len(w.calls) == 2  # asked again once


def test_a_custom_reply_that_tells_a_secret_is_asked_again_then_left_out():
    notes.clear_cache()
    bad = {"text": "- Hana is a smuggler."}
    w = Writer(bad, bad)
    out = notes.custom("Who is Hana?", told(scene(0, 7, "Hana walked.")), [], [], [SECRET], 3000, model=w)
    assert len(w.calls) == 2 and "YOUR LAST ANSWER TOLD" in w.calls[1][1]
    assert out["reason"] == "held" and out["body"] == "" and "smuggler" not in str(out)
    w = Writer(bad, {"text": "- Hana walked."})
    assert notes.custom("Who is Hana?", told(scene(0, 7, "Hana walked.")), [], [], [SECRET], 3000,
                        model=w)["body"].endswith("- Hana walked.")


def test_with_secrets_asked_for_the_custom_part_may_write_them():
    notes.clear_cache()
    w = Writer({"text": "- Hana is a smuggler (secret: Kaito does not know)."})
    out = notes.custom("Who is Hana?", told(scene(0, 7, "Hana walked.")), [], [], [SECRET], 3000, model=w,
                       told_secrets=True)
    assert out["made"] == "model" and "smuggler" in out["body"] and len(w.calls) == 1


def test_an_empty_custom_answer_is_an_answer():
    notes.clear_cache()
    w = Writer({"text": "  "})
    out = notes.custom("Anything.", told(scene(0, 7, "Hana walked.")), [], [], [], 3000, model=w)
    assert len(w.calls) == 1 and out["made"] == "model" and out["reason"] == "none" and out["body"] == ""


def test_the_custom_part_is_cached_by_its_prompt_and_its_input():
    notes.clear_cache()
    w = Writer({"text": "- a"}, {"text": "- b"}, {"text": "- c"})
    args = (told(scene(0, 7, "Hana walked.")), [], [], [], 3000)
    first, again = notes.custom("One.", *args, model=w), notes.custom("One.", *args, model=w)
    assert len(w.calls) == 1 and again["cached"] and again["body"] == first["body"]
    assert notes.custom("One!", *args, model=w)["body"].endswith("- b") and len(w.calls) == 2
    with_setting = notes.custom("One.", *args, model=w, setting=[])
    assert with_setting["body"].endswith("- c") and len(w.calls) == 3


def test_the_setting_goes_in_only_when_asked_for():
    notes.clear_cache()
    canon = [setting_entry("card:desc", "Hana is a lighthouse keeper.", field="desc"),
             setting_entry("lore:kaito", "Kaito is a squire.", keys=["Kaito"], scope="character", mode="normal"),
             setting_entry("lore:mira", "Mira is a baker.", keys=["Mira"], scope="character", mode="normal")]
    entities = [{"id": "e-Kaito", "name": "Kaito", "aliases": []}]
    w = Writer({"text": "- x"})
    out = notes.custom("Compare.", told(scene(0, 7, "Kaito rode out.")), [], [], [], 3000, model=w, setting=canon,
                       entities=entities)
    system, user = w.calls[0]
    assert "You also get the SETTING" in system and user.startswith("SETTING:\n[key: card:desc] (card)")
    assert "Kaito is a squire." in user and "lore:mira" not in user
    assert out["entries"] == 1 and out["left_out"] == 0
    assert "entries" not in notes.custom("Compare.", told(scene(0, 7, "Kaito rode out.")), [], [], [], 3000,
                                         model=Writer({"text": "- y"}))


def test_a_fact_kept_from_someone_picks_no_setting_entry():
    """As PHASE-53 ranks entries: with secrets off, a kept fact neither goes in nor picks the entry about its subject."""
    notes.clear_cache()
    canon = [setting_entry("lore:kaito", "Kaito is a squire.", keys=["Kaito"], scope="character", mode="normal")]
    entities = [{"id": "e-Kaito", "name": "Kaito", "aliases": []}]
    hidden = fact("Kaito", "has_status", value="spy", turn=6, knowledge="limited", hidden_from=["Hana"])
    hidden["subject_entity"] = {"id": "e-Kaito", "name": "Kaito"}
    args = ("Compare.", told(scene(0, 7, "Hana walked.")), [], [hidden], [], 3000)
    off = notes.custom(*args, model=Writer({"text": "- x"}), setting=canon, entities=entities)
    on = notes.custom(*args, model=Writer({"text": "- y"}), setting=canon, entities=entities, told_secrets=True)
    assert off["entries"] == 0 and on["entries"] == 1


def test_the_custom_part_comes_last_in_the_note():
    notes.clear_cache()
    view = {"facts": [fact("Hana", "relationship", obj="Kaito", value="sister")], "threads": [], "secrets": []}
    ask = notes.Ask.of({"sections": ["custom", "address"], "custom_prompt": "One line."})
    out = notes.make(ask, view, told(scene(0, 7, "Hana walked.")), 12, Writer({"text": "- one line"}), "2026-11-05")
    assert [s["kind"] for s in out["sections"]] == ["address", "custom"]
    assert out["text"].endswith("## Address and standing\n- Hana ↔ Kaito: Hana→Kaito relationship sister\n\n"
                                "## Custom (owner's prompt)\n- one line\n[/NMOS note]")
    part = out["sections"][1]
    assert part["made"] == "model" and part["chars"] == len("## Custom (owner's prompt)\n- one line")


def test_the_prompt_is_one_for_every_chat(migrated):
    with make_client(migrated) as c:
        assert c.get("/v1/notes/prompt").json() == {"prompt": ""}
        assert c.put("/v1/notes/prompt", json={"prompt": "  List outfits.  "}).json() == {"prompt": "List outfits."}
        assert c.get("/v1/notes/prompt").json() == {"prompt": "List outfits."}
        assert c.put("/v1/notes/prompt", json={"prompt": "x" * (notes.PROMPT_MAX + 1)}).status_code == 422
        assert c.put("/v1/notes/prompt", json={"prompt": None}).status_code == 422
        assert c.put("/v1/notes/prompt", json={"prompt": ""}).json() == {"prompt": ""}
        assert c.get("/v1/notes/prompt").json() == {"prompt": ""}
    with psycopg.connect(migrated) as conn:
        assert conn.execute("SELECT count(*) FROM app_config WHERE key = 'notes_custom_prompt'").fetchone()[0] == 0


def test_the_endpoint_writes_the_custom_part(migrated, monkeypatch):
    from test_generations import conv_id
    from test_summaries import ON, drain as drain_summaries, story_chat

    asked: list[tuple[str, str]] = []

    class Fake:
        def __init__(self, *args, **kwargs):
            pass

        def complete_metered(self, system, user):
            asked.append((system, user))
            return {"text": "- Turns went by."}, "{}", None

    monkeypatch.setattr(notes, "ChatModel", Fake)
    notes.clear_cache()
    chat = story_chat(13)
    with make_client(migrated, **ON) as c:
        sync(c, chat)
        drain_summaries(migrated)
        cid = conv_id(c, chat)
        out = c.post(f"/v1/conversations/{cid}/notes",
                     json={"sections": ["custom"], "custom_prompt": "Say what happened."}).json()
        assert c.post(f"/v1/conversations/{cid}/notes", json={"sections": ["custom"]}).status_code == 422
    assert len(asked) == 1 and "Say what happened." in asked[0][0] and "[turns 0–7] Turn 0 begins" in asked[0][1]
    assert "SETTING" not in asked[0][1]
    assert out["sections"][0]["kind"] == "custom" and out["sections"][0]["made"] == "model"
    assert "## Custom (owner's prompt)\n- Turns went by.\n[/NMOS note]" in out["text"]
