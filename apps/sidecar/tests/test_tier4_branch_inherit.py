"""PHASE-67 part 2 (audit G6.1, design decision 11c): a branched chat inherits its origin's memory (`branch.py`).

Synthetic chats only (names from the synthetic name map). Every model and embedder here is a counting stand-in: the
counts are the paid calls a real one would have made.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any
from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from conftest import active_generation, make_client
from nmos_sidecar import branch, reveals, summaries
from nmos_sidecar.extraction import process_extract
from nmos_sidecar.facts import memory_view
from nmos_sidecar.ids import uuid7
from nmos_sidecar.vectors import process_embed
from nmos_sidecar.worker import run_once
from simchat import SimChat
from test_extraction import fake_complete
from test_generations import EMB, LLM
from test_sidecar_integration import recall, sync
from test_summaries import stub as summary_stub
from test_vectors import FakeEmbedder

ON = {**LLM, **EMB, "summaries": True}
KEPT = re.compile(r"(?P<who>[A-Z]\w+) secretly plans to (?P<what>[^,]+), hidden from (?P<from>[A-Z]\w+)\.")
FOUND = re.compile(r"(?P<who>[A-Z]\w+) found out: (?P<what>[^.]+)\.")


class Model:
    """Counting stand-in: places (`X is in the Y.`), secrets (`X secretly plans to Y, hidden from Z.`), reveals
    (`Z found out: …`) and summaries."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, system: str, user: str) -> tuple[dict, str]:
        self.calls += 1
        if system in (summaries.SCENE_PROMPT, summaries.STORY_PROMPT):
            return summary_stub(system, user)
        out, raw = fake_complete(system, user)
        target = user.split("TARGET", 1)[1]
        out["assertions"] += [{"subject": m["who"], "subject_type": "character", "predicate": "goal",
                               "value": m["what"], "modality": "actual", "knowledge": "limited",
                               "known_by": [m["who"], "{{user}}"], "hidden_from": [m["from"]]}
                              for m in KEPT.finditer(target)]
        listed = [line.split(". ", 1)[0] for line in user.split("TARGET", 1)[0].splitlines() if line[:1] == "S"]
        out["secrets"] = [{"secret": listed[0], "found_out_by": [m["who"]], "evidence": m.group(0)}
                          for m in FOUND.finditer(target) if listed]
        return out, raw


class Embedder(FakeEmbedder):
    def __init__(self) -> None:
        super().__init__()
        self.texts = 0

    def embed(self, texts, timeout_s):
        self.texts += len(texts)
        return super().embed(texts, timeout_s)


def kinds(conn) -> dict[str, Any]:
    out = {}
    for kind in ("extract", "reveal", "embed", "summarize"):
        if conn.execute("SELECT 1 FROM projection_generation WHERE kind = %s", (kind,)).fetchone():
            out[kind] = active_generation(conn, kind)
    return out


def drain(url: str, model: Model, emb: Embedder) -> int:
    n = 0
    with psycopg.connect(url, row_factory=dict_row, autocommit=True) as conn:
        g = kinds(conn)
        jobs = {"extract": (g["extract"].key, lambda cn, j: process_extract(cn, j, model, g["extract"],
                                                                            g["extract"].spec["context_turns"])),
                "embed": (g["embed"].key, lambda cn, j: process_embed(cn, j, emb, g["embed"])),
                "summarize": (g["summarize"].key, lambda cn, j: summaries.process(cn, j, model, g["summarize"]))}
        if "reveal" in g:
            jobs["reveal"] = (g["reveal"].key, lambda cn, j: reveals.process(cn, j, model, g["reveal"],
                                                                             g["reveal"].spec["context_turns"]))
        while run_once(conn, jobs):
            n += 1
    return n


def conv(db, chat: SimChat) -> dict[str, Any]:
    return db.execute("SELECT * FROM conversation WHERE host_chat_ref = %s", (chat.id,)).fetchone()


def queued(db, chat: SimChat) -> list[dict[str, Any]]:
    return db.execute("SELECT kind, payload FROM job WHERE conversation_id = %s AND status = 'queued' ORDER BY id",
                      (conv(db, chat)["id"],)).fetchall()


