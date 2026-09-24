"""O5 (ADR 0018): full-manifest host observations are compacted losslessly."""

from __future__ import annotations

import random

from conftest import make_client
from nmos_sidecar import retention
from nmos_sidecar.worker import prune
from simchat import SimChat
from test_extraction import filler
from test_sidecar_integration import sync


def full_observations(db) -> dict:
    """id -> (columns, rows) of every observation that holds the whole manifest right now."""
    return {r["id"]: (r["raw_manifest"]["columns"], r["raw_manifest"]["entries"]) for r in db.execute(
        "SELECT id, raw_manifest FROM host_observation WHERE kind = 'manifest' AND raw_manifest ? 'entries'"
        " ORDER BY id").fetchall()}


def edited_chat(client, rnd: random.Random, actions: int = 30) -> SimChat:
    chat = SimChat()
    filler(chat, 20)
    sync(client, chat)
    for _ in range(actions):
        pick = rnd.random()
        if pick < 0.3:
            chat.user(f"more {rnd.random():.5f}")
            chat.reply(f"answer {rnd.random():.5f}")
        elif pick < 0.5:
            chat.edit(rnd.randrange(len(chat.messages)), f"edited {rnd.random():.5f}")
        elif pick < 0.7 and chat.messages[-1]["role"] == "char":
            chat.reroll(f"rerolled {rnd.random():.5f}")
        elif pick < 0.8 and chat.messages[-1].get("swipes"):
            chat.swipe(0)
        elif pick < 0.9:
            chat.delete(rnd.randrange(1, len(chat.messages)))
        else:
            chat.disable(rnd.randrange(len(chat.messages)))
        sync(client, chat)
    return chat


def test_compaction_rebuilds_every_observation_exactly(migrated, db):
    with make_client(migrated) as c:
        for seed in range(3):
            edited_chat(c, random.Random(seed))
    before = full_observations(db)
    size = db.execute("SELECT sum(pg_column_size(raw_manifest)) AS n FROM host_observation").fetchone()["n"]
    assert len(before) > 30
    compacted = retention.compact_observations(db)
    assert compacted > 0
    for obs_id, original in before.items():
        assert retention.observed_rows(db, obs_id) == original
    assert retention.compact_observations(db) == 0  # idempotent
    after = db.execute("SELECT sum(pg_column_size(raw_manifest)) AS n FROM host_observation").fetchone()["n"]
    assert after < size
    # Every compacted observation points at a base that is still full.
    bad = db.execute("SELECT o.id FROM host_observation o JOIN host_observation b"
                     " ON b.id = (o.raw_manifest->>'base_observation')::uuid"
                     " WHERE NOT b.raw_manifest ? 'entries'").fetchall()
    assert bad == []


def test_each_chats_first_observation_and_large_changes_stay_full(migrated, db):
    chat = SimChat()
    filler(chat, 10)
    with make_client(migrated) as c:
        sync(c, chat)                      # first sight: full, the chat's first base
        chat.edit(3, "a small edit")
        sync(c, chat)                      # one row changed: compacted
        for i in range(1, len(chat.messages), 2):
            chat.edit(i, f"rewritten {i}")
        sync(c, chat)                      # half the rows changed: stays full, the next base
        chat.edit(4, "another small edit")
        sync(c, chat)                      # compacted against the second base
    ids = list(full_observations(db))
    assert len(ids) == 4
    assert retention.compact_observations(db) == 2
    kinds = [("entries" in r["raw_manifest"], r["raw_manifest"].get("base_observation")) for r in db.execute(
        "SELECT raw_manifest FROM host_observation WHERE id = ANY(%s) ORDER BY id", (ids,)).fetchall()]
    assert kinds == [(True, None), (False, str(ids[0])), (True, None), (False, str(ids[2]))]
    assert [r["observation_id"] for r in db.execute(
        "SELECT observation_id FROM observation_base ORDER BY observation_id").fetchall()] == [ids[0], ids[2]]


def test_appended_observations_are_left_alone(migrated, db):
    chat = SimChat()
    filler(chat, 5)
    with make_client(migrated) as c:
        sync(c, chat)
        for i in range(3):
            chat.user(f"next {i}")
            chat.reply("ok")
            sync(c, chat)
    appended = db.execute("SELECT id, raw_manifest FROM host_observation WHERE raw_manifest ? 'appended'"
                          " ORDER BY id").fetchall()
    assert appended
    prune(db, 30)  # the worker's maintenance pass runs compaction
    assert db.execute("SELECT id, raw_manifest FROM host_observation WHERE raw_manifest ? 'appended'"
                      " ORDER BY id").fetchall() == appended


def test_deleting_a_conversation_removes_its_bases(migrated, db):
    chat = SimChat()
    filler(chat, 5)
    with make_client(migrated) as c:
        sync(c, chat)
        chat.edit(2, "edited")
        sync(c, chat)
        retention.compact_observations(db)
        assert db.execute("SELECT count(*) AS n FROM observation_base").fetchone()["n"] == 1
        conv = c.get("/v1/conversations").json()[0]["id"]
        assert c.post(f"/v1/conversations/{conv}/delete").status_code == 200
    assert db.execute("SELECT count(*) AS n FROM observation_base").fetchone()["n"] == 0
    assert db.execute("SELECT count(*) AS n FROM host_observation").fetchone()["n"] == 0
