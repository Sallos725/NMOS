"""PHASE-69: Memory Explorer, Focused Attention & Repairs, Dashboard Home, and Upgraded Person Sheet."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from conftest import make_client
from nmos_sidecar import inspector, views
from simchat import SimChat
from test_sidecar_integration import sync

CID = "0190f3a4-1b2c-7d3e-8f40-123456789abc"
HANA = "0190f3a4-1b2c-7d3e-8f40-00000000000a"
KAITO = "0190f3a4-1b2c-7d3e-8f40-00000000000b"
MILL = "0190f3a4-1b2c-7d3e-8f40-00000000000c"


def _explore_fixture(**over):
    story_fact = {
        "id": 101, "subject": "Hana", "predicate": "located_in", "object": "old mill", "value": None,
        "turn": 9, "position": 9, "polarity": "positive", "because": "hiding from the guard",
        "subject_entity": {"id": HANA, "name": "Hana"}, "object_entity": {"id": MILL, "name": "old mill"},
    }
    canon_fact = {
        "id": 102, "subject": "Hana", "predicate": "identity", "object": None, "value": "lighthouse keeper",
        "turn": 0, "position": 0, "polarity": "positive", "canon": "card:description",
        "subject_entity": {"id": HANA, "name": "Hana"},
    }
    addr_fact = {
        "id": 103, "subject": "Kaito", "predicate": "addresses", "object": "Hana", "value": "선배",
        "turn": 4, "position": 4, "polarity": "positive",
        "address_condition": {"scope": "public"},
        "subject_entity": {"id": KAITO, "name": "Kaito"}, "object_entity": {"id": HANA, "name": "Hana"},
    }
    rel_fact = {
        "id": 104, "subject": "Hana", "predicate": "relationship", "object": "Kaito", "value": "childhood friend",
        "turn": 3, "position": 3, "polarity": "positive",
        "subject_entity": {"id": HANA, "name": "Hana"}, "object_entity": {"id": KAITO, "name": "Kaito"},
    }
    pair = {
        "ids": (HANA, KAITO), "names": {HANA: "Hana", KAITO: "Kaito"},
        "relationship": [rel_fact], "role": [], "feels": [], "speech": [addr_fact], "position": 4,
    }
    data = {
        "conv": {"id": CID, "name": "Harbor", "character": "Hana", "turns": 14},
        "facts": [story_fact, canon_fact, addr_fact],
        "pairs": [pair],
        "threads": [
            {"id": 11, "kind": "promise", "by": "Hana", "to": "Kaito", "text": "return the silver key",
             "turn": 6, "status": "open", "horizon": "arc", "restated": []},
            {"id": 12, "kind": "goal", "by": "Kaito", "to": None, "text": "fix the lantern",
             "turn": 2, "status": "achieved", "closed_by": {"turn": 8, "evidence": "fixed"}, "restated": []},
        ],
        "secrets": [
            {"id": 21, "text": "Hana identity: smuggler", "holders": ["Hana"], "kept_from": ["Kaito"],
             "open": ["Kaito"], "ended": {}, "turn": 2},
        ],
        "beliefs": [
            {"id": 31, "subject": "Kaito", "subject_entity": {"id": KAITO, "name": "Kaito"},
             "value": "the lighthouse is empty", "turn": 7, "status": "held"},
        ],
        "forgotten": [
            {"id": 32, "who": "Hana", "subject": "Hana", "value": "the harbor password",
             "turn": 10, "withdrew": [{"text": "Hana knows: password"}]},
        ],
        "disguises": [
            {"id": 33, "subject": "Hana", "subject_entity": {"id": HANA, "name": "Hana"},
             "guise": "traveling merchant", "current": True, "kept_from": ["Kaito"], "revealed": [], "turn": 11},
        ],
        "told": [
            {"id": 41, "subject": "Hana", "object": "Kaito", "value": "the bridge collapsed",
             "participants": ["bridge"], "turn": 12},
        ],
        "items": [
            {"item": "silver key", "history": [
                {"subject": "Hana", "predicate": "possesses", "object": "silver key", "turn": 1, "outcome": "superseded"},
                {"subject": "Kaito", "predicate": "possesses", "object": "silver key", "turn": 8, "outcome": "current"},
            ]},
        ],
        "entities": [
            {"id": HANA, "type": "character", "name": "Hana", "names": ["Hana", "Hanachan"], "mentions": 15, "persona": False},
            {"id": KAITO, "type": "character", "name": "Kaito", "names": ["Kaito"], "mentions": 9, "persona": True},
            {"id": MILL, "type": "place", "name": "old mill", "names": ["old mill"], "mentions": 3, "persona": False},
        ],
        "entities_map": {"hana": HANA, "kaito": KAITO},
        "pins": [{"entity_id": HANA, "repair": "rep-pin-1"}],
        "excluded": {},
        "canon_rows": [
            {"key": "card:description", "content": "Hana tends the harbor lighthouse.", "metadata": {"scope": "card"}},
            {"key": "lore:old_mill", "content": "An abandoned mill east of the pier.", "metadata": {"keys": ["mill"]}},
        ],
        "canon_history": {"card:description": {"versions": 2}, "lore:old_mill": {"versions": 1}},
        "canon_held": {"card:description": {"requests": 5}},
        "canon_read": {"card:description": {"job": "done", "calls": 1}},
    }
    data.update(over)
    return data


def _attention_fixture(**over):
    stale_th = {"id": 55, "kind": "promise", "by": "Hana", "to": "Kaito", "text": "meet at noon",
                "turn": 1, "status": "open", "horizon": "scene", "restated": []}
    canon_against = {"id": 201, "subject": "Hana", "predicate": "located_in", "object": "harbor",
                     "value": None, "turn": 0, "canon": "card:description"}
    conflicts = [{"kind": "canon", "fact": 202, "text": "Hana located in old mill", "turn": 9, "against": canon_against}]
    repairs = [
        {"id": "rep-1", "kind": "fact_correct", "target": {"turn": 5, "text": "Hana has status: tired"},
         "value": {"value": "rested"}, "created_at": datetime(2026, 11, 26, 1, 0, tzinfo=timezone.utc),
         "applied": True, "removed_at": None, "batch_id": "batch-1"},
        {"id": "rep-2", "kind": "thread_close", "target": {"turn": 2, "by": "Kaito", "text": "buy oil"},
         "value": {"outcome": "achieved"}, "created_at": datetime(2026, 11, 26, 0, 30, tzinfo=timezone.utc),
         "applied": False, "removed_at": datetime(2026, 11, 26, 0, 45, tzinfo=timezone.utc)},
    ]
    queue = inspector._attention({"threads": [stale_th], "conflicts": conflicts}, repairs, 30, "ko")
    data = {
        "conv": {"id": CID, "name": "Harbor", "character": "Hana", "turns": 30},
        "queue": queue,
        "conflicts": conflicts,
        "repairs": repairs,
        "owned_facts": {},
    }
    data.update(over)
    return data


def test_views_style_stays_strictly_scoped_under_nmos():
    flat = re.sub(r"\}\s*\}", "}", re.sub(r"@media[^{]*\{", "", views.STYLE))
    rules = re.findall(r"([^{}]+)\{[^{}]*\}", flat)
    assert rules
    for selectors in rules:
        for sel in selectors.split(","):
            assert sel.strip().startswith(".nmos"), sel
    assert "@import" not in views.STYLE and "url(" not in views.STYLE


def test_phase71_views_style_passive_tags_and_edit_disclosure():
    assert ".nmos .v-tag{" in views.STYLE and "cursor:default" in views.STYLE
    assert ".nmos .v .chip{" in views.STYLE
    assert '.nmos .v-edit>summary::before{content:"\\25B8"' in views.STYLE
    assert '.nmos .v-edit[open]>summary::before{content:"\\25BE"' in views.STYLE
    assert "\x15B8" not in views.STYLE and "\x15BE" not in views.STYLE


def test_hub_compact_deduplicates_nav_tiles_and_keeps_legacy_default_intact():
    data = {
        "conv": {"id": CID, "name": "Harbor", "character": "Hana", "turns": 14},
        "working": {
            "state": "ok", "failed": 0, "pending": 0,
            "reply": {
                "placed": 6, "ms": 420, "tokens": 1240,
                "lines": [
                    {"kind": "fact", "text": "Hana located in: old mill", "echoed": True},
                    {"kind": "thread", "text": "Hana → Kaito promised: return the silver key", "echoed": False},
                ],
            },
        },
        "work": {"extraction": {"done": 14, "due": 14}, "embeddings": {"done": 28, "due": 28}},
        "memory": {
            "cast": 2, "open": 3, "stale": 0, "changed": 1,
            "now": ["Hana · old mill"],
            "threads": [{"kind": "promise", "text": "return the silver key"}],
        },
        "attention": 2, "usage": {"calls": 18}, "chats": 5,
    }
    legacy = views.hub(data, "ko")
    assert 'data-act="notes"' in legacy and 'data-act="settings"' in legacy and 'data-act="backup"' in legacy
    assert f'/inspector/c/{CID}#s-attention' in legacy

    compact = views.hub(data, "ko", compact=True)
    assert "<table" not in compact
    assert 'data-act="notes"' not in compact
    assert 'data-act="settings"' not in compact
    assert 'data-act="backup"' not in compact
    assert 'href="/views/chats"' not in compact
    assert f'href="/views/c/{CID}/attention"' in compact
    assert f'href="/views/c/{CID}/explore"' in compact
    assert f'href="/views/c/{CID}/memory"' in compact
    assert f'href="/views/c/{CID}/working"' in compact
    assert "Hana 위치: old mill" in compact and "1,240" in compact
    assert "v-prog" in compact

    no_chat = views.hub({"conv": None, "working": {"state": "idle"}, "chats": 3}, "ko", compact=True)
    assert 'data-act="settings"' not in no_chat and 'data-act="backup"' not in no_chat
    assert 'href="/views/chats"' in no_chat


def test_explore_renders_all_seven_categories_as_cards_with_metadata_and_no_tables():
    with inspector.turn_links(CID, None, "ko"):
        html = views.explore(_explore_fixture(), "ko")
    assert "<table" not in html
    assert 'class="v-exp-toolbar-slot"' in html
    for cat in ("facts", "pairs", "threads", "epistemic", "items", "entities", "canon"):
        assert f'id="s-{cat}" data-cat="{cat}"' in html
        assert f'class="v-card v-exp-card' in html and f'data-cat="{cat}"' in html
    assert 'data-canon="1"' in html  # canon_fact
    assert 'data-who="Hana|old mill"' in html
    assert f'href="/inspector/c/{CID}/t/9"' in html
    assert 'class="v-edit"' in html
    assert 'data-repair="fact_retract:101"' in html
    assert 'data-repair="thread_close:11:' in html
    assert 'data-repair="told_retract:41"' in html
    assert "공적인 자리" in html
    assert "traveling merchant" in html
    assert "lore:old_mill" in html


def test_attention_renders_focused_three_sections_with_bulk_markers_and_empty_state():
    with inspector.turn_links(CID, None, "ko"):
        html = views.attention(_attention_fixture(), "ko")
    assert "<table" not in html
    ids = re.findall(r'class="v-sec" id="(s-[a-z]+)"', html)
    assert ids == ["s-attention", "s-conflicts", "s-repairs"]
    assert "s-commits" not in html and "s-members" not in html and "s-retrievals" not in html
    assert 'class="v-card-check"' in html and 'data-bulk="' in html
    assert 'data-repair="thread_close:55:' in html
    assert 'data-repair="fact_lock:201"' in html
    assert 'data-repair="undo_batch:batch-1"' in html
    assert 'data-repair="undo:rep-1"' in html

    empty = views.attention({"conv": {"id": CID, "name": "Harbor", "turns": 5},
                             "queue": [], "conflicts": [], "repairs": [], "owned_facts": {}}, "ko")
    assert 'class="v-empty"' in empty and "확인할 항목이 없습니다" in empty


def test_rich_person_sheet_adds_editable_facts_held_items_disguises_and_switcher():
    d = {
        "conv": {"id": CID, "name": "Harbor", "character": "Hana", "turns": 14},
        "entity": {"id": HANA, "name": "Hana", "names": ["Hana", "Hanachan"], "persona": False,
                   "excluded": None, "pinned": "rep-pin-1"},
        "now": ["old mill"],
        "pairs": _explore_fixture()["pairs"],
        "threads": _explore_fixture()["threads"][:1],
        "knows": _explore_fixture()["secrets"],
        "kept": [],
        "marks": [(9, True, "Hana meets Kaito", "event")],
        "first": 0, "last": 14,
        "entities": {"hana": HANA, "kaito": KAITO},
        "facts": [_explore_fixture()["facts"][0]],
        "held": [{"id": 301, "subject": "Hana", "predicate": "possesses", "object": "brass compass",
                  "turn": 5, "polarity": "positive", "subject_entity": {"id": HANA, "name": "Hana"}}],
        "disguises": _explore_fixture()["disguises"],
        "characters": [{"id": HANA, "name": "Hana"}, {"id": KAITO, "name": "Kaito"}],
    }
    with inspector.turn_links(CID, None, "ko"):
        rich = views.person(d, "ko", rich=True)
    assert "<table" not in rich
    assert 'id="s-facts"' in rich and 'data-repair="fact_retract:101"' in rich
    assert 'id="s-held"' in rich and "brass compass" in rich
    assert 'id="s-disguises"' in rich and "traveling merchant" in rich
    assert 'class="who"' in rich and f'href="/views/c/{CID}/person/{KAITO}"' in rich
    assert "항상 고정됨" in rich
    assert f'href="/views/c/{CID}/explore"' in rich
    assert f'href="/inspector/c/{CID}/e/{HANA}"' in rich


def test_phase69_views_escape_xss_payloads_everywhere():
    bad = '<img src=x onerror=alert(1)>" onmouseover="x()'
    fx = _explore_fixture()
    fx["conv"]["name"] = bad
    fx["facts"][0]["value"] = bad
    fx["facts"][0]["because"] = bad
    fx["threads"][0]["text"] = bad
    fx["secrets"][0]["text"] = bad
    fx["canon_rows"][0]["content"] = bad
    fx["entities"][0]["name"] = bad

    at = _attention_fixture()
    at["conflicts"][0]["text"] = bad
    at["repairs"][0]["value"]["value"] = bad

    pages = [
        views.explore(fx, "ko"),
        views.attention(at, "ko"),
        views.hub({
            "conv": {"id": CID, "name": bad, "character": bad, "turns": 3},
            "working": {"state": "ok", "failed": 0, "pending": 0,
                        "reply": {"placed": 1, "ms": 100, "tokens": 50,
                                  "lines": [{"kind": "fact", "text": bad, "echoed": False}]}},
            "memory": {"cast": 1, "open": 1, "stale": 0, "changed": 0, "now": [bad],
                       "threads": [{"kind": "goal", "text": bad}]},
            "attention": 1, "usage": {"calls": 1}, "chats": 1,
        }, "ko", compact=True),
    ]
    for html in pages:
        assert "<img" not in html
        assert "onerror=alert(1)>" not in html
        assert '" onmouseover=' not in html
        assert "&lt;img" in html


def test_phase69_endpoints_integration(migrated):
    from memeval import stub_extractor
    from test_extraction import drain
    from test_generations import LLM

    chat = SimChat("phase69-views")
    chat.user("Hana is in the library.")
    chat.reply("Noted.")
    chat.user('Hana says to Kaito: "I promise to meet you at the lighthouse."')
    chat.reply("Noted.")
    chat.user("Hana moved to the harbor.")
    chat.reply("Noted.")
    chat.user("next")

    with make_client(migrated, **LLM) as c:
        sync(c, chat, character_name="Hana", chat_name="Harbor")
        drain(migrated, stub_extractor)
        hub_res = c.get("/v1/views/hub", params={"chat": chat.id, "compact": "1", "lang": "ko"})
        assert hub_res.status_code == 200, hub_res.text
        hub_body = hub_res.json()
        cid = hub_body["conversation"]
        assert cid
        assert 'v-hub-compact' in hub_body["html"]
        assert 'data-act="settings"' not in hub_body["html"]
        assert f'/views/c/{cid}/explore' in hub_body["html"]

        exp_api = c.get(f"/v1/views/c/{cid}/explore", params={"lang": "ko"})
        assert exp_api.status_code == 200, exp_api.text
        exp_html = exp_api.json()["html"]
        assert 'id="s-facts"' in exp_html and "<table" not in exp_html and "harbor" in exp_html
        assert c.get(f"/views/c/{cid}/explore").status_code == 200

        attn_api = c.get(f"/v1/views/c/{cid}/attention", params={"lang": "ko"})
        assert attn_api.status_code == 200, attn_api.text
        attn_html = attn_api.json()["html"]
        assert 'id="s-attention"' in attn_html and 'id="s-repairs"' in attn_html and "<table" not in attn_html
        assert c.get(f"/views/c/{cid}/attention").status_code == 200

        mem_rich = c.get(f"/v1/views/c/{cid}/memory", params={"rich": "1", "lang": "ko"})
        assert mem_rich.status_code == 200 and f'/views/c/{cid}/explore' in mem_rich.json()["html"]

        hana = next(e for e in c.get(f"/v1/conversations/{cid}/entities").json() if e["name"] == "Hana")
        person_rich = c.get(f"/v1/views/c/{cid}/person/{hana['id']}", params={"rich": "1", "lang": "ko"})
        assert person_rich.status_code == 200
        p_html = person_rich.json()["html"]
        assert 'id="s-facts"' in p_html and 'class="v-edit"' in p_html and f'/views/c/{cid}/explore' in p_html

        missing = "00000000-0000-0000-0000-000000000000"
        assert c.get(f"/v1/views/c/{missing}/explore").status_code == 404
        assert c.get(f"/v1/views/c/{missing}/attention").status_code == 404