def story(turns: int = 20) -> SimChat:
    """Turn t: a user line and a reply. A secret at turn 2 found out at turn 4 (before the branch point at 12), another
    at turn 6 found out at turn 15 (after it)."""
    chat = SimChat()
    lines = {2: "Luca secretly plans to visit the tower, hidden from Noel.",
             4: "Noel found out: Luca goal: visit the tower.",
             6: "Mira secretly plans to take the brass key, hidden from Ren.",
             15: "Ren found out: Mira goal: take the brass key."}
    for t in range(turns):
        chat.user(lines.get(t, f"Akari{t} is in the hall{t}."))
        chat.reply(f"Reply {t}: Sora{t} is in the yard{t}.")
    return chat


POINT = 25  # the reply of turn 12: the branch copies messages 0..25 (H5), then its marker


def view_rows(db, head: UUID, upto: int | None = None) -> dict[str, list]:
    """What a read serves, without the ids and hashes that differ between two chats by construction."""
    key = active_generation(db, "extract").key
    v = memory_view(db, head, key, upto=upto)
    drop = {"id", "turn_hash", "host_logical_id", "listed_hash", "eid", "repair", "assertion_id", "rid"}

    def clean(x: Any) -> Any:
        if isinstance(x, dict):
            return {k: clean(v) for k, v in sorted(x.items()) if k not in drop and not k.endswith("_id")}
        if isinstance(x, (list, tuple)):
            return [clean(v) for v in x]
        return x if isinstance(x, (str, int, float, bool, type(None))) else str(x)
    return {k: clean(v.get(k)) for k in ("facts", "claims", "threads", "secrets", "unrevealed", "conflicts")}


@pytest.fixture
def world(migrated):
    model, emb = Model(), Embedder()
    with make_client(migrated, embedder=FakeEmbedder(), **ON) as c:
        origin = story()
        later = origin.messages[28:]  # synced as a chat is, a turn at a time: here once at turn 13, then to the end
        del origin.messages[28:]
        sync(c, origin)
        drain(migrated, model, emb)
        origin.messages += later
        origin.user("And then?")
        sync(c, origin)
        drain(migrated, model, emb)
        yield c, migrated, origin, model, emb


# --- items 1, 2 and 7: the prefix is served from copies, zero calls, the same facts and secrets -------------------------

def test_the_prefix_is_copied_with_no_job_and_no_call_and_reads_as_the_origin_did(world, db):
    c, url, origin, model, emb = world
    assert model.calls > 0 and emb.texts > 0
    model.calls = emb.texts = 0
    br = origin.branch(POINT, name="Origin chat")
    sync(c, br)
    marker = conv(db, br)["branch_inherit"]
    assert marker["status"] == "done" and marker["by"] == "first_sync" and marker["prefix"] == POINT + 1
    assert marker["turns"] == 13 and marker["last_turn"] == 12
    assert marker["copied"]["extractions"] == 13 and marker["copied"]["assertions"] > 13
    assert marker["copied"]["scene_summaries"] == 1 and marker["copied"]["stories"] >= 1
    assert marker["copied"]["embedding_chunks"] >= POINT + 1
    assert queued(db, br) == []  # no job for a prefix turn, message, window or story
    # The first request in the branch: the user continues from the branch point.
    br.user("Where is everyone?")
    sync(c, br)
    assert [j["kind"] for j in queued(db, br)] == ["embed"]  # the new message only; turn 12's copy is its extraction
    drain(url, model, emb)
    assert model.calls == 0 and emb.texts == 1
    o, b = conv(db, origin), conv(db, br)
    assert view_rows(db, b["head_commit_id"]) == view_rows(db, o["head_commit_id"], upto=POINT)
    # The request path: the branch's first retrieve serves a copied fact, and its replay (ADR 0027) reproduces it.
    out = recall(c, br, "Where is Akari3?", [m["chatId"] for m in br.messages[-4:]])
    assert "hall3" in out["packet"]["text"]
    assert c.get(f"/v1/trace/{out['trace_id']}/replay").json()["reproduced"] is True
    # item 7: the secret found out before the branch point is found out in the branch; the one found out later in the
    # origin is still kept from Ren in the branch, with its marks.
    key = active_generation(db, "extract").key
    secrets = {s["text"]: s for s in memory_view(db, b["head_commit_id"], key)["secrets"]}
    origin_secrets = {s["text"]: s for s in memory_view(db, o["head_commit_id"], key)["secrets"]}
    kept = next(s for t, s in secrets.items() if "brass key" in t)
    assert kept["open"] == ["Ren"] and not kept.get("ended")
    assert not next(s for t, s in origin_secrets.items() if "brass key" in t)["open"]
    assert not next(s for t, s in secrets.items() if "tower" in t)["open"]
    # Copies record where they came from and cost nothing.
    rows = db.execute(
        "SELECT x.coverage, x.usage FROM extraction x JOIN source_revision sr ON sr.id = x.source_revision_id"
        " JOIN source_object so ON so.id = sr.source_object_id WHERE so.conversation_id = %s", (b["id"],)).fetchall()
    assert all(r["coverage"]["inherited_from"] == str(o["id"]) and r["usage"]["calls"] == 0 for r in rows)
    usage = c.get(f"/v1/conversations/{b['id']}/coverage", params={"usage": True})
    assert usage.status_code == 200


