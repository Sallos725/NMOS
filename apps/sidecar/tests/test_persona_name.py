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
    rows = [row(1, "{{user}}", "located_in", "타쿠미의 집", **C, object_type="place"),
            row(2, "타쿠미", "located_in", "주방", **C, object_type="place"),
            row(3, "타쿠미", "possesses", "타쿠미", **C, object_type="item")]  # an item of that name stays an item
    r = resolve(CONV, rows, persona=["타쿠미"])
    assert r.key("character", "타쿠미") == r.key("character", "{{user}}") == r.key("character", "유저")
    assert r.key("item", "타쿠미") != r.key("character", "타쿠미")
    e = r.entity("character", "타쿠미")
    assert e["persona"] and e["name"] == "{{user}}" and set(e["names"]) == {"{{user}}", "타쿠미"}
    assert not r.entity("item", "타쿠미")["persona"]
    assert r.is_persona("character", " 타쿠미 ") and not r.is_persona("item", "타쿠미")
    # Without the host's name they stay two characters, as before.
    plain = resolve(CONV, rows)
    assert plain.key("character", "타쿠미") != plain.key("character", "{{user}}")
    assert not plain.entity("character", "타쿠미")["persona"]


def test_a_full_name_ending_with_the_persona_name_is_the_persona():
    """resolve-v5 (PHASE-11 step 3, ADR 0038): the story writes the persona's full name as well; M0 found one chat
    split in two by it (docs/perf/m0-baseline.md)."""
    rows = [row(1, "아오키 타쿠미", "located_in", "주방", **C, object_type="place"),
            row(2, "타쿠미", "located_in", "거실", **C, object_type="place"),
            row(3, "타쿠미마", "has_trait", None, "x", **C),
            row(4, "타쿠미 선배", "has_trait", None, "y", **C),
            row(5, "아델라", "possesses", "아오키 타쿠미", **C, object_type="item")]
    r = resolve(CONV, rows, persona=["타쿠미"])
    me = r.key("character", "{{user}}")
    assert r.key("character", "아오키 타쿠미") == r.key("character", " 아오키   타쿠미 ") == me
    assert r.key("character", "타쿠미마") != me  # not a separate word
    assert r.key("character", "타쿠미 선배") != me  # the name must end it
    assert r.key("item", "아오키 타쿠미") != me  # characters only
    assert "아오키 타쿠미" in r.entity("character", "{{user}}")["names"]
    assert resolve(CONV, rows).key("character", "아오키 타쿠미") != resolve(CONV, rows).key("character", "{{user}}")


def test_persona_names_include_the_personas_story_aliases():
    rows = [row(1, "타쿠미", "has_trait", None, "커피를 진하게 마심", **C), row(2, "타쿠미", "also_called", None, "타쿠", **C)]
    r = resolve(CONV, rows, persona=["타쿠미"])
    assert r.key("character", "타쿠") == r.key("character", "{{user}}")
    assert {"{{user}}", "user", "유저", "타쿠미", "타쿠"} <= r.persona_names
    assert resolve(CONV, rows).persona_names == frozenset({"{{user}}", "{user}", "user", "유저"})


def annotated(rows, persona=("타쿠미",)):
    r = resolve(CONV, rows, persona=persona)
    for x in rows:
        _annotate(x, r)
    return rows, r


