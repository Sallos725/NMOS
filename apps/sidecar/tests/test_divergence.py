"""PHASE-53: diverged from the setting — the inputs, the check, the call, the fallback."""

from __future__ import annotations

from nmos_sidecar import divergence
from nmos_sidecar.llm import LLMError


def fact(subject, predicate, *, obj=None, value=None, turn=5, eid=None, canon=None, polarity="positive", **kw):
    """A current fact as `memory_view` makes it (the fields this part reads)."""
    return {"subject": subject, "predicate": predicate, "object": obj, "value": value, "turn": turn,
            "position": turn, "polarity": polarity, "canon": canon,
            "subject_entity": {"id": eid or f"e-{subject}", "name": subject}, "history": [], **kw}


def scene(first, last, text, told=()):
    return {"window": None, "summary": {"id": f"s{first}", "first_turn": first, "last_turn": last, "text": text,
                                        "coverage": {"secrets": list(told)}}}


def told(*scenes, story=None):
    return {"scenes": list(scenes), "story": story}


# --- the story's side -----------------------------------------------------------------------------------------------

def test_the_story_side_holds_story_facts_newest_first_then_the_scenes_in_order():
    facts = [fact("Ren", "has_status", value="arrested", turn=42),
             fact("Ren", "located_in", obj="capital prison", turn=44),
             fact("Ren", "identity", value="captain", turn=-1, canon="card:desc")]  # canon: not the story's
    text, spans, held = divergence.story_input(
        facts, told(scene(0, 7, "Ren leads the guard."), scene(40, 47, "Ren is taken away in chains.")), [], False)
    assert text.index("[t44] Ren located in capital prison") < text.index("[t42] Ren has status: arrested")
    assert "captain" not in text
    assert text.index("[turns 0–7] Ren leads the guard.") < text.index("[turns 40–47] Ren is taken away")
    assert (42, 42) in spans and (44, 44) in spans and (40, 47) in spans and held == 0


def test_a_denial_says_not():
    text, _, _ = divergence.story_input([fact("Ren", "member_of", obj="Royal Guard", polarity="negative")],
                                        None, [], False)
    assert "[t5] NOT Ren member of Royal Guard" in text


def test_the_story_side_keeps_to_its_cap_and_leaves_held_scenes_out():
    secret = {"open": ["Kaito"], "holders": ["Hana"], "text": "Hana identity: smuggler", "turn": 2, "position": 2}
    long = [scene(8 * i, 8 * i + 7, "x" * 3000, told=("smuggler",)) for i in range(10)]
    leaky = scene(80, 87, "Hana is a smuggler, Kaito must never know.")
    text, spans, held = divergence.story_input([], told(*long, leaky), [secret], False)
    assert len(text) <= divergence.STORY_CHARS + 200 and held == 1 and "smuggler" not in text
    assert (72, 79) in spans and (0, 7) not in spans  # the newest that fit


# --- the setting's side ----------------------------------------------------------------------------------------------

def entry(key, text, **metadata):
    """A manifest entry as `canon.manifest` gives it."""
    return {"key": key, "hash": "h", "metadata": metadata, "content": text, "revision_id": None}


ENTITIES = [{"id": "e-Ren", "type": "character", "name": "Ren", "names": ["Ren", "Captain Ren"],
             "aliases": [{"name": "Ren", "other": "레나"}], "persona": False},
            {"id": "e-Mira", "type": "character", "name": "Mira", "names": ["Mira"], "aliases": [], "persona": False},
            {"id": "e-Taku", "type": "character", "name": "Taku", "names": ["Taku"], "aliases": [], "persona": True}]
MANIFEST = [entry("card:name", "Hana"), entry("card:desc", "{{char}} serves under Captain Ren."),
            entry("persona", "{{user}} is a traveler.", name="Taku"),
            entry("note", "Keep it slow.\n[NMOS note · t3 · 2026-10-23]\nold\n[/NMOS note]"),
            entry("lore:guard", "The Royal Guard answers to its captain.", keys=["Ren", "guard"], comment="Royal Guard"),
            entry("lore:bakery", "Mira bakes at dawn.", keys=["Mira"], comment="Bakery"),
            entry("lore:sea", "The current is cold.", keys=["sea"], comment="Sea")]  # "ren" inside a word: no


