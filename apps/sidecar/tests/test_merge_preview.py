"""PHASE-20: a join, a split or an undo shown before it is made (Q1–Q4)."""

from __future__ import annotations

import uuid

from conftest import make_client
from nmos_sidecar import preview
from nmos_sidecar.entities import resolve
from simchat import SimChat
from test_extraction import drain
from test_generations import LLM
from test_repairs import aliased, setup
from test_semantics import row
from test_sidecar_integration import sync
from memeval import stub_extractor


def two_names() -> SimChat:
    """Two names the owner may join: a place each, the same identity, a secret kept from the other, a promise and
    a relationship between them."""
    chat = SimChat()
    for text in ("Mina is in the chapel.", "Rin is in the harbor.", "Mina is a knight.", "Rin is a knight.",
                 "Mina keeps a secret from Rin: the letter is forged.", 'Mina says to Rin: "I promise to wait."',
                 "Mina is Rin's classmate."):
        chat.user(text)
        chat.reply("Noted.")
    chat.user("Go on.")
    return chat


JOIN = {"entity_type": "character", "name": "Rin", "same_as": "Mina"}


def current(c, cid: str) -> set[int]:
    return {f["id"] for f in c.get(f"/v1/conversations/{cid}/facts").json()}


def kinds(p: dict) -> dict[str, int]:
    return p["counts"]


def test_a_join_preview_says_what_the_join_changes_and_the_join_does_exactly_that(migrated, db):
    chat = two_names()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        before = current(c, cid)
        res = c.post(f"/v1/conversations/{cid}/entity-links/preview", json=JOIN)
        assert res.status_code == 200, res.text
        p = res.json()
        assert p["changes"] and p["action"] == "join"
        assert len(p["before"]) == 2 and len(p["after"]) == 1 and set(p["after"][0]["names"]) == {"Mina", "Rin"}
        lines = p["lines"]
        replaced = next(x for x in lines if x["kind"] == "fact_replaced")  # the later place wins, by the story's order
        assert (replaced["fact"]["object"], replaced["by"]["object"]) == ("chapel", "harbor")
        merged = next(x for x in lines if x["kind"] == "fact_merged")
        assert merged["fact"]["value"] == merged["by"]["value"] == "knight"
        assert any(x["kind"] == "self_relation" and x["fact"]["value"] == "classmate" for x in lines)
        assert any(x["kind"] == "self_thread" and x["thread"]["text"] == "wait" for x in lines)
        assert any(x["kind"] == "secret" and x["kept_from_holder"] for x in lines)  # kept from the one who holds it
        assert db.execute("SELECT count(*) AS n FROM entity_link").fetchone()["n"] == 0  # nothing written
        # The join made from this preview changes exactly what it said.
        out = c.post(f"/v1/conversations/{cid}/entity-links", json={**JOIN, "expect": p["fingerprint"]})
        assert out.status_code == 200, out.text
        gone = {x["fact"]["id"] for x in lines if x["kind"] in ("fact_replaced", "fact_merged", "fact_ended")}
        back = {x["fact"]["id"] for x in lines if x["kind"] == "fact_back"}
        assert current(c, cid) == (before - gone) | back
        # The undo's preview is the join read the other way round.
        link = out.json()["link"]["id"]
        undo = c.post(f"/v1/conversations/{cid}/entity-links/{link}/remove/preview").json()
        assert undo["action"] == "unlink" and len(undo["after"]) == 2
        assert {x["fact"]["id"] for x in undo["lines"] if x["kind"] == "fact_back"} == gone
        assert c.post(f"/v1/conversations/{cid}/entity-links/{link}/remove",
                      json={"expect": undo["fingerprint"]}).status_code == 200
        assert current(c, cid) == before


def test_a_preview_of_memory_that_changed_since_is_refused(migrated, db):
    chat = two_names()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        p = c.post(f"/v1/conversations/{cid}/entity-links/preview", json=JOIN).json()
        chat.user("Rin is in the garden.")  # the story moves on before the owner clicks
        chat.reply("Noted.")
        chat.user("Go on.")
        sync(c, chat)
        drain(migrated, stub_extractor)
        stale = c.post(f"/v1/conversations/{cid}/entity-links", json={**JOIN, "expect": p["fingerprint"]})
        assert stale.status_code == 409
        fresh = stale.json()["detail"]["preview"]
        assert fresh["fingerprint"] != p["fingerprint"] and fresh["changes"]
        assert db.execute("SELECT count(*) AS n FROM entity_link").fetchone()["n"] == 0
        assert c.post(f"/v1/conversations/{cid}/entity-links",
                      json={**JOIN, "expect": fresh["fingerprint"]}).status_code == 200
        # An extraction that lands on the same head and changes the difference refuses it as well.
        chat.user("Mina is in the tower.")
        chat.reply("Noted.")
        chat.user("Go on.")
        sync(c, chat)  # the new turns are on the head, not yet extracted
        link = c.get(f"/v1/conversations/{cid}/entities").json()
        rid = next(x["id"] for e in link for x in e["links"])
        undo = c.post(f"/v1/conversations/{cid}/entity-links/{rid}/remove/preview").json()
        head = db.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid,)).fetchone()["head_commit_id"]
        drain(migrated, stub_extractor)
        assert db.execute("SELECT head_commit_id FROM conversation WHERE id = %s",
                          (cid,)).fetchone()["head_commit_id"] == head
        assert c.post(f"/v1/conversations/{cid}/entity-links/{rid}/remove",
                      json={"expect": undo["fingerprint"]}).status_code == 409
        # Without a fingerprint the API joins as before.
        assert c.post(f"/v1/conversations/{cid}/entity-links",
                      json={"entity_type": "character", "name": "Mina", "same_as": "Rin"}).status_code == 200