def test_the_tail_reply_copied_provisional_is_served_once_accepted(world, db):
    """The branch point's reply is provisional in the branch until the user continues (D5); its copied turn is then
    served, and its job is settled as done without a call."""
    c, url, origin, model, emb = world
    br = origin.branch(POINT)
    sync(c, br)
    b = conv(db, br)
    key = active_generation(db, "extract").key
    turns = {f["turn"] for f in memory_view(db, b["head_commit_id"], key)["facts"]}
    assert 12 not in turns and 11 in turns
    br.user("Go on.")
    sync(c, br)
    b = conv(db, br)
    assert 12 in {f["turn"] for f in memory_view(db, b["head_commit_id"], key)["facts"]}
    assert db.execute("SELECT count(*) AS n FROM job WHERE conversation_id = %s AND kind = 'extract'",
                      (b["id"],)).fetchone()["n"] == 0  # never queued, on the first sync or this one


# --- item 1: no origin, or other content, is today's behavior ---------------------------------------------------------

def test_a_branch_whose_origin_is_not_here_behaves_as_before(migrated, db):
    with make_client(migrated, embedder=FakeEmbedder(), **ON) as c:
        origin = story(10)
        br = origin.branch(9)  # the origin was never synced
        sync(c, br)
        b = conv(db, br)
        assert b["branch_inherit"]["status"] == "no_origin"
        assert {j["kind"] for j in queued(db, br)} == {"extract", "embed"}


def test_the_prefix_ends_at_the_first_message_that_differs(world, db):
    c, url, origin, model, emb = world
    br = origin.branch(POINT)
    origin.edit(6, "Akari3 is in the cellar.")  # turn 3's user line, edited in the origin after the branch was made
    sync(c, origin)
    sync(c, br)
    marker = conv(db, br)["branch_inherit"]
    assert marker["status"] == "done" and marker["prefix"] == 6 and marker["last_turn"] == 2
    assert marker["copied"]["extractions"] == 3
    jobs = [j for j in queued(db, br) if j["kind"] == "extract"]
    assert len(jobs) == 9  # turns 3..11 (accepted) are extracted as in any new chat; 0..2 are not
    drain(url, model, emb)
    assert conv(db, br)["branch_inherit"]["copied"].get("scene_summaries") is None


# --- item 3: after the branch point the chats are independent ---------------------------------------------------------

