"""Phase 5, ADR 0012 items 5–6: known entity names in the extraction prompt."""

from __future__ import annotations

import re

from conftest import active_generation, make_client
from nmos_sidecar import extraction
from nmos_sidecar.config import Settings
from simchat import SimChat
from test_extraction import drain, facts
from test_generations import LLM
from test_sidecar_integration import sync

NAMED = re.compile(r"(?P<who>[A-Z]\w+) has the (?P<item>[\w ]+?)\.")


class Recorder:
    """Stub model: 'X has the Y.' → X possesses Y; keeps every prompt it was sent."""

    def __init__(self):
        self.prompts: list[str] = []

    def __call__(self, system: str, user: str) -> tuple[dict, str]:
        self.prompts.append(user)
        target = user.split("TARGET", 1)[1]
        return {"assertions": [{"subject": m["who"], "subject_type": "character", "predicate": "possesses",
                                "object": m["item"], "object_type": "item", "modality": "actual"}
                               for m in NAMED.finditer(target)]}, "{}"


def hints_of(prompt: str) -> list[str]:
    if "KNOWN ENTITIES" not in prompt:
        return []
    block = prompt.split("KNOWN ENTITIES", 1)[1].split("\n\n", 1)[0]
    return [line[2:] for line in block.splitlines() if line.startswith("- ")]


def step(c, migrated, chat, model, user, reply="Noted."):
    """One turn, extracted before the next one starts (the worker takes turns as they complete)."""
    chat.user(user)
    sync(c, chat)
    drain(migrated, model)
    chat.reply(reply)


def test_hints_list_earlier_entities_most_recent_first_capped(migrated, db):
    model, chat = Recorder(), SimChat()
    with make_client(migrated, extract_hints=2, **LLM) as c:
        for line in ("Hana has the coast map.", "Kaito has the lantern.", "Yui has the silver key.",
                     "Hana has the compass.", "next"):
            step(c, migrated, chat, model, line)
    last = model.prompts[-1]
    # Before turn 3: map (turn 0), lantern (1), key (2), and three people. Newest first, two at most.
    assert hints_of(last) == ["silver key (item)", "Yui (character)"]
    stored = db.execute("SELECT hints FROM extraction ORDER BY created_at DESC LIMIT 1").fetchone()["hints"]
    assert stored == {"entities": [{"name": "silver key", "type": "item"}, {"name": "Yui", "type": "character"}],
                      "promises": []}
    # The first turn had nothing before it: no section, an empty list recorded.
    assert hints_of(model.prompts[0]) == []
    assert active_generation(db, "extract").spec["hints"] == 2


def test_hints_never_come_from_inactive_turns(migrated, db):
    model, chat = Recorder(), SimChat()
    with make_client(migrated, **LLM) as c:
        step(c, migrated, chat, model, "Hana has the coast map.")
        step(c, migrated, chat, model, "Kaito has the lantern.")
        chat.delete(0)  # the map's turn is gone
        chat.delete(0)
        step(c, migrated, chat, model, "Yui has the silver key.")
        step(c, migrated, chat, model, "next")
    assert all("coast map" not in h for h in hints_of(model.prompts[-1]))
    assert "lantern (item)" in hints_of(model.prompts[-1])


def test_an_extraction_that_used_a_hint_stays_valid_when_its_source_goes(migrated, db):
    model, chat = Recorder(), SimChat()
    with make_client(migrated, extract_turns=1, **LLM) as c:
        step(c, migrated, chat, model, "Hana has the coast map.")
        step(c, migrated, chat, model, "Idle.")
        step(c, migrated, chat, model, "Kaito has the coast map.")
        step(c, migrated, chat, model, "next")
        assert "coast map (item)" in hints_of(model.prompts[-1])  # Kaito's turn ("Idle." is too short to call)
        calls = len(model.prompts)
        chat.delete(0)  # outside turn 2's one-turn context: its turn hash is unchanged
        chat.delete(0)
        sync(c, chat)
        drain(migrated, model)
        # The Idle turn's context held the deleted turn, so it is extracted again; Kaito's turn is not.
        assert all("Kaito has" not in p.split("TARGET", 1)[1] for p in model.prompts[calls:])
        assert [(f["subject"], f["object"]) for f in facts(c, chat)] == [("Kaito", "coast map")]


