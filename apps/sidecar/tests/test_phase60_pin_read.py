"""PHASE-60 S8 (ADR 0087): the owner's pins and `@name` in the packet (`packet-v20`).

A pinned character is present, not louder: it joins the scene's cast, gets a <Cast> group beyond the cast's own four
(at most PIN_EXTRA, in pin order), and its now and standing facts are required as a name in the message makes them.
A request records the names its pins resolved to (`recall_options.pins`); its replay reads them. The store side is
tests/test_phase60_pin_store.py. Synthetic names only."""

from __future__ import annotations

import re
import uuid

import psycopg

from conftest import make_client
from memeval import stub_extractor
from nmos_sidecar.entities import resolve
from nmos_sidecar.packet import PIN_POLICIES
from nmos_sidecar.retrieval import PIN_EXTRA, RecallOptions, pinned_characters
from simchat import SimChat
from test_extraction import drain
from test_generations import LLM, conv_id
from test_hints import step
from test_phase60_pin_store import pin, pin_row
from test_entity_exclude import exclude
from test_semantics import row
from test_sidecar_integration import recall, sync

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


# --- in the packet (stub model, test database) -------------------------------------------------------------------------

PAIR = re.compile(r"(?P<a>\w+) and (?P<b>\w+) are (?P<what>\w+)\.")
TRAIT = re.compile(r"(?P<who>\w+) is (?P<what>brave|calm)\.")
IDLE = ("Idle chatter 1 about clouds.", "Idle chatter 2 about clouds.", "Idle chatter 3 about clouds.")
QUIET = "오늘은 날씨가 맑네."  # names no one


def pin_stub(system: str, user: str) -> tuple[dict, str]:
    """The suite's stub, plus a relationship ("A and B are rivals.") and a trait ("A is brave.")."""
    out, raw = stub_extractor(system, user)
    target = user.split("TARGET", 1)[1]
    base = {"modality": "actual", "source": "narration", "epistemic": "stated", "confidence": 0.9}
    out["assertions"] += [{**base, "subject": m["a"], "subject_type": "character", "predicate": "relationship",
                           "object": m["b"], "object_type": "character", "value": m["what"], "evidence": m.group(0)}
                          for m in PAIR.finditer(target)]
    out["assertions"] += [{**base, "subject": m["who"], "subject_type": "character", "predicate": "has_trait",
                           "value": m["what"], "evidence": m.group(0)} for m in TRAIT.finditer(target)]
    return out, raw


def story(c, url: str, *lines: str) -> SimChat:
    chat = SimChat()
    for line in lines:
        step(c, url, chat, pin_stub, line)
    return chat


def ask(c, url: str, chat: SimChat, query: str) -> dict:
    """A request: the message synced and extracted first, then recalled (a growing chat, as the host sends it)."""
    chat.user(query)
    sync(c, chat)
    drain(url, pin_stub)
    out = recall(c, chat, query, budget=1500)
    chat.reply("Noted.")
    return out


def group(text: str, name: str) -> str | None:
    """The <Character> block of `name` in a packet, its lines included, or None."""
    m = re.search(r'    <Character name="' + re.escape(name) + r'"[^>]*>\n(?:      .*\n)*?    </Character>', text)
    return m.group(0) if m else None


def groups(text: str) -> list[str]:
    return re.findall(r'<Character name="([^"]+)"', text)


def trace(c, out: dict) -> dict:
    return c.get(f"/v1/trace/{out['trace_id']}").json()


def entry(t: dict, needle: str) -> dict | None:
    return next((e for e in t["lines"] if needle in (e.get("text") or "")), None)


SERA = ("세라 is in the garden. 세라 and 카이토 are rivals. 세라 is brave.",) + IDLE
ALL = "세라 is in the garden. 카이토 is in the hall. 하나 is in the yard. 유나 is in the tower. 레오 is in the gate."
CLIENT = dict(rest_after=10**6, **LLM)  # nothing rests: repeated requests are alike


