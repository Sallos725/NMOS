"""Databases written by earlier releases upgrade and keep working (audit A-16).

Each `fixtures/upgrade/<release>.sql` is a `pg_dump` of a database that release's own sidecar and worker
wrote (`tools/make_upgrade_fixture.py`): two chats with edits, a reroll, a swipe, a disabled message and
a branch, extractions, embeddings and recall traces (Phase 13 `main` and earlier: none has canon yet). `<release>.chat.json` is the chats as the host last
showed them. The test restores the dump, applies the current migrations and starts the current sidecar,
then goes on with the story."""

from __future__ import annotations

import json
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar.migrate import apply_migrations
from nmos_sidecar.rebuild import rebuild_all
from simchat import SimChat
from test_canon import push
from test_canon_facts import Model, current, drain as drain_canon, view
from test_extraction import drain, facts
from test_generations import EMB, LLM
from test_sidecar_integration import recall, sync
from test_summaries import drain as drain_summaries
from test_vectors import FakeEmbedder, drain_embeddings

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = sorted((ROOT / "fixtures/upgrade").glob("*.sql"))
LATEST = max(p.name for p in (ROOT / "migrations").glob("[0-9][0-9][0-9][0-9]_*.sql"))


def restore(url: str, dump: Path) -> list[SimChat]:
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(dump.read_text())
    recorded = json.loads(dump.with_suffix(".chat.json").read_text())
    chats = []
    for c in recorded["chats"]:
        chat = SimChat(c["id"])
        chat.messages = c["messages"]
        chats.append(chat)
    return chats


def objects(client, chat: SimChat, subject: str, predicate: str) -> set[str]:
    return {f["object"] for f in facts(client, chat) if f["subject"] == subject and f["predicate"] == predicate}