def test_the_persona_name_is_never_a_mention():
    rows, r = annotated([
        row(1, "타쿠미", "has_trait", None, "커피를 진하게 마심", **C),
        row(2, "노엘", "event", None, "아침 식사를 맛있게 먹음", **C, salience="major",
            participants=with_(("타쿠미", "character"))),
        row(3, "노엘", "has_trait", None, "커피를 미지근하게 마심", **C, known_by=["타쿠미"], knowledge="limited"),
        row(4, "루카", "has_trait", None, "귀가 쫑긋함", **C)])
    trait, event, noel, luca = rows
    q = "타쿠미는 루카의 머리를 쓰다듬는다."  # the owner narrates the persona by name in every message
    picked = relevant_facts(rows, q, "", set(), 8, events_limit=3, persona=r.persona_names)
    assert picked == [luca]
    assert "타쿠미" not in event["names"]  # a persona participant adds no name, as `{{user}}` never did
    # Without the persona names (the old behavior) the persona's own facts took the slots.
    assert trait in relevant_facts(rows, q, "", set(), 8, events_limit=3)
    # A first-person question still brings the persona's facts (it did for `{{user}}`).
    assert trait in relevant_facts(rows, "내 커피 취향 기억나?", "", set(), 8, persona=r.persona_names)


def test_a_promise_to_the_named_persona_is_not_mentioned_by_the_persona_name():
    rows = [row(1, "루카", "promised", "타쿠미", "비밀을 지켜주기로 함", subject_type="character",
                object_type="character", source="character_claim", asserted_by="루카")]
    (t,), _, _ = fold(rows, resolve(CONV, rows, persona=["타쿠미"]))
    r = resolve(CONV, rows, persona=["타쿠미"])
    assert relevant_threads([t], "타쿠미는 고개를 끄덕인다.", "", set(), 3, persona=r.persona_names) == []
    assert relevant_threads([t], "루카, 약속 기억나?", "", set(), 3, persona=r.persona_names) == [t]


# --- through the API ---------------------------------------------------------------------------------

def conversation(db, chat):
    return db.execute("SELECT * FROM conversation WHERE host_chat_ref = %s", (chat.id,)).fetchone()


def test_the_host_persona_name_is_recorded_and_follows_renames(client, db):
    chat = SimChat()
    chat.user("안녕")
    chat.reply("반가워")
    chat.user("다음")
    sync(client, chat, persona_name=" 타쿠미 ")
    assert conversation(db, chat)["host_persona_name"] == "타쿠미"
    sync(client, chat)  # an older plugin, or the host permission was refused: the name stays
    assert conversation(db, chat)["host_persona_name"] == "타쿠미"
    chat.reply("또 보자")
    chat.user("응")
    sync(client, chat, persona_name="타쿠")
    assert conversation(db, chat)["host_persona_name"] == "타쿠"
    too_long = client.post("/v1/sync/reconcile", json={**chat.manifest(), "persona_name": "x" * 201})
    assert too_long.status_code == 422


def persona_complete(system: str, user: str) -> tuple[dict, str]:
    target = user.split("TARGET", 1)[1]
    items = []
    for who in ("{{user}}", "타쿠미"):
        for place in ("거실", "주방"):
            if f"{who} goes to the {place}" in target:
                items.append({"subject": who, "subject_type": "character", "predicate": "located_in",
                              "object": place, "object_type": "place", "modality": "actual"})
    if "Luca has the cookie" in target:
        items.append({"subject": "루카", "subject_type": "character", "predicate": "possesses", "object": "쿠키",
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
        for line in ("{{user}} goes to the 거실.", "타쿠미 goes to the 주방.", "Luca has the cookie.", "next"):
            chat.user(line)
            sync(c, chat, persona_name="타쿠미")
            drain(migrated, model)
            chat.reply("Noted.")
        located = [f for f in facts(c, chat) if f["predicate"] == "located_in"]
        assert [(f["subject"], f["object"], f["versions"]) for f in located] == [("타쿠미", "주방", 2)]
        assert located[0]["subject_entity"]["name"] == "{{user}}"
        cid = conversation(db, chat)["id"]
        persona = next(e for e in c.get(f"/v1/conversations/{cid}/entities").json() if e.get("persona"))
        assert set(persona["names"]) == {"{{user}}", "타쿠미"}
    # The persona is left out of KNOWN ENTITIES under either spelling (the prompt names it already).
    assert hints_of(model.prompts[-1]) and not any("타쿠미" in h or "{{user}}" in h for h in hints_of(model.prompts[-1]))