def test_an_owner_pin_gives_an_unnamed_character_a_group_and_requires_its_now_and_standing_facts(migrated):
    with make_client(migrated, packet_policy="packet-v20", **CLIENT) as c:
        chat = story(c, migrated, *SERA)
        before = ask(c, migrated, chat, QUIET)
        assert group(before["packet"]["text"], "세라") is None and "rivals" not in before["packet"]["text"]
        assert pin(c, conv_id(c, chat), "세라").status_code == 200
        out = ask(c, migrated, chat, QUIET)
        text, t = out["packet"]["text"], trace(c, out)
    assert '<Fact kind="located_in"' in group(text, "세라") and "garden" in group(text, "세라")
    assert "세라 relationship 카이토: rivals" in text
    standing = entry(t, "세라 relationship 카이토")
    assert standing["placed"] and standing["label"] == "required"
    assert entry(t, "garden")["label"] == "required" and entry(t, "garden")["section"] == "cast"
    assert entry(t, "brave") is None  # its other facts: ranked as before, and a quiet message brings none
    assert "세라" in t["latency_ms"]["scene_cast"]  # present


def test_a_pin_is_not_louder_than_a_name_for_the_characters_other_facts(migrated):
    """A trait is offered for the name alone (supportive); a pin brings it no closer."""
    with make_client(migrated, packet_policy="packet-v20", **CLIENT) as c:
        chat = story(c, migrated, *SERA)
        named = trace(c, ask(c, migrated, chat, "세라 보고 싶다."))
        assert entry(named, "brave")["label"] == "supportive"
        assert pin(c, conv_id(c, chat), "세라").status_code == 200
        pinned = trace(c, ask(c, migrated, chat, QUIET))
    assert entry(pinned, "brave") is None


def test_under_v19_a_pin_changes_nothing(migrated):
    with make_client(migrated, packet_policy="packet-v19", **CLIENT) as c:
        chat = story(c, migrated, *SERA)
        before = ask(c, migrated, chat, QUIET)
        assert pin(c, conv_id(c, chat), "세라").status_code == 200
        after = recall(c, chat, QUIET, budget=1500)  # the same request again, on the same head
        t = trace(c, after)
    assert after["packet"]["text"] == before["packet"]["text"] and group(after["packet"]["text"], "세라") is None
    assert "pins" not in t["recall_options"]


def test_at_most_three_extra_groups_the_most_recently_pinned_and_undo_takes_one_back(migrated):
    with make_client(migrated, packet_policy="packet-v20", **CLIENT) as c:
        chat = story(c, migrated, ALL, *IDLE)
        cid = conv_id(c, chat)
        plain = ask(c, migrated, chat, QUIET)["packet"]["text"]
        assert groups(plain) == []
        made = [pin(c, cid, n).json()["repair"]["id"] for n in NAMES]
        text = ask(c, migrated, chat, QUIET)["packet"]["text"]
        assert groups(text) == ["레오", "유나", "하나"]
        assert c.post(f"/v1/conversations/{cid}/repairs/{made[-1]}/remove").status_code == 200
        assert groups(ask(c, migrated, chat, QUIET)["packet"]["text"]) == ["유나", "하나", "카이토"]
        for rid in made[:-1]:
            assert c.post(f"/v1/conversations/{cid}/repairs/{rid}/remove").status_code == 200
        assert groups(ask(c, migrated, chat, QUIET)["packet"]["text"]) == []


def test_the_casts_own_four_groups_are_not_displaced(migrated):
    """Four characters in the scene keep their groups; a pinned fifth gets one after them."""
    scene_turn = "카이토 is in the hall. 하나 is in the yard. 유나 is in the tower. 레오 is in the gate."
    with make_client(migrated, packet_policy="packet-v20", **CLIENT) as c:
        chat = story(c, migrated, "세라 is in the garden.", *IDLE, scene_turn)
        own = groups(ask(c, migrated, chat, QUIET)["packet"]["text"])
        assert sorted(own) == sorted(["카이토", "하나", "유나", "레오"])
        assert pin(c, conv_id(c, chat), "세라").status_code == 200
        assert pin(c, conv_id(c, chat), "하나").status_code == 200  # already in the scene: no second group
        assert groups(ask(c, migrated, chat, QUIET)["packet"]["text"]) == own + ["세라"]