def test_a_join_of_names_that_are_one_entity_already_changes_nothing(migrated):
    chat = SimChat()
    for text in ("Mina is in the chapel.", "Mina is also called Mi.", "Mi is a knight."):
        chat.user(text)
        chat.reply("Noted.")
    chat.user("Go on.")
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat, aliased)
        p = c.post(f"/v1/conversations/{cid}/entity-links/preview",
                   json={"entity_type": "character", "name": "Mi", "same_as": "Mina"}).json()
        assert not p["changes"] and p["lines"] == [] and len(p["before"]) == len(p["after"]) == 1
        bad = c.post(f"/v1/conversations/{cid}/entity-links/preview",
                     json={"entity_type": "character", "name": "Mina", "same_as": "Sora"})
        assert bad.status_code == 422  # not mentioned: as the join itself


def test_a_split_and_its_undo_are_previewed_like_a_join(migrated):
    chat = SimChat()
    for text in ("Mina is in the chapel.", "Rin is in the harbor.", "Mina is also called Rin."):
        chat.user(text)
        chat.reply("Noted.")
    chat.user("Go on.")
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat, aliased)
        body = {"kind": "name_split", "item": "Mina", "other": "Rin"}
        p = c.post(f"/v1/conversations/{cid}/repairs/preview", json=body).json()
        assert p["action"] == "split" and len(p["before"]) == 1 and len(p["after"]) == 2
        back = next(x for x in p["lines"] if x["kind"] == "fact_back")
        assert back["fact"]["object"] == "chapel" and back["instead_of"]["object"] == "harbor"
        assert not any(x["kind"] == "repair" for x in p["lines"])  # the split itself is not a change to list
        rep = c.post(f"/v1/conversations/{cid}/repairs", json={**body, "expect": p["fingerprint"]})
        assert rep.status_code == 200, rep.text
        rid = rep.json()["repair"]["id"]
        undo = c.post(f"/v1/conversations/{cid}/repairs/{rid}/remove/preview").json()
        assert undo["action"] == "unsplit" and len(undo["after"]) == 1
        assert c.post(f"/v1/conversations/{cid}/repairs/{rid}/remove", json={"expect": "stale"}).status_code == 409
        assert c.post(f"/v1/conversations/{cid}/repairs/{rid}/remove",
                      json={"expect": undo["fingerprint"]}).status_code == 200
        # Other repairs have no preview.
        other = c.post(f"/v1/conversations/{cid}/repairs/preview", json={"kind": "fact_retract", "item": "1"})
        assert other.status_code == 422


# --- the difference itself, on views built by hand -----------------------------------------------------------------

def view(rows: list[dict], links=(), **parts) -> dict:
    r = resolve(uuid.UUID(int=20), rows, links=list(links))
    return {"resolution": r, "facts": parts.get("facts", []), "threads": parts.get("threads", []),
            "secrets": parts.get("secrets", []), "repairs": parts.get("repairs", []),
            "conflicts": parts.get("conflicts", [])}


LINK = {"id": "l1", "entity_type": "character", "name": "Rin", "same_as": "Mina", "created_at": 1}
ROWS = [row(1, "Mina", "located_in", "chapel", None, subject_type="character"),
        row(2, "Rin", "located_in", "harbor", None, subject_type="character")]
NAMES = [("character", "Rin"), ("character", "Mina")]


def test_a_repair_whose_match_changes_and_a_new_conflict_are_listed():
    rep = {"id": "r1", "kind": "fact_retract", "target": {"turn": 1}}
    conflict = {"kind": "disputed", "fact": 2, "turn": 2, "text": "t", "against": {"id": 1}}
    before = view(ROWS, repairs=[{**rep, "applied": "1"}])
    after = view(ROWS, [LINK], repairs=[{**rep, "applied": None}], conflicts=[conflict])
    lines = preview.diff(before, after, NAMES)["lines"]
    assert {"kind": "repair", "repair": {"id": "r1", "kind": "fact_retract", "target": {"turn": 1}},
            "before": "1", "after": None} in lines
    assert {"kind": "conflict_new", "conflict": {"kind": "disputed", "fact": 2, "turn": 2, "text": "t"}} in lines
    # The action's own repair (a split) is not listed.
    assert not [x for x in preview.diff(before, after, NAMES, {"r1"})["lines"] if x["kind"] == "repair"]


def test_a_join_with_the_persona_is_listed():
    rows = ROWS + [row(3, "{{user}}", "located_in", "garden", None, subject_type="character")]
    persona_link = {**LINK, "name": "Rin", "same_as": "{{user}}"}
    before, after = view(rows), view(rows, [persona_link])
    lines = preview.diff(before, after, [("character", "Rin"), ("character", "{{user}}")])["lines"]
    assert {"kind": "persona"} in lines


def test_the_fingerprint_changes_with_what_the_preview_read():
    p = preview.diff(view(ROWS), view(ROWS, [LINK]), NAMES)
    state = {"head": "h1", "links": [], "repairs": []}
    assert preview.fingerprint(p, state) == preview.fingerprint(p, dict(state))
    assert preview.fingerprint(p, {**state, "head": "h2"}) != preview.fingerprint(p, state)
    assert preview.fingerprint({**p, "lines": [{"kind": "persona"}]}, state) != preview.fingerprint(p, state)
