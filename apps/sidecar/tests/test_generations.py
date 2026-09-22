"""D20: extractor generations (#6), embedding projections (#7) and generation coverage (#8)."""

from __future__ import annotations

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import active_generation, make_client
from nmos_sidecar import extraction
from nmos_sidecar.config import Settings
from nmos_sidecar.generations import endpoint_identity
from nmos_sidecar.worker import handlers, run_once
from simchat import SimChat
from test_extraction import drain, facts, filler
from test_sidecar_integration import recall, sync
from test_vectors import FakeEmbedder, build_chat, drain_embeddings

LLM = {"llm_url": "http://fake-llm/v1", "llm_model": "fake"}
EMB = {"embed_url": "http://fake-emb/v1", "embed_model": "fake-embed"}


def queued(db, kind: str) -> int:
    return db.execute("SELECT count(*) AS n FROM job WHERE kind = %s AND status = 'queued'", (kind,)).fetchone()["n"]


def conv_id(client, chat) -> str:
    return next(c["id"] for c in client.get("/v1/conversations").json() if c["host_chat_ref"] == chat.id)


def fact_chat() -> SimChat:
    chat = SimChat()
    chat.user("Hinata is in the old chapel.")
    chat.reply("The chapel is quiet.")
    filler(chat, 5)
    return chat


# --- #6 extractor generation ---------------------------------------------------------------------

def test_generation_key_ignores_credentials_and_url_spelling():
    base = Settings(database_url="", **LLM)
    same = [Settings(database_url="", llm_api_key="sk-other", **LLM),
            Settings(database_url="", llm_url="HTTP://Fake-LLM/v1/", llm_model="fake")]
    assert all(extraction.extractor(s).key == extraction.extractor(base).key for s in same)
    assert extraction.extractor(Settings(database_url="", llm_url="http://other/v1", llm_model="fake")).key \
        != extraction.extractor(base).key
    assert endpoint_identity("https://API.example.com:8443/v1/") == "https://api.example.com:8443/v1"


def test_changing_llm_model_reextracts_existing_chat(migrated, db):
    with make_client(migrated, **LLM) as c:
        chat = fact_chat()
        sync(c, chat)
        drain(migrated)
        old = active_generation(db, "extract")
        assert [f["object"] for f in facts(c, chat)] == ["old chapel"]
        out = c.put("/v1/config", json={"llm_model": "fake-2"}).json()
        eligible = len(chat.messages) - 1
        assert out["queued_jobs"] == eligible  # every pair the old generation covered is rebuilt
        new = active_generation(db, "extract")
        assert new.key != old.key and new.model == "fake-2"
        assert c.get("/v1/health").json()["generations"]["extract"] == new.key
        # Facts come only from the active generation: nothing until the new model has run.
        assert facts(c, chat) == []
        drain(migrated)
        assert [f["object"] for f in facts(c, chat)] == ["old chapel"]
        # The old generation stays for audit.
        by_gen = {r["extractor_key"]: r["n"] for r in db.execute(
            "SELECT extractor_key, count(*) AS n FROM extraction GROUP BY 1").fetchall()}
        assert by_gen == {old.key: eligible, new.key: eligible}


def test_changing_llm_endpoint_reextracts_existing_chat(migrated, db):
    with make_client(migrated, **LLM) as c:
        chat = fact_chat()
        sync(c, chat)
        drain(migrated)
        out = c.put("/v1/config", json={"llm_url": "http://other-provider/v1"}).json()
        assert out["queued_jobs"] == len(chat.messages) - 1
        assert active_generation(db, "extract").endpoint == "http://other-provider/v1"


def test_changing_only_llm_api_key_does_not_reextract(migrated, db):
    with make_client(migrated, **LLM) as c:
        chat = fact_chat()
        sync(c, chat)
        drain(migrated)
        key = active_generation(db, "extract").key
        out = c.put("/v1/config", json={"llm_api_key": "sk-rotated"}).json()
        assert out["queued_jobs"] == 0 and queued(db, "extract") == 0
        assert active_generation(db, "extract").key == key
        assert [f["object"] for f in facts(c, chat)] == ["old chapel"]


