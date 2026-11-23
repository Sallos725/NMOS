"""PHASE-60 S8 (ADR 0087): the owner's pins and `@name` in the packet (`packet-v20`).

A pinned character is present, not louder: it joins the scene's cast, gets a <Cast> group beyond the cast's own four
(at most PIN_EXTRA, in pin order), and its now and standing facts are required as a name in the message makes them.
A request records the names its pins resolved to (`recall_options.pins`); its replay reads them. The store side is
tests/test_phase60_pin_store.py. Synthetic names only."""

from __future__ import annotations

import uuid

from nmos_sidecar.entities import resolve
from nmos_sidecar.packet import PIN_POLICIES
from nmos_sidecar.retrieval import PIN_EXTRA, RecallOptions, pinned_characters
from test_semantics import row

C = {"subject_type": "character"}
V20 = RecallOptions(policy="packet-v20")
AT = RecallOptions(policy="packet-v20", pin_at_mentions=True)
NAMES = ["세라", "카이토", "하나", "유나", "레오"]


def place(pos: int, who: str, where: str = "정원") -> dict:
    return row(pos, who, "located_in", where, None, **{**C, "object_type": "place"})


def chat(persona=("타쿠미",)):
    rows = [place(i, n) for i, n in enumerate(NAMES)] + [place(9, "타쿠미", "집")]
    r = resolve(uuid.uuid4(), rows, persona=persona)
    return r, {e["name"]: e for e in r.entities()}


def view_of(r, pins=(), excluded=()) -> dict:
    """A view with the owner's pins (names, newest first) and the entities the owner left out."""
    by = {e["name"]: e for e in r.entities()}
    return {"facts": [], "claims": [], "other": [], "threads": [],
            "pins": [{"entity_id": by[n]["id"], "name": n} for n in pins],
            "excluded": {str(by[n]["id"]): {"scope": "cast"} for n in excluded}}


def picked(view, r, query="", options=AT, recorded=None) -> list[tuple[str, str]]:
    return [(p["name"], p["source"]) for p in pinned_characters(view, r, query, options, recorded)]


# --- the pinned set (pure) -------------------------------------------------------------------------------------------


def test_packet_v20_only():
    assert PIN_POLICIES == frozenset({"packet-v20"}) and PIN_EXTRA == 3
    r, _ = chat()
    for policy in ("packet-v19", "packet-v16", "packet-v8"):
        assert picked(view_of(r, ["세라"]), r, "@카이토", RecallOptions(policy=policy, pin_at_mentions=True)) == []
    assert picked(view_of(r, ["세라"]), r, "", V20) == [("세라", "owner")]


def test_owner_pins_keep_the_views_order_newest_first_and_carry_entity_keys():
    r, by = chat()
    out = pinned_characters(view_of(r, ["유나", "세라", "하나"]), r, "", V20)
    assert [(p["name"], p["source"]) for p in out] == [("유나", "owner"), ("세라", "owner"), ("하나", "owner")]
    assert [p["key"] for p in out] == [by[n]["id"] for n in ("유나", "세라", "하나")]


def test_at_mentions_only_with_the_setting_and_before_the_owners_pins_once_each():
    r, _ = chat()
    v = view_of(r, ["세라", "하나"])
    assert picked(v, r, "@카이토 어디 있어?", V20) == [("세라", "owner"), ("하나", "owner")]
    assert picked(v, r, "@카이토 어디 있어?") == [("카이토", "at"), ("세라", "owner"), ("하나", "owner")]
    # a character both mentioned and pinned is pinned once, by the mention
    assert picked(v, r, "@하나에게 물어봐, @카이토도") == [("하나", "at"), ("카이토", "at"), ("세라", "owner")]


def test_an_at_inside_a_word_or_before_an_unknown_name_does_nothing():
    r, _ = chat()
    assert picked(view_of(r), r, "a@세라 메일 보내") == []
    assert picked(view_of(r), r, "@없는이름 어디 있어?") == []
    assert picked(view_of(r), r, "세라 어디 있어?") == []  # a plain name is no pin


def test_an_excluded_character_and_the_persona_are_never_pinned():
    r, _ = chat()
    assert picked(view_of(r, ["세라", "카이토"], excluded=["세라"]), r, "@세라") == [("카이토", "owner")]
    assert picked(view_of(r, ["타쿠미", "카이토"]), r, "@타쿠미 @{{user}}") == [("카이토", "owner")]


def test_recorded_pins_are_resolved_as_they_were_named_and_nothing_else_is_read():
    r, _ = chat()
    v = view_of(r, ["하나"])  # a pin the owner made later: the record says what the request had
    recorded = [{"name": "카이토", "entity_type": "character", "source": "at"},
                {"name": "세라", "entity_type": "character", "source": "owner"},
                {"name": "없는이름", "entity_type": "character", "source": "owner"}]
    assert picked(v, r, "@유나", recorded=recorded) == [("카이토", "at"), ("세라", "owner")]
    assert picked(v, r, "@유나", recorded=[]) == []  # a trace without pins replays with none
    # an exclusion in force at the replay still wins (it is read as of the request)
    assert picked(view_of(r, excluded=["세라"]), r, recorded=recorded) == [("카이토", "at")]
