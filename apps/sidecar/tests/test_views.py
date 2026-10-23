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
    assert "/inspector/c/0190f3a4-1b2c-7d3e-8f40-123456789abc" in html
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