def test_worker_does_not_process_new_generation_job_with_old_handler(migrated, db):
    with make_client(migrated, **LLM) as c:
        chat = fact_chat()
        sync(c, chat)
        old_handlers = handlers(Settings(database_url=migrated, **LLM))  # the worker before its 30 s reload
        c.put("/v1/config", json={"llm_model": "fake-2"})
    pending = queued(db, "extract")
    assert pending == len(chat.messages) - 1
    # The old model's queued jobs became obsolete; the new ones are not claimable by the old handler.
    assert db.execute("SELECT count(*) AS n FROM job WHERE status = 'obsolete'").fetchone()["n"] == pending
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        assert run_once(conn, old_handlers) is False
    assert queued(db, "extract") == pending
    assert db.execute("SELECT count(*) AS n FROM extraction").fetchone()["n"] == 0


def test_generation_mismatch_is_refused_even_if_claimed(migrated, db):
    from nmos_sidecar.extraction import process_extract
    with make_client(migrated, **LLM) as c:
        sync(c, fact_chat())
    job = db.execute("SELECT * FROM job WHERE kind = 'extract' LIMIT 1").fetchone()
    other = extraction.extractor(Settings(database_url="", llm_url="http://x/v1", llm_model="y"))
    with pytest.raises(ValueError, match="generation"):
        process_extract(db, job, lambda s, u: ({}, ""), other, 6)


# --- #8 coverage across generation changes --------------------------------------------------------

def long_chat(n: int = 15) -> SimChat:
    chat = SimChat()
    filler(chat, n)
    chat.user("last")
    return chat


def test_compiler_upgrade_tracks_partial_coverage_and_backfills_beyond_recent_window(migrated, db, monkeypatch):
    chat = long_chat()
    eligible = len(chat.messages)
    with make_client(migrated, extract_backfill=100, **LLM) as c:
        sync(c, chat)
        drain(migrated)
        cid = conv_id(c, chat)
        cov = c.get(f"/v1/conversations/{cid}/coverage").json()["extraction"]
        assert (cov["compiled"], cov["eligible"], cov["complete"]) == (eligible, eligible, True)

    monkeypatch.setattr(extraction, "COMPILER_VERSION", "extract-next")  # a compiler upgrade
    with make_client(migrated, extract_backfill=4, **LLM) as c:
        cov = c.get(f"/v1/conversations/{cid}/coverage").json()["extraction"]
        # Recent window first, the rest of the previously covered history at background priority.
        prio = [r["priority"] for r in db.execute(
            "SELECT priority FROM job WHERE status = 'queued' ORDER BY priority").fetchall()]
        assert prio == [extraction.RECENT_PRIORITY] * 4 + [extraction.HISTORY_PRIORITY] * (eligible - 4)
        assert cov["complete"] is False and cov["compiled"] == 0 and cov["pending"] == eligible
        assert cov["historical_only"] == eligible and cov["generation"]["spec"]["compiler"] == "extract-next"
        assert "partial" in c.get("/inspector").text
        drain(migrated)
        cov = c.get(f"/v1/conversations/{cid}/coverage").json()["extraction"]
        assert (cov["compiled"], cov["percent"], cov["complete"]) == (eligible, 100.0, True)
    # The previous generation's extractions are kept for audit.
    assert db.execute("SELECT count(*) AS n FROM extraction WHERE compiler_version <> 'extract-next'"
                      ).fetchone()["n"] == eligible


def test_historical_generation_does_not_trigger_permanent_stale_startup_loop(migrated, db):
    chat = long_chat(4)
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        drain(migrated)
        c.put("/v1/config", json={"llm_model": "fake-2"})
        drain(migrated)
    db.execute("DELETE FROM job WHERE status IN ('done', 'obsolete')")  # what prune() does after 7 days
    for _ in range(2):
        with make_client(migrated, llm_url=LLM["llm_url"], llm_model="fake-2"):
            pass
        assert db.execute("SELECT count(*) AS n FROM job").fetchone()["n"] == 0


def test_failed_jobs_count_against_completeness(migrated, db):
    chat = long_chat(3)
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        db.execute("UPDATE job SET status = 'dead' WHERE id = (SELECT min(id) FROM job)")
        drain(migrated)
        cov = c.get(f"/v1/conversations/{conv_id(c, chat)}/coverage").json()["extraction"]
    assert cov["failed"] == 1 and cov["complete"] is False and cov["compiled"] == cov["eligible"] - 1


