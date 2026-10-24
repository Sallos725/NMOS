"""PHASE-52: the panel's new screens, rendered by the sidecar (the hub first)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from conftest import make_client
from nmos_sidecar import tokens, views
from simchat import SimChat
from test_sidecar_integration import sync

TOKENS = Path(__file__).resolve().parents[3] / "fixtures/unit/design-tokens-v1.json"


def test_tokens_are_the_fixtures():
    doc = json.loads(TOKENS.read_text(encoding="utf-8"))
    assert tokens.TOKENS == {k: doc[k] for k in ("color", "type", "space", "radius")}
    assert "--c-text-muted:#9294a0" in tokens.css_vars() and "--t-body:16px" in tokens.css_vars()


def test_every_rule_of_the_stylesheet_is_the_panels():
    """The panel injects this stylesheet into the host's page: no rule may reach outside `.nmos`."""
    flat = re.sub(r"\}\s*\}", "}", re.sub(r"@media[^{]*\{", "", views.STYLE))  # the rules inside a media query too
    rules = re.findall(r"([^{}]+)\{[^{}]*\}", flat)
    assert rules
    for selectors in rules:
        for sel in selectors.split(","):
            assert sel.strip().startswith(".nmos"), sel
    assert "@import" not in views.STYLE and "url(" not in views.STYLE


def hub_data(**over):
    data = {"conv": {"id": "0190f3a4-1b2c-7d3e-8f40-123456789abc", "name": "Harbor", "character": "Hana", "turns": 13},
            "working": {"state": "ok", "reply": {"placed": 14, "ms": 312}, "failed": 0, "pending": 0},
            "memory": {"cast": 3, "open": 10, "stale": 0, "changed": 1, "now": ["Hana · the lighthouse"]},
            "attention": 0, "usage": {"calls": 41}, "chats": 4}
    data.update(over)
    return data


def test_the_hub_is_blocks_in_order_and_needs_a_look_only_when_there_is_something():
    html = views.hub(hub_data(), "ko")
    blocks = re.findall(r'class="v-block[^"]*"[^>]*>\s*<span class="v-bt">([^<]+)', html)
    assert blocks == ["작동 중", "기억", "작가의 노트", "사용량", "설정", "백업", "다른 채팅"]
    assert "확인 필요" not in html and "<table" not in html
    assert 'data-act="notes"' in html and 'data-act="settings"' in html and 'data-act="backup"' in html
    assert "/views/c/0190f3a4-1b2c-7d3e-8f40-123456789abc/working" in html
    assert "/views/c/0190f3a4-1b2c-7d3e-8f40-123456789abc/memory" in html
    flagged = views.hub(hub_data(attention=2), "en")
    assert "Needs a look" in flagged and re.search(r"Needs a look</span>\s*<span class=\"v-bs\">2", flagged)


def test_the_working_line_says_what_is_wrong():
    assert "v-block v-wide ok" in views.hub(hub_data(), "ko")
    failed = views.hub(hub_data(working={"state": "warn", "reply": None, "failed": 2, "pending": 0}), "ko")
    assert "v-block v-wide warn" in failed and "실패 2" in failed
    off = views.hub(hub_data(working={"state": "off", "reply": None, "failed": 0, "pending": 0}), "ko")
    assert "이 채팅은 NMOS가 꺼져 있어요" in off


def test_without_a_known_chat_the_hub_offers_the_chats_and_settings():
    html = views.hub({"conv": None, "working": {"state": "idle"}, "chats": 4}, "ko")
    blocks = re.findall(r'<span class="v-bt">([^<]+)', html)
    assert blocks == ["연결됨", "설정", "백업", "다른 채팅"]
    assert "아직 이 채팅의 기록이 없어요" in html


def test_the_hub_endpoint_and_the_feature(migrated):
    chat = SimChat("views-hub")
    chat.user("Hello.")
    chat.reply("Hana waits at the lighthouse.")
    with make_client(migrated) as c:
        assert c.get("/v1/health").json()["features"]["views"] is True
        css = c.get("/v1/views/style").json()["css"]
        assert css == views.STYLE
        sync(c, chat)
        r = c.get("/v1/views/hub", params={"chat": chat.id, "lang": "en"})
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["conversation"] and 'class="v-block' in out["html"] and "Memory" in out["html"]
        unknown = c.get("/v1/views/hub", params={"chat": "no-such-chat"}).json()
        assert unknown["conversation"] is None and "다른 채팅" in unknown["html"] and ">기억<" not in unknown["html"]
        page = c.get("/views/hub", params={"chat": chat.id})
        assert page.status_code == 200 and '<div class="nmos">' in page.text and "<style>" in page.text



