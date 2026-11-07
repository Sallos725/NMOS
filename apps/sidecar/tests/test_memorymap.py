"""PHASE-55: the memory map, from the read every request makes (`memory_view`), and its screens."""

from __future__ import annotations

import re

from conftest import make_client
from nmos_sidecar import memorymap, views
from test_inspector_timeline import PANEL_TAGS
from test_sidecar_integration import sync

CID = "0190f3a4-1b2c-7d3e-8f40-123456789abc"
HANA, KAITO, MIRA, ME = (f"0190f3a4-1b2c-7d3e-8f40-00000000000{c}" for c in "abcd")
SERA, SERA_FULL, GONE = (f"0190f3a4-1b2c-7d3e-8f40-0000000000{c}" for c in ("e1", "e2", "e3"))
GUILD, MILL = "0190f3a4-1b2c-7d3e-8f40-0000000000f1", "0190f3a4-1b2c-7d3e-8f40-0000000000f2"
NAMES = {HANA: "Hana", KAITO: "Kaito", MIRA: "Mira", ME: "Yuu", SERA: "세라", SERA_FULL: "세라 델 모렌", GONE: "Bot",
         GUILD: "the guild", MILL: "the old mill"}


def step(turn, value=None, obj=None, outcome="current", canon=None, polarity="positive"):
    h = {"position": turn + 1, "turn": turn, "value": value, "object": obj, "polarity": polarity, "outcome": outcome}
    if canon:
        h["canon"] = canon
    return h


def fact(subject, predicate, obj=None, value=None, history=None, *, turn=5, otype="character", **kw):
    history = history or [step(turn, value, NAMES.get(obj, obj))]
    cur = history[-1]
    f = {"id": kw.pop("id", f"{subject}{predicate}{obj}{turn}"), "subject": NAMES[subject], "subject_type": "character",
         "predicate": predicate, "object": NAMES.get(obj, obj), "object_type": otype if obj else None,
         "value": cur["value"], "polarity": cur["polarity"], "turn": cur["turn"], "position": cur["position"],
         "subject_entity": {"id": subject, "name": NAMES[subject]}, "history": history}
    if obj in NAMES:
        f["object_entity"] = {"id": obj, "name": NAMES[obj]}
    if cur.get("canon"):
        f["canon"] = cur["canon"]
    f.update(kw)
    return f


def entity(eid, kind="character", mentions=1, **kw):
    return {"id": eid, "type": kind, "name": NAMES[eid], "names": [NAMES[eid]], "mentions": mentions, **kw}


def view(facts, *, entities=None, assertions=(), excluded=None):
    ents = entities if entities is not None else [
        entity(HANA, mentions=9), entity(KAITO, mentions=5), entity(MIRA), entity(ME, persona=True),
        entity(GUILD, "group"), entity(MILL, "place")]
    return {"facts": facts, "entities": ents, "excluded": excluded or {}, "assertions": list(assertions),
            "resolution": None}


SETTING = step(-1, "childhood friend", canon="lore:1")


def test_each_fact_falls_in_one_source_by_its_history():
    only = fact(HANA, "relationship", KAITO, history=[SETTING])
    over = fact(HANA, "relationship", MIRA, history=[{**SETTING, "outcome": "superseded"}, step(4, "rival")])
    told = fact(KAITO, "has_status", value="tired", history=[step(3, "tired")])
    fixed = fact(KAITO, "located_in", "the pier", history=[step(2, None, "the pier")], owner=True)
    assert [memorymap.source(f) for f in (only, over, told, fixed)] == ["setting", "over", "story", "owner"]
    event = fact(HANA, "event", value="the fire", history=[step(6, "the fire")])
    knows = fact(HANA, "knows", value="the code", history=[step(6, "the code")])
    src = memorymap.sources(view([only, over, told, fixed, event, knows]), 3)
    assert src["total"] == {"setting": 1, "over": 1, "story": 3, "owner": 1} and src["facts"] == 6  # as the prototype
    assert src["rows"][0] == {"predicate": "relationship", "setting": 1, "over": 1, "story": 0, "owner": 0}
    assert (src["told"], src["turns"], src["per_turn"]) == (4, 4, 1.0)  # the story's current facts over t0–t3
    assert memorymap.sources(view([]), None)["per_turn"] is None


