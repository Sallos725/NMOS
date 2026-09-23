"""Phase 5, ADR 0012: read-time entity resolution (pure rules, then through the API)."""

from __future__ import annotations

from uuid import UUID

from conftest import make_client
from nmos_sidecar.entities import RESOLVER_VERSION, resolve
from simchat import SimChat
from test_extraction import drain, facts
from test_generations import LLM
from test_sidecar_integration import sync

CONV = UUID("01900000-0000-7000-8000-000000000001")


def fact(pos, subject, predicate, obj=None, value=None, stype="character", otype=None, **kw):
    return {"position": pos, "turn": pos, "subject": subject, "subject_type": stype, "predicate": predicate,
            "object": obj, "object_type": otype, "value": value, "modality": "actual", "source": "narration", **kw}


def alias(pos, name, other, stype="character"):
    return fact(pos, name, "also_called", value=other, stype=stype)


def test_same_name_and_type_is_one_entity_different_types_are_two():
    r = resolve(CONV, [fact(1, "하나", "possesses", "지도", otype="item"),
                       fact(2, "지도", "located_in", "지도", stype="item", otype="place")])
    item, place = r.key("item", "지도"), r.key("place", "지도")
    assert item != place and r.key("item", " 지도 ") == item
    assert r.key("character", "하나") == r.key("character", "하나")


def test_persona_names_are_one_entity():
    r = resolve(CONV, [fact(1, "{{user}}", "has_status", value="tired"), fact(2, "유저", "has_status", value="ok")])
    assert r.key("character", "{{user}}") == r.key("character", "유저") == r.key("character", "user")


def test_stated_alias_links_names_and_first_mention_names_the_entity():
    r = resolve(CONV, [fact(1, "하나", "located_in", "역", otype="place"), alias(3, "Hana", "하나"),
                       fact(4, "Hana", "located_in", "집", otype="place")])
    assert r.key("character", "Hana") == r.key("character", "하나")
    entity = r.entity("character", "Hana")
    assert entity["name"] == "하나" and set(entity["names"]) == {"하나", "Hana"}
    assert entity["aliases"] == [{"name": "Hana", "other": "하나", "turn": 3}]


def test_alias_from_a_claim_or_a_dream_links_nothing():
    rows = [fact(1, "하나", "has_status", value="ok"), {**alias(2, "Hana", "하나"), "source": "character_claim"},
            {**alias(3, "Hanako", "하나"), "modality": "dreamed"}]
    r = resolve(CONV, rows)
    assert len({r.key("character", n) for n in ("하나", "Hana", "Hanako")}) == 3


def test_a_name_shared_by_two_entities_is_ambiguous():
    rows = [fact(1, "하나 선배", "identity", value="3학년"), fact(2, "하나 후배", "identity", value="1학년"),
            alias(3, "하나 선배", "하나"), alias(4, "하나 후배", "하나"), fact(5, "하나", "located_in", "역", otype="place")]
    r = resolve(CONV, rows)
    assert r.key("character", "하나 선배") != r.key("character", "하나 후배")
    assert r.status("character", "하나") == "ambiguous"
    assert set(r.candidates("character", "하나")) == {"하나 선배", "하나 후배"}
    # An ambiguous mention keeps its text key: it neither merges nor attaches to either candidate.
    assert r.key("character", "하나") not in {r.key("character", "하나 선배"), r.key("character", "하나 후배")}


def test_ids_are_stable_and_versioned():
    rows = [fact(1, "하나", "has_status", value="ok")]
    a, b = resolve(CONV, rows), resolve(CONV, rows + [fact(2, "카이토", "has_status", value="ok")])
    assert a.entity("character", "하나")["id"] == b.entity("character", "하나")["id"]
    other = resolve(UUID("01900000-0000-7000-8000-000000000002"), rows)
    assert other.entity("character", "하나")["id"] != a.entity("character", "하나")["id"]
    assert RESOLVER_VERSION.startswith("resolve-")


# --- through extraction and the API ----------------------------------------------------------------

def alias_complete(system: str, user: str) -> tuple[dict, str]:
    target = user.split("TARGET", 1)[1]
    items = []
    if "하나(Hana)" in target:
        items.append({"subject": "하나", "subject_type": "character", "predicate": "also_called", "value": "Hana",
                      "modality": "actual"})
    if "Hana has the map" in target:
        items.append({"subject": "Hana", "subject_type": "character", "predicate": "possesses", "object": "map",
                      "object_type": "item", "modality": "actual"})
    if "하나 gives the map to Kaito" in target:
        items.append({"subject": "Kaito", "subject_type": "character", "predicate": "possesses", "object": "map",
                      "object_type": "item", "modality": "actual"})
    if "하나 is in the station" in target:
        items.append({"subject": "하나", "subject_type": "character", "predicate": "located_in", "object": "station",
                      "object_type": "place", "modality": "actual"})
    if "Hana is in the harbor" in target:
        items.append({"subject": "Hana", "subject_type": "character", "predicate": "located_in", "object": "harbor",
                      "object_type": "place", "modality": "actual"})
    return {"assertions": items}, "{}"


def alias_chat() -> SimChat:
    chat = SimChat()
    chat.user("Meet 하나(Hana).")
    chat.reply("She waves.")
    chat.user("하나 is in the station.")
    chat.reply("Trains.")
    chat.user("Hana is in the harbor.")
    chat.reply("Gulls.")
    chat.user("next")
    return chat


def test_aliased_names_share_one_current_location(migrated, db):
    chat = alias_chat()
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        drain(migrated, alias_complete)
        located = [f for f in facts(c, chat) if f["predicate"] == "located_in"]
        # One entity, so the later statement under the other name supersedes the earlier one.
        assert [(f["subject"], f["object"], f["versions"]) for f in located] == [("Hana", "harbor", 2)]
        assert located[0]["subject_entity"]["name"] == "하나"

        # Deleting the turn that stated the alias splits the entity at the next read (ADR 0012, item 4).
        chat.delete(0)
        chat.delete(0)
        sync(c, chat)
        drain(migrated, alias_complete)  # the later turns' context changed, so they are extracted again
        located = [f for f in facts(c, chat) if f["predicate"] == "located_in"]
        assert sorted((f["subject"], f["object"]) for f in located) == [("Hana", "harbor"), ("하나", "station")]


def test_inspector_lists_entities_and_the_alias_turn(migrated, db):
    chat = alias_chat()
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        drain(migrated, alias_complete)
        cid = next(x["id"] for x in c.get("/v1/conversations").json() if x["host_chat_ref"] == chat.id)
        page = c.get(f"/inspector/c/{cid}?lang=en").text
        api = c.get(f"/v1/conversations/{cid}/entities").json()
    assert "Entities" in page and "Hana" in page
    hana = next(e for e in api if e["name"] == "하나")
    assert set(hana["names"]) == {"하나", "Hana"} and hana["aliases"][0]["turn"] == 0  # no greeting: the first turn is 0
    assert {e["name"] for e in api} >= {"하나", "station", "harbor"}
    # Object mentions carry their own type through the fact query (a missing column typed them "?").
    assert {(e["name"], e["type"]) for e in api} >= {("station", "place"), ("harbor", "place")}
