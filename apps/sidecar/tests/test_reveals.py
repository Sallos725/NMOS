"""Phase 22 (docs/phases/PHASE-22.md, Q2–Q4): reveal checks instead of K29's re-extraction (ADR 0057)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from psycopg.types.json import Jsonb

from conftest import active_generation, make_client
from nmos_sidecar import generations
from nmos_sidecar.facts import served_assertions
from nmos_sidecar.ids import uuid7
from test_extraction import drain
from test_generations import LLM
from test_hints import step
from test_secrets import SecretRecorder, extractions, first_import, goal_of


def head(db) -> UUID:
    return db.execute("SELECT head_commit_id FROM conversation").fetchone()["head_commit_id"]


def check_rows(db) -> set[int]:
    """Ids of the assertions reveal checks stored."""
    return {r["id"] for r in db.execute("SELECT a.id FROM assertion a JOIN extraction x ON x.id = a.extraction_id"
                                        " WHERE x.window_hash LIKE 'reveal:%'").fetchall()}


def served_from_checks(db, key: str | None = None, **as_of) -> list[dict]:
    rows = served_assertions(db, head(db), key or active_generation(db, "extract").key, **as_of)
    return [r for r in rows if r["id"] in check_rows(db)]


def checked(c, migrated, db) -> tuple[SecretRecorder, str]:
    """K29's chat, after "Extract all history" and its two checks: Noel found the secret out in turn 2, by a check."""
    model = SecretRecorder()
    chat, conv = first_import(c, migrated, model, db)
    c.post(f"/v1/conversations/{conv}/extract-history")
    drain(migrated, model)
    (reveal,) = served_from_checks(db)
    assert reveal["predicate"] == "learned" and reveal["turn"] == 2 and reveal["subject"] == "Noel"
    # A check's row reads as the extraction it checked.
    assert reveal["generation"] == active_generation(db, "extract").key
    return model, conv


def test_a_turn_with_no_open_secret_before_it_is_checked_without_a_call(migrated, db):
    model = SecretRecorder()
    with make_client(migrated, **LLM) as c:
        _, conv = first_import(c, migrated, model, db)
        rv = active_generation(db, "reveal")
        turn0 = db.execute("SELECT x.id, x.source_revision_id AS rid, x.window_hash FROM extraction x"
                           " JOIN active_membership am ON am.source_revision_id = x.source_revision_id"
                           " AND am.turn_hash = x.window_hash WHERE am.turn = 0").fetchone()
        db.execute("INSERT INTO job (kind, dedupe_key, conversation_id, payload, priority) VALUES ('reveal', 'manual', %s,"
                   " %s, 300)", (conv, Jsonb({"extraction_id": str(turn0["id"]), "revision_id": str(turn0["rid"]),
                                             "window_hash": turn0["window_hash"], "generation": rv.key})))
        db.commit()
        calls = len(model.prompts)
        assert drain(migrated, model) == 1 and len(model.prompts) == calls
        (made,) = db.execute("SELECT usage, hints FROM extraction WHERE window_hash LIKE 'reveal:%'").fetchall()
        assert made["usage"] == {"calls": 0} and made["hints"] == {"checks": str(turn0["id"]), "secrets": []}


def test_a_check_stops_counting_when_its_extraction_no_longer_serves_the_turn(migrated, db):
    with make_client(migrated, **LLM) as c:
        model, conv = checked(c, migrated, db)
        # A new extractor generation's extraction of turn 2 serves it now: the check of the old one does not count.
        ex = active_generation(db, "extract")
        newer = generations.make("extract", "http://other-llm/v1", "other")
        generations.activate(db, newer)
        db.commit()
        turn2 = db.execute("SELECT x.source_revision_id AS rid, x.window_hash FROM extraction x"
                           " JOIN active_membership am ON am.source_revision_id = x.source_revision_id"
                           " AND am.turn_hash = x.window_hash WHERE am.turn = 2 AND x.extractor_key = %s",
                           (ex.key,)).fetchone()
        db.execute("INSERT INTO extraction (id, source_revision_id, window_hash, compiler_version, extractor_key, model,"
                   " raw) VALUES (%s, %s, %s, 'test', %s, 'other', '{}')",
                   (uuid7(), turn2["rid"], turn2["window_hash"], newer.key))
        db.commit()
        assert served_assertions(db, head(db), newer.key) and not served_from_checks(db, newer.key)
        assert served_from_checks(db, ex.key)  # read with the old generation preferred, it serves again
        # A rebuild discards the turn's extraction (and the check): nothing of the check is served meanwhile.
        out = c.post(f"/v1/conversations/{conv}/rebuild").json()
        assert out["discarded"] > 0 and not served_from_checks(db, ex.key)
        assert all(x["discarded_at"] is not None for x in extractions(db) if x["window_hash"].startswith("reveal:"))


def test_a_join_undo_re_extraction_drops_the_check_with_its_turn(migrated, db):
    """discard_turns (PHASE-20 Q7) discards the turn's extractions; the check stays stored but stops counting."""
    from nmos_sidecar.extraction import discard_turns

    with make_client(migrated, **LLM) as c:
        checked(c, migrated, db)
        turn2 = db.execute("SELECT am.source_revision_id AS rid, am.turn_hash FROM active_membership am"
                           " JOIN conversation c ON c.head_commit_id = am.commit_id WHERE am.turn = 2").fetchone()
        assert discard_turns(db, [turn2]) == 1  # the turn's extraction, not its check
        db.commit()
        assert not served_from_checks(db)