def test_a_pair_is_one_edge_with_both_directions_and_addresses_only_in_its_detail():
    rel = fact(HANA, "relationship", KAITO, history=[SETTING])
    role = fact(KAITO, "role_toward", HANA, history=[step(4, "bodyguard")])
    feels = fact(HANA, "feels_toward", KAITO, history=[step(5, "trust")])
    calls = fact(MIRA, "addresses", HANA, history=[step(5, "언니")])
    g = memorymap.graph(view([rel, role, feels, calls]))
    ties = [e for e in g["edges"] if e["kind"] == "tie"]
    assert len(ties) == 1 and {ties[0]["a"], ties[0]["b"]} == {HANA, KAITO} and len(ties[0]["facts"]) == 3
    assert ties[0]["mark"] == "story"  # a story fact on it
    assert MIRA not in {n["id"] for n in g["nodes"]}  # a form of address alone draws no tie
    alone = memorymap.graph(view([rel]))
    assert alone["edges"][0]["mark"] == "setting"
    changed = fact(HANA, "relationship", KAITO, history=[{**SETTING, "outcome": "superseded"}, step(4, "rival")])
    assert memorymap.graph(view([changed]))["edges"][0]["mark"] == "changed"
    restated = fact(HANA, "relationship", KAITO, history=[{**SETTING, "outcome": "superseded"},
                                                          step(4, "childhood friend")])
    assert memorymap.graph(view([restated]))["edges"][0]["mark"] == "story"  # said again, not changed


def test_groups_and_the_current_place_are_edges_events_and_debts_are_not():
    member = fact(HANA, "member_of", GUILD, otype="group", history=[step(-1, None, "the guild", canon="lore:2")])
    there = fact(KAITO, "located_in", MILL, otype="place", history=[step(7, None, "the old mill")])
    away = fact(MIRA, "located_in", "the harbor", otype="place", history=[step(7, None, "the harbor", polarity="negative")])
    owes = fact(HANA, "owes", KAITO, value="a favor", history=[step(3, "a favor")])
    event = fact(HANA, "event", value="the fire", history=[step(6, "the fire")], participants=[{"name": "Kaito"}])
    g = memorymap.graph(view([member, there, away, owes, event]))
    kinds = sorted((e["kind"], e["mark"]) for e in g["edges"])
    assert kinds == [("group", "setting"), ("place", "story")]
    assert {n["id"]: n["kind"] for n in g["nodes"]}[GUILD] == "group"
    assert "text:place:the harbor" not in {n["id"] for n in g["nodes"]}


def test_left_out_entities_are_counted_not_drawn_and_the_persona_is_marked():
    rel = fact(ME, "relationship", HANA, history=[step(2, "partner")])
    bot = fact(GONE, "relationship", HANA, history=[step(2, "pet")])
    g = memorymap.graph(view([rel, bot], entities=[entity(HANA), entity(ME, persona=True), entity(GONE)],
                             excluded={GONE: {"scope": "cast"}}))
    ids = {n["id"]: n for n in g["nodes"]}
    assert GONE not in ids and g["excluded"] == 1 and ids[ME]["persona"]


def test_the_scene_and_the_persona_are_in_the_middle():
    rel = fact(HANA, "relationship", KAITO, history=[step(2, "partner")])
    g = memorymap.graph(view([rel]), scene=["kaito"])
    d = memorymap.drawn(g)
    assert d["pos"][KAITO] != d["pos"][HANA] and {n["id"] for n in d["nodes"]} == {HANA, KAITO, ME}
    middle = {k for k, (x, y) in d["pos"].items() if abs(x) + abs(y) < memorymap.GAP}
    assert middle == {KAITO, ME}


