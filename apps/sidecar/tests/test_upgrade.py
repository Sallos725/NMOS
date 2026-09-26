"""Databases written by earlier releases upgrade and keep working (audit A-16).

Each `fixtures/upgrade/<release>.sql` is a `pg_dump` of a database that release's own sidecar and worker
wrote (`tools/make_upgrade_fixture.py`): two chats with edits, a reroll, a swipe, a disabled message and
a branch, extractions, embeddings and recall traces. `<release>.chat.json` is the chats as the host last
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
from test_extraction import drain, facts
from test_generations import EMB, LLM
from test_sidecar_integration import recall, sync
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
    applied = apply_migrations(database_url)
    assert applied and applied[-1] == LATEST

    with make_client(database_url, embedder=FakeEmbedder(), **LLM, **EMB) as c:  # startup backfills run here
        assert c.get("/v1/health").status_code == 200
        convs = {x["host_chat_ref"]: x["id"] for x in c.get("/v1/conversations").json()}
        assert set(convs) == {main.id, branch.id}

        # The host still shows what the earlier release recorded: nothing to sync.
        assert sync(c, main)["status"] == "noop"
        assert sync(c, branch)["status"] == "noop"
        # Facts that release extracted are served until the current extractor covers their turns (ADR 0014).
        assert "bell tower" in objects(c, main, "Mina", "located_in")
        old_trace = c.get(f"/v1/conversations/{convs[main.id]}/traces").json()
        assert old_trace, "the earlier release's recall traces are kept"

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

    # The current worker re-derives with the current generations, without a failed job.
    drain(database_url)
    drain_embeddings(database_url)
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        failed = conn.execute("SELECT kind, last_error FROM job WHERE last_error IS NOT NULL").fetchall()
    assert failed == []

    with make_client(database_url, embedder=FakeEmbedder(), **LLM, **EMB) as c:
        assert "garden" in objects(c, main, "Mina", "located_in")
        assert "old chapel" not in objects(c, main, "Mina", "located_in")  # edited away: masked (invariant 7)
        assert recall(c, main, "Where is Mina?")["packet"]["text"]
        assert c.post(f"/v1/conversations/{convs[branch.id]}/delete").status_code == 200
        assert {x["host_chat_ref"] for x in c.get("/v1/conversations").json()} == {main.id}
    assert rebuild_all(database_url)
