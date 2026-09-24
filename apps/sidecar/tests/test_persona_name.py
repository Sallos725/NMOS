"""ADR 0023: the host's persona name is the persona (`{{user}}`), for resolution, recall and hints."""

from __future__ import annotations

from uuid import UUID

from conftest import make_client
from nmos_sidecar.entities import resolve
from nmos_sidecar.facts import _annotate, relevant_facts
from nmos_sidecar.threads import fold, relevant_threads
from simchat import SimChat
from test_extraction import drain, facts
from test_generations import LLM
from test_hints import hints_of
from test_semantics import row
from test_sidecar_integration import sync

CONV = UUID("01900000-0000-7000-8000-000000000023")
C = {"subject_type": "character"}


def with_(*people):
    return tuple({"name": n, "type": t} for n, t in people)


def test_the_persona_name_is_the_persona_entity():
    rows = [row(1, "{{user}}", "located_in", "유우마의 집", **C, object_type="place"),
            row(2, "유우마", "located_in", "주방", **C, object_type="place"),
            row(3, "유우마", "possesses", "유우마", **C, object_type="item")]  # an item of that name stays an item
    r = resolve(CONV, rows, persona=["유우마"])
    assert r.key("character", "유우마") == r.key("character", "{{user}}") == r.key("character", "유저")
    assert r.key("item", "유우마") != r.key("character", "유우마")
    e = r.entity("character", "유우마")
    assert e["persona"] and e["name"] == "{{user}}" and set(e["names"]) == {"{{user}}", "유우마"}
    assert not r.entity("item", "유우마")["persona"]
    assert r.is_persona("character", " 유우마 ") and not r.is_persona("item", "유우마")
    # Without the host's name they stay two characters, as before.
    plain = resolve(CONV, rows)
    assert plain.key("character", "유우마") != plain.key("character", "{{user}}")
    assert not plain.entity("character", "유우마")["persona"]


def test_persona_names_include_the_personas_story_aliases():
    rows = [row(1, "유우마", "has_trait", None, "커피를 진하게 마심", **C), row(2, "유우마", "also_called", None, "유우", **C)]
    r = resolve(CONV, rows, persona=["유우마"])
    assert r.key("character", "유우") == r.key("character", "{{user}}")
    assert {"{{user}}", "user", "유저", "유우마", "유우"} <= r.persona_names
    assert resolve(CONV, rows).persona_names == frozenset({"{{user}}", "{user}", "user", "유저"})


def annotated(rows, persona=("유우마",)):
    r = resolve(CONV, rows, persona=persona)
    for x in rows:
        _annotate(x, r)
    return rows, r


def test_the_persona_name_is_never_a_mention():
    rows, r = annotated([
        row(1, "유우마", "has_trait", None, "커피를 진하게 마심", **C),
        row(2, "블랑", "event", None, "아침 식사를 맛있게 먹음", **C, salience="major",
            participants=with_(("유우마", "character"))),
        row(3, "블랑", "has_trait", None, "커피를 미지근하게 마심", **C, known_by=["유우마"], knowledge="limited"),
        row(4, "엘피", "has_trait", None, "귀가 쫑긋함", **C)])
    trait, event, blanc, elpi = rows
    q = "유우마는 엘피의 머리를 쓰다듬는다."  # the owner narrates the persona by name in every message
    picked = relevant_facts(rows, q, "", set(), 8, events_limit=3, persona=r.persona_names)
    assert picked == [elpi]
    assert "유우마" not in event["names"]  # a persona participant adds no name, as `{{user}}` never did
    # Without the persona names (the old behavior) the persona's own facts took the slots.
    assert trait in relevant_facts(rows, q, "", set(), 8, events_limit=3)
    # A first-person question still brings the persona's facts (it did for `{{user}}`).
    assert trait in relevant_facts(rows, "내 커피 취향 기억나?", "", set(), 8, persona=r.persona_names)


def test_a_promise_to_the_named_persona_is_not_mentioned_by_the_persona_name():
    rows = [row(1, "엘피", "promised", "유우마", "비밀을 지켜주기로 함", subject_type="character",
                object_type="character", source="character_claim", asserted_by="엘피")]
    (t,), _, _ = fold(rows, resolve(CONV, rows, persona=["유우마"]))
    r = resolve(CONV, rows, persona=["유우마"])
    assert relevant_threads([t], "유우마는 고개를 끄덕인다.", "", set(), 3, persona=r.persona_names) == []
    assert relevant_threads([t], "엘피, 약속 기억나?", "", set(), 3, persona=r.persona_names) == [t]


# --- through the API ---------------------------------------------------------------------------------

def conversation(db, chat):
    return db.execute("SELECT * FROM conversation WHERE host_chat_ref = %s", (chat.id,)).fetchone()


def test_the_host_persona_name_is_recorded_and_follows_renames(client, db):
    chat = SimChat()
    chat.user("안녕")
    chat.reply("반가워")
    chat.user("다음")
    sync(client, chat, persona_name=" 유우마 ")
    assert conversation(db, chat)["host_persona_name"] == "유우마"
    sync(client, chat)  # an older plugin, or the host permission was refused: the name stays
    assert conversation(db, chat)["host_persona_name"] == "유우마"
    chat.reply("또 보자")
    chat.user("응")
    sync(client, chat, persona_name="유우")
    assert conversation(db, chat)["host_persona_name"] == "유우"
    too_long = client.post("/v1/sync/reconcile", json={**chat.manifest(), "persona_name": "x" * 201})
    assert too_long.status_code == 422


def persona_complete(system: str, user: str) -> tuple[dict, str]:
    target = user.split("TARGET", 1)[1]
    items = []
    for who in ("{{user}}", "유우마"):
        for place in ("거실", "주방"):
            if f"{who} goes to the {place}" in target:
                items.append({"subject": who, "subject_type": "character", "predicate": "located_in",
                              "object": place, "object_type": "place", "modality": "actual"})
    if "Elpi has the cookie" in target:
        items.append({"subject": "엘피", "subject_type": "character", "predicate": "possesses", "object": "쿠키",
                      "object_type": "item", "modality": "actual"})
    return {"assertions": items}, "{}"


class Recorder:
    def __init__(self):
        self.prompts: list[str] = []

    def __call__(self, system: str, user: str) -> tuple[dict, str]:
        self.prompts.append(user)
        return persona_complete(system, user)


def test_both_spellings_share_one_current_location_and_leave_the_hints(migrated, db):
    model, chat = Recorder(), SimChat()
    with make_client(migrated, **LLM) as c:
        for line in ("{{user}} goes to the 거실.", "유우마 goes to the 주방.", "Elpi has the cookie.", "next"):
            chat.user(line)
            sync(c, chat, persona_name="유우마")
            drain(migrated, model)
            chat.reply("Noted.")
        located = [f for f in facts(c, chat) if f["predicate"] == "located_in"]
        assert [(f["subject"], f["object"], f["versions"]) for f in located] == [("유우마", "주방", 2)]
        assert located[0]["subject_entity"]["name"] == "{{user}}"
        cid = conversation(db, chat)["id"]
        persona = next(e for e in c.get(f"/v1/conversations/{cid}/entities").json() if e.get("persona"))
        assert set(persona["names"]) == {"{{user}}", "유우마"}
    # The persona is left out of KNOWN ENTITIES under either spelling (the prompt names it already).
    assert hints_of(model.prompts[-1]) and not any("유우마" in h or "{{user}}" in h for h in hints_of(model.prompts[-1]))