def test_names_that_may_be_one_person_are_flagged_by_the_rule_only():
    ents = [entity(SERA), entity(SERA_FULL), entity(HANA), entity(ME, persona=True)]
    sus = memorymap.suspects(view([], entities=ents))
    assert [(s["full"]["name"], s["short"]["name"]) for s in sus] == [("세라 델 모렌", "세라")]  # PHASE-54's rule

    class Split:  # the owner split them (ADR 0044): never flagged
        splits = [(None, None, {"entity_type": "character", "name": "세라", "other": "세라 델 모렌"})]

        def entity(self, kind, name):
            return next((e for e in ents if e["name"] == name), None)

    assert memorymap.suspects({**view([], entities=ents), "resolution": Split()}) == []
    assert memorymap.suspects(view([], entities=ents, excluded={SERA: {"scope": "cast"}})) == []
    words = [entity(HANA), {**entity(KAITO), "name": "Ana Bell", "names": ["Ana Bell"]},
             {**entity(MIRA), "name": "Ana Bell Ross", "names": ["Ana Bell Ross"]}]
    assert [(s["full"]["name"], s["short"]["name"]) for s in memorymap.suspects(view([], entities=words))] == \
        [("Ana Bell Ross", "Ana Bell")]  # the first words
    persona = [{**entity(ME, persona=True), "name": "세라", "names": ["세라"]}, entity(SERA_FULL)]
    assert memorymap.suspects(view([], entities=persona)) == []


def test_events_are_the_storys_in_turn_order_with_who_and_why():
    late = fact(HANA, "event", value="the fire", history=[step(9, "the fire")], salience="major", because="a lamp fell",
                participant_entities=[{"name": "kai", "entity": {"id": KAITO, "name": "Kaito"}}, {"name": "a guard"}],
                generation="extract-v18")
    early = fact(KAITO, "event", value="arrives", history=[step(2, "arrives")], salience="minor", generation="extract-v17")
    lore = fact(HANA, "event", value="the war", history=[step(-1, "the war", canon="lore:3")])
    evs = memorymap.events(view([late, early, lore]))
    assert [e["text"] for e in evs] == ["arrives", "the fire"]
    assert evs[1]["participants"] == ["Kaito", "a guard"] and evs[1]["because"] == "a lamp fell"
    dp = memorymap.depth(evs)
    assert {k: dp[k] for k in ("events", "participants", "because", "outcome", "major", "minor", "none")} == \
        {"events": 2, "participants": 1, "because": 1, "outcome": 0, "major": 1, "minor": 1, "none": 0}
    assert set(dp["by_generation"]) == {"extract-v17", "extract-v18"}


def test_rings_are_deterministic_and_never_put_two_nodes_on_one_spot():
    middle, inner, outer = ["a"], [f"c{i}" for i in range(23)], [f"g{i}" for i in range(16)]
    pos, radius = memorymap.rings(middle, inner, outer)
    assert pos == memorymap.rings(middle, inner, outer)[0] and pos["a"] == (0.0, 0.0)
    spots = list(pos.values())
    assert len(set(spots)) == len(spots) == 40
    for i, (x1, y1) in enumerate(spots):
        for x2, y2 in spots[i + 1:]:
            assert ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5 > 40
    assert radius < 700


def big_graph(n=30, groups=10):
    facts = [fact(HANA, "relationship", f"c{i}", history=[step(2, "friend")], otype="character") for i in range(n)]
    facts += [fact(HANA, "member_of", f"g{i}", otype="group", history=[step(3, None, f"g{i}")]) for i in range(groups)]
    return memorymap.graph(view(facts))


def test_the_drawing_is_capped_counts_what_it_left_out_and_can_draw_everyone():
    g = big_graph()
    d = memorymap.drawn(g)
    kinds = [n["kind"] for n in d["nodes"]]
    assert kinds.count("character") == 24 and kinds.count("group") == 8
    assert d["left"] == {"character": 8, "group": 2}  # 32 characters with Hana and the persona
    every = memorymap.drawn(g, everyone=True)
    assert every["left"] == {} and len(every["nodes"]) == 42
    focus = memorymap.drawn(g, focus="text:character:c3")
    assert {n["id"] for n in focus["nodes"]} == {"text:character:c3", HANA}


# --- the screens --------------------------------------------------------------------------------------------------------