# --- memory, one document (PHASE-52 D2) --------------------------------------------------------------------------------

CID = "0190f3a4-1b2c-7d3e-8f40-123456789abc"
HANA, KAITO = "0190f3a4-1b2c-7d3e-8f40-00000000000a", "0190f3a4-1b2c-7d3e-8f40-00000000000b"


def thread(i, text, *, by="Hana", to=None, kind="goal", turn=5, **kw):
    return {"id": i, "kind": kind, "by": by, "to": to, "text": text, "turn": turn, "status": "open", "restated": [],
            "knowledge": None, "hidden_from": None, **kw}


def memory_data(**over):
    rel = {"subject": "Hana", "predicate": "relationship", "object": "Kaito", "value": "childhood friend", "turn": 3,
           "position": 3, "subject_entity": {"id": HANA, "name": "Hana"}, "object_entity": {"id": KAITO, "name": "Kaito"}}
    calls = {**rel, "subject": "Kaito", "object": "Hana", "predicate": "addresses", "value": "누나",
             "subject_entity": {"id": KAITO, "name": "Kaito"}, "object_entity": {"id": HANA, "name": "Hana"}}
    moved = {"subject": "Hana", "predicate": "located_in", "object": "old mill", "value": None, "turn": 9,
             "position": 9, "polarity": "positive", "subject_entity": {"id": HANA, "name": "Hana"}}
    data = {"conv": {"id": CID, "name": "Harbor", "character": "Hana", "turns": 13},
            "now": [{"name": "Hana", "entity": HANA, "said": ["the lighthouse", "wet coat"]},
                    {"name": "Kaito", "entity": KAITO, "said": ["the pier"]}],
            "threads": [thread(i, f"goal {i}") for i in range(1, 6)], "stale": 2,
            "pairs": [{"ids": (HANA, KAITO), "names": {HANA: "Hana", KAITO: "Kaito"}, "relationship": [rel],
                       "role": [], "feels": [], "speech": [calls], "position": 3}],
            "story": {"first_turn": 0, "last_turn": 7, "text": "Hana went to the lighthouse."},
            "scenes": [{"first_turn": 0, "last_turn": 7, "text": "Scene one."}],
            "secrets": [{"id": 9, "text": "Hana identity: smuggler", "holders": ["Hana"], "open": ["Kaito"], "turn": 2}],
            "changes": [{"fact": moved, "old": "harbor town", "new": "old mill"}],
            "facts": 138, "attention": 1, "entities": {"hana": HANA, "kaito": KAITO}}
    data.update(over)
    return data


def test_memory_is_one_document_in_the_decided_order():
    html = views.memory(memory_data(), "ko")
    ids = re.findall(r'class="v-sec" id="(s-[a-z]+)"', html)
    assert ids == ["s-now", "s-open", "s-people", "s-sofar", "s-secrets", "s-changed"]
    assert "<table" not in html and "extract-" not in html
    assert re.findall(r'<a href="#(s-[a-z]+)">', html)[:6] == ids  # the jump row


def test_lists_show_three_and_fold_the_rest_and_say_what_was_left_out():
    html = views.memory(memory_data(), "ko")
    opened = html.split('id="s-open"')[1].split('class="v-sec"')[0]
    shown, folded = opened.split('<details class="v-more">')
    assert shown.count('class="v-line') == 3 and folded.count('class="v-line') == 2 and "2개 더 보기" in folded
    assert "30턴 넘게 언급 없는 열린 일 2개" in opened


def test_names_lead_to_their_person_and_lines_carry_their_repairs():
    html = views.memory(memory_data(), "ko")
    assert f'href="/views/c/{CID}/person/{HANA}"' in html
    assert html.count('data-repair="thread_close:') == 5
    assert '&quot;누나&quot;' in html and "harbor town" in html and "old mill" in html


def test_secrets_are_the_owners_to_see():
    html = views.memory(memory_data(), "ko")
    secrets = html.split('id="s-secrets"')[1].split('class="v-sec"')[0]
    assert "smuggler" in secrets and "Kaito" in secrets


