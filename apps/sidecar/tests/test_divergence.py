"""PHASE-53: diverged from the setting — the inputs, the check, the call, the fallback."""

from __future__ import annotations

from nmos_sidecar import divergence


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