def map_data(facts=None, **kw):
    facts = facts if facts is not None else [
        fact(HANA, "relationship", KAITO, history=[{**SETTING, "outcome": "superseded"}, step(4, "rival")]),
        fact(KAITO, "role_toward", HANA, history=[step(4, "bodyguard")]),
        fact(HANA, "member_of", GUILD, otype="group", history=[step(-1, None, "the guild", canon="lore:2")]),
        fact(HANA, "event", value="the fire", history=[step(9, "the fire")], salience="major", because="a lamp fell",
             participants=[{"name": "Kaito"}]),
        fact(KAITO, "has_status", value="tired", history=[step(-1, "tired", canon="lore:4")]),
        fact(SERA, "relationship", HANA, history=[step(6, "sister")]),
        fact(SERA_FULL, "relationship", KAITO, history=[step(7, "mentor")])]
    ents = kw.pop("entities", None) or [entity(HANA, mentions=9), entity(KAITO), entity(SERA), entity(SERA_FULL),
                                        entity(ME, persona=True), entity(GUILD, "group")]
    v = view(facts, entities=ents)
    return {"conv": {"id": CID, "name": "Harbor", "character": "Hana", "turns": 9},
            "map": memorymap.build(v, 9, kw.pop("scene", ["Hana"])),
            "entities": {"hana": HANA, "kaito": KAITO}}


def panel_safe(html: str) -> None:
    """The panel's sanitizer keeps these tags, and its own attributes (adapters/pocketrisu-plugin/src/inspector.ts)."""
    assert "style=" not in html and "<script" not in html and "<svg" not in html and "<table" not in html
    assert set(re.findall(r"<([a-z0-9]+)", html)) <= PANEL_TAGS - {"table", "thead", "tbody", "tr", "th", "td"}
    for href in re.findall(r'href="([^"]*)"', html):
        assert re.fullmatch(rf"/views/c/{CID}/(map(\?focus=[0-9a-f-]{{36}})?|memory|person/[0-9a-f-]{{36}})"
                            rf"|/inspector/c/{CID}|#s-[a-z]+", href), href
    for name in set(re.findall(r'\s(data-[a-z]+)=', html)):
        assert name in {"data-l", "data-w"}, name
    for value in re.findall(r'data-[lw]="([^"]*)"', html):
        assert re.fullmatch(r"(?:100(?:\.0{1,3})?|\d{1,2}(?:\.\d{1,3})?)", value), value


def test_the_map_is_four_sections_in_the_panels_tags():
    html = views.memory_map(map_data(), "ko")
    panel_safe(html)
    assert re.findall(r'class="v-sec" id="(s-[a-z]+)"', html) == ["s-src", "s-ties", "s-events", "s-depth"]
    assert "지금 사실 7개 · 설정에서만 29% · 이야기에서 71%" in html  # the event counted, as the prototype
    assert "이야기에서 온 지금 사실: 한 턴에 약 0.5개 · t0–t9" in html
    assert 'class="g-m changed">설정에서 바뀜' in html and 'class="g-m setting">설정' in html
    assert f'href="/views/c/{CID}/map?focus={KAITO}"' in html
    assert "한 사람일지도?" in html and f"/views/c/{CID}/person/{SERA_FULL}" in html
    assert "함께: Kaito · 이유: a lamp fell" in html and 'class="v-pin major"' in html
    assert "다른 인물이 나옴 · 1/1 · 100%" in html and "적을 칸이 없어요" in html
    assert "extract-v" not in html.split("<details")[0]  # identifiers only under details
    assert "/views/c/" + CID + "/map" in html and "브라우저" in html  # the panel says where the drawing is


def test_the_browser_page_adds_the_drawing_and_a_person_has_their_own_map():
    page = views.memory_map(map_data(), "en", page=True)
    assert '<div class="v-graph whole"><svg' in page and 'class="g-e changed"' in page and 'class="g-e split"' in page
    assert "Show all" not in page  # nothing left out
    focus = views.memory_map(map_data(), "en", focus=KAITO, page=True)
    assert "Around Kaito" in focus and '<div class="v-graph one"><svg' in focus and 's-src' not in focus
    assert f'href="/views/c/{CID}/person/{KAITO}"' in focus
    panel_focus = views.memory_map(map_data(), "ko", focus=KAITO)
    panel_safe(panel_focus)
    assert views.memory_map(map_data(), "ko", focus="no-such") == views.memory_map(map_data(), "ko")