def test_the_memory_endpoint(migrated):
    chat = SimChat("views-memory")
    chat.user("Hello.")
    chat.reply("Hana waits at the lighthouse.")
    with make_client(migrated) as c:
        sync(c, chat)
        cid = c.get("/v1/views/hub", params={"chat": chat.id}).json()["conversation"]
        r = c.get(f"/v1/views/c/{cid}/memory")
        assert r.status_code == 200, r.text
        assert 'id="s-now"' in r.json()["html"]
        assert c.get(f"/views/c/{cid}/memory").status_code == 200
        assert c.get("/v1/views/c/00000000-0000-0000-0000-000000000000/memory").status_code == 404



# --- a person's sheet and the timeline in circles (PHASE-52 D3, D4) ---------------------------------------------------

from nmos_sidecar import timeline  # noqa: E402


def test_circles_merge_so_marks_stay_apart_and_keep_a_major_mark():
    marks = [(t, t == 503, f"change {t}") for t in range(1000)]
    out = timeline.circles(marks, 0, 999)
    assert len(out) <= 30 and sum(b["count"] for b in out) == 1000
    assert [b for b in out if b["major"]] and any(b["lo"] <= 503 <= b["hi"] for b in out if b["major"])
    crowded = timeline.circles([(t, False, "x") for t in range(30, 40)], 0, 75)  # ten turns close together
    assert len(crowded) <= 4
    few = timeline.circles([(3, False, "a"), (3, True, "b"), (9, False, "c")], 0, 12)
    assert [(b["lo"], b["hi"], b["count"], b["major"]) for b in few] == [(3, 3, 2, True), (9, 9, 1, False)]


def person_data(**over):
    d = memory_data()
    data = {"conv": d["conv"], "entity": {"id": HANA, "name": "Hana", "names": ["Hana", "Hanachan"]},
            "now": ["the lighthouse", "wet coat"], "pairs": d["pairs"], "threads": d["threads"][:2],
            "knows": [d["secrets"][0]], "kept": [], "marks": [(2, False, "Hana identity: smuggler"),
                                                               (9, True, "Hana meets Kaito")],
            "first": 0, "last": 12, "entities": d["entities"]}
    data.update(over)
    return data


def test_a_persons_sheet():
    html = views.person(person_data(), "ko")
    assert re.findall(r'class="v-sec" id="(s-[a-z]+)"', html) == ["s-now", "s-rels", "s-threads", "s-knows", "s-time"]
    assert "Hanachan" in html and "<table" not in html and "<svg" not in html
    pins = re.findall(r'<span class="v-pin( major)?" data-l="([0-9.]+)"></span>', html)
    assert [(bool(m), float(l)) for m, l in pins] == [(False, 16.667), (True, 75.0)]  # turns 2 and 9 of 0–12
    assert 'class="v-mini" aria-hidden="true"' in html and "data-v=" not in html  # a bar to look at, not to tap
    # the ring's change leads, then the rest in turn order
    events = re.findall(r'<div class="v-ev( major)?"><span class="v-t">t(\d+)</span><span class="v-d"></span>'
                        r'<span class="v-x">([^<]*)</span>', html)
    assert events == [(" major", "9", "Hana meets Kaito"), ("", "2", "Hana identity: smuggler")]
    assert f'href="/views/c/{CID}/memory"' in html


def test_a_persons_timeline_leads_with_at_most_five_and_folds_the_rest():
    marks = [(t, True, f"change {t}") for t in range(0, 76, 2)]  # a lead's: every change major
    html = views.person(person_data(marks=marks, last=75), "ko")
    timeline = html.split('id="s-time"')[1]
    shown, folded = timeline.split('<details class="v-more">')
    assert shown.count('class="v-ev major"') == 5 and shown.count('class="v-ev"') == 0
    assert folded.count('class="v-ev"') == len(marks) - 5 and "33개 더 보기" in folded
    turns = [int(x) for x in re.findall(r'class="v-ev major"><span class="v-t">t(\d+)<', shown)]
    assert turns == sorted(turns) and len(set(turns)) == 5
    quiet = views.person(person_data(marks=[(t, False, f"minor {t}") for t in range(5)], last=12), "ko")
    assert quiet.split('id="s-time"')[1].split('<details')[0].count('class="v-ev"') == 3  # no rings: the first three


def test_the_person_endpoint(migrated):
    chat = SimChat("views-person")
    chat.user("Hello.")
    chat.reply("Hana waits at the lighthouse.")
    with make_client(migrated) as c:
        sync(c, chat)
        cid = c.get("/v1/views/hub", params={"chat": chat.id}).json()["conversation"]
        missing = c.get(f"/v1/views/c/{cid}/person/0190f3a4-1b2c-7d3e-8f40-00000000000a")
        assert missing.status_code == 404 and missing.json()["detail"] == "person not found"



