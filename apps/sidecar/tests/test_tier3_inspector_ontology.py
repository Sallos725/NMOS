"""PHASE-66 part 5 (Tier 3, Wave 4): the Inspector and the panel views show what `extract-v21` stores.

Part 1 (this commit): the unchanged-view differential. Every Inspector page and panel view of a chat without
extract-v21 rows is recorded as a golden file, generated ONCE at 9cc329d (before any Wave 4 change), and every later
change is compared with it byte for byte. Never regenerate it to make a change pass (`NMOS_WRITE_GOLDEN=1` is only
for recording the baseline). Synthetic names only."""

from __future__ import annotations

import json
from typing import Any

from base_rules import base_rules  # noqa: F401 -- autouse: the base's keys, without the revision marker (PHASE-66 part 5)
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


# --- part 2: every new kind and mark is shown, and the repairs it offers are accepted ------------------------------

import re  # noqa: E402
from html.parser import HTMLParser  # noqa: E402

from nmos_sidecar import inspector, timeline, views  # noqa: E402
import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from nmos_sidecar import dropped, readmodel, repairs  # noqa: E402
from test_extraction import drain  # noqa: E402
from test_tier3_read_ontology import EPI, GUISE, ONTO, PRIV, PUB, model_for  # noqa: E402

COND = {
    "t0": [a("하나", "relationship", "도윤", "동료", condition=PUB),
           a("하나", "relationship", "도윤", "연인", condition=PRIV),
           a("하나", "has_status", None, "피곤함", knowledge="public_except", hidden_from=["도윤"]),
           a("하나", "possesses", "회복 물약", None, ot="item", item_kind="fungible")],
    "t1": [a("하나", "cover_identity", None, "상인",
             condition={"scope": "public", "when": "시장", "audience": ["민수"], "as_guise": "카이"}),
           a("하나", "vital_status", None, "살아 있음")],
}


def ids_of(c, cid: str) -> dict[str, str]:
    return {e["name"]: str(e["id"]) for e in c.get(f"/v1/conversations/{cid}/entities").json()}


def screens(c, cid: str, who: str, lang: str = "ko") -> dict[str, str]:
    eid = ids_of(c, cid)[who]
    return {"chat": c.get(f"/inspector/c/{cid}", params={"lang": lang}).text,
            "embed": c.get(f"/v1/inspector/c/{cid}", params={"lang": lang}).json()["html"],
            "character": c.get(f"/inspector/c/{cid}/e/{eid}", params={"lang": lang}).text,
            "character_embed": c.get(f"/v1/inspector/c/{cid}/e/{eid}", params={"lang": lang}).json()["html"],
            "memory": c.get(f"/v1/views/c/{cid}/memory", params={"lang": lang}).json()["html"],
            "person": c.get(f"/v1/views/c/{cid}/person/{eid}", params={"lang": lang}).json()["html"],
            "map": c.get(f"/v1/views/c/{cid}/map", params={"lang": lang}).json()["html"],
            "graph": json.dumps(c.get(f"/v1/views/c/{cid}/map/graph", params={"lang": lang, "all": "true"}).json(),
                                ensure_ascii=False),
            "hub": c.get("/v1/views/hub", params={"conversation": cid, "lang": lang}).json()["html"]}


