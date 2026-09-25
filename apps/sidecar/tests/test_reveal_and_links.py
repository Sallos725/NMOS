"""extract-v9: event salience by what an event changes, revealed names of unnamed characters (ADR 0024);
the owner's entity links (ADR 0025, migration 0019)."""

from __future__ import annotations

from uuid import UUID

from conftest import make_client
from nmos_sidecar.entities import resolve
from nmos_sidecar.extraction import SYSTEM_PROMPT, build_prompt, entity_hints, hints_block, normalize
from nmos_sidecar.predicates import alias_evidenced, registry_prompt
from simchat import SimChat
from test_entities import alias, fact
from test_extraction import drain, facts
from test_generations import LLM
from test_sidecar_integration import sync

CONV = UUID("01900000-0000-7000-8000-000000000024")
RABBIT = "?흰 토끼 귀의 여자"


def hint(name, kind="character", also=None):
    return {"name": name, "type": kind, **({"also": also} if also else {})}


# --- extract-v9 prompt ------------------------------------------------------------------------------

def test_salience_is_judged_by_what_an_event_changes_in_action_or_words():
    prompt = SYSTEM_PROMPT.format(registry=registry_prompt())
    for phrase in ("whether it\n  happens in action or only in words", "an admission of guilt or responsibility",
                   "formal to informal speech", "an important object destroyed",
                   "record such an incident itself as an event", "meals, chores, travel",
                   "Judge by what the event changes"):
        assert phrase in prompt, phrase


def test_unnamed_characters_are_listed_apart_and_checked_last():
    hints = [hint("라디아"), hint(RABBIT), hint("?검은 망토의 남자", also=["카이"]), hint("온실", "place")]
    block = "\n".join(hints_block(hints))
    known, unnamed = block.split("UNNAMED CHARACTERS")
    assert "- 라디아 (character)" in known and "- 온실 (place)" in known
    assert "- ?검은 망토의 남자 / 카이 (character)" in known  # revealed already: it has a name
    assert unnamed.splitlines()[1:] == [f"- {RABBIT}"]
    ctx = {"target": {"turn": 5}, "context": [], "members": [{"metadata": {"role": "user"}, "content": "hi"}]}
    prompt = build_prompt(ctx, hints)
    assert prompt.rstrip().endswith('"value": "<the description as listed>"}.') and RABBIT in prompt.splitlines()[-1]
    assert "Before answering" not in build_prompt(ctx, hints[:1])  # nothing unnamed: no reminder


def test_an_unnamed_character_is_listed_with_what_it_looked_like():
    rows = [{"position": 1, "turn": 1, "subject": RABBIT, "subject_type": "character", "predicate": "has_trait",
             "object": None, "value": "긴 흰 토끼 귀", "evidence": "길고 흰 토끼 귀가 솟아 있었다", "participants": None},
            {"position": 2, "turn": 2, "subject": "엘피", "subject_type": "character", "predicate": "event",
             "object": None, "value": "누군가와 마주침", "evidence": "어? 엘피?",
             "participants": [{"name": RABBIT, "type": "character"}]}]
    ctx = {"target": {"conversation_id": CONV, "turn": 3}}
    rabbit = next(h for h in entity_hints(None, ctx, "k", 40, rows) if h["name"] == RABBIT)
    assert [s["turn"] for s in rabbit["seen"]] == [1, 2]  # the description first, then the latest mention
    block = hints_block([rabbit])
    assert block[1:3] == [f"- {RABBIT}", '  seen in turn 1: ?흰 토끼 귀의 여자 has trait: 긴 흰 토끼 귀 ("길고 흰 토끼 귀가 솟아 있었다")']


def test_a_revealed_name_needs_the_description_to_have_been_listed():
    reveal = {"subject": "라디아", "subject_type": "character", "predicate": "also_called", "value": RABBIT}
    text = "라디아가 무릎걸음으로 다가왔다. 긴 토끼 귀 하나가 앞으로 축 처졌다."
    assert alias_evidenced(reveal, text, [hint(RABBIT)])
    assert alias_evidenced({**reveal, "subject": RABBIT, "value": "라디아"}, text, [hint(RABBIT)])  # either way round
    assert not alias_evidenced(reveal, text, [])  # never listed: the model coined it now
    assert not alias_evidenced(reveal, text, [hint(RABBIT, "item")])  # listed as another type
    assert not alias_evidenced(reveal, "토끼 귀가 보였다.", [hint(RABBIT)])  # the name is not in the turn
    assert alias_evidenced({**reveal, "value": "라디아 교수"}, text + " 라디아 교수님.", [])  # both stated, as before
    rows = normalize([reveal, {**reveal, "value": "?다른 사람"}], text, [hint(RABBIT)])
    assert [(r["value"], r["status"]) for r in rows] == [(RABBIT, "valid"), ("?다른 사람", "pending")]


