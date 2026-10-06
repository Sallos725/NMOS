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
    return re.findall(r'<a class="(tl-bar[^"]*)" href="#a-[^"]+"[^>]*? aria-pressed="(?:true|false)" '
                      r'style="left:([\d.]+)%;width:calc\(([\d.]+)% - 2px\)"', page)


def test_a_history_is_spans_of_turns():
    f = fact(1, HANA, "located_in", [step(None, "old", "superseded"), step(2, "library", "superseded", closed_turn=7),
                                     step(7, "harbor", "current")])
    assert [(s["start"], s["end"], s["outcome"]) for s in timeline.segments(f, 10)] == \
        [(2, 6, "superseded"), (7, 10, "current")]  # a legacy entry without a turn is left out
    canon = fact(2, HANA, "identity", [step(None, "squire", "superseded", canon="card", closed_turn=5),
                                       step(5, "knight", "current")], owner=True)
    s = timeline.segments(canon, 9)
    assert (s[0]["start"], s[0]["end"], s[0]["canon"]) == (0, 4, True)  # canon sits before turn 0 (ADR 0047)
    assert s[1].get("owner") and not s[0].get("owner")  # only the current version carries the owner's mark
    ended = fact(3, HANA, "has_status", [step(3, "wounded", "ended")])  # closed, but by what is unknown
    assert [(x["start"], x["end"]) for x in timeline.segments(ended, 9)] == [(3, 3)]
    assert timeline.window(60, "recent") == (36, 60) and timeline.window(60, None) == (0, 60)
    # Two values current at once share one history; each lane draws its own current value only.
    first, second = step(4, "surveyor", "current"), step(6, "former clerk", "current")
    one = fact(5, HANA, "identity", [step(0, "apprentice", "superseded", closed_turn=6), first, second],
               value="surveyor", turn=4)
    assert [x["value"] for x in timeline.segments(one, 9)] == ["apprentice", "surveyor"]
    # The story restating a value is not a change: one bar until the value changes.
    held = fact(4, HANA, "possesses", [step(2, "compass", "superseded", closed_turn=4),
                                       step(4, "compass", "superseded", closed_turn=6), step(6, "map", "current")])
    assert [(x["start"], x["end"], x["value"]) for x in timeline.segments(held, 9)] == [(2, 5, "compass"), (6, 9, "map")]
    assert timeline.window(None, None) == (0, 0)


def rows(*specs: tuple) -> list[dict]:
    """Assertion rows as the fold reads them: (position, turn, predicate, subject, object, value[, subject_type])."""
    return [{"id": pos, "position": pos, "turn": turn, "predicate": pred, "subject": sub, "object": obj, "value": val,
             "polarity": "positive", "subject_type": rest[0] if rest else "character", "object_type": None,
             "knowledge": "public"} for pos, turn, pred, sub, obj, val, *rest in specs]


def test_a_shared_history_is_drawn_per_direction_and_holder():
    """facts.version_key keeps one history for a pair's relationship (both directions) and for an item (every holder):
    a lane draws its own entries, each until the statement that closed it (`closed_turn`), not the next entry."""
    from nmos_sidecar import facts

    pair = facts._pair_versions(rows((1, 1, "relationship", "Hana", "Kaito", "admires"),
                                     (2, 3, "relationship", "Kaito", "Hana", "resents"),
                                     (3, 6, "relationship", "Hana", "Kaito", "pities")))
    hana = next(f for f in pair if f["subject"] == "Hana")
    assert hana["history"][0]["closed_turn"] == 6 and "closed_turn" not in hana["history"][2]
    lane = timeline.segments(hana, 9, timeline.own_entries({"hana"}))
    assert [(s["start"], s["end"], s["value"]) for s in lane] == [(1, 5, "admires"), (6, 9, "pities")]

    book = facts._versions(rows((1, 2, "possesses", "Ian", "logbook", None), (2, 5, "possesses", "Doyun", "logbook", None)))
    held = next(f for f in book if f["subject"] == "Doyun")
    assert held["history"][0]["closed_turn"] == 5  # Ian held it until Doyun did
    assert [(s["start"], s["end"]) for s in timeline.segments(held, 9, timeline.own_entries({"doyun"}))] == [(5, 9)]