def test_conditioned_facts_show_their_slots_side_by_side_and_the_marks_in_plain_words(migrated: str):
    chat = Chat(migrated, COND, name="w4-cond")
    with chat.client() as c:
        chat.run(c)
        ko, en = screens(c, str(chat.cid), "하나"), screens(c, str(chat.cid), "하나", "en")
    # the two slots of one pair's relationship, each with its label, in the Inspector's pairs and the panel's
    for page in (ko["chat"], ko["character"], ko["embed"]):  # a chip, as a conditional address's (PHASE-64)
        assert re.search(r"회사</span> [^<]*동료", page) and re.search(r"둘만 있을 때</span> [^<]*연인", page)
    assert "동료 [회사]" in ko["memory"] and "연인 [둘만 있을 때]" in ko["memory"]
    assert "동료 [회사]" in ko["person"] and "연인 [둘만 있을 때]" in ko["person"]
    assert "[회사]" in ko["map"] and "[둘만 있을 때]" in ko["map"]  # the map's ties (the lines under its drawing)
    # before whom and under which guise, plain marks beside the slot; the slot itself as a chip and in the lane
    assert "앞에서: 민수" in ko["chat"] and "변장한 모습: 카이" in ko["chat"]
    assert "before: 민수" in en["chat"] and "as: 카이" in en["chat"]
    assert "위장 신분 [시장]" in ko["character"]  # the timeline's lane of a conditioned cover
    # a fungible item and public-except knowledge in plain words; the new predicates by name
    assert "여럿 중 하나" in ko["chat"] and "one of many alike" in en["chat"]
    assert "모두 앎 (예외 있음)" in ko["chat"] and "public, except" in en["chat"]
    assert ">생사<" in ko["chat"] and ">vital status<" in en["chat"] and ">위장 신분<" in ko["chat"]
    assert "살아 있음" in ko["hub"] or "살아 있음" in ko["memory"]  # how a character is now


def test_the_ontologys_predicates_and_a_guise_secret_are_shown(migrated: str):
    chat = Chat(migrated, ONTO, name="w4-onto")
    with chat.client() as c:
        chat.run(c)
        ko, en = screens(c, str(chat.cid), "하나"), screens(c, str(chat.cid), "하나", "en")
    for word in ("사는 곳", "위장 신분", "변장", "직위"):
        assert f">{word}<" in ko["chat"], word
    assert ">안에 있음<" in ko["chat"] and ">contained in<" in en["chat"]
    for lane in ("사는 곳", "위장 신분", "직위"):  # the character's timeline lanes
        assert f'<span class="tl-k">{lane}' in ko["character"], lane
    # a guise kept from someone is a secret, in the Inspector's secrets and the panel's
    assert 'id="s-secrets"' in ko["chat"] and "disguised as" in ko["chat"].split('id="s-secrets"', 1)[1]


def test_beliefs_and_forgettings_have_their_own_sections(migrated: str):
    chat = Chat(migrated, EPI, name="w4-epi")
    with chat.client() as c:
        chat.run(c)
        yuna, doyun = screens(c, str(chat.cid), "유나"), screens(c, str(chat.cid), "도윤", "en")
        hana = screens(c, str(chat.cid), "하나")
    page = yuna["character"]
    beliefs = page.split('id="s-beliefs"', 1)[1].split("</details>", 1)[0]
    assert "카이의 정체는 상인" in beliefs and "도윤이 배신했다" in beliefs
    assert ">끝남<" in beliefs and "knows" in beliefs  # ended, by the knows that ended it
    forgot = page.split('id="s-forgotten"', 1)[1].split("</details>", 1)[0]
    assert ">모든 기억<" in forgot and "비밀 통로의 위치" in forgot and ">아는 인물에서 뺌<" in forgot
    assert "보물은 동굴에 있다" in doyun["character"] and "Beliefs" in doyun["character"]
    assert "잊은 인물: 유나" in hana["character"]  # a fact whose known_by a forgetting reduced
    # the embedded page has the same sections
    assert 'id="s-beliefs"' in yuna["character_embed"] and 'id="s-forgotten"' in yuna["character_embed"]


REPAIR = re.compile(r'data-repair="([^"]+)"')


def offered(page: str) -> list[tuple[str, str, str | None]]:
    out = []
    for raw in REPAIR.findall(page):
        kind, item, *extra = raw.split(":", 2)
        out.append((kind, item, extra[0] if extra else None))
    return out