def test_the_setting_side_always_holds_the_card_persona_and_note_and_ranks_the_lorebook():
    facts = [fact("Ren", "has_status", value="arrested", turn=42)]
    given, left = divergence.canon_input(MANIFEST, ENTITIES, facts, "Mira watched them go.")
    keys = [g["key"] for g in given]
    assert keys[:3] == ["card:desc", "persona", "note"]
    assert keys[3:] == ["lore:guard", "lore:bakery"] and left == 0  # Ren has a story fact; Mira is only named
    assert given[0]["text"] == "Hana serves under Captain Ren." and given[1]["text"] == "Taku is a traveler."
    assert given[2]["text"] == "Keep it slow." and given[3]["label"] == 'lorebook "Royal Guard"'
    assert given[0]["label"] == "card" and given[1]["label"] == "persona" and given[2]["label"] == "author's note"


def test_an_alias_picks_an_entry_and_the_persona_picks_none():
    manifest = [entry("lore:jail", "레나는 감옥에 있다.", keys=["감옥"], comment="Jail"),  # a particle on the name
                entry("lore:taku", "Taku is the user.", keys=["Taku"], comment="Taku")]
    given, _ = divergence.canon_input(manifest, ENTITIES, [fact("Ren", "has_status", value="arrested")], "")
    assert [g["key"] for g in given] == ["lore:jail"]


def test_the_setting_side_keeps_to_its_caps():
    manifest = [entry("card:desc", "d" * 9000)] + [
        entry(f"lore:{i:02d}", f"Ren {i} " + "y" * 6000, keys=["Ren"]) for i in range(10)]
    given, left = divergence.canon_input(manifest, ENTITIES, [fact("Ren", "has_status", value="arrested")], "")
    assert all(len(g["text"]) <= divergence.ENTRY_CHARS for g in given)
    assert sum(len(g["text"]) for g in given) <= divergence.CANON_CHARS and left == 4


# --- the check and the line -----------------------------------------------------------------------------------------

GIVEN = [{"key": "card:desc", "label": "card", "text": "Hana serves under Captain Ren of the Royal Guard."},
         {"key": "lore:guard", "label": 'lorebook "Royal Guard"', "text": "The Royal Guard answers to Captain Ren."}]
SPANS = [(42, 42), (40, 47)]


def item(**kw):
    return {"key": "lore:guard", "quote": "answers to Captain Ren", "subject": "Ren", "now": "arrested",
            "turns": [42], "kind": "life", **kw}


def test_the_check_keeps_an_item_that_quotes_its_text_and_cites_the_story():
    rows = divergence.check([item(quote="ANSWERS  to captain ren", turns=["t42", "44"])], GIVEN, SPANS, 50)
    assert rows == [{"key": "lore:guard", "label": 'lorebook "Royal Guard"', "quote": "ANSWERS  to captain ren",
                     "subject": "Ren", "now": "arrested", "turns": [42, 44], "kind": "life"}]


def test_the_check_drops_what_it_cannot_find():
    bad = [item(key="lore:moon"),                      # not a text given
           item(quote="answers to Captain Mira"),      # not in the text
           item(quote="Captain Ren"),                  # too short to be a quote
           item(turns=[60]),                           # after the head
           item(turns=[30]),                           # not a turn the story gave
           item(turns=[]), item(now=""), "nonsense"]
    assert divergence.check(bad, GIVEN, SPANS, 50) == []
    assert divergence.check("nonsense", GIVEN, SPANS, 50) == []


def test_the_same_quote_twice_is_one_line_with_the_newer_turns_and_an_unknown_kind_is_other():
    rows = divergence.check([item(turns=[42]), item(turns=[45], kind="poem")], GIVEN, SPANS, 50)
    assert len(rows) == 1 and rows[0]["turns"] == [45] and rows[0]["kind"] == "other"


def test_a_line_names_its_text_and_turns():
    assert divergence.line({**item(), "label": 'lorebook "Royal Guard"', "turns": [42, 44],
                            "now": "arrested and held in the capital prison"}) == (
        '- Ren (lorebook "Royal Guard"): the setting says "answers to Captain Ren" → now arrested and held in the'
        ' capital prison (t42–44)')
    assert divergence.line({**item(), "label": "card", "subject": "", "turns": [42]}).startswith(
        '- card: the setting says "answers to Captain Ren" → now arrested (t42)')