# --- read-time resolution ---------------------------------------------------------------------------

def test_a_revealed_character_is_one_entity_named_by_its_name():
    rows = [fact(1, RABBIT, "event", value="엘피와 마주침"),
            fact(2, "엘피", "event", value="쿠키를 전함", participants=[{"name": RABBIT, "type": "character"}]),
            alias(3, "라디아", RABBIT), fact(4, "라디아", "identity", value="교수")]
    r = resolve(CONV, rows)
    e = r.entity("character", RABBIT)
    assert e is r.entity("character", "라디아") and e["name"] == "라디아"  # the description came first
    assert e["names"] == [RABBIT, "라디아"]


def test_owner_links_join_mentioned_names_and_wait_for_unmentioned_ones():
    rows = [fact(1, "엘피", "event", value="토끼 수인과 마주침",
                 participants=[{"name": "정체불명의 토끼 수인", "type": "character"}]),
            fact(2, "라디아", "identity", value="교수")]
    link = {"id": "l1", "entity_type": "character", "name": "정체불명의 토끼 수인", "same_as": "라디아"}
    r = resolve(CONV, rows, links=[link])
    e = r.entity("character", "라디아")
    assert r.entity("character", "정체불명의 토끼 수인") is e and e["name"] == "라디아"
    assert e["links"] == [{"id": "l1", "name": "정체불명의 토끼 수인", "same_as": "라디아"}]
    assert resolve(CONV, rows).entity("character", "정체불명의 토끼 수인") is not resolve(CONV, rows).entity(
        "character", "라디아")
    # A name the head does not mention links nothing; another type is another entity.
    r = resolve(CONV, rows, links=[{**link, "same_as": "비올레"}, {**link, "entity_type": "item"}])
    assert r.entity("character", "정체불명의 토끼 수인") is not r.entity("character", "라디아")
    assert all(not e["links"] for e in r.entities())


def test_an_owner_link_settles_an_ambiguous_name_without_merging_the_candidates():
    rows = [fact(1, "하나 선배", "identity", value="3학년"), fact(2, "하나 후배", "identity", value="1학년"),
            alias(3, "하나 선배", "하나"), alias(4, "하나 후배", "하나"), fact(5, "하나", "located_in", "역", otype="place")]
    assert resolve(CONV, rows).status("character", "하나") == "ambiguous"
    r = resolve(CONV, rows, links=[{"id": "l", "entity_type": "character", "name": "하나", "same_as": "하나 후배"}])
    assert r.status("character", "하나") == "resolved"
    assert r.entity("character", "하나") is r.entity("character", "하나 후배")
    assert r.entity("character", "하나 선배") is not r.entity("character", "하나 후배")


# --- through extraction and the API ----------------------------------------------------------------

def reveal_complete(system: str, user: str) -> tuple[dict, str]:
    shown, target = user.split("\nTARGET turn", 1)
    items = []
    if "토끼 귀가 솟아" in target:
        items.append({"subject": "엘피", "subject_type": "character", "predicate": "event", "value": "누군가와 마주침",
                      "salience": "minor", "modality": "actual",
                      "with": [{"name": RABBIT, "type": "character"}]})
    if "라디아가 다가왔다" in target and RABBIT in shown:
        items.append({"subject": "라디아", "subject_type": "character", "predicate": "also_called", "value": RABBIT,
                      "modality": "actual"})
    if "라디아는 교수" in target:
        items.append({"subject": "라디아", "subject_type": "character", "predicate": "identity", "value": "교수",
                      "modality": "actual"})
    return {"assertions": items}, "{}"