def test_a_replay_as_of_before_the_check_leaves_it_out(migrated, db):
    with make_client(migrated, **LLM) as c:
        model = SecretRecorder()
        chat, conv = first_import(c, migrated, model, db)
        before = datetime.now(timezone.utc)
        c.post(f"/v1/conversations/{conv}/extract-history")
        drain(migrated, model)
        assert served_from_checks(db) and not served_from_checks(db, known_at=before)
        assert goal_of(db)["revealed"]


def test_an_archive_with_checks_restores_the_same_reveals(migrated, db, database_url_factory, tmp_path):
    """ADR 0050: a check is an extraction of its own generation; an archive carries it and its rows."""
    import psycopg
    from psycopg.rows import dict_row

    from nmos_sidecar import archive

    with make_client(migrated, **LLM) as c:
        checked(c, migrated, db)
    source = tmp_path / f"a{archive.SUFFIX}"
    archive.export_file(migrated, str(source))
    target = database_url_factory()
    archive.restore_file(target, str(source))
    with psycopg.connect(target, row_factory=dict_row, autocommit=True) as restored:
        assert [r["value"] for r in served_from_checks(restored)] == [r["value"] for r in served_from_checks(db)]
        assert goal_of(restored)["revealed"] == goal_of(db)["revealed"]


def test_waiting_checks_stop_when_extraction_is_turned_off_or_its_model_changes(migrated, db):
    model = SecretRecorder()
    with make_client(migrated, **LLM) as c:
        _, conv = first_import(c, migrated, model, db)
        assert c.post(f"/v1/conversations/{conv}/extract-history").json()["queued"]["reveal"] == 2
        assert c.put("/v1/config", json={"llm_model": "another"}).status_code == 200  # a new reveal generation
        assert db.execute("SELECT count(*) AS n FROM job WHERE kind = 'reveal' AND status = 'queued'").fetchone()["n"] == 0
        assert c.post(f"/v1/conversations/{conv}/extract-history").json()["queued"]["reveal"] == 0  # the new generation has none of these turns yet
        assert c.put("/v1/config", json={"llm_url": ""}).status_code == 200
        assert db.execute("SELECT count(*) AS n FROM job WHERE kind = 'reveal' AND status IN ('queued', 'running')"
                          ).fetchone()["n"] == 0


def test_only_the_latest_reveal_generation_is_served_and_counts_as_looking(migrated, db):
    """Copilot review of #213: a reveal-only generation change neither serves two checks nor settles a turn."""
    from nmos_sidecar import reveals

    with make_client(migrated, **LLM) as c:
        _, conv = checked(c, migrated, db)
        ex, rv = active_generation(db, "extract"), active_generation(db, "reveal")
        assert reveals.unchecked(db, ex.key, rv.key, conv) == []
        newer = generations.make("reveal", "http://fake-llm/v1", "fake", version="reveal-v2")
        generations.activate(db, newer)
        db.commit()
        assert [r["turn"] for r in reveals.unchecked(db, ex.key, newer.key, conv)] == [1, 2]
        assert served_from_checks(db)  # the older generation serves until the turn is checked again
        check = db.execute("SELECT source_revision_id AS rid, window_hash, hints FROM extraction"
                           " WHERE window_hash LIKE 'reveal:%%' AND jsonb_array_length(hints->'secrets') > 0"
                           " AND EXISTS (SELECT 1 FROM assertion a WHERE a.extraction_id = extraction.id)").fetchone()
        db.execute("INSERT INTO extraction (id, source_revision_id, window_hash, compiler_version, extractor_key, model,"
                   " raw, hints) VALUES (%s, %s, %s, 'reveal-v2', %s, 'fake', '{}', %s)",
                   (uuid7(), check["rid"], check["window_hash"], newer.key, Jsonb(check["hints"])))
        db.commit()
        assert not served_from_checks(db)  # the newer check found nothing: only it counts


def test_a_check_made_before_an_earlier_turns_reveal_is_checked_again(migrated, db):
    """Copilot review of #213: two workers checked neighbouring turns at once; another press recovers it."""
    from nmos_sidecar import reveals

    with make_client(migrated, **LLM) as c:
        model = SecretRecorder()
        chat, conv = first_import(c, migrated, model, db)
        c.post(f"/v1/conversations/{conv}/extract-history")
        drain(migrated, model)
        step(c, migrated, chat, model, "Noel waves.")  # a later turn, extracted after the reveal
        ex, rv = active_generation(db, "extract"), active_generation(db, "reveal")
        later = db.execute("SELECT x.id, x.source_revision_id AS rid, x.window_hash FROM extraction x"
                           " JOIN active_membership am ON am.source_revision_id = x.source_revision_id"
                           " AND am.turn_hash = x.window_hash JOIN conversation c ON c.head_commit_id = am.commit_id"
                           " WHERE x.extractor_key = %s ORDER BY am.turn DESC LIMIT 1", (ex.key,)).fetchone()
        db.execute("INSERT INTO job (kind, dedupe_key, conversation_id, payload, priority) VALUES ('reveal', 'turn3', %s,"
                   " %s, 300)", (conv, Jsonb({"extraction_id": str(later["id"]), "revision_id": str(later["rid"]),
                                             "window_hash": later["window_hash"], "generation": rv.key})))
        db.commit()
        drain(migrated, SecretRecorder())
        assert reveals.unchecked(db, ex.key, rv.key, conv) == []  # made after turn 2's reveal: settled
        # As if the later turn's check had finished first, while turn 2's was still asking the model.
        db.execute("UPDATE extraction SET created_at = (SELECT min(created_at) FROM extraction) WHERE window_hash = %s",
                   ("reveal:" + later["window_hash"],))
        db.commit()
        assert len(reveals.unchecked(db, ex.key, rv.key, conv)) == 1
        assert c.post(f"/v1/conversations/{conv}/extract-history").json()["queued"]["reveal"] == 1