def test_the_repairs_offered_for_beliefs_forgettings_and_new_predicates_are_accepted(migrated: str):
    chat = Chat(migrated, EPI, name="w4-epi-repairs")
    with chat.client() as c:
        chat.run(c)
        view = chat.view()
        cid = str(chat.cid)
        page = screens(c, cid, "유나")["character"] + screens(c, cid, "도윤")["character"]
        beliefs = {str(b["id"]): b for b in view["beliefs"]}
        forgotten = {str(g["id"]): g for g in view["forgotten"]}
        acts = offered(page)
        for item in (*beliefs, *forgotten):  # retract and correct (its value), never a lock
            kinds = {(k, x) for k, i, x in acts if i == item}
            assert ("fact_retract", None) in kinds and ("fact_correct", "value") in kinds, item
            assert not any(k == "fact_lock" for k, _ in kinds), item
        # the guard in add_repair finds a belief and a forgetting: a correction is accepted, not answered 422
        b = next(i for i, x in beliefs.items() if x["value"] == "도윤이 배신했다")
        res = c.post(f"/v1/conversations/{cid}/repairs",
                     json={"kind": "fact_correct", "item": b, "new_value": "도윤이 배신했을지도 모른다"})
        assert res.status_code == 200, res.text
        g = next(i for i, x in forgotten.items() if x["who"] == "도윤")
        res = c.post(f"/v1/conversations/{cid}/repairs",
                     json={"kind": "fact_correct", "item": g, "new_value": "동굴의 위치"})
        assert res.status_code == 200, res.text
        after = chat.view()
        assert "도윤이 배신했을지도 모른다" in {x["value"] for x in after["beliefs"]}
        assert "동굴의 위치" in {x["value"] for x in after["forgotten"]}
        # a retraction offered on the corrected page goes through too
        left = next(str(x["id"]) for x in after["beliefs"] if x["value"] == "카이의 정체는 상인")
        assert ("fact_retract", left, None) in offered(screens(c, cid, "유나")["character"])
        res = c.post(f"/v1/conversations/{cid}/repairs", json={"kind": "fact_retract", "item": left})
        assert res.status_code == 200 and res.json()["applied"] == left, res.text


def test_the_buttons_on_the_new_predicates_are_accepted_per_slot(migrated: str):
    chat = Chat(migrated, COND, name="w4-cond-repairs")
    with chat.client() as c:
        chat.run(c)
        cid = str(chat.cid)
        view = chat.view()
        rels = {f["condition"]["scope"]: str(f["id"]) for f in view["facts"] if f["predicate"] == "relationship"}
        vital = next(str(f["id"]) for f in view["facts"] if f["predicate"] == "vital_status")
        acts = offered(screens(c, cid, "하나")["chat"])
        for item in (*rels.values(), vital):
            assert ("fact_retract", item, None) in acts, item
        assert ("fact_correct", vital, "value") in acts
        # one slot's relationship corrected alone: the other slot keeps its value
        res = c.post(f"/v1/conversations/{cid}/repairs",
                     json={"kind": "fact_correct", "item": rels["private"], "new_value": "약혼자"})
        assert res.status_code == 200, res.text
        now = {f["condition"]["scope"]: f["value"] for f in chat.view()["facts"] if f["predicate"] == "relationship"}
        assert now == {"public": "동료", "private": "약혼자"}
        res = c.post(f"/v1/conversations/{cid}/repairs", json={"kind": "fact_retract", "item": vital})
        assert res.status_code == 200, res.text


# --- part 3: every new string is model text, escaped wherever it lands ----------------------------------------------

EVIL_WHEN = ('<img src=x onerror=alert(1)>"\'</textarea><script>alert(2)</script>' * 2)[:60]
EVIL_GUISE = "<img src=x onerror=alert(8)>"
EVIL = {
    "t0": [a("하나", "feels_toward", "도윤", "<script>alert(3)</script>",
             condition={"scope": "situational", "when": EVIL_WHEN, "audience": ['"><svg onload=alert(4)>'],
                        "as_guise": "\u202egnp.exe</textarea>"}),
           a("하나", "relationship", "도윤", "동료\"'><b>", condition={"scope": "situational", "when": "<i>밤</i>"}),
           a("하나", "has_status", None, "<script>alert(7)</script>", condition={"scope": "situational", "when": EVIL_WHEN}),
           a("하나", "believes", None, "<script>alert(5)</script>\u202e"),
           a("루카", "disguised_as", EVIL_GUISE, None, knowledge="limited", known_by=["루카"], hidden_from=["유나"],
             guise=EVIL_GUISE),
           a("유나", "feels_toward", EVIL_GUISE, "동경"),
           a("하나", "forgot", None, "</textarea><img src=x onerror=alert(6)>")],
}