def test_the_character_page_draws_bars_that_link_to_their_rows():
    located = fact(10, HANA, "located_in", [step(2, "library", "superseded", closed_turn=7),
                                            step(7, "harbor", "current")], value="harbor", turn=7)
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
    assert '<details class="tl-group"><summary class="tl-h">Relationships from them</summary>' in page  # closed at first
    assert 'class="tl-bar open"' in page and 'href="#a-14"' in page and '<tr id="a-14">' in page  # the open thread
    assert 'class="tl-dot s-major"' in page and 'href="#a-12"' in page
    assert "the map is fake" not in page.split('id="s-timeline"')[1].split("</details>")[0]  # knows: its own table
    # The first current bar starts selected with its detail rendered; every other detail is built on a click from the
    # bar's own data, so nothing is rendered twice (an iPhone's memory, owner 2026-10-06).
    body = page.split("<main>", 1)[1].replace(timeline.SCRIPT, "")  # the style and the script name it too
    assert body.count('aria-pressed="true"') == 1 and body.count('class="tl-card"') == 1 and " hidden" not in body
    assert 'data-v="harbor" data-s="t7 – now" data-o="current"' in page
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
    body = inspector.character(CONV, "e1", view([sly]), None, now=3).split("<main>", 1)[1].replace(timeline.SCRIPT, "")
    assert body.count('aria-pressed="true"') == 1 and 'aria-pressed="{' not in body


def test_facts_that_never_changed_fold_away():
    moved = fact(10, HANA, "located_in", [step(2, "library", "superseded", closed_turn=7), step(7, "harbor", "current")])
    trait = fact(11, HANA, "has_trait", [step(1, "tall", "current")])
    few = inspector.character(CONV, "e1", view([moved, trait]), None, lang="en", now=10)
    assert 'class="tl-fold"' not in few  # an early chat: nothing folded
    assert '<details class="tl-group" open><summary class="tl-h">Facts</summary>' in few  # a group folds as a whole
    more = [fact(20 + i, HANA, "has_trait", [step(1, f"trait {i}", "current")]) for i in range(8)]
    page = inspector.character(CONV, "e1", view([moved, trait, *more]), None, lang="en", now=10)
    timeline_html = page.split('id="s-timeline"')[1].split("</details></details>")[0]
    shown, fold = timeline_html.split('<details class="tl-fold">', 1)
    assert "library" in shown and "tall" not in shown
    assert "<summary>Unchanged facts (9)</summary>" in fold and "tall" in fold
    assert 'aria-pressed="true"' not in fold.split('</details>')[0]  # the first detail comes from a lane in sight


def test_a_large_chat_is_capped_and_counted():
    many = [fact(100 + i, HANA, f"has_trait", [step(i + 1, f"trait {i}", "current")]) for i in range(45)]
    page = inspector.character(CONV, "e1", view(many), None, lang="en", now=50)
    assert len(bars(page)) == timeline.LANES and "+5 more in the tables below" in page


def test_the_recent_window_draws_the_last_25_turns():
    old = fact(10, HANA, "located_in", [step(3, "village", "superseded", closed_turn=20),
                                        step(20, "city", "superseded", closed_turn=50), step(50, "port", "current")])
    page = inspector.character(CONV, "e1", view([old]), None, lang="en", now=60, span="recent")
    # The village (3–19) ended before turn 36; the city (20–49) reaches into the window from its left edge.
    assert [b[:2] for b in bars(page)] == [("tl-bar past", "0.0"), ("tl-bar", "56.0")]
    assert "village" not in page.split('id="s-timeline"')[1].split("</details>")[0]
    assert '>t36</span>' in page and 'now t60' in page and "<b>Last 25 turns</b>" in page


def test_the_persona_has_a_timeline_and_the_first_cast_line():
    me = entity("p", "Yuma", persona=True)
    own = fact(10, ("p", "Yuma"), "possesses", [step(2, "compass", "current")], object="compass")
    page = inspector.character(CONV, "p", view([own], entities=[me, entity("e1", "Hana")]), None, now=5)
    assert len(bars(page)) == 1 and "소지: compass" in page  # a lane per thing held, named by it
    strip = timeline.cast(inspector._tl_t("en"), [entity("e1", "Hana"), me], [own], [], 5, None, lambda e: f"/x/{e}", "")
    # Owner, 2026-10-06: the persona's facts are memory too; ADR 0023 keeps its names out of recall, not out of view.
    shown, folded = strip.split("<details", 1)
    assert 'Yuma<span class="tl-me">you</span>' in shown and "Hana" in folded


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