def test_later_writes_stay_in_their_chat_and_an_edit_detaches_as_anywhere(world, db):
    c, url, origin, model, emb = world
    br = origin.branch(POINT)
    sync(c, br)
    b = conv(db, br)
    o = conv(db, origin)
    before = db.execute("SELECT count(*) AS n FROM extraction x JOIN source_revision sr ON sr.id = x.source_revision_id"
                        " JOIN source_object so ON so.id = sr.source_object_id WHERE so.conversation_id = %s",
                        (b["id"],)).fetchone()["n"]
    origin.reply("Late: Kaito is in the garden.")
    origin.user("Later still.")
    sync(c, origin)
    db.execute("INSERT INTO entity_link (id, conversation_id, entity_type, name, same_as) VALUES (%s, %s, 'character',"
               " 'Akari1', 'Akari2')", (uuid7(), o["id"]))
    drain(url, model, emb)
    assert db.execute("SELECT count(*) AS n FROM extraction x JOIN source_revision sr ON sr.id = x.source_revision_id"
                      " JOIN source_object so ON so.id = sr.source_object_id WHERE so.conversation_id = %s",
                      (b["id"],)).fetchone()["n"] == before
    assert db.execute("SELECT count(*) AS n FROM entity_link WHERE conversation_id = %s", (b["id"],)).fetchone()["n"] == 0
    # An edit inside the branch's prefix: turn 5's copy no longer serves it, and the turn is queued again.
    key = active_generation(db, "extract").key
    br.edit(10, "Akari5 is in the attic.")
    br.user("Next.")
    sync(c, br)
    b = conv(db, br)
    facts = memory_view(db, b["head_commit_id"], key)["facts"]
    assert not [f for f in facts if f["subject"] == "Akari5"]
    assert any(j["kind"] == "extract" for j in queued(db, br))
    drain(url, model, emb)
    facts = memory_view(db, b["head_commit_id"], key)["facts"]
    assert [f["object"] for f in facts if f["subject"] == "Akari5"] == ["attic"]
    assert [f["object"] for f in memory_view(db, o["head_commit_id"], key)["facts"] if f["subject"] == "Akari5"] \
        == ["hall5"]


def test_deleting_either_chat_leaves_the_other_whole(world, db):
    c, url, origin, model, emb = world
    br = origin.branch(POINT)
    sync(c, br)
    br.user("Go on.")
    sync(c, br)
    b, o = conv(db, br), conv(db, origin)
    seen = view_rows(db, b["head_commit_id"])
    assert c.post(f"/v1/conversations/{o['id']}/delete").status_code == 200
    assert view_rows(db, b["head_commit_id"]) == seen
    assert conv(db, br)["branched_from_conversation_id"] is None
    # And the other way round: a new origin, its branch deleted.
    other = story(10)
    other.user("ok")
    sync(c, other)
    drain(url, model, emb)
    ob = conv(db, other)
    seen = view_rows(db, ob["head_commit_id"])
    br2 = other.branch(9)
    sync(c, br2)
    assert conv(db, br2)["branch_inherit"]["status"] == "done"
    assert c.post(f"/v1/conversations/{conv(db, br2)['id']}/delete").status_code == 200
    assert view_rows(db, ob["head_commit_id"]) == seen


# --- item 4: the owner's settings as of the branch point, copied once -------------------------------------------------

def repair(db, conv_id: UUID, kind: str, target: dict, value: dict | None = None) -> UUID:
    rid = uuid7()
    db.execute("INSERT INTO owner_repair (id, conversation_id, kind, target, value) VALUES (%s, %s, %s, %s, %s)",
               (rid, conv_id, kind, Jsonb(target), Jsonb(value or {})))
    return rid


def turn_hash(db, head: UUID, turn: int) -> str:
    return db.execute("SELECT turn_hash FROM active_membership WHERE commit_id = %s AND turn = %s AND turn_hash IS NOT"
                      " NULL", (head, turn)).fetchone()["turn_hash"]


