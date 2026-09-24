"""O5 retention (ADR 0015): superseded embeddings and normalized text are pruned once replaced;
superseded LLM extractions are kept."""

from __future__ import annotations

from conftest import active_generation, make_client
from nmos_sidecar import normtext, retention
from nmos_sidecar.worker import prune
from test_extraction import drain, fake_complete
from test_generations import EMB, LLM, beta3_upgrade, conv_id, fact_chat, queued, vec_client, QUERY
from test_sidecar_integration import recall, sync
from test_vectors import build_chat, drain_embeddings


def by_projection(db) -> dict[str, int]:
    return {r["projection"]: r["n"] for r in db.execute(
        "SELECT projection, count(DISTINCT source_revision_id) AS n FROM revision_embedding GROUP BY 1").fetchall()}


def switched(c, url, db, chat):
    """A chat embedded by projection A, then the embedding model changed to B (nothing drained yet)."""
    sync(c, chat)
    drain_embeddings(url)
    old = active_generation(db, "embed").key
    c.put("/v1/config", json={"embed_model": "fake-embed-2"})
    return old, active_generation(db, "embed").key


def test_superseded_vectors_are_pruned_once_the_new_projection_covers_the_chat(migrated, db):
    chat = build_chat()
    with vec_client(migrated) as c:
        old, new = switched(c, migrated, db, chat)
        n = by_projection(db)[old]
        assert retention.prune_embeddings(db) == 0  # B has not embedded anything yet: A stays
        drain_embeddings(migrated)
        assert by_projection(db) == {old: n, new: n}
        prune(db, 30)  # the worker's maintenance pass
        assert by_projection(db) == {new: n}
        assert retention.prune_embeddings(db) == 0  # idempotent
        assert "등대 지하" in recall(c, chat, QUERY, in_context=[])["packet"]["text"]
        cov = c.get(f"/v1/conversations/{conv_id(c, chat)}/coverage").json()["embeddings"]
        assert cov["complete"] is True


def test_nothing_is_pruned_while_the_new_projection_has_work_pending(migrated, db):
    chat = build_chat()
    with vec_client(migrated) as c:
        old, new = switched(c, migrated, db, chat)
        # One job runs; the rest stay queued. The revision B already embedded keeps its A vectors too.
        with_jobs = queued(db, "embed")
        assert with_jobs > 1
        db.execute("UPDATE job SET run_after = now() + interval '1 hour' WHERE kind = 'embed' AND status = 'queued'"
                   " AND id <> (SELECT max(id) FROM job WHERE kind = 'embed' AND status = 'queued')")
        assert drain_embeddings(migrated) == 1
        assert retention.prune_embeddings(db) == 0
        assert by_projection(db)[old] == by_projection(db)[new] + with_jobs - 1


def test_a_failed_revision_keeps_the_chat_from_being_pruned(migrated, db):
    chat = build_chat()
    with vec_client(migrated) as c:
        old, new = switched(c, migrated, db, chat)
        db.execute("UPDATE job SET status = 'dead' WHERE id = (SELECT max(id) FROM job WHERE kind = 'embed'"
                   " AND status = 'queued')")
        drain_embeddings(migrated)
        assert retention.prune_embeddings(db) == 0
        n = by_projection(db)[old]
        assert by_projection(db)[new] == n - 1


def test_each_chat_is_pruned_on_its_own_coverage(migrated, db):
    done, waiting = build_chat(), build_chat()
    with vec_client(migrated) as c:
        sync(c, done)
        sync(c, waiting)
        drain_embeddings(migrated)
        old = active_generation(db, "embed").key
        c.put("/v1/config", json={"embed_model": "fake-embed-2"})
        waiting_id = conv_id(c, waiting)
        db.execute("UPDATE job SET run_after = now() + interval '1 hour' WHERE kind = 'embed' AND status = 'queued'"
                   " AND conversation_id = %s", (waiting_id,))
        drain_embeddings(migrated)
        assert retention.prune_embeddings(db) > 0
        left = db.execute("SELECT DISTINCT so.conversation_id AS conv FROM revision_embedding re"
                          " JOIN source_revision sr ON sr.id = re.source_revision_id"
                          " JOIN source_object so ON so.id = sr.source_object_id WHERE re.projection = %s",
                          (old,)).fetchall()
        assert [str(r["conv"]) for r in left] == [waiting_id]