# PHASE-32 step 3: the panel. The plugin's sanitizer keeps these tags, and `class`, `title`, `open`, section ids,
# Inspector links and the timeline's own data attributes (adapters/pocketrisu-plugin/src/inspector.ts).
PANEL_TAGS = {"div", "p", "h1", "h2", "span", "b", "br", "a", "table", "thead", "tbody", "tr", "th", "td", "details",
              "summary"}


def panel_safe(html: str) -> None:
    assert "style=" not in html and "<script" not in html and "aria-" not in html
    assert set(re.findall(r"<([a-z0-9]+)", html)) <= PANEL_TAGS
    for href in re.findall(r'href="([^"]*)"', html):
        assert re.fullmatch(r"/inspector/c/[^/?#]+(/e/[^/?#]+)?", href), href
    for name in set(re.findall(r'\s(data-[a-z]+)=', html)):
        assert name in {"data-l", "data-w", "data-v", "data-s", "data-o", "data-k", "data-p", "data-span"}, name


def test_the_panel_gets_a_closed_section_only_when_it_asks():
    located = fact(10, HANA, "located_in", [step(2, "library", "superseded", closed_turn=7), step(7, "harbor", "current")])
    v = view([located])
    plain = inspector.character(CONV, "e1", v, None, embed=True)
    asked = inspector.character(CONV, "e1", v, None, embed=True, lazy=True)
    assert 'id="s-timeline"' not in plain
    assert '<details id="s-timeline"><summary><h2>시간축</h2></summary><div class="tl-lazy"></div></details>' in asked
    assert asked.replace(re.search(r'<details id="s-timeline">.*?</details>', asked).group(0), "") \
        .replace(' · <a href="#s-timeline">시간축</a>', "") == plain  # nothing else changes
    conversation = inspector.detail(CONV, [], [], [], [], [], None, embed=True, lazy=True)
    assert '<details id="s-people"><summary><h2>등장인물 (시간축)</h2></summary><div class="tl-lazy"></div>' in conversation


def test_the_panel_timeline_is_what_the_sanitizer_keeps():
    located = fact(10, HANA, "located_in", [step(2, "library", "superseded", closed_turn=7), step(7, "harbor", "current")],
                   owner=True)
    event = fact(12, HANA, "event", None, value="the <b>fire</b>", turn=5, salience="major")
    thread = {"id": 14, "kind": "promise", "by": "Hana", "to": "Kaito", "text": "meet", "turn": 3, "position": 3,
              "status": "open", "closed_by": None, "restated": []}
    part = inspector.character_timeline(CONV, "e1", view([located, event], [thread]), "en", now=10, span="recent")
    panel_safe(part)
    assert 'class="tl-bar past" data-v="library" data-s="t2 – t6" data-o="superseded" data-l="18.182" data-w="45.454"' in part
    assert 'data-p="Hana → Kaito"' in part and 'data-v="the &lt;b&gt;fire&lt;/b&gt;"' in part
    assert '<span class="tl-span" data-span="">Whole chat</span> · <b>Last 25 turns</b>' in part
    assert inspector.character_timeline(CONV, "nobody", view([located]), "en", now=10) == ""
    long = fact(13, HANA, "event", None, value="x" * 1000, turn=6)
    cut = re.search(r'data-v="(x+…)"', inspector.character_timeline(CONV, "e1", view([long]), "en", now=10)).group(1)
    assert len(cut) == timeline.DATA_MAX  # under the panel's 400 (escaped text counts as its characters)
    people = inspector.conversation_cast(CONV, {"facts": [located], "entities": view([])["entities"], "scene": ["e1"]},
                                         10, "en")
    panel_safe(people)
    assert 'href="/inspector/c/c1/e/e1"' in people and 'data-l="' in people


