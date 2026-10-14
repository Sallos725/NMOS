"""D22: per-chat "extract all history" and "rebuild memory" (ADR 0008)."""

from __future__ import annotations

from conftest import make_client
from nmos_sidecar import extraction
from simchat import SimChat
from test_extraction import drain, facts, filler
from test_generations import EMB, LLM, conv_id
from test_sidecar_integration import sync
from test_vectors import FakeEmbedder, drain_embeddings


def history_chat() -> SimChat:
    chat = SimChat()
    chat.user("Akari is in the old chapel.")
    chat.reply("The chapel is quiet.")
    filler(chat, 7)
    chat.user("last")
    return chat


def extract_jobs(db) -> int:
    return db.execute("SELECT count(*) AS n FROM job WHERE kind = 'extract' AND status = 'queued'").fetchone()["n"]


def test_extract_history_queues_what_first_sight_left_out(migrated, db):
    with make_client(migrated, embedder=FakeEmbedder(), extract_backfill=2, embed_backfill=4, **LLM, **EMB) as c:
        chat = history_chat()
        sync(c, chat)
        drain(migrated)
        drain_embeddings(migrated)
        cid = conv_id(c, chat)
        assert facts(c, chat) == []  # turn 0 is older than the first-sight backfill
        out = c.post(f"/v1/conversations/{cid}/extract-history").json()
        assert out["queued"] == {"extract": 6, "embed": len(chat.messages) - 4, "canon": 0, "reveal": 0}
        assert out["coverage"]["extraction"]["pending"] == 6
        drain(migrated)
        drain_embeddings(migrated)
        cov = c.get(f"/v1/conversations/{cid}/coverage").json()
        assert cov["extraction"]["complete"] and cov["embeddings"]["complete"]
        assert [f["object"] for f in facts(c, chat)] == ["old chapel"]
        # Idempotent: nothing is missing any more.
        assert c.post(f"/v1/conversations/{cid}/extract-history").json()["queued"] == {"extract": 0, "embed": 0, "canon": 0, "reveal": 0}


def test_rebuild_discards_and_reextracts_every_turn(migrated, db):
    calls = []

    def complete(system, user):
        from test_extraction import fake_complete
        calls.append(user)
        return fake_complete(system, user)

    with make_client(migrated, extract_backfill=3, **LLM) as c:
        chat = history_chat()
        sync(c, chat)
        cid = conv_id(c, chat)
        c.post(f"/v1/conversations/{cid}/extract-history")
        drain(migrated, complete)
        assert [f["object"] for f in facts(c, chat)] == ["old chapel"] and len(calls) == 8
        out = c.post(f"/v1/conversations/{cid}/rebuild").json()
        assert out["discarded"] == 8 and out["queued"] == {"extract": 8, "canon": 0}
        # Facts disappear at once (discarded extractions never match) and coverage is partial.
        assert facts(c, chat) == [] and out["coverage"]["extraction"]["compiled"] == 0
        prio = sorted(r["priority"] for r in db.execute("SELECT priority FROM job WHERE status = 'queued'"))
        assert prio == [250] * 3 + [900] * 5  # recent backfill first
        drain(migrated, complete)
        assert len(calls) == 16 and [f["object"] for f in facts(c, chat)] == ["old chapel"]
    rows = db.execute("SELECT count(*) FILTER (WHERE discarded_at IS NULL) AS live, count(*) AS total"
                      " FROM extraction").fetchone()
    assert (rows["live"], rows["total"]) == (8, 16)  # the discarded run stays for audit


def test_interrupted_rebuild_is_completed_by_the_next_scheduling_run(migrated, db):
    from nmos_sidecar import extraction
    from conftest import active_generation
    with make_client(migrated, extract_backfill=2, **LLM) as c:
        chat = history_chat()
        sync(c, chat)
        c.post(f"/v1/conversations/{conv_id(c, chat)}/extract-history")
        drain(migrated)
        extraction.discard(db, conv_id(c, chat))  # crashed before queueing
    with make_client(migrated, extract_backfill=2, **LLM):
        pass  # startup scheduling
    assert extract_jobs(db) == 8


def test_actions_refuse_unknown_chats_and_disabled_providers(client, migrated):
    chat = history_chat()
    sync(client, chat)
    cid = conv_id(client, chat)
    missing = "00000000-0000-7000-8000-000000000000"
    assert client.post(f"/v1/conversations/{missing}/rebuild").status_code == 404
    assert client.post(f"/v1/conversations/{missing}/retry-failed").status_code == 404
    assert client.post(f"/v1/conversations/{cid}/rebuild").status_code == 409
    assert client.post(f"/v1/conversations/{cid}/extract-history").status_code == 409
    assert client.post(f"/v1/conversations/{cid}/retry-failed").status_code == 409


