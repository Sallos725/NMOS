"""PHASE-32: memory on a time axis in the browser Inspector — a character's facts as bars over turns, one line per
character on the conversation page, and the panel (`embed`) untouched."""

from __future__ import annotations

import re

from nmos_sidecar import inspector, timeline

CONV = {"id": "c1", "host_chat_ref": "chat", "head_commit_id": "h"}


def entity(eid: str, name: str, persona: bool = False, mentions: int = 1) -> dict:
    return {"id": eid, "type": "character", "name": name, "names": [name], "mentions": mentions, "aliases": [],
            "links": [], "persona": persona}


def fact(fid: int, subject: tuple[str, str], predicate: str, history: list[dict] | None = None, **kw) -> dict:
    eid, name = subject
    f = {"id": fid, "subject": name, "subject_entity": {"id": eid, "name": name}, "predicate": predicate,
         "polarity": "positive", "position": fid, "turn": kw.get("turn", 1), "value": kw.get("value"),
         "object": kw.get("object"), "object_entity": kw.get("object_entity"), "knowledge": "public",
         "source": "story", "versions": len(history or [None])}
    f.update({k: v for k, v in kw.items() if k not in ("turn", "value", "object", "object_entity")})
    if history is not None:  # entries as facts.py makes them: the fact's predicate and subject
        f["history"] = [{"predicate": predicate, "subject": name, **h} for h in history]
    return f


def step(turn: int | None, value: str, outcome: str, **kw) -> dict:
    return {"turn": turn, "position": turn or 0, "value": value, "object": None, "polarity": "positive",
            "outcome": outcome, **kw}


HANA = ("e1", "Hana")


def view(facts: list[dict], threads: list[dict] | None = None, entities: list[dict] | None = None) -> dict:
    return {"entities": entities or [entity("e1", "Hana"), entity("e2", "Kaito")], "facts": facts, "claims": [],
            "other": [], "conflicts": [], "threads": threads or [], "secrets": []}


def bars(page: str) -> list[tuple[str, str, str]]:
    """(classes, left, width) of every bar, in order."""
    return re.findall(r'<a class="(tl-bar[^"]*)" href="#a-[^"]+" data-d="tl-\d+" aria-pressed="(?:true|false)" '
                      r'style="left:([\d.]+)%;width:calc\(([\d.]+)% - 2px\)"', page)


def test_a_history_is_spans_of_turns():
    f = fact(1, HANA, "located_in", [step(None, "old", "superseded"), step(2, "library", "superseded"),
                                     step(7, "harbor", "current")])
    assert [(s["start"], s["end"], s["outcome"]) for s in timeline.segments(f, 10)] == \
        [(2, 6, "superseded"), (7, 10, "current")]  # a legacy entry without a turn is left out
    canon = fact(2, HANA, "identity", [step(None, "squire", "superseded", canon="card"), step(5, "knight", "current")],
                 owner=True)
    s = timeline.segments(canon, 9)
    assert (s[0]["start"], s[0]["end"], s[0]["canon"]) == (0, 4, True)  # canon sits before turn 0 (ADR 0047)
    assert s[1].get("owner") and not s[0].get("owner")  # only the current version carries the owner's mark
    ended = fact(3, HANA, "has_status", [step(3, "wounded", "ended")])
    assert [(x["start"], x["end"]) for x in timeline.segments(ended, 9)] == [(3, 3)]
    assert timeline.window(60, "recent") == (36, 60) and timeline.window(60, None) == (0, 60)
    assert timeline.window(None, None) == (0, 0)


def test_the_character_page_draws_bars_that_link_to_their_rows():
    located = fact(10, HANA, "located_in", [step(2, "library", "superseded"), step(7, "harbor", "current")],
                   value="harbor", turn=7)
    feels = fact(11, HANA, "feels_toward", [step(4, "wary", "current")], object="Kaito",
                 object_entity={"id": "e2", "name": "Kaito"}, value="wary", turn=4)
    event = fact(12, HANA, "event", None, value="the fire", turn=5, salience="major")
    knows = fact(13, HANA, "knows", None, value="the map is fake", turn=3)
    thread = {"id": 14, "kind": "promise", "by": "Hana", "to": "Kaito", "text": "meet at the lighthouse", "turn": 3,
              "position": 3, "status": "open", "closed_by": None, "restated": []}
    page = inspector.character(CONV, "e1", view([located, feels, event, knows], [thread]), None, lang="en", now=10)
    assert 'id="s-timeline"' in page and page.count(timeline.SCRIPT) == 1
    # 11 turns (0–10): library 2–6, harbor 7–10.
    assert bars(page)[:2] == [("tl-bar past", "18.182", "45.454"), ("tl-bar", "63.636", "36.364")]
    assert 'href="#a-10"' in page and '<tr id="a-10">' in page  # the bar's fact has its row
    assert "Relationships from them" in page and "feels toward → Kaito" in page
    assert 'class="tl-bar open"' in page and 'href="#a-14"' in page and '<tr id="a-14">' in page  # the open thread
    assert 'class="tl-dot s-major"' in page and 'href="#a-12"' in page
    assert "the map is fake" not in page.split('id="s-timeline"')[1].split("</details>")[0]  # knows: its own table
    # The first current bar starts selected, its detail shown; every other detail waits for a click.
    body = page.split("<main>", 1)[1]  # the style names the selected state too
    assert body.count('aria-pressed="true"') == 1 and len(re.findall(r'class="tl-card" id="tl-\d+">', body)) == 1
    assert len(re.findall(r'class="tl-card" id="tl-\d+" hidden>', body)) == 4
    assert 'span=recent' in page  # the window switch