def test_an_excluded_character_and_the_persona_are_never_pinned_in_the_packet(migrated):
    with make_client(migrated, packet_policy="packet-v20", **CLIENT) as c:
        chat = story(c, migrated, *SERA)
        cid = conv_id(c, chat)
        assert pin(c, cid, "세라").status_code == 200
        assert exclude(c, cid, "세라").status_code == 200
        pin_row(migrated, cid, "{{user}}")  # the API refuses it; a row that names it anyway pins no one
        out = ask(c, migrated, chat, QUIET)
        assert group(out["packet"]["text"], "세라") is None and "pins" not in trace(c, out)["recall_options"]


def test_a_fact_kept_from_the_pinned_character_is_private_it_is_present(migrated):
    secret = ("하나 keeps a secret from 세라: the map is fake.", "세라 is in the garden.") + IDLE
    with make_client(migrated, packet_policy="packet-v20", **CLIENT) as c:
        chat = story(c, migrated, *secret)
        before = ask(c, migrated, chat, "하나, 지도는 어디 있어?")["packet"]["text"]
        assert "the map is fake" in before and "<Private>" not in before  # 세라 is not in the scene
        assert pin(c, conv_id(c, chat), "세라").status_code == 200
        after = ask(c, migrated, chat, "하나, 지도는 어디 있어?")["packet"]["text"]
    private = after.split("<Private>", 1)[1].split("</Private>", 1)[0]
    assert "the map is fake" in private and 'hidden_from="세라"' in private


def test_a_pinned_group_has_the_shape_of_an_ordinary_one(migrated):
    """A12: no new attribute; the group a pin brings is the one a name in the message brings."""
    with make_client(migrated, packet_policy="packet-v20", **CLIENT) as c:
        chat = story(c, migrated, *SERA)
        named = group(ask(c, migrated, chat, "세라 보고 싶다.")["packet"]["text"], "세라")
        assert pin(c, conv_id(c, chat), "세라").status_code == 200
        pinned = group(ask(c, migrated, chat, QUIET)["packet"]["text"], "세라")
    assert named is not None and pinned == named and pinned.startswith('    <Character name="세라">\n')


FULL = "카이토 is in the hall. 하나 is in the yard. 유나 is in the tower. 레오 is in the gate."
FIVE = "카이토, 하나, 유나, 레오, 그리고 {}세라 모두 모여."


def in_full_scene(c, url: str, chat: SimChat, query: str) -> dict:
    """A request right after a turn about the four others: they are the scene's cast (CAST_TURNS)."""
    step(c, url, chat, pin_stub, FULL)
    return ask(c, url, chat, query)


def test_at_name_pins_for_that_request_only_and_only_with_the_setting(migrated):
    """Five characters named, four in the scene: the fifth has no group of its own (CAST_MAX), so only a pin gives one."""
    with make_client(migrated, packet_policy="packet-v20", **CLIENT) as c:
        chat = story(c, migrated, "세라 is in the garden.", *IDLE)
        assert group(in_full_scene(c, migrated, chat, FIVE.format("@"))["packet"]["text"], "세라") is None  # off
        assert c.put("/v1/config", json={"pin_at_mentions": True}).status_code == 200
        assert group(in_full_scene(c, migrated, chat, FIVE.format("@"))["packet"]["text"], "세라") is not None
        assert group(in_full_scene(c, migrated, chat, FIVE.format(""))["packet"]["text"], "세라") is None  # the next
        for query in (FIVE.format("a@"), FIVE.format("@없는이름 ")):
            assert group(in_full_scene(c, migrated, chat, query)["packet"]["text"], "세라") is None, query