def test_settings_are_inherited_once_re_anchored_and_the_branch_own_wins(world, db):
    c, url, origin, model, emb = world
    o = conv(db, origin)
    oid, head = o["id"], o["head_commit_id"]
    assert c.put(f"/v1/conversations/{oid}/memory-mode", json={"strict": True, "narrator": "Luca"}).status_code == 200
    assert c.put(f"/v1/conversations/{oid}/replies-only", json={"on": True}).status_code == 200
    link = uuid7()
    db.execute("INSERT INTO entity_link (id, conversation_id, entity_type, name, same_as) VALUES (%s, %s, 'character',"
               " 'Akari1', 'Sora1')", (link, oid))
    h3 = turn_hash(db, head, 3)
    inside = repair(db, oid, "fact_retract", {"turn": 3, "turn_hash": h3, "predicate": "located_in",
                                               "subject": "Akari3", "subject_type": "character", "object": "hall3",
                                               "object_type": "place", "text": "Akari3 located_in hall3"},
                    {"turn": 5})
    key = active_generation(db, "extract").key
    assert not [f for f in memory_view(db, head, key)["facts"] if f["subject"] == "Akari3"]  # it applies in the origin
    repair(db, oid, "fact_retract", {"turn": 15, "turn_hash": turn_hash(db, head, 15), "predicate": "located_in",
                                     "subject": "Akari15", "text": "x"})  # a later turn: not inherited
    repair(db, oid, "thread_close", {"turn": 3, "turn_hash": h3, "kind": "goal", "by": "Akari3", "text": "x"},
           {"outcome": "achieved", "turn": 18})  # takes effect after the branch point: not inherited
    exclude = repair(db, oid, "entity_exclude", {"entity_type": "character", "name": "Sora4"})
    pin = repair(db, oid, "entity_pin", {"entity_type": "character", "name": "Akari7"})
    source = story(3)
    source.user("x")
    sync(c, source)
    s = conv(db, source)
    carry = uuid7()
    db.execute("INSERT INTO conversation_carry (id, target_conversation_id, source_conversation_id, mode,"
               " cutoff_commit_id, cutoff_position, snapshot) VALUES (%s, %s, %s, 'continue', %s, 0, '{}')",
               (carry, oid, s["id"], s["head_commit_id"]))
    br = origin.branch(POINT)
    # The branch takes a narrator of its own before its first applied sync (the needs-bodies round names it).
    first = c.post("/v1/sync/reconcile", json=br.manifest()).json()
    assert first["status"] == "needs_bodies"
    assert c.put(f"/v1/conversations/{first['conversation_id']}/memory-mode",
                 json={"strict": False, "narrator": "Mira"}).status_code == 200
    sync(c, br)
    b = conv(db, br)
    # The branch chose its memory mode (strict off, narrator Mira): that pair is its own; replies-only is inherited.
    assert (b["memory_strict"], b["memory_narrator"], b["replies_only"]) == (False, "Mira", True)
    links = db.execute("SELECT * FROM entity_link WHERE conversation_id = %s", (b["id"],)).fetchall()
    assert [(x["name"], x["same_as"], x["inherited_from"]) for x in links] == [("Akari1", "Sora1", link)]
    reps = {r["inherited_from"]: r for r in db.execute("SELECT * FROM owner_repair WHERE conversation_id = %s",
                                                        (b["id"],)).fetchall()}
    assert set(reps) == {inside, exclude, pin}
    assert reps[inside]["target"]["turn_hash"] == turn_hash(db, b["head_commit_id"], 3) != h3
    assert reps[inside]["value"] == {"turn": 5}
    carried = db.execute("SELECT * FROM conversation_carry WHERE target_conversation_id = %s", (b["id"],)).fetchall()
    assert [(x["source_conversation_id"], x["inherited_from"]) for x in carried] == [(s["id"], carry)]
    assert b["branch_inherit"]["copied"]["repairs_not_inherited"] == 2
    # The retraction applies in the branch as in the origin.
    assert not [f for f in memory_view(db, b["head_commit_id"], key)["facts"] if f["subject"] == "Akari3"]
    # Copied once: a later change in the origin does not follow, a second sync copies nothing again.
    assert c.put(f"/v1/conversations/{oid}/replies-only", json={"on": False}).status_code == 200
    repair(db, oid, "entity_exclude", {"entity_type": "character", "name": "Sora5"})
    br.user("More.")
    sync(c, br)
    assert conv(db, br)["replies_only"] is True
    assert db.execute("SELECT count(*) AS n FROM owner_repair WHERE conversation_id = %s",
                      (b["id"],)).fetchone()["n"] == 3