def test_vectors_of_revisions_off_the_head_are_kept(migrated, db):
    chat = build_chat()
    with vec_client(migrated) as c:
        sync(c, chat)
        drain_embeddings(migrated)
        old = active_generation(db, "embed").key
        chat.edit(0, "하나는 은빛 열쇠를 등대 꼭대기에 숨겼다.")  # the first revision leaves the head
        sync(c, chat)
        drain_embeddings(migrated)
        edited_away = by_projection(db)[old]
        c.put("/v1/config", json={"embed_model": "fake-embed-2"})
        drain_embeddings(migrated)
        assert retention.prune_embeddings(db) == edited_away - 1  # only the old first revision stays
        assert by_projection(db)[old] == 1


def test_legacy_vectors_are_pruned_after_the_upgrade_reembeds_them(migrated, db):
    chat = build_chat()
    legacy = beta3_upgrade(migrated, db, chat)
    with vec_client(migrated, embed_url="http://endpoint-b/v1", embed_backfill=1) as c:
        key = active_generation(db, "embed").key
        assert retention.prune_embeddings(db) == 0
        drain_embeddings(migrated)
        assert retention.prune_embeddings(db) == len(legacy)
        assert by_projection(db) == {key: len(legacy)}
        text = recall(c, chat, QUERY, in_context=[])["packet"]["text"]
        assert "등대 지하" in text and "잡담 3" not in text


def test_switching_back_after_pruning_reembeds(migrated, db):
    chat = build_chat()
    with vec_client(migrated) as c:
        old, new = switched(c, migrated, db, chat)
        drain_embeddings(migrated)
        n = by_projection(db)[new]
        retention.prune_embeddings(db)
        assert c.put("/v1/config", json={"embed_model": None}).json()["queued_jobs"] == n
        assert drain_embeddings(migrated) == n
        retention.prune_embeddings(db)
        assert by_projection(db) == {old: n}


def test_superseded_llm_extractions_are_kept(migrated, db):
    chat = fact_chat()
    with make_client(migrated, **LLM, **EMB) as c:
        sync(c, chat)
        drain(migrated, fake_complete)
        old = active_generation(db, "extract").key
        c.put("/v1/config", json={"llm_model": "fake-2"})
        drain(migrated, fake_complete)
        before = db.execute("SELECT count(*) AS n FROM extraction WHERE extractor_key = %s", (old,)).fetchone()["n"]
        assertions = db.execute("SELECT count(*) AS n FROM assertion").fetchone()["n"]
        assert before > 0
        prune(db, 30)
        assert db.execute("SELECT count(*) AS n FROM extraction WHERE extractor_key = %s",
                          (old,)).fetchone()["n"] == before
        assert db.execute("SELECT count(*) AS n FROM assertion").fetchone()["n"] == assertions


def test_older_normalizer_text_is_pruned_at_startup(migrated, db):
    chat = build_chat()
    with make_client(migrated) as c:
        sync(c, chat)
    rows = db.execute("SELECT source_revision_id AS id, clean_content FROM revision_text").fetchall()
    for r in rows:
        db.execute("INSERT INTO revision_text (source_revision_id, normalizer, clean_content, original_chars,"
                   " clean_chars) VALUES (%s, 'clean-v1', %s, 1, 1)", (r["id"], r["clean_content"]))
    # A revision whose current row is missing keeps its older text until the current one is written.
    lone = rows[0]["id"]
    db.execute("DELETE FROM revision_text WHERE source_revision_id = %s AND normalizer = %s",
               (lone, normtext.NORMALIZER_VERSION))
    assert retention.prune_text(db) == len(rows) - 1
    assert db.execute("SELECT normalizer FROM revision_text WHERE source_revision_id = %s",
                      (lone,)).fetchone()["normalizer"] == "clean-v1"
    with make_client(migrated):  # startup: backfill writes the current row, then the older one goes
        pass
    counts = {r["normalizer"]: r["n"] for r in db.execute(
        "SELECT normalizer, count(*) AS n FROM revision_text GROUP BY 1").fetchall()}
    assert counts == {normtext.NORMALIZER_VERSION: len(rows)}