# --- #7 embedding projection -----------------------------------------------------------------------

def vec_client(url, **extra):
    return make_client(url, embedder=FakeEmbedder(), **{**EMB, **extra})


def test_same_model_new_endpoint_reembeds_and_query_never_searches_old_projection(migrated, db):
    chat = build_chat()
    with vec_client(migrated) as c:
        sync(c, chat)
        drain_embeddings(migrated)
        old = active_generation(db, "embed")
        query = "혹시 그 반짝이는 은빛 물건은 어디 숨겼지?"
        assert "등대 지하" in recall(c, chat, query, in_context=[])["packet"]["text"]
        out = c.put("/v1/config", json={"embed_url": "http://other-emb/v1"}).json()
        embedded = db.execute("SELECT count(DISTINCT source_revision_id) AS n FROM revision_embedding").fetchone()["n"]
        assert out["queued_jobs"] == embedded
        new = active_generation(db, "embed")
        assert new.key != old.key and new.model == old.model
        # Same model name and dimensions, but the old corpus vectors are a different space.
        res = recall(c, chat, query, in_context=[])
        trace = c.get(f"/v1/trace/{res['trace_id']}").json()
        assert trace["latency_ms"]["vector_mode"] == "on"
        assert all(cand["sim"] is None for cand in trace["candidates"])
        assert trace["latency_ms"]["embedding_projection"] == new.key[:20]
        drain_embeddings(migrated)
        assert "등대 지하" in recall(c, chat, query, in_context=[])["packet"]["text"]


def test_changing_only_embedding_api_key_does_not_reembed(migrated, db):
    chat = build_chat()
    with vec_client(migrated) as c:
        sync(c, chat)
        drain_embeddings(migrated)
        key = active_generation(db, "embed").key
        assert c.put("/v1/config", json={"embed_api_key": "sk-rotated"}).json()["queued_jobs"] == 0
        assert active_generation(db, "embed").key == key and queued(db, "embed") == 0


def test_multiple_embedding_projections_can_coexist(migrated, db):
    chat = build_chat()
    with vec_client(migrated) as c:
        sync(c, chat)
        drain_embeddings(migrated)
        c.put("/v1/config", json={"embed_model": "fake-embed-2"})
        drain_embeddings(migrated)
        projections = db.execute("SELECT count(DISTINCT projection) AS n FROM revision_embedding").fetchone()["n"]
        assert projections == 2
        # Switching back reuses the complete first projection: nothing to re-embed.
        assert c.put("/v1/config", json={"embed_model": None}).json()["queued_jobs"] == 0
        cov = c.get(f"/v1/conversations/{conv_id(c, chat)}/coverage").json()["embeddings"]
        assert cov["complete"] is True and cov["generation"]["model"] == "fake-embed"


def test_worker_does_not_process_new_embedding_job_with_old_handler(migrated, db):
    chat = build_chat()
    with vec_client(migrated) as c:
        sync(c, chat)
        old_handlers = handlers(Settings(database_url=migrated, **EMB))
        c.put("/v1/config", json={"embed_url": "http://other-emb/v1"})
    pending = queued(db, "embed")
    assert pending > 0
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        assert run_once(conn, old_handlers) is False
    assert queued(db, "embed") == pending


def test_pre_projection_vectors_are_adopted_once(migrated, db):
    chat = build_chat()
    with make_client(migrated) as c:  # no embeddings configured yet
        sync(c, chat)
    rid = db.execute("SELECT id FROM source_revision ORDER BY id LIMIT 1").fetchone()["id"]
    db.execute("INSERT INTO revision_embedding (source_revision_id, projection, model, chunk, dim, text_start, text_end,"
               " embedding) VALUES (%s, 'legacy:fake-embed', 'fake-embed', 0, 3, 0, 5, '[1,0,0]')", (rid,))
    with vec_client(migrated):
        pass
    key = active_generation(db, "embed").key
    assert db.execute("SELECT projection FROM revision_embedding").fetchone()["projection"] == key