def test_an_inherited_repair_is_anchored_to_the_branchs_messages_and_survives_its_renumbering(world, db):
    """PHASE-67 part 4: the origin's anchored repair moves onto the branch's own messages (`repairs.reanchor`), so
    deleting an earlier message of the branch (every later turn renumbered) keeps it applying there."""
    c, url, origin, model, emb = world
    o = conv(db, origin)
    oid, head = o["id"], o["head_commit_id"]
    key = active_generation(db, "extract").key
    rid = repair(db, oid, "fact_retract", {"turn": 5, "turn_hash": turn_hash(db, head, 5), "predicate": "located_in",
                                            "subject": "Akari5", "subject_type": "character", "object": "hall5",
                                            "object_type": "place", "text": "Akari5 located_in hall5"}, {"turn": 7})
    assert not [f for f in memory_view(db, head, key)["facts"] if f["subject"] == "Akari5"]  # a live read anchors it
    anchor = db.execute("SELECT anchor FROM owner_repair WHERE id = %s", (rid,)).fetchone()["anchor"]
    assert anchor["target"]["message"] == origin.messages[11]["chatId"]  # turn 5's reply
    br = origin.branch(POINT)
    sync(c, br)
    b = conv(db, br)
    mine = db.execute("SELECT * FROM owner_repair WHERE conversation_id = %s AND inherited_from = %s",
                      (b["id"], rid)).fetchone()
    assert mine["anchor"]["target"]["message"] == br.messages[11]["chatId"] != anchor["target"]["message"]
    assert mine["anchor"]["apply"]["messages"][0] == br.messages[14]["chatId"]  # turn 7's user message
    assert not [f for f in memory_view(db, b["head_commit_id"], key)["facts"] if f["subject"] == "Akari5"]
    del br.messages[2:4]  # turn 1 of the branch is gone: its turns 2-12 are 1-11 now
    sync(c, br)
    drain(url, model, emb)
    view = memory_view(db, conv(db, br)["head_commit_id"], key)
    assert [f["turn"] for f in view["facts"] if f["subject"] == "Akari7"] == [6]  # renumbered
    assert not [f for f in view["facts"] if f["subject"] == "Akari5"]
    assert next(r for r in view["repairs"] if r["id"] == mine["id"])["applied"] is not None

# --- items 5 and 6: idempotent, fail-open, the explicit back-fill, the bound ------------------------------------------

def test_a_second_sync_and_a_retry_copy_nothing_again(world, db):
    c, url, origin, model, emb = world
    br = origin.branch(POINT)
    sync(c, br)
    b = conv(db, br)
    count = "SELECT (SELECT count(*) FROM summary WHERE conversation_id = %(c)s) + (SELECT count(*) FROM owner_repair" \
            " WHERE conversation_id = %(c)s) + (SELECT count(*) FROM extraction x JOIN source_revision sr ON" \
            " sr.id = x.source_revision_id JOIN source_object so ON so.id = sr.source_object_id" \
            " WHERE so.conversation_id = %(c)s) AS n"
    n = db.execute(count, {"c": b["id"]}).fetchone()["n"]
    assert sync(c, br)["status"] == "noop"
    res = c.post("/v1/sync/bodies", json={"chat_id": br.id, "bodies": br.bodies(
        [{"host_logical_id": m["chatId"], "revision_hash": e["revision_hash"]}
         for m, e in zip(br.messages, br.manifest()["messages"])]), "then_reconcile": br.manifest()})
    assert res.status_code == 200 and res.json()["reconcile"]["status"] == "noop"
    assert db.execute(count, {"c": b["id"]}).fetchone()["n"] == n
    out = c.post(f"/v1/conversations/{b['id']}/branch-inherit", json={"dry_run": False}).json()
    assert out["status"] == "done" and sum(out["copied"].values()) == 0
    assert db.execute(count, {"c": b["id"]}).fetchone()["n"] == n