def test_a_person_with_facts_has_a_sheet_and_circles(migrated):
    from test_canon_facts import Model, drain, story
    from test_generations import LLM

    chat, model = story(), Model()
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        drain(migrated, model)
        cid = c.get("/v1/views/hub", params={"chat": chat.id}).json()["conversation"]
        hana = next(e for e in c.get(f"/v1/conversations/{cid}/entities").json() if e["name"] == "Hana")
        html = c.get(f"/v1/views/c/{cid}/person/{hana['id']}").json()["html"]
        memory = c.get(f"/v1/views/c/{cid}/memory").json()["html"]
    assert ">Hana<" in html and 'class="v-ev' in html and 'class="v-pin' in html and "old mill" in html
    assert f'/views/c/{cid}/person/{hana["id"]}' in memory



# --- working, in plain words (PHASE-52 D5) -----------------------------------------------------------------------------

def working_data(**over):
    data = {"conv": {"id": CID, "name": "Harbor", "character": "Hana", "turns": 13},
            "reply": {"at": "2026-10-23T12:00:00+00:00", "ms": 1206.2, "tokens": 1980,
                      "lines": [{"kind": "fact", "text": "Hana located in: old mill", "placed": True, "echoed": True},
                                {"kind": "fact", "text": "Kaito has status: tired", "placed": True},
                                {"kind": "thread", "text": "Hana → Kaito promised: meet at the lighthouse", "placed": True},
                                {"kind": "fact", "text": "left out", "placed": False}]},
            "work": {"extraction": {"compiled": 13, "eligible": 13, "failed": 0, "pending": 0},
                     "embeddings": {"embedded": 27, "eligible": 27, "failed": 0, "pending": 0},
                     "summaries": {"produced": 2, "failed": 0, "pending": 0},
                     "canon": {"read": 10, "wanted": 10, "failed": 0, "pending": 0}},
            "errors": [], "usage": {"calls": 176, "input": 387955, "output": 84996}}
    data.update(over)
    return data


def test_working_says_it_in_words_not_xml():
    html = views.working(working_data(), "ko")
    assert re.findall(r'class="v-sec" id="(s-[a-z]+)"', html) == ["s-reply", "s-sent", "s-work", "s-usage"]
    assert "<Fact" not in html and "&lt;Fact" not in html and "<table" not in html
    assert "Hana 위치: old mill" in html and "left out" not in html  # only what was placed, in plain words
    assert "13/13" in html and "176" in html and "has-failed" not in html and 'data-act="retry"' not in html


def test_working_offers_retry_when_something_failed():
    html = views.working(working_data(work={**working_data()["work"],
                                            "extraction": {"compiled": 11, "eligible": 13, "failed": 2, "pending": 0}},
                                      errors=["HTTP 429: rate limited"]), "ko")
    assert 'class="has-failed"' in html and 'data-act="retry"' in html and "HTTP 429" in html


def test_working_without_a_request_yet():
    html = views.working(working_data(reply=None), "ko")
    assert "아직 이 채팅에서 받은 요청이 없어요" in html


def test_the_working_endpoint(migrated):
    chat = SimChat("views-working")
    chat.user("Hello.")
    chat.reply("Hana waits at the lighthouse.")
    with make_client(migrated) as c:
        sync(c, chat)
        cid = c.get("/v1/views/hub", params={"chat": chat.id}).json()["conversation"]
        r = c.get(f"/v1/views/c/{cid}/working")
        assert r.status_code == 200, r.text
        assert 'id="s-work"' in r.json()["html"]



# --- other chats (PHASE-52 D7) ------------------------------------------------------------------------------------------

def test_the_chats_are_a_list_to_search_with_failures_marked():
    rows = [{"id": CID, "host_chat_name": "Harbor", "host_character_name": "Hana", "messages": 26,
             "last_retrieval": "2026-10-23T12:00:00+00:00", "created_at": "2026-10-01T00:00:00+00:00", "failed": 0},
            {"id": KAITO, "host_chat_name": None, "host_character_name": "Kaito", "messages": 4,
             "last_retrieval": None, "created_at": "2026-10-02T00:00:00+00:00", "failed": 2}]
    html = views.chats(rows, "ko", current=CID)
    assert html.count('class="v-line v-chat"') == 2 and '<div class="v-filter"></div>' in html
    assert f'href="/views/hub?conversation={CID}"' in html and "지금 열린 채팅" in html
    assert 'title="2026-10-23T12:00:00+00:00"' in html and "실패 2" in html and "<table" not in html