def test_the_panel_routes(migrated):
    from test_inspector import STORY, character_links, story_client
    from test_sidecar_integration import sync

    client, c, drain = story_client(migrated, STORY)
    with client:
        sync(client, c)
        drain()
        conv = client.get("/v1/conversations").json()[0]["id"]
        hana = character_links(client.get(f"/inspector/c/{conv}").text, conv)["Hana"]
        base = f"/v1/inspector/c/{conv}/e/{hana}"
        assert client.get(base).json()["html"] == client.get(f"{base}?span=recent").json()["html"]  # as before
        assert '<div class="tl-lazy"></div>' in client.get(f"{base}?timeline=lazy").json()["html"]
        part = client.get(f"{base}?part=timeline&span=recent").json()["html"]
        panel_safe(part)
        assert "tl-bar" in part and "<b>최근 25턴</b>" in part
        people = client.get(f"/v1/inspector/c/{conv}?part=timeline").json()["html"]
        panel_safe(people)
        assert f'href="/inspector/c/{conv}/e/{hana}"' in people
        assert '<div class="tl-lazy"></div>' in client.get(f"/v1/inspector/c/{conv}?timeline=lazy").json()["html"]


def test_what_the_setting_gave_folds_apart_and_a_lane_says_its_value():
    """Owner, 2026-10-07: a lorebook brings many facts the story never touches; they fold under their own line, a
    lane's name carries its value now, and a value from the setting is drawn quieter."""
    moved = fact(10, HANA, "located_in", [step(0, "dormitory", "superseded", canon=True, closed_turn=2),
                                          step(2, "room 204", "current")])
    canon = [fact(30 + i, HANA, "has_trait", [step(0, f"setting trait {i}", "current", canon=True)]) for i in range(6)]
    story = [fact(40 + i, HANA, "has_trait", [step(1, f"story trait {i}", "current")]) for i in range(4)]
    page = inspector.character(CONV, "e1", view([moved, *canon, *story]), None, lang="en", now=10)
    timeline_html = page.split('id="s-timeline"')[1]
    assert '<span class="tl-k">located in</span><span class="tl-val">room 204</span>' in timeline_html
    assert "<summary>Unchanged facts (4)</summary>" in timeline_html
    setting = timeline_html.split('<details class="tl-fold tl-setting"><summary>From the setting (lorebook, card): 6'
                                  '</summary>', 1)[1].split("</details>")[0]
    assert "setting trait 0" in setting and "story trait" not in setting
    assert '<span class="tl-val canon">setting trait 0</span>' in setting
    assert not re.search(r'class="tl-bar[^"]*"[^>]*>[^<]+</a>', timeline_html)  # bars carry no text


def test_threads_start_closed_with_their_counts():
    threads = [{"id": i, "kind": "goal", "text": f"goal {i}", "by": "Hana", "to": None, "turn": i + 1,
                "position": i + 1, "status": "open" if i < 3 else "done", "restated": [],
                "closed_by": None if i < 3 else {"turn": i + 4, "subject": "Hana", "predicate": "event", "value": "done"}}
               for i in range(5)]
    page = inspector.character(CONV, "e1", view([], threads), None, lang="en", now=20)
    assert '<details class="tl-group"><summary class="tl-h">Threads · 3 open · 2 closed</summary>' in page


def test_the_fact_table_folds_what_the_setting_alone_gave():
    """Owner, 2026-10-07: the tables too (current facts, relationship pairs): rows only the setting gave fold below."""
    story = fact(50, HANA, "has_trait", [step(3, "brave", "current")], turn=3, value="brave")
    setting = fact(51, HANA, "has_trait", [step(0, "Born in the north", "current", canon=True)], turn=0,
                   value="Born in the north", canon=True)
    corrected = fact(52, HANA, "has_trait", [step(0, "tall", "current", canon=True)], turn=0, value="tall", canon=True,
                     owner=True)
    page = inspector.character(CONV, "e1", view([story, setting, corrected]), None, lang="en", now=10)
    about = page.split('id="s-about"')[1]
    shown, fold = about.split('<details class="fold-setting">', 1)
    assert "brave" in shown and "tall" in shown and "Born in the north" not in shown  # the owner's correction stays up
    assert "Only from the setting (lorebook, card): 1" in fold and "Born in the north" in fold.split("</details>")[0]