def test_a_failing_copy_fails_open_and_the_back_fill_takes_it_on_request(world, db, monkeypatch, caplog):
    c, url, origin, model, emb = world

    def broken(*a, **k):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(branch, "_copy_embeddings", broken)
    br = origin.branch(POINT)
    with caplog.at_level(logging.WARNING, logger="nmos.branch"):
        sync(c, br)
    assert "branch memory not inherited" in caplog.text
    b = conv(db, br)
    assert b["branch_inherit"]["status"] == "failed"
    assert db.execute("SELECT count(*) AS n FROM summary WHERE conversation_id = %s", (b["id"],)).fetchone()["n"] == 0
    jobs = queued(db, br)
    assert {j["kind"] for j in jobs} == {"extract", "embed", "summarize"}  # today's: the branch starts on its own
    br.user("Go on.")
    sync(c, br)  # a later sync never tries again on its own
    assert conv(db, br)["branch_inherit"]["status"] == "failed"
    monkeypatch.undo()
    preview = c.post(f"/v1/conversations/{b['id']}/branch-inherit", json={}).json()
    assert preview["dry_run"] is True and preview["copied"]["extractions"] == 13
    assert db.execute("SELECT count(*) AS n FROM summary WHERE conversation_id = %s", (b["id"],)).fetchone()["n"] == 0
    done = c.post(f"/v1/conversations/{b['id']}/branch-inherit", json={"dry_run": False}).json()
    assert done["copied"] == preview["copied"] and done["jobs_settled"] > 0
    assert conv(db, br)["branch_inherit"]["by"] == "backfill"
    model.calls = emb.texts = 0
    drain(url, model, emb)
    assert model.calls == 0 and emb.texts == 1  # "Go on." only, the branch's own message after the prefix
    again = c.post(f"/v1/conversations/{b['id']}/branch-inherit", json={"dry_run": False}).json()
    assert sum(again["copied"].values()) == 0
    assert c.post(f"/v1/conversations/{uuid7()}/branch-inherit", json={}).status_code == 404
    assert c.post(f"/v1/conversations/{b['id']}/branch-inherit", json={"dry_run": "no"}).status_code == 422


def test_a_branch_synced_before_this_code_keeps_its_own_and_takes_only_what_it_lacks(world, db, monkeypatch):
    c, url, origin, model, emb = world
    monkeypatch.setattr(branch, "on_first_sync", lambda conn, cid: None)  # as before this module: no marker
    br = origin.branch(POINT)
    br.user("Go on.")
    sync(c, br)
    b = conv(db, br)
    assert b["branch_inherit"] is None
    with psycopg.connect(url, row_factory=dict_row, autocommit=True) as conn:  # the branch's own: its newest turn
        g = kinds(conn)
        job = conn.execute(  # its newest turn, which no secret of the story depends on
            "SELECT j.* FROM job j JOIN active_membership am ON am.source_revision_id = (j.payload->>'revision_id')::uuid"
            " AND am.commit_id = %s WHERE j.conversation_id = %s AND j.kind = 'extract' ORDER BY am.turn DESC LIMIT 1",
            (b["head_commit_id"], b["id"])).fetchone()
        assert process_extract(conn, {**job, "locked_at": None}, model, g["extract"],
                               g["extract"].spec["context_turns"]) == "done"
    monkeypatch.undo()
    out = c.post(f"/v1/conversations/{b['id']}/branch-inherit", json={"dry_run": False}).json()
    assert out["status"] == "done" and out["copied"]["extractions"] == 12  # 13 turns, one the branch had already
    model.calls = emb.texts = 0
    drain(url, model, emb)
    assert model.calls == 0 and emb.texts == 1  # the new user message only


def test_two_hundred_turns_first_sync_time(migrated, db):
    """Item 6: a 200-turn origin with a few thousand assertions, branched at turn 150."""
    model, emb = Model(), Embedder()
    chat = SimChat()
    for t in range(200):
        chat.user(" ".join(f"Akari{t}x{i} is in the hall{i}." for i in range(8)))
        chat.reply(" ".join(f"Sora{t}x{i} is in the yard{i}." for i in range(8)))
    chat.user("And then?")
    with make_client(migrated, embedder=FakeEmbedder(), extract_backfill=300, **ON) as c:
        sync(c, chat)
        drain(migrated, model, emb)
        n = db.execute("SELECT count(*) AS n FROM assertion").fetchone()["n"]
        assert n >= 3000
        br = chat.branch(301)  # the reply of turn 150
        started = time.perf_counter()
        sync(c, br)
        wall = (time.perf_counter() - started) * 1000
        marker = conv(db, br)["branch_inherit"]
        assert marker["status"] == "done" and marker["turns"] == 151
        assert marker["copied"]["assertions"] >= 151 * 16
        print(f"\nfirst sync of a 151-turn prefix: copy {marker['ms']} ms, sync round trip {wall:.0f} ms,"
              f" copied {marker['copied']}")
        assert marker["ms"] < branch.BUDGET_S * 1000
        # The origin was synced at once, so it never wrote a story of exactly the branch's 18 due scenes: that story
        # is the one call the branch makes (each scene is copied).
        assert [(j["kind"], j["payload"]["level"]) for j in queued(db, br)] == [("summarize", "story")]
        assert marker["copied"]["scene_summaries"] == 18