def test_show_all_draws_past_the_caps():
    facts = [fact(HANA, "relationship", f"c{i}", history=[step(2, "friend")]) for i in range(30)]
    capped = views.memory_map(map_data(facts), "en", page=True)
    assert "Left out of the drawing: 8 characters" in capped and f'/views/c/{CID}/map?all=1#s-ties' in capped
    every = views.memory_map(map_data(facts), "en", everyone=True, page=True)
    assert "Left out" not in every and "Show fewer" in every and every.count('<circle') == 32


def test_the_drawing_as_data_for_the_panel():
    g = views.map_graph(map_data(), "ko")
    ids = {n["id"] for n in g["nodes"]}
    assert {HANA, KAITO, ME} <= ids and all(isinstance(n["x"], float) and isinstance(n["y"], float) for n in g["nodes"])
    assert all(e["a"] in ids and e["b"] in ids and e["mark"] in ("setting", "story", "changed") for e in g["edges"])
    assert g["suspects"] == [{"a": SERA_FULL, "b": SERA}] and not g["capped"]
    me = next(n for n in g["nodes"] if n["id"] == ME)
    assert me["name"] == "Yuu (나)" and me["lead"] and me["entity"] == ME
    guild = next(n for n in g["nodes"] if n["id"] == GUILD)
    assert guild["kind"] == "group" and guild["entity"] is None  # only a character opens a map
    assert g["words"]["ties"] == "관계 {n}" and g["words"]["fit"] == "맞춤"
    one = views.map_graph(map_data(), "en", focus=KAITO)
    assert one["focus"] == KAITO and all(KAITO in (e["a"], e["b"]) for e in one["edges"])
    assert views.map_graph(map_data(), "en", focus="nobody")["focus"] is None
    facts = [fact(HANA, "relationship", f"c{i}", history=[step(2, "friend")]) for i in range(30)]
    capped = views.map_graph(map_data(facts), "en")
    assert capped["capped"] and capped["words"]["left"] == "Left out of the drawing: 8 characters"
    assert len(views.map_graph(map_data(facts), "en", everyone=True)["nodes"]) == 32
    assert 'class="v-note v-graph-note"' in views.memory_map(map_data(), "ko")  # where the panel draws it


def test_an_empty_chat_has_a_map_that_says_so():
    html = views.memory_map(map_data([], entities=[entity(ME, persona=True)], scene=[]), "en")
    panel_safe(html)
    assert html.count("Nothing yet") == 4


def test_chat_text_is_escaped_on_the_map():
    bad = '<img src=x onerror=alert(1)>"'
    NAMES["bad"] = bad
    facts = [fact(HANA, "relationship", "bad", history=[step(2, bad)]),
             fact(HANA, "event", value=bad, history=[step(3, bad)], because=bad, participants=[{"name": bad}]),
             fact(HANA, "located_in", bad, otype="place", history=[step(3, None, bad)])]
    data = map_data(facts)
    data["conv"]["name"] = bad
    for html in (views.memory_map(data, "ko"), views.memory_map(data, "ko", page=True)):
        assert "<img" not in html and "onerror=alert(1)>" not in html and "&lt;img" in html


def test_the_hub_and_the_memory_document_change_only_when_asked():
    from test_views import hub_data, memory_data
    assert views.hub(hub_data(), "ko") == views.hub(hub_data(), "ko", False)
    blocks = re.findall(r'<span class="v-bt">([^<]+)', views.hub(hub_data(), "ko", True))
    assert blocks == ["작동 중", "기억", "기억 지도", "작가의 노트", "사용량", "설정", "백업", "다른 채팅"]
    assert "/map" not in views.memory(memory_data(), "ko")
    assert f'<a href="/views/c/{CID}/map">기억 지도</a>' in views.memory(memory_data(), "ko", True)