def play_reveal(c, migrated, complete) -> SimChat:
    """Turn by turn, as a live chat is extracted: the reveal turn sees the first turn's facts as hints."""
    chat = SimChat()
    chat.user("엘피와 복도로 간다.")
    chat.reply("서류 더미 너머로 길고 흰 토끼 귀가 솟아 있었다.")
    chat.user("떨어진 서류를 줍는다.")
    sync(c, chat)
    drain(migrated, complete)
    chat.reply("라디아가 다가왔다. 라디아는 교수였다.")
    chat.user("next")
    sync(c, chat)
    drain(migrated, complete)
    return chat


def entities_of(c, chat) -> tuple[str, list[dict]]:
    cid = next(x["id"] for x in c.get("/v1/conversations").json() if x["host_chat_ref"] == chat.id)
    return cid, c.get(f"/v1/conversations/{cid}/entities").json()


def test_a_reveal_turn_links_the_description_it_was_shown(migrated, db):
    with make_client(migrated, **LLM) as c:
        chat = play_reveal(c, migrated, reveal_complete)
        _, api = entities_of(c, chat)
    radia = next(e for e in api if e["name"] == "라디아")
    assert set(radia["names"]) == {RABBIT, "라디아"} and radia["aliases"][0]["turn"] == 1
    hints = [h["hints"]["entities"] for h in db.execute("SELECT hints FROM extraction WHERE hints IS NOT NULL")]
    seen = [{"turn": 0, "fact": "엘피 event: 누군가와 마주침", "evidence": ""}]
    assert [{"name": RABBIT, "type": "character", "seen": seen}, {"name": "엘피", "type": "character"}] in hints


def test_owner_links_through_the_api(migrated, db):
    no_alias = lambda s, u: ({"assertions": [a for a in reveal_complete(s, u)[0]["assertions"]
                                             if a["predicate"] != "also_called"]}, "{}")
    with make_client(migrated, **LLM) as c:
        chat = play_reveal(c, migrated, no_alias)
        cid, api = entities_of(c, chat)
        assert {e["name"] for e in api} >= {RABBIT, "라디아"}
        path = f"/v1/conversations/{cid}/entity-links"
        bad = [{"entity_type": "character", "name": RABBIT, "same_as": "비올레"},  # not mentioned
               {"entity_type": "item", "name": RABBIT, "same_as": "라디아"},  # no such item
               {"entity_type": "character", "name": "라디아", "same_as": " 라디아 "}]  # the same name
        assert [c.post(path, json=b).status_code for b in bad] == [422, 422, 422]
        res = c.post(path, json={"entity_type": "character", "name": RABBIT, "same_as": "라디아"})
        assert res.status_code == 200
        link = res.json()["link"]
        assert res.json()["entity"]["name"] == "라디아" and set(res.json()["entity"]["names"]) == {RABBIT, "라디아"}
        _, api = entities_of(c, chat)
        radia = next(e for e in api if e["name"] == "라디아")
        assert radia["links"] == [{"id": link["id"], "name": RABBIT, "same_as": "라디아"}]
        page = c.get(f"/inspector/c/{cid}?lang=en").text
        assert "Joined by the owner" in page and f"{RABBIT} = 라디아" in page
        # A fact about the description now names 라디아 too, so a mention of 라디아 brings it back.
        met = next(f for f in facts(c, chat) if f["predicate"] == "event")
        assert "라디아" in met["names"]
        # A rebuild keeps the owner's link: it is not derived memory.
        assert c.post(f"/v1/conversations/{cid}/rebuild").status_code == 200
        drain(migrated, no_alias)
        _, api = entities_of(c, chat)
        assert set(next(e for e in api if e["name"] == "라디아")["names"]) == {RABBIT, "라디아"}
        # Removing it splits the names at the next read and keeps the row for audit.
        assert c.post(f"{path}/{link['id']}/remove").status_code == 200
        assert c.post(f"{path}/{link['id']}/remove").status_code == 404
        _, api = entities_of(c, chat)
        assert {e["name"] for e in api} >= {RABBIT, "라디아"}
        assert db.execute("SELECT removed_at FROM entity_link").fetchone()["removed_at"] is not None
        # Deleting the conversation deletes its links (ADR 0009).
        assert c.post(f"/v1/conversations/{cid}/delete").json()["deleted"]["entity_links"] == 1
    assert db.execute("SELECT count(*) AS n FROM entity_link").fetchone()["n"] == 0
