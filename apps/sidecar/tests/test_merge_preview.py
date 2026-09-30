"""PHASE-20: a join, a split or an undo shown before it is made (Q1–Q4)."""

from __future__ import annotations

import uuid

from conftest import make_client
from nmos_sidecar import generations, preview
from nmos_sidecar.facts import memory_view
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


def read(db, cid: str) -> dict:
    """The chat's memory as the API reads it."""
    head = db.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid,)).fetchone()["head_commit_id"]
    return memory_view(db, head, generations.active(db, "extract"), canon_key=generations.active(db, "canon"))


def same_as_done(p: dict, before: dict, after: dict, names, exclude=frozenset()) -> None:
    """The preview is the difference read after the action, line for line (PHASE-20 Q10)."""
    done = preview.diff(before, after, names, exclude)
    assert {k: p[k] for k in ("changes", "before", "after", "lines", "counts")} == done


NAMES = [("character", "Rin"), ("character", "Mina")]


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
        was = read(db, cid)
        out = c.post(f"/v1/conversations/{cid}/entity-links", json={**JOIN, "expect": p["fingerprint"]})
        assert out.status_code == 200, out.text
        joined = read(db, cid)
        same_as_done(p, was, joined, NAMES)
        gone = {x["fact"]["id"] for x in lines if x["kind"] in ("fact_replaced", "fact_merged", "fact_ended")}
        back = {x["fact"]["id"] for x in lines if x["kind"] == "fact_back"}
        assert current(c, cid) == (before - gone) | back
        # The undo's preview is the join read the other way round.
        link = out.json()["link"]["id"]
        undo = c.post(f"/v1/conversations/{cid}/entity-links/{link}/remove/preview").json()
        assert undo["action"] == "unlink" and len(undo["after"]) == 2
        assert {x["fact"]["id"] for x in undo["lines"] if x["kind"] == "fact_back"} == gone
        mirror = {x["kind"] for x in undo["lines"]}
        assert {"self_relation_gone", "self_thread_gone"} <= mirror
        assert any(x["kind"] == "secret" and x["kept_from_holder_gone"] for x in undo["lines"])
        assert c.post(f"/v1/conversations/{cid}/entity-links/{link}/remove",
                      json={"expect": undo["fingerprint"]}).status_code == 200
        assert current(c, cid) == before
        same_as_done(undo, joined, read(db, cid), NAMES)


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


def test_a_split_and_its_undo_are_previewed_like_a_join(migrated, db):
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
        was = read(db, cid)
        rep = c.post(f"/v1/conversations/{cid}/repairs", json={**body, "expect": p["fingerprint"]})
        assert rep.status_code == 200, rep.text
        rid = rep.json()["repair"]["id"]
        split = read(db, cid)
        same_as_done(p, was, split, [("character", "Mina"), ("character", "Rin")], {"preview", rid})
        undo = c.post(f"/v1/conversations/{cid}/repairs/{rid}/remove/preview").json()
        assert undo["action"] == "unsplit" and len(undo["after"]) == 1
        assert c.post(f"/v1/conversations/{cid}/repairs/{rid}/remove", json={"expect": "stale"}).status_code == 409
        assert c.post(f"/v1/conversations/{cid}/repairs/{rid}/remove",
                      json={"expect": undo["fingerprint"]}).status_code == 200
        same_as_done(undo, split, read(db, cid), [("character", "Mina"), ("character", "Rin")], {rid})
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


PAIRS = [("self_relation", "self_relation_gone"), ("self_thread", "self_thread_gone"), ("thread_merged", "thread_back"),
         ("thread_status", "thread_status"), ("secret_merged", "secret_back"), ("secret", "secret"), ("repair", "repair"),
         ("conflict_new", "conflict_gone"), ("persona", "persona_gone"), ("canon_alias", "canon_alias_gone")]
MIRROR = {a: b for a, b in PAIRS} | {b: a for a, b in PAIRS}
GONE = ("fact_replaced", "fact_merged", "fact_ended")