def test_the_map_endpoints(migrated):
    from test_canon_facts import Model, drain, story
    from test_generations import LLM

    chat, model = story(), Model()
    with make_client(migrated, **LLM) as c:
        assert c.get("/v1/health").json()["features"]["map"] is True
        sync(c, chat)
        drain(migrated, model)
        hub = c.get("/v1/views/hub", params={"chat": chat.id}).json()
        cid = hub["conversation"]
        assert "기억 지도" not in hub["html"]
        assert f"/views/c/{cid}/map" in c.get("/v1/views/hub", params={"chat": chat.id, "map": 1}).json()["html"]
        assert f"/views/c/{cid}/map" not in c.get(f"/v1/views/c/{cid}/memory").json()["html"]
        assert f"/views/c/{cid}/map" in c.get(f"/v1/views/c/{cid}/memory", params={"map": 1}).json()["html"]
        r = c.get(f"/v1/views/c/{cid}/map")
        assert r.status_code == 200 and "<svg" not in r.json()["html"] and 'id="s-src"' in r.json()["html"]
        hana = next(e for e in c.get(f"/v1/conversations/{cid}/entities").json() if e["name"] == "Hana")
        focus = c.get(f"/v1/views/c/{cid}/map", params={"focus": hana["id"]}).json()["html"]
        page = c.get(f"/views/c/{cid}/map", params={"all": 1})
        assert page.status_code == 200 and '<div class="nmos">' in page.text
        assert c.get(f"/v1/views/c/{cid}/map", params={"focus": "x"}).status_code == 422
        assert c.get("/v1/views/c/0190f3a4-1b2c-7d3e-8f40-999999999999/map").status_code == 404
        assert c.get("/v1/health").json()["features"]["map_graph"] is True
        graph = c.get(f"/v1/views/c/{cid}/map/graph", params={"all": 1, "lang": "en"}).json()
        assert {"nodes", "edges", "suspects", "words"} <= set(graph) and graph["everyone"] is True
        assert c.get("/v1/views/c/0190f3a4-1b2c-7d3e-8f40-999999999999/map/graph").status_code == 404
    assert "Hana" in focus


def _crowd(n: int) -> dict:
    nodes = [{"id": f"c{i}", "name": f"Person {i}", "kind": "character", "entity": None, "scene": i == 0,
              "persona": False} for i in range(n)]
    pos = {x["id"]: memorymap.rings([x["id"] for x in nodes[:1]], [x["id"] for x in nodes[1:]], [])[0][x["id"]]
           for x in nodes}
    radius = max(abs(v) for xy in pos.values() for v in xy)
    return {"nodes": nodes, "edges": [], "suspects": [], "pos": pos, "radius": radius}


def test_the_page_drawing_fits_its_column_and_a_large_one_keeps_only_the_cast_named():
    """PHASE-55 amendment 2: the whole map showed cut off; nothing scrolls sideways, every dot is inside the viewBox."""
    assert "overflow-x" not in views.STYLE.split(".nmos .v-graph{")[1].split("}")[0]
    assert "max-width:100%" in views.STYLE.split(".nmos .v-graph svg{")[1].split("}")[0]
    big = _crowd(120)
    svg = views._svg("c", big, "en")
    x, y, w, h = (float(v) for v in re.search(r'viewBox="([^"]+)"', svg).group(1).split())
    for cx, cy, r in re.findall(r'cx="([-\d.]+)" cy="([-\d.]+)" r="([\d.]+)"', svg):
        assert x <= float(cx) - float(r) and float(cx) + float(r) <= x + w
        assert y <= float(cy) - float(r) and float(cy) + float(r) <= y + h
    assert svg.count("<text") == 1 and ">Person 0</text>" in svg and "<title>Person 7</title>" in svg
    assert views._svg("c", big, "en", True).count("<text") == 120  # one person's map keeps every name
    small = views._svg("c", _crowd(9), "en")
    assert small.count("<text") == 9 and "font-size" not in small


def test_a_drawn_name_runs_inward_at_a_side_and_stops_at_its_length():
    d = _crowd(9)
    d["nodes"][1]["name"] = "n" * 40
    d["pos"]["c1"], d["pos"]["c2"], d["pos"]["c3"] = (-200.0, 0.0), (200.0, 0.0), (0.0, 200.0)
    d["radius"] = 200.0
    svg = views._svg("c", d, "en")
    assert f'text-anchor="start">{"n" * 23}…</text>' in svg and f'<title>{"n" * 40}</title>' in svg
    assert 'text-anchor="end">Person 2</text>' in svg and 'text-anchor="middle">Person 3</text>' in svg