@pytest.mark.parametrize("dump", FIXTURES, ids=[p.stem for p in FIXTURES])
def test_a_database_of_an_earlier_release_upgrades_and_keeps_working(dump, database_url):
    main, branch = restore(database_url, dump)
    with psycopg.connect(database_url) as conn:  # extracted per message: before extract-v4 (ADR 0008)
        per_message = conn.execute(
            "SELECT EXISTS (SELECT 1 FROM extraction e JOIN projection_generation g ON g.key = e.extractor_key"
            " WHERE coalesce(g.spec->>'unit', 'message') = 'message')").fetchone()[0]
    applied = apply_migrations(database_url)
    # A release with today's schema (0.3.0 → 0.4.0 adds no migration) has nothing left to apply.
    assert (applied or [LATEST])[-1] == LATEST
    with psycopg.connect(database_url) as conn:
        assert conn.execute("SELECT 1 FROM schema_migrations WHERE version = %s", (LATEST,)).fetchone()

    with make_client(database_url, embedder=FakeEmbedder(), **LLM, **EMB) as c:  # startup backfills run here
        assert c.get("/v1/health").status_code == 200
        convs = {x["host_chat_ref"]: x["id"] for x in c.get("/v1/conversations").json()}
        assert set(convs) == {main.id, branch.id}

        # The host still shows what the earlier release recorded: nothing to sync.
        assert sync(c, main)["status"] == "noop"
        assert sync(c, branch)["status"] == "noop"
        # Facts that release extracted per turn are served until the current extractor covers their turns
        # (ADR 0014); per-message extractions are not (ADR 0031) and come back once re-extracted.
        assert ("bell tower" in objects(c, main, "Mina", "located_in")) is not per_message
        if not per_message:  # Phase 11: its promise reads as an open thread, its relationship as one pair
            page = c.get(f"/inspector/c/{convs[main.id]}", params={"lang": "en"}).text
            section = lambda sid: page[page.index(f'id="s-{sid}"'):page.index("</details>", page.index(f'id="s-{sid}"'))]
            promise = next(row for row in section("threads").split("<tr>") if "return before the bell rings" in row)
            assert 'title="open"' in promise
            pairs = section("pairs")
            assert 'Relationships <span class="n">1</span>' in pairs and pairs.count("Mina ↔ Rin") == 1
            # Phase 13: the owner closes that thread on the upgraded chat (migration 0024), and takes it back.
            cid = convs[main.id]
            promise = next(t for t in c.get(f"/v1/conversations/{cid}/threads").json()
                           if "return before the bell rings" in t["text"])
            made = c.post(f"/v1/conversations/{cid}/repairs", json={"kind": "thread_close", "item": str(promise["id"])})
            assert made.status_code == 200 and made.json()["applied"], made.text
            status = lambda: next(t["status"] for t in c.get(f"/v1/conversations/{cid}/threads").json()
                                  if "return before the bell rings" in t["text"])
            assert status() == "kept"
            undo = c.post(f"/v1/conversations/{cid}/repairs/{made.json()['repair']['id']}/remove")
            assert undo.status_code == 200 and status() == "open"
        old_trace = c.get(f"/v1/conversations/{convs[main.id]}/traces").json()
        assert old_trace, "the earlier release's recall traces are kept"
        # Packets an earlier release recorded (since the ledger, beta.19) replay under their own policy; one
        # whose story is unchanged and needs no vectors of another embedder compiles the same (Phase 9).
        for t in old_trace:
            replayed = c.get(f"/v1/trace/{t['id']}/replay").json()
            assert replayed["status"] in ("ok", "not_recorded", "changed"), replayed
            if replayed["status"] == "ok" and not replayed["notes"]:
                assert replayed["reproduced"] is True, (dump.stem, replayed["policy"])

        # The story goes on: an append, a recall that replays as recorded, an edit.
        main.reply("Mina is in the garden.")
        main.user("Where is Mina?")
        assert sync(c, main)["status"] == "applied"
        out = recall(c, main, "Where is Mina?")
        assert out["packet"]["text"]
        assert c.get(f"/v1/trace/{out['trace_id']}/replay").json()["reproduced"] is True
        main.edit(1, "Mina is in the crypt. Mina has the brass key.")
        assert sync(c, main)["status"] == "applied"
        assert c.get(f"/inspector/c/{convs[main.id]}").status_code == 200
        # Phase 10: an upgraded chat has the default memory mode (migration 0021) and takes another.
        mode = c.get(f"/v1/conversations/{convs[main.id]}/memory-mode").json()
        assert (mode["strict"], mode["narrator"]) == (False, None)
        assert c.put(f"/v1/conversations/{convs[main.id]}/memory-mode", json={"strict": True}).json()["strict"]
        assert set(recall(c, main, "Where is Mina?")["memory"]) == {"offered", "cut", "fits_at"}  # ADR 0036
        # Phase 12: once the story makes a window due, the upgraded chat has its scene summary queued (ADR 0042).
        for i in range(14):
            main.reply(f"Mina walks on, step {i}.")
            main.user(f"And then, step {i}?")
        assert sync(c, main)["status"] == "applied"

    # The current worker re-derives with the current generations, without a failed job.
    drain(database_url)
    drain_embeddings(database_url)
    assert drain_summaries(database_url) >= 3  # both windows the append made due, then the story so far
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        failed = conn.execute("SELECT kind, last_error FROM job WHERE last_error IS NOT NULL").fetchall()
    assert failed == []

    with make_client(database_url, embedder=FakeEmbedder(), **LLM, **EMB) as c:
        assert "garden" in objects(c, main, "Mina", "located_in")
        assert "old chapel" not in objects(c, main, "Mina", "located_in")  # edited away: masked (invariant 7)
        assert '<Summary kind="story"' in recall(c, main, "Where is Mina?", budget=2000)["packet"]["text"]
        assert c.post(f"/v1/conversations/{convs[branch.id]}/delete").status_code == 200
        assert {x["host_chat_ref"] for x in c.get("/v1/conversations").json()} == {main.id}
        # Phase 14: the upgraded chat takes its canon (migrations 0025, 0026, ADR 0045, 0047).
        card = {"card:name": ("Mina", {"field": "name"}), "card:desc": ("{{char}} is in the lighthouse.", {"field": "desc"})}
        assert push(c, main, card)["applied"]
    model = Model()
    assert drain_canon(database_url, model) == 1 and len(model.canon_calls()) == 1  # the card, read once
    (place,) = current(view(database_url, main), "Mina", "located_in")  # canon is before turn 0; the story supersedes it
    assert place["object"] == "garden" and place["history"][0]["canon"] == "card:desc"
    assert place["history"][0]["object"] == "lighthouse" and place["history"][0]["outcome"] == "superseded"
    assert rebuild_all(database_url)