def mirrored(before: dict, after: dict, names=NAMES) -> list[dict]:
    """Every line of one direction has its mirror in the other (an undo previews the join read backwards)."""
    there, back = preview.diff(before, after, names)["lines"], preview.diff(after, before, names)["lines"]
    others = lambda lines: sorted(x["kind"] for x in lines if x["kind"] in MIRROR)  # noqa: E731
    assert sorted(MIRROR[k] for k in others(there)) == others(back)
    ids = lambda lines, kinds: sorted(x["fact"]["id"] for x in lines if x["kind"] in kinds)  # noqa: E731
    assert ids(there, GONE) == ids(back, ("fact_back",)) and ids(back, GONE) == ids(there, ("fact_back",))
    return there


def fact_row(pos, subject, predicate, obj=None, value=None, **kw):
    return {**row(pos, subject, predicate, obj, value, subject_type="character", **kw), "history": [], "versions": 1}


def thread_row(tid, by, to, status="open", text="wait"):
    return {"id": tid, "kind": "promise", "by": by, "to": to, "text": text, "turn": tid, "status": status}


def secret_row(sid, subject, holders, kept_from, text="the letter is forged"):
    return {"id": sid, "text": text, "turn": sid, "subject": subject, "holders": holders, "kept_from": kept_from,
            "open": kept_from}


def test_every_line_kind_has_its_mirror_on_hand_built_views():
    ended = fact_row(3, "Mina", "has_status", value="asleep")
    place_m, place_r = fact_row(1, "Mina", "located_in", "chapel"), fact_row(2, "Rin", "located_in", "harbor")
    rel = fact_row(4, "Mina", "relationship", "Rin", "classmate", object_type="character")
    t_open, t_gone, t_back = thread_row(10, "Mina", "Rin"), thread_row(11, "Rin", None), thread_row(12, "Mina", None)
    s_kept, s_merged, s_back = (secret_row(20, "Mina", ["Mina"], ["Rin"]), secret_row(21, "Rin", [], ["Sora"]),
                                secret_row(22, "Mina", [], ["Sora"]))
    before = view(ROWS, facts=[place_m, place_r, ended, rel], threads=[t_open, t_gone],
                  secrets=[s_kept, s_merged], conflicts=[{"kind": "locked", "fact": 1, "turn": 1, "text": "x"}])
    after = view(ROWS, [LINK], facts=[place_r, rel], threads=[{**t_open, "status": "kept"}, t_back],
                 secrets=[s_kept, s_back])
    lines = mirrored(before, after)
    kinds = {x["kind"] for x in lines}
    assert kinds >= {"fact_replaced", "fact_ended", "self_relation", "self_thread", "thread_status", "thread_merged",
                     "thread_back", "secret", "secret_merged", "secret_back", "conflict_gone"}
    assert next(x for x in lines if x["kind"] == "secret")["kept_from_holder"]
    back = {x["kind"] for x in preview.diff(after, before, NAMES)["lines"]}
    assert back >= {"fact_back", "self_relation_gone", "self_thread_gone", "conflict_new"}
    assert next(x for x in preview.diff(after, before, NAMES)["lines"] if x["kind"] == "secret")["kept_from_holder_gone"]


def test_canon_aliases_that_come_with_a_join_and_go_with_its_undo():
    canon = [{"key": "e1", "names": ["Mina", "Rin", "MR"]}]  # one entry naming both: an alias only once they are one
    before = view(ROWS)
    before["resolution"] = resolve(uuid.UUID(int=20), ROWS, canon=canon)
    after = view(ROWS, [LINK])
    after["resolution"] = resolve(uuid.UUID(int=20), ROWS, links=[LINK], canon=canon)
    assert {"kind": "canon_alias", "name": "Mina", "other": "MR"} in [
        {k: x[k] for k in ("kind", "name", "other")} for x in preview.diff(before, after, NAMES)["lines"]
        if x["kind"] == "canon_alias"]
    assert any(x["kind"] == "canon_alias_gone" for x in preview.diff(after, before, NAMES)["lines"])


def test_a_join_with_the_persona_is_undone_as_persona_gone():
    rows = ROWS + [row(3, "{{user}}", "located_in", "garden", None, subject_type="character")]
    names = [("character", "Rin"), ("character", "{{user}}")]
    joined = view(rows, [{**LINK, "same_as": "{{user}}"}])
    assert {"kind": "persona_gone"} in preview.diff(joined, view(rows), names)["lines"]