def test_the_panel_gets_none_of_it():
    """PHASE-32 Q2: the panel's sanitizer drops `style`, so `embed` stays as it was: no timeline, no row anchors."""
    located = fact(10, HANA, "located_in", [step(2, "library", "superseded"), step(7, "harbor", "current")])
    v = view([located])
    embedded = inspector.character(CONV, "e1", v, None, embed=True)
    assert "tl-" not in embedded and 'id="a-' not in embedded and "<script" not in embedded
    assert embedded == inspector.character(CONV, "e1", v, None, embed=True, now=10, span="recent")
    page = inspector.detail(CONV, [], [], [], [], [], None, embed=True, cast={"facts": [], "entities": [], "scene": []})
    assert 'id="s-people"' not in page and "<script" not in page


def test_values_are_escaped():
    evil = fact(10, ("e1", "<b>Hana</b>"), "located_in", [step(1, "<i>cellar</i>", "current")])
    page = inspector.character(CONV, "e1", view([evil], entities=[entity("e1", "<b>Hana</b>")]), None, now=3)
    assert "<i>cellar" not in page and "<b>Hana" not in page and "&lt;i&gt;cellar&lt;/i&gt;" in page
    # A value shaped like the selection placeholder stays text.
    sly = fact(11, ("e1", "Hana"), "goal", [step(1, 'x" aria-pressed="{tl-0}', "current")])
    body = inspector.character(CONV, "e1", view([sly]), None, now=3).split("<main>", 1)[1]
    assert body.count('aria-pressed="true"') == 1 and 'aria-pressed="{' not in body


def test_a_large_chat_is_capped_and_counted():
    many = [fact(100 + i, HANA, f"has_trait", [step(i + 1, f"trait {i}", "current")]) for i in range(45)]
    page = inspector.character(CONV, "e1", view(many), None, lang="en", now=50)
    assert len(bars(page)) == timeline.LANES and "+5 more in the tables below" in page


def test_the_recent_window_draws_the_last_25_turns():
    old = fact(10, HANA, "located_in", [step(3, "village", "superseded"), step(20, "city", "superseded"),
                                        step(50, "port", "current")])
    page = inspector.character(CONV, "e1", view([old]), None, lang="en", now=60, span="recent")
    # The village (3–19) ended before turn 36; the city (20–49) reaches into the window from its left edge.
    assert [b[:2] for b in bars(page)] == [("tl-bar past", "0.0"), ("tl-bar", "56.0")]
    assert "village" not in page.split('id="s-timeline"')[1].split("</details>")[0]
    assert '>t36</span>' in page and 'now t60' in page and "<b>Last 25 turns</b>" in page


def test_the_persona_has_a_timeline_but_no_cast_line():
    me = entity("p", "Yuma", persona=True)
    own = fact(10, ("p", "Yuma"), "possesses", [step(2, "compass", "current")], object="compass")
    page = inspector.character(CONV, "p", view([own], entities=[me, entity("e1", "Hana")]), None, now=5)
    assert len(bars(page)) == 1
    strip = timeline.cast(lambda k: k, [me, entity("e1", "Hana")], [own], [], 5, None, lambda e: f"/x/{e}", "")
    assert "Yuma" not in strip and "Hana" in strip


def test_the_cast_puts_the_scene_first_and_folds_the_rest():
    people = [entity("e1", "Hana", mentions=2), entity("e2", "Kaito", mentions=9), entity("e3", "Ren", mentions=5)]
    facts = [fact(10, HANA, "located_in", [step(2, "library", "superseded"), step(7, "harbor", "current")]),
             fact(11, ("e2", "Kaito"), "event", None, value="the fire", turn=4,
                  participant_entities=[{"name": "Hana", "type": "character", "entity": {"id": "e1"}}])]
    strip = timeline.cast(inspector._tl_t("en"), people, facts, ["e1"], 10, "recent",
                          lambda e: f"/inspector/c/c1/e/{e}?span=recent", "")
    shown, folded = strip.split("<details", 1)
    assert "Hana" in shown and "Kaito" not in shown  # the scene first
    assert folded.index("Kaito") < folded.index("Ren")  # the rest by mentions, folded
    assert "2 more characters" in folded and "<details class=\"tl-others\">" in "<details" + folded
    hana = shown.split('href="/inspector/c/c1/e/e1?span=recent"')[1].split("</a>")[0]
    assert len(re.findall(r'class="tl-tick"', hana)) == 3 and " t7<" in hana  # turns 2, 4 (the event) and 7
    assert timeline.changes("e1", facts, 10) == [2, 4, 7]


def test_the_conversation_page_draws_the_cast_in_the_browser_only(migrated):
    from test_inspector import STORY, character_links, story_client
    from test_sidecar_integration import sync

    client, c, drain = story_client(migrated, STORY)
    with client:
        sync(client, c)
        drain()
        conv = client.get("/v1/conversations").json()[0]["id"]
        page = client.get(f"/inspector/c/{conv}").text
        assert 'id="s-people"' in page and 'class="tl-row tl-line"' in page
        hana = character_links(page, conv)["Hana"]
        mine = client.get(f"/inspector/c/{conv}/e/{hana}?span=recent").text
        assert 'id="s-timeline"' in mine and "tl-bar" in mine and "<b>최근 25턴</b>" in mine
        for path in (f"/v1/inspector/c/{conv}", f"/v1/inspector/c/{conv}/e/{hana}"):
            html = client.get(path).json()["html"]
            assert "tl-" not in html and "<script" not in html and 'id="a-' not in html