class Tags(HTMLParser):
    """Every start tag and attribute value of a page, as a browser's parser reads them."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.attrs: list[tuple[str, str]] = []
        self.scripts: list[str] = []
        self._in_script = False

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs += [(k, v or "") for k, v in attrs]
        self._in_script = tag == "script"

    def handle_endtag(self, tag):
        self._in_script = False

    def handle_data(self, data):
        if self._in_script:
            self.scripts.append(data)


def parsed(page: str) -> Tags:
    p = Tags()
    p.feed(page)
    return p


INJECTED = ("img", "textarea")  # no page draws one; <svg>, <b> and <i> are the pages' own, checked as raw text


def assert_safe(page: str, scripts_allowed: int) -> None:
    p = parsed(page)
    assert not set(p.tags) & set(INJECTED), set(p.tags) & set(INJECTED)
    assert p.tags.count("script") <= scripts_allowed
    assert not any(k.startswith("on") for k, _ in p.attrs)  # no event handler attribute
    assert not any("alert(" in s for s in p.scripts)  # the page's own script carries no model text
    for raw in ("<script>alert", "</textarea>", "<img src=x", "<svg onload", "'><b>", "<i>밤</i>"):
        assert raw not in page, raw


def test_hostile_model_text_is_escaped_on_every_screen(migrated: str):
    chat = Chat(migrated, EVIL, name="w4-evil")
    with chat.client() as c:
        chat.run(c)
        view = chat.view()
        assert view["facts"] and view["beliefs"] and view["forgotten"]
        feel = next(f for f in view["facts"] if f["predicate"] == "feels_toward")
        assert feel["condition"]["when"] == EVIL_WHEN.strip()  # the sanitizer kept the markup: the page must escape it
        for lang in ("ko", "en"):
            got = screens(c, str(chat.cid), "하나", lang)
            for name, page in got.items():
                if name == "graph":  # JSON data (names only), never HTML: nothing of the rows' text is in it
                    assert "alert(" not in page
                    continue
                assert_safe(page, scripts_allowed=2)
            # what the attributes carry round-trips as text, never as markup
            values = [v for _, v in parsed(got["character"]).attrs]
            assert any("<script>alert(3)</script>" in v for v in values)  # a timeline bar's data-v, as text
            assert "&lt;script&gt;alert(5)&lt;/script&gt;" in got["character"]  # the belief
            assert "&lt;/textarea&gt;&lt;img src=x onerror=alert(6)&gt;" in got["character"]  # the forgetting
            assert "\u202egnp.exe&lt;/textarea&gt;" in got["chat"]  # an RTL override stays text inside its element
            # the 60-character `when` full of markup is shown, escaped, as the slot's chip and the timeline lane
            assert f'<span class="chip">{inspector._v(EVIL_WHEN.strip())}</span>' in got["chat"]
            assert inspector._v(EVIL_WHEN.strip()) in got["character"] and inspector._v(EVIL_WHEN.strip()) in got["person"]
            # a conditioned status is a selectable state lane: its label and its card carry the `when` escaped
            lane = f'<span class="tl-k">{inspector._v(inspector._t(lang, "p.has_status"))} [{inspector._v(EVIL_WHEN.strip())}]'
            assert lane in got["character"]
            # the panel's sections of beliefs and forgettings are not reached through the API yet (api.py's
            # memory_data / person_data do not pass them): see the direct renderer test


def test_the_renderers_escape_hostile_rows_without_a_database():
    evil = "\"'><script>alert(1)</script></textarea>\u202e"
    cond = {"scope": "situational", "when": EVIL_WHEN, "audience": [evil], "as_guise": evil}
    ent = {"id": "e1", "name": evil}
    fact = {"id": 7, "subject": evil, "predicate": "cover_identity", "object": None, "value": evil, "turn": 1,
            "position": 1, "polarity": "positive", "knowledge": "limited", "knowledge_scope": "public_except",
            "hidden_from": [evil], "forgotten_by": [evil], "condition": cond, "subject_entity": ent,
            "source": "narration", "versions": 1, "guise": evil, "item_kind": "fungible"}
    belief = {**fact, "predicate": "believes", "status": "ended", "condition": None,
              "ended_by": {"id": 8, "turn": 2, "position": 2, "subject": evil, "predicate": "knows", "object": None,
                           "value": evil, "polarity": "positive"}}
    forgot = {**fact, "predicate": "forgot", "scope": "matter", "since": None, "who": evil, "condition": None,
              "withdrew": [{"id": 9, "turn": 1, "predicate": "knows", "text": evil, "how": "fact"}]}
    rel = {**fact, "predicate": "relationship", "object": evil, "object_entity": {"id": "e2", "name": evil},
           "condition": cond}
    for lang in ("ko", "en"):
        html = (inspector._facts_table([fact], None, lang) + inspector._beliefs_table([belief], lang)
                + inspector._forgotten_table([forgot], lang)
                + inspector._pairs_table(inspector.pairs([rel]), lang)
                + timeline.character(inspector._tl_t(lang), "e1", [fact, rel], [], {evil}, 3, None, ""))
        assert_safe(html, scripts_allowed=1)
        p = {"ids": ("e1", "e2"), "names": {"e1": evil, "e2": evil}, "relationship": [rel], "role": [], "feels": [],
             "speech": [], "position": 1}
        assert_safe("".join(views._pair_bits({**p, "role": [rel]}, lang)), 0)
        assert evil in inspector.fact_line_text(rel)  # raw text: every caller escapes it (`_v`)
        assert_safe(inspector._v(inspector.fact_line_text(rel)), 0)
        assert inspector._v(evil) in html and inspector._v(EVIL_WHEN) in html


def test_the_chat_page_and_the_panels_sections_render_beliefs_and_forgettings_when_given(migrated: str):
    """`inspector.detail(beliefs=, forgotten=)` and the panel's `beliefs` / `forgotten` keys: what the call sites in
    api.py would pass (they do not yet, the one api.py line this part may change being the guard)."""
    chat = Chat(migrated, EPI, name="w4-epi-direct")
    with chat.client() as c:
        chat.run(c)
        view = chat.view()
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        conv = readmodel.conversation(conn, chat.cid)
    for lang in ("ko", "en"):
        page = inspector.detail(conv, [], [], [], [], view["facts"], None, lang=lang, embed=True,
                                beliefs=view["beliefs"], forgotten=view["forgotten"])
        assert 'id="s-beliefs"' in page and 'id="s-forgotten"' in page and "도윤이 배신했다" in page
        bare = inspector.detail(conv, [], [], [], [], view["facts"], None, lang=lang, embed=True)
        assert 's-beliefs' not in bare and 's-forgotten' not in bare  # absent: the page as before
        yuna = next(e for e in view["entities"] if e["name"] == "유나")
        base = {"conv": {"id": str(chat.cid), "name": "w4", "turns": 3}, "now": [], "threads": [], "stale": 0,
                "pairs": [], "secrets": [], "changes": [], "facts": 0, "attention": 0, "entities": {}}
        memory = views.memory({**base, "beliefs": view["beliefs"], "forgotten": view["forgotten"]}, lang)
        assert 'id="s-beliefs"' in memory and 'id="s-forgotten"' in memory and 'href="#s-beliefs"' in memory
        assert "카이의 정체는 상인" in memory and 'data-repair="fact_retract:' in memory
        assert "s-beliefs" not in views.memory(base, lang)
        person = {**base, "entity": {"id": str(yuna["id"]), "name": "유나", "names": ["유나"], "persona": False,
                                     "excluded": None, "pinned": None},
                  "knows": [], "kept": [], "marks": [], "first": 0, "last": 3,
                  "beliefs": [b for b in view["beliefs"] if b["subject"] == "유나"],
                  "forgotten": [g for g in view["forgotten"] if g["who"] == "유나"]}
        sheet = views.person(person, lang)
        assert 'id="s-beliefs"' in sheet and 'id="s-forgotten"' in sheet
        assert "s-beliefs" not in views.person({k: v for k, v in person.items() if k not in ("beliefs", "forgotten")},
                                               lang)


def test_the_panels_sections_escape_hostile_beliefs_and_forgettings():
    evil = "\"'><script>alert(1)</script></textarea>‮"
    belief = {"id": 1, "subject": evil, "predicate": "believes", "value": evil, "turn": 2, "status": "ended",
              "ended_by": {"id": 2, "turn": 3, "subject": evil, "predicate": "knows", "object": None, "value": evil}}
    forgot = {"id": 3, "subject": evil, "who": evil, "predicate": "forgot", "value": evil, "scope": "matter",
              "since": None, "turn": 4, "withdrew": [{"id": 4, "turn": 1, "predicate": "knows", "text": evil,
                                                     "how": "fact"}]}
    for lang in ("ko", "en"):
        html = "".join(views.belief_lines([belief], lang) + views.forgot_lines([forgot], lang))
        assert_safe(html, 0)
        assert inspector._v(evil) in html


def test_every_button_on_the_ontologys_pages_plans(migrated: str):
    """Each repair the chat page and each character page offer for an extract-v21 row is one `repairs.plan` accepts
    (it changes nothing): retract, and every correction field, the object ones included."""
    chat = Chat(migrated, ONTO, name="w4-onto-plan")
    with chat.client() as c:
        chat.run(c)
        view = chat.view()
        cid = str(chat.cid)
        pages = [c.get(f"/inspector/c/{cid}").text] + [
            c.get(f"/inspector/c/{cid}/e/{eid}").text for eid in ids_of(c, cid).values()]
    v21 = {str(f["id"]): f for f in view["facts"] if f["predicate"] in (
        "vital_status", "lives_in", "cover_identity", "disguised_as", "holds_rank", "contained_in")}
    seen = set()
    for kind, item, extra in {x for p in pages for x in offered(p)}:
        if item not in v21 or kind not in ("fact_retract", "fact_correct"):
            continue
        seen.add((v21[item]["predicate"], kind, extra))
        f = v21[item]
        if kind == "fact_retract":
            repairs.plan(kind, item, view, 3)
        elif extra == "object":
            repairs.plan(kind, item, view, 3, new_object=f"{f['object']} 2")
        else:
            repairs.plan(kind, item, view, 3, new_value=f"{f.get('value') or ''} 2")
    assert {p for p, _, _ in seen} == {"vital_status", "lives_in", "cover_identity", "disguised_as", "holds_rank",
                                       "contained_in"}
    assert ("holds_rank", "fact_correct", "object") in seen and ("holds_rank", "fact_correct", "value") in seen
    # every row's object and value are on the chat page, a rank beside its group
    page = pages[0]
    for f in v21.values():
        for x in (f.get("object"), f.get("value")):
            if x:
                assert inspector._v(x) in page, (f["predicate"], x)
    assert "<span>: 단장</span>" in page
    assert '<span class="tl-k">직위 → 기사단' in "".join(pages[1:])  # one lane per group


def test_a_belief_a_re_extraction_drops_is_offered_for_restore_and_restored(migrated: str):
    chat = Chat(migrated, EPI, name="w4-epi-drop")
    with chat.client() as c:
        chat.run(c)
        chat.view()  # its head and generation key, as W3's restore test reads them
        c.post(f"/v1/conversations/{chat.cid}/rebuild")
        drain(migrated, model_for(EPI, frozenset({("유나", "도윤이 배신했다")})))
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            lost = dropped.find(conn, chat.head, chat.key, chat.view())
        listed = [d for d in lost if d["predicate"] == "believes"]
        assert [d["value"] for d in listed] == ["도윤이 배신했다"]
        # the attention queue offers its restore, and the API takes it
        assert f'data-repair="fact_restore:{listed[0]["id"]}"' in c.get(f"/inspector/c/{chat.cid}").text
        res = c.post(f"/v1/conversations/{chat.cid}/repairs", json={"kind": "fact_restore", "item": str(listed[0]["id"])})
        assert res.status_code == 200, res.text
        assert "도윤이 배신했다" in {b["value"] for b in chat.view()["beliefs"]}


def test_beliefs_and_forgettings_reach_the_chat_page_and_the_panels_screens(migrated: str):
    chat = Chat(migrated, EPI, name="w4-epi-wired")
    with chat.client() as c:
        chat.run(c)
        for lang in ("ko", "en"):
            got = screens(c, str(chat.cid), "유나", lang)
            for name in ("chat", "embed", "memory", "person"):
                assert 'id="s-beliefs"' in got[name] and 'id="s-forgotten"' in got[name], (name, lang)
                assert "카이의 정체는 상인" in got[name], (name, lang)
            # the person sheet holds only this person's: 도윤's belief is on his own
            assert "보물은 동굴에 있다" not in got["person"].split('id="s-beliefs"', 1)[1].split('id="s-forgotten"')[0]
            assert 'data-repair="fact_correct:' in got["memory"] and 'data-repair="fact_lock:' not in got["memory"]


def test_a_fact_held_toward_a_guise_is_grouped_under_its_disguise(migrated: str):
    chat = Chat(migrated, GUISE, name="w4-guise")
    with chat.client() as c:
        chat.run(c)
        view = chat.view()
        luka, yuna = screens(c, str(chat.cid), "루카"), screens(c, str(chat.cid), "유나")
    disguise = view["disguises"][0]
    held = {str(f["id"]): f for f in view["facts"] if str(f["id"]) in {str(i) for i in disguise["held"]}}
    assert held  # 유나's adoration and address toward the knight
    # the wearer's page: a section of their disguises, with what is held toward each
    section = luka["character"].split('id="s-disguises"', 1)[1].split("</details>", 1)[0]
    # 유나 never found out here: her latest feeling toward the knight (배신감 replaced 동경 in the guise's slot) stays
    # the guise's, named toward the guise as written, never toward its wearer
    assert ">카이<" in section and "유나 feels toward 카이: 배신감" in section and "feels toward 루카" not in section
    # the facts list: each held fact right under its disguise row, marked as toward the guise (never as 루카's own)
    rows = luka["chat"].split('id="s-facts"', 1)[1].split("</table>", 1)[0].split("<tr")
    at = next(i for i, r in enumerate(rows) if ">변장<" in r)
    assert all("↳ " in rows[at + 1 + k] for k in range(len(held))), rows[at:at + 1 + len(held)]
    assert "변장한 모습 카이(루카)를 향해" in rows[at + 1]
    # plain marks elsewhere: the pairs, the panel
    assert "변장한 모습 카이(루카)를 향해" in yuna["memory"] and "변장한 모습 카이(루카)를 향해" in yuna["person"]
    assert "유나→카이" in yuna["memory"]  # the panel names the guise too
    assert "변장한 모습 카이(루카)를 향해" in yuna["chat"].split('id="s-pairs"', 1)[1]


def test_a_carried_belief_line_is_no_thread_in_the_panel():
    assert not views._is_thread({"line": "belief", "by": "유나", "text": "카이의 정체는 상인"})
    assert not views._is_thread({"kind": "belief", "text": "카이의 정체는 상인"})
    assert views._is_thread({"line": "thread", "by": "유나", "text": "약속"})