# --- step 3: re-extracting the turns a join covered (Q7) -------------------------------------------------------------

MORE = ("Rin is in the garden.", "Mina is a scholar.", "Rin is Mina's classmate.")


def carry_on(chat: SimChat, texts=MORE) -> None:
    for text in texts:
        chat.user(text)
        chat.reply("Noted.")
    chat.user("Go on.")


def hints_by_turn(db, cid: str) -> dict[int, list]:
    """Each turn's served extraction hints, names only, as KNOWN ENTITIES listed them."""
    rows = db.execute(
        "SELECT am.turn, x.hints FROM conversation c JOIN active_membership am ON am.commit_id = c.head_commit_id"
        " JOIN extraction x ON x.source_revision_id = am.source_revision_id AND x.window_hash = am.turn_hash"
        " WHERE c.id = %s AND x.discarded_at IS NULL AND am.turn_hash IS NOT NULL", (cid,)).fetchall()
    return {r["turn"]: sorted(sorted([h["name"], *(h.get("also") or ())]) for h in r["hints"]["entities"])
            for r in rows}


def test_an_undo_re_extracts_the_turns_the_join_covered_as_if_it_never_held(migrated, db):
    chat, twin = two_names(), two_names()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        tid = setup(c, migrated, twin)
        link = c.post(f"/v1/conversations/{cid}/entity-links", json=JOIN).json()["link"]["id"]
        carry_on(chat)
        carry_on(twin)
        for x in (chat, twin):
            sync(c, x)
        drain(migrated, stub_extractor)
        covered = [t for t, names in hints_by_turn(db, cid).items() if ["Mina", "Rin"] in names]
        assert covered and hints_by_turn(db, cid) != hints_by_turn(db, tid)  # extracted with the names as one
        early = c.post(f"/v1/conversations/{cid}/entity-links/{link}/reextract")
        assert early.status_code == 422  # the join still holds
        undo = c.post(f"/v1/conversations/{cid}/entity-links/{link}/remove/preview").json()
        assert undo["reextract"] == {"turns": len(covered)}
        assert c.post(f"/v1/conversations/{cid}/entity-links/{link}/remove").status_code == 200
        res = c.post(f"/v1/conversations/{cid}/entity-links/{link}/reextract")
        assert res.status_code == 200, res.text
        out = res.json()
        assert out["turns"] == sorted(covered) and out["discarded"] >= len(covered) and out["queued"] == len(covered)
        drain(migrated, stub_extractor)
        # No served extraction lists the names as one any more (the re-extraction reads the chat as it is now, so
        # a turn may list entities its first extraction had not seen yet), and memory is the never-joined chat's.
        assert not [t for t, names in hints_by_turn(db, cid).items() if ["Mina", "Rin"] in names]
        assert {(f["subject"], f["predicate"], f["object"], f["value"]) for f in c.get(
            f"/v1/conversations/{cid}/facts").json()} == {(f["subject"], f["predicate"], f["object"], f["value"])
                                                          for f in c.get(f"/v1/conversations/{tid}/facts").json()}
        again = c.post(f"/v1/conversations/{cid}/entity-links/{link}/reextract").json()
        assert again["turns"] == [] and again["queued"] == 0  # nothing left to redo


def test_no_re_extraction_while_the_names_are_one_entity_anyway(migrated):
    chat = SimChat()
    for text in ("Mina is in the chapel.", "Mina is also called Mi."):
        chat.user(text)
        chat.reply("Noted.")
    chat.user("Go on.")
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat, aliased)
        link = c.post(f"/v1/conversations/{cid}/entity-links",
                      json={"entity_type": "character", "name": "Mi", "same_as": "Mina"}).json()["link"]["id"]
        c.post(f"/v1/conversations/{cid}/entity-links/{link}/remove")
        res = c.post(f"/v1/conversations/{cid}/entity-links/{link}/reextract")
        assert res.status_code == 422 and "one entity now" in res.json()["detail"]
        assert c.post(f"/v1/conversations/{cid}/entity-links/{uuid.uuid4()}/reextract").status_code == 404