def test_the_chats_endpoint(migrated):
    chat = SimChat("views-chats")
    chat.user("Hello.")
    chat.reply("Hi.")
    with make_client(migrated) as c:
        sync(c, chat)
        out = c.get("/v1/views/chats").json()
        assert 'class="v-line v-chat"' in out["html"]
        assert c.get("/views/chats").status_code == 200



def test_without_a_model_the_hub_still_says_working():
    html = views.hub(hub_data(working={"state": "ok", "reply": {"placed": 3, "ms": 100}, "failed": 0, "pending": 0,
                                       "no_extraction": True}), "ko")
    assert "v-block v-wide ok" in html and "사실 추출 꺼짐" in html



def test_now_matches_any_of_a_characters_names():
    facts = [{"subject": "Viola", "predicate": "located_in", "object": "room 301", "subject_entity": {"name": "Viola del Marcia"}},
             {"subject": "Viola del Marcia", "predicate": "has_status", "value": "tired"}]
    assert views.now_said(facts, ["Viola del Marcia", "Viola"]) == ["room 301", "tired"]



def test_ledger_lines_in_plain_words():
    assert views.plain("Aina located in: room 301", "ko") == "Aina 위치: room 301"
    assert views.plain("Aina knows: the plan", "ko") == "Aina 앎: the plan"
    assert views.plain("story 0–71: Ian met Aina.", "ko") == "t0–71: Ian met Aina."
    assert views.plain("Aina located in: room 301", "en") == "Aina located in: room 301"



def test_rings_stay_rare():
    marks = [(t, True, "major") for t in range(0, 76, 2)]  # every change major, as a lead's can be
    out = timeline.circles(marks, 0, 75)
    assert sum(1 for b in out if b["major"]) == 5


def test_chat_text_is_escaped_on_every_screen():
    """`/views/…` pages reach a browser without the plugin's sanitizer, so everything from a chat is escaped."""
    bad = '<img src=x onerror=alert(1)>"'
    pair = memory_data()["pairs"][0]
    mem = memory_data(conv={"id": CID, "name": bad, "character": bad, "turns": 13},
                      now=[{"name": bad, "entity": None, "said": [bad]}], threads=[thread(1, bad)],
                      pairs=[{**pair, "relationship": [{**pair["relationship"][0], "value": bad}],
                              "speech": [{**pair["speech"][0], "value": bad}]}],
                      story={"first_turn": 0, "last_turn": 7, "text": bad},
                      secrets=[{"id": 9, "text": bad, "holders": [bad], "open": [bad], "turn": 2}])
    pages = [views.memory(mem, "ko"),
             views.person(person_data(entity={"id": HANA, "name": bad, "names": [bad]}, now=[bad],
                                      threads=[thread(1, bad)], marks=[(2, True, bad)]), "ko"),
             views.working(working_data(reply={**working_data()["reply"],
                                               "lines": [{"kind": "fact", "text": bad, "placed": True}]}), "ko"),
             views.chats([{"id": CID, "host_chat_name": bad, "host_character_name": bad, "messages": 1,
                           "last_retrieval": None, "created_at": "2026-10-01T00:00:00+00:00", "failed": 0}], "ko"),
             views.hub(hub_data(conv={"id": CID, "name": bad, "character": bad, "turns": 3},
                                memory={"cast": 1, "open": 0, "stale": 0, "changed": 0, "now": [bad]}), "ko")]
    for html in pages:
        assert "<img" not in html and "onerror=alert(1)>" not in html
    assert "&lt;img" in pages[0] and "&lt;img" in pages[3]


def test_the_hub_rows_end_flush_and_a_thread_offers_only_its_kinds_endings():
    """Blocks grow to fill their row, whatever their number (iPhone and desktop); a goal is not offered "paid"."""
    assert ".nmos .v-blocks{display:flex;flex-wrap:wrap" in views.STYLE and "flex:1 1 140px" in views.STYLE
    assert "grid-row:span" not in views.STYLE
    from nmos_sidecar import repairs
    assert repairs.offered("goal") == ("achieved", "abandoned", "failed")
    assert repairs.offered("promise") == ("kept", "broken") and repairs.offered("debt") == ("paid", "abandoned")
    for kind in ("promise", "goal", "question", "threat", "debt", "other"):
        assert repairs.offered(kind)[0] == repairs.default_outcome(kind)
        assert set(repairs.offered(kind)) <= set(repairs.outcomes(kind))