# --- the call -------------------------------------------------------------------------------------------------------

class Writer:
    """A stand-in model: its replies in order (an exception is raised), the prompts it saw."""

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, system, user):
        self.calls.append((system, user))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply, "{}"


FACTS = [fact("Ren", "has_status", value="arrested", turn=42)]
TOLD = told(scene(40, 47, "Ren is taken away in chains."))
GOOD = {"diverged": [{"key": "lore:guard", "quote": "The Royal Guard answers to its captain", "subject": "Ren",
                      "now": "arrested", "turns": [42], "kind": "life"}]}
FALLBACK = ["- Ren — status: was free → now arrested (t42)"]


def run(model, *, secrets=(), told_secrets=False, fallback=FALLBACK, manifest=MANIFEST):
    return divergence.diverged(manifest, ENTITIES, FACTS, TOLD, list(secrets), 47, model, told_secrets, fallback)


def test_the_model_finds_it_and_the_part_says_it():
    divergence.clear_cache()
    w = Writer(GOOD)
    out = run(w)
    assert out["made"] == "model" and out["lines"] == 1 and out["dropped"] == 0 and out["entries"] == 1  # Mira unnamed
    assert out["body"] == ('## Diverged from the setting\n- Ren (lorebook "Royal Guard"): the setting says "The Royal'
                           ' Guard answers to its captain" → now arrested (t42)')
    system, user = w.calls[0]
    assert "SETTING" in user and "[key: lore:guard · lorebook \"Royal Guard\"]" in user and "[t42]" in user


def test_nothing_changed_is_an_answer():
    divergence.clear_cache()
    out = run(Writer({"diverged": []}))
    assert out["made"] == "model" and out["body"] == "" and out["reason"] == "none"


def test_a_broken_reply_is_asked_again_then_the_fallback():
    divergence.clear_cache()
    w = Writer(LLMError("bad json"), {"diverged": "nope"})
    out = run(w)
    assert len(w.calls) == 2 and out["made"] == "facts"
    assert out["body"] == "## Diverged from the setting\n- Ren — status: was free → now arrested (t42)"


def test_a_reply_with_nothing_that_holds_is_asked_again_with_why():
    divergence.clear_cache()
    bad = {"diverged": [{**GOOD["diverged"][0], "quote": "The Royal Guard answers to the queen"}]}
    w = Writer(bad, GOOD)
    out = run(w)
    assert out["made"] == "model" and "copy each quote exactly" in w.calls[1][1]


def test_a_reply_that_tells_a_kept_secret_is_asked_again_then_the_fallback():
    divergence.clear_cache()
    secret = {"open": ["Kaito"], "holders": ["Ren"], "text": "Ren identity: royal guard traitor", "turn": 41,
              "position": 41}
    leak = {"diverged": [{**GOOD["diverged"][0], "now": "arrested as the royal guard traitor"}]}
    w = Writer(leak, leak)
    out = run(w, secrets=[secret])
    assert len(w.calls) == 2 and "TOLD THESE SECRETS" in w.calls[1][1] and out["made"] == "facts"
    assert "OPEN SECRETS" in w.calls[0][1]


def test_no_model_no_setting_or_no_story_is_the_fallback_without_a_call():
    divergence.clear_cache()
    assert run(None)["made"] == "facts"
    w = Writer(GOOD)
    assert run(w, manifest=[])["made"] == "facts" and not w.calls
    empty = run(None, fallback=[])
    assert empty["body"] == "" and empty["reason"] == "none"


def test_asked_twice_with_nothing_changed_the_model_answers_once_and_a_failure_is_not_remembered():
    divergence.clear_cache()
    w = Writer(GOOD)
    first, again = run(w), run(w)
    assert len(w.calls) == 1 and not first["cached"] and again["cached"]
    divergence.clear_cache()
    f = Writer(LLMError("down"), LLMError("down"), GOOD)
    assert run(f)["made"] == "facts" and run(f)["made"] == "model"