# --- item 2: fallback generations and reveal checks -------------------------------------------------------------------

def test_turns_the_origin_serves_by_an_earlier_generation_are_served_so_with_no_call(migrated, db):
    """A model change carried on (PHASE-57 A3): the origin's turns are served by the earlier generation; the branch's
    copies of them serve its prefix the same way, and the active generation's first-sight jobs are taken back."""
    model, emb = Model(), Embedder()
    with make_client(migrated, embedder=FakeEmbedder(), **ON) as c:
        origin = story(14)
        origin.user("And then?")
        sync(c, origin)
        drain(migrated, model, emb)
        old = active_generation(db, "extract").key
        assert c.put("/v1/config", json={"llm_model": "fake-2"}).status_code == 200  # carry on, the default
        new = active_generation(db, "extract").key
        assert new != old
        drain(migrated, model, emb)
        model.calls = emb.texts = 0
        br = origin.branch(POINT)
        sync(c, br)
        br.user("Go on.")
        sync(c, br)
        b, o = conv(db, br), conv(db, origin)
        assert {x["extractor_key"] for x in db.execute(
            "SELECT x.extractor_key FROM extraction x JOIN source_revision sr ON sr.id = x.source_revision_id"
            " JOIN source_object so ON so.id = sr.source_object_id WHERE so.conversation_id = %s",
            (b["id"],)).fetchall()} == {old}
        assert [j["kind"] for j in queued(db, br)] == ["embed"]
        drain(migrated, model, emb)
        assert model.calls == 0 and emb.texts == 1
        assert view_rows(db, b["head_commit_id"]) == view_rows(db, o["head_commit_id"], upto=POINT)


def test_reveal_checks_are_copied_with_the_extraction_they_checked(migrated, db):
    """A turn extracted before an earlier secret was (K29) is checked by "extract all history" (ADR 0057); the check
    is copied with its turn, and the branch needs no check of its own."""
    model, emb = Model(), Embedder()
    with make_client(migrated, embedder=FakeEmbedder(), **ON) as c:
        origin = story(14)
        origin.user("And then?")
        sync(c, origin)
        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            g = kinds(conn)
            for job in conn.execute(  # newest turn first: no turn knows an earlier secret
                    "SELECT j.* FROM job j JOIN conversation c ON c.id = j.conversation_id JOIN active_membership am"
                    " ON am.commit_id = c.head_commit_id AND am.source_revision_id = (j.payload->>'revision_id')::uuid"
                    " WHERE j.kind = 'extract' AND j.status = 'queued' ORDER BY am.turn DESC").fetchall():
                process_extract(conn, {**job, "locked_at": None}, model, g["extract"],
                                g["extract"].spec["context_turns"])
            conn.execute("UPDATE job SET status = 'done' WHERE kind = 'extract'")
        drain(migrated, model, emb)
        o = conv(db, origin)
        res = c.post(f"/v1/conversations/{o['id']}/extract-history")
        assert res.status_code == 200 and res.json()["queued"]["reveal"] > 0
        drain(migrated, model, emb)
        key = active_generation(db, "extract").key
        tower = next(s for s in memory_view(db, o["head_commit_id"], key)["secrets"] if "tower" in s["text"])
        assert not tower["open"]  # found out at turn 4, by the check
        model.calls = 0
        br = origin.branch(POINT)
        sync(c, br)
        b = conv(db, br)
        assert b["branch_inherit"]["copied"]["reveal_checks"] >= 1
        br.user("Go on.")
        sync(c, br)
        b = conv(db, br)
        tower = next(s for s in memory_view(db, b["head_commit_id"], key)["secrets"] if "tower" in s["text"])
        assert not tower["open"]
        res = c.post(f"/v1/conversations/{b['id']}/extract-history")
        assert res.status_code == 200 and res.json()["queued"]["reveal"] == 0  # copied checks read as checked
        drain(migrated, model, emb)
        assert model.calls == 0
