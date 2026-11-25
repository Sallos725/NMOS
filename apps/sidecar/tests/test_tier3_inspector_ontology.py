"""PHASE-66 part 5 (Tier 3, Wave 4): the Inspector and the panel views show what `extract-v21` stores.

Part 1 (this commit): the unchanged-view differential. Every Inspector page and panel view of a chat without
extract-v21 rows is recorded as a golden file, generated ONCE at 9cc329d (before any Wave 4 change), and every later
change is compared with it byte for byte. Never regenerate it to make a change pass (`NMOS_WRITE_GOLDEN=1` is only
for recording the baseline). Synthetic names only."""

from __future__ import annotations

import json
from typing import Any

from conftest import make_client
from simchat import SimChat
from test_phase60_views_unchanged import STORY, check_golden, normalize
from test_sidecar_integration import sync
from test_tier3_read_ontology import Chat, a

V20 = {
    "t0": [a("하나", "addresses", "도윤", "존댓말, '과장님'", address_condition={"scope": "public", "when": "회사"})],
    "t1": [a("하나", "addresses", "도윤", "반말, '오빠'", address_condition={"scope": "private", "when": "둘만 있을 때"},
             knowledge="limited", known_by=["하나", "도윤"], hidden_from=["민수"])],
    "t2": [a("하나", "relationship", "도윤", "동료"), a("도윤", "has_status", None, "바쁨")],
}


def pages(c, cid: str) -> dict[str, Any]:
    """Every page and panel view of one chat, ko and en, embedded and not, whole JSON bodies."""
    ents = c.get(f"/v1/conversations/{cid}/entities").json()
    people = sorted((e for e in ents if e.get("type") == "character"), key=lambda e: e["name"])
    out: dict[str, Any] = {}

    def get(name: str, path: str, **params: Any) -> None:
        res = c.get(path, params=params)
        assert res.status_code == 200, (name, res.text)
        out[name] = res.text if "text/html" in res.headers.get("content-type", "") else res.json()

    for lang in ("ko", "en"):
        get(f"hub.{lang}", "/v1/views/hub", conversation=cid, lang=lang)
        get(f"hub-map.{lang}", "/v1/views/hub", conversation=cid, lang=lang, map="true")
        get(f"working.{lang}", f"/v1/views/c/{cid}/working", lang=lang)
        get(f"memory.{lang}", f"/v1/views/c/{cid}/memory", lang=lang)
        get(f"memory-map.{lang}", f"/v1/views/c/{cid}/memory", lang=lang, map="true")
        get(f"map.{lang}", f"/v1/views/c/{cid}/map", lang=lang)
        get(f"graph.{lang}", f"/v1/views/c/{cid}/map/graph", lang=lang)
        get(f"graph-all.{lang}", f"/v1/views/c/{cid}/map/graph", lang=lang, all="true")
        get(f"inspector.{lang}", f"/inspector/c/{cid}", lang=lang)
        get(f"inspector-embed.{lang}", f"/v1/inspector/c/{cid}", lang=lang)
        get(f"inspector-lazy.{lang}", f"/v1/inspector/c/{cid}", lang=lang, timeline="lazy", status="lazy")
        get(f"inspector-cast.{lang}", f"/v1/inspector/c/{cid}", lang=lang, part="timeline")
        get(f"inspector-status.{lang}", f"/v1/inspector/c/{cid}", lang=lang, part="status")
        for i, e in enumerate(people):
            get(f"person{i}.{lang}", f"/v1/views/c/{cid}/person/{e['id']}", lang=lang)
            get(f"graph-focus{i}.{lang}", f"/v1/views/c/{cid}/map/graph", lang=lang, focus=e["id"])
            get(f"character{i}.{lang}", f"/inspector/c/{cid}/e/{e['id']}", lang=lang)
            get(f"character-embed{i}.{lang}", f"/v1/inspector/c/{cid}/e/{e['id']}", lang=lang)
            get(f"character-part{i}.{lang}", f"/v1/inspector/c/{cid}/e/{e['id']}", lang=lang, part="timeline")
        for turn in (0, 1, 2):
            get(f"turn{turn}.{lang}", f"/inspector/c/{cid}/t/{turn}", lang=lang)
    out["_entities"] = {str(e["id"]): f"<entity:{e['type']}:{e['name']}>" for e in ents}
    return out


def recorded(out: dict[str, Any]) -> str:
    """One golden text per chat: each page normalized on its own. An entity's id becomes its type and name (an edge's
    ends are ordered by id, so numbering ids by first appearance would differ per run); every other uuid is numbered
    by first appearance in the page (`normalize`)."""
    ents = out.pop("_entities")

    def text(body: Any) -> str:
        raw = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, sort_keys=True)
        for eid, name in ents.items():
            raw = raw.replace(eid, name)
        if isinstance(body, dict) and isinstance(body.get("edges"), list):
            # a tie has no direction: the graph orders its two ends by entity id, which differs per run
            graph = json.loads(raw)
            for e in graph["edges"]:
                if e.get("kind") == "tie":
                    e["a"], e["b"] = sorted((e["a"], e["b"]))
            graph["edges"].sort(key=lambda e: json.dumps(e, sort_keys=True))
            raw = json.dumps(graph, ensure_ascii=False, sort_keys=True)
        return normalize(raw)
    return "\n".join(f"=== {name}\n" + text(body) for name, body in sorted(out.items())) + "\n"


def test_every_view_of_a_stub_chat_without_v21_rows_is_unchanged(migrated: str):
    from memeval import stub_extractor
    from test_extraction import drain
    from test_generations import LLM

    chat = SimChat("tier3-w4-views-unchanged")
    for said in STORY:
        chat.user(said)
        chat.reply("Noted.")
    chat.user("next")
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        drain(migrated, stub_extractor)
        cid = c.get("/v1/views/hub", params={"chat": chat.id}).json()["conversation"]
        check_golden("../tier3-w4/stub-chat.txt", recorded(pages(c, cid)))


def test_every_view_of_a_v20_chat_with_conditional_addresses_is_unchanged(migrated: str):
    v20 = Chat(migrated, V20, compiler="extract-v20", name="tier3-w4-v20")
    with v20.client() as c:
        v20.run(c)
        check_golden("../tier3-w4/v20-chat.txt", recorded(pages(c, str(v20.cid))))