def test_hints_off_sends_no_section_and_records_none(migrated, db):
    model, chat = Recorder(), SimChat()
    with make_client(migrated, extract_hints=0, **LLM) as c:
        step(c, migrated, chat, model, "Hana has the coast map.")
        step(c, migrated, chat, model, "Kaito has the lantern.")
        step(c, migrated, chat, model, "next")
    assert all("KNOWN ENTITIES" not in p for p in model.prompts)
    assert {r["hints"] for r in db.execute("SELECT hints FROM extraction").fetchall()} == {None}


def test_hint_count_is_part_of_the_generation():
    base = Settings(database_url="", **LLM)
    assert extraction.extractor(base).spec["hints"] == 40
    assert extraction.extractor(Settings(database_url="", extract_hints=0, **LLM)).key != extraction.extractor(base).key


PROMISE = re.compile(r'(?P<who>[A-Z]\w+) says to (?P<to>[A-Z]\w+): "I promise to (?P<what>[^."]+)\."')
KEPT = re.compile(r"(?P<who>[A-Z]\w+) kept the promise to (?P<what>[^.]+)\.")


class PromiseRecorder(Recorder):
    """Also: a promise its maker says, and 'X kept the promise to Y.' → fulfilled (PHASE-7)."""

    def __call__(self, system: str, user: str) -> tuple[dict, str]:
        out, raw = super().__call__(system, user)
        target = user.split("TARGET", 1)[1]
        out["assertions"] += [{"subject": m["who"], "subject_type": "character", "predicate": "promised",
                               "object": m["to"], "object_type": "character", "value": m["what"], "modality": "actual",
                               "source": "character_claim", "asserted_by": m["who"]} for m in PROMISE.finditer(target)]
        out["assertions"] += [{"subject": m["who"], "subject_type": "character", "predicate": "fulfilled",
                               "value": m["what"], "modality": "actual"} for m in KEPT.finditer(target)]
        return out, raw


def promises_of(prompt: str) -> list[str]:
    if "OPEN PROMISES" not in prompt:
        return []
    block = prompt.split("OPEN PROMISES", 1)[1].split("\n\n", 1)[0]
    return [line[2:] for line in block.splitlines() if line.startswith("- ")]


def test_open_promises_are_shown_when_their_people_are_named_until_kept(migrated, db):
    """PHASE-7 Q3: the extractor sees the open promises it may close, recorded with the extraction."""
    model, chat = PromiseRecorder(), SimChat()
    with make_client(migrated, **LLM) as c:
        step(c, migrated, chat, model, 'Hana says to Kaito: "I promise to meet you at the lighthouse."')
        step(c, migrated, chat, model, "The rain goes on.")
        step(c, migrated, chat, model, "Hana waits by the window.")
        step(c, migrated, chat, model, "Hana kept the promise to meet you at the lighthouse.")
        step(c, migrated, chat, model, "Hana smiles.")
        step(c, migrated, chat, model, "next")  # a turn is extracted once the user continues from it
    listed = "Hana → Kaito: meet you at the lighthouse (turn 0)"
    assert promises_of(model.prompts[0]) == []  # made in this turn: nothing earlier
    assert promises_of(model.prompts[1]) == [listed]  # Hana is named in the context
    assert promises_of(model.prompts[3]) == [listed]
    assert promises_of(model.prompts[4]) == []  # kept in turn 3
    stored = db.execute("SELECT hints FROM extraction e JOIN active_membership am"
                        " ON am.source_revision_id = e.source_revision_id WHERE am.turn = 3"
                        " LIMIT 1").fetchone()["hints"]
    assert stored["promises"] == [{"by": "Hana", "to": "Kaito", "text": "meet you at the lighthouse", "turn": 0}]


def test_promise_hints_need_a_named_person():
    ctx = {"target": {"conversation_id": __import__("uuid").uuid4(), "turn": 5},
           "context": [{"turn": 4, "metadata": {"role": "user"}, "content": "The rain goes on."}],
           "members": [{"turn": 5, "metadata": {"role": "char", "name": "Narrator"}, "content": "Quiet."}]}
    rows = [{"id": 1, "position": 1, "turn": 0, "subject": "Hana", "subject_type": "character",
             "predicate": "promised", "object": "{{user}}", "object_type": "character", "value": "wait",
             "polarity": "positive", "modality": "actual", "source": "narration", "asserted_by": None}]
    assert extraction.promise_hints(ctx, rows) == []
    ctx["members"][0]["metadata"]["name"] = "Hana"  # the speaker label names her
    assert extraction.promise_hints(ctx, rows) == [{"by": "Hana", "to": "{{user}}", "text": "wait", "turn": 0}]