def test_retry_failed_requeues_the_dead_jobs_only(migrated, db):
    """The panel's "retry failed" (owner, 2026-10-14): a dead job of this chat runs again, an old turn's too, and
    nothing else is queued, unlike "extract all history"."""
    with make_client(migrated, extract_backfill=2, **LLM) as c:
        chat = history_chat()
        sync(c, chat)
        cid = conv_id(c, chat)
        c.post(f"/v1/conversations/{cid}/extract-history")
        # One recent turn and one older than the backfill fail for good; the rest are extracted.
        dead = [r["id"] for r in db.execute(
            "(SELECT id FROM job WHERE kind = 'extract' ORDER BY priority LIMIT 1)"
            " UNION ALL (SELECT id FROM job WHERE kind = 'extract' ORDER BY priority DESC LIMIT 1)")]
        db.execute("UPDATE job SET status = 'dead', attempts = 5, last_error = 'HTTP 401 <bad key>' WHERE id = ANY(%s)",
                   (dead,))
        drain(migrated)
        cov = c.get(f"/v1/conversations/{cid}/coverage", params={"usage": "true"}).json()
        assert cov["extraction"]["failed"] == 2
        assert [e["error"] for e in cov["failed_errors"]] == ["HTTP 401 <bad key>"] * 2
        assert "failed_errors" not in c.get(f"/v1/conversations/{cid}/coverage").json()  # the HUD's polls
        out = c.post(f"/v1/conversations/{cid}/retry-failed").json()
        assert out["retried"]["extract"] == 2 and sum(out["retried"].values()) == 2
        assert out["coverage"]["extraction"]["pending"] == 2
        rows = db.execute("SELECT id, attempts, last_error FROM job WHERE status = 'queued'").fetchall()
        assert sorted(r["id"] for r in rows) == sorted(dead) and all(r["attempts"] == 0 for r in rows)
        assert all(r["last_error"] is None for r in rows)
        drain(migrated)
        assert c.get(f"/v1/conversations/{cid}/coverage").json()["extraction"]["complete"]
        assert c.post(f"/v1/conversations/{cid}/retry-failed").json()["retried"]["extract"] == 0


def test_mass_delete_hides_facts_and_a_restored_range_reuses_its_extractions(migrated, db):
    """ADR 0008 §5: "delete all below" is an ordinary reconciliation; nothing is re-extracted for a
    tail cut, and a snapshot that shows the range again gets its facts back without model calls."""
    calls = []

    def complete(system, user):
        from test_extraction import fake_complete
        calls.append(user)
        return fake_complete(system, user)

    with make_client(migrated, **LLM) as c:
        chat = SimChat()
        filler(chat, 3)
        chat.user("Akari is in the old chapel.")
        chat.reply("ok")
        chat.user("Akari moved to the bell tower.")
        chat.reply("ok")
        filler(chat, 2, "b")
        chat.user("last")
        sync(c, chat)
        drain(migrated, complete)
        assert [f["object"] for f in facts(c, chat)] == ["bell tower"]
        full = list(chat.messages)
        chat.messages = full[:8]  # delete everything below the chapel turn
        out = sync(c, chat)
        assert out["changes_summary"] == {"delete": len(full) - 8}
        assert [f["object"] for f in facts(c, chat)] == ["old chapel"]
        assert db.execute("SELECT count(*) AS n FROM job WHERE status = 'queued'").fetchone()["n"] == 0
        before = len(calls)
        chat.messages = full  # e.g. a later full snapshot after a truncated one
        sync(c, chat)
        drain(migrated, complete)
        assert len(calls) == before and [f["object"] for f in facts(c, chat)] == ["bell tower"]


def test_extract_history_retries_failed_turns(migrated, db):
    with make_client(migrated, extract_backfill=2, **LLM) as c:
        chat = history_chat()
        sync(c, chat)
        db.execute("UPDATE job SET status = 'dead', attempts = 5 WHERE kind = 'extract'")
        cid = conv_id(c, chat)
        assert c.get(f"/v1/conversations/{cid}/coverage").json()["extraction"]["failed"] == 2
        assert c.post(f"/v1/conversations/{cid}/extract-history").json()["queued"]["extract"] == 8
        assert db.execute("SELECT count(*) AS n FROM job WHERE status = 'queued' AND attempts = 0").fetchone()["n"] == 8
        # A generation's backfill and history are claimed oldest first within a priority (claim(), PHASE-10):
        # the earlier generation serves those turns meanwhile.
        order = [r["t"] for r in db.execute(
            "SELECT (SELECT am.turn FROM active_membership am JOIN conversation cv ON cv.head_commit_id = am.commit_id"
            " WHERE am.source_revision_id = (j.payload->>'revision_id')::uuid) AS t"
            " FROM job j WHERE j.status = 'queued'"
            " ORDER BY j.priority, CASE WHEN j.priority >= %s THEN j.id ELSE -j.id END", (extraction.RECENT_PRIORITY,))]
        assert order[:2] == [6, 7] and order[2:] == [0, 1, 2, 3, 4, 5]


def test_failed_errors_leave_out_an_earlier_generation(migrated, db):
    """No retry runs an earlier generation's dead job, and no count shows it: its error is not shown either."""
    with make_client(migrated, extract_backfill=2, **LLM) as c:
        chat = history_chat()
        sync(c, chat)
        cid = conv_id(c, chat)
        db.execute("UPDATE job SET status = 'dead', last_error = 'old model gone',"
                   " payload = jsonb_set(payload, '{generation}', '\"extract:earlier\"') WHERE kind = 'extract'")
        cov = c.get(f"/v1/conversations/{cid}/coverage", params={"usage": "true"}).json()
        assert cov["failed_errors"] == [] and c.post(f"/v1/conversations/{cid}/retry-failed").json()["retried"]["extract"] == 0
