"""Startup work commits step by step (audit A-08).

The sidecar backfills derived data when it starts (normalized text, turn data, parser state, missing
jobs). Run as one transaction, a startup interrupted late (a crash, a restart during a long backfill
after a normalizer change) threw away every batch already done, and the next start began again."""

from __future__ import annotations

import pytest

from conftest import make_client
from nmos_sidecar import normtext
from simchat import SimChat
from test_sidecar_integration import sync


def test_an_interrupted_startup_keeps_the_batches_it_finished(migrated, db, monkeypatch):
    with make_client(migrated) as c:
        chat = SimChat()
        for i in range(3):
            chat.user(f"Message {i} about the harbor.")
            chat.reply(f"Reply {i}.")
        sync(c, chat)
    revisions = db.execute("SELECT count(*) AS n FROM source_revision").fetchone()["n"]
    db.execute("DELETE FROM revision_text")  # derived: as after a normalizer change
    db.commit()

    monkeypatch.setattr(normtext.backfill, "__defaults__", (2,))  # batches of two
    write, calls = normtext.write, {"n": 0}

    def failing_write(conn, revision_id, content):
        calls["n"] += 1
        if calls["n"] > 4:
            raise RuntimeError("interrupted")
        write(conn, revision_id, content)

    monkeypatch.setattr(normtext, "write", failing_write)
    with pytest.raises(RuntimeError, match="interrupted"), make_client(migrated):
        pass
    assert db.execute("SELECT count(*) AS n FROM revision_text").fetchone()["n"] == 4  # two batches kept

    monkeypatch.setattr(normtext, "write", write)
    with make_client(migrated):
        pass
    assert db.execute("SELECT count(*) AS n FROM revision_text").fetchone()["n"] == revisions


def test_the_worker_waits_for_the_migrations_the_sidecar_runs(database_url):
    """The sidecar applies migrations when it starts, and compose starts the worker alongside it; a worker
    claiming jobs against an older schema fails them (and burns their attempts) until the sidecar is done."""
    import threading

    from nmos_sidecar import migrate, worker

    assert migrate.pending(database_url) == [p.name for p in migrate.migration_files()]
    stop, done = threading.Event(), threading.Event()
    waiter = threading.Thread(target=lambda: (worker.wait_for_schema(database_url, stop, poll_s=0.05), done.set()))
    waiter.start()
    try:
        assert not done.wait(0.3)
        migrate.apply_migrations(database_url)
        assert done.wait(5)
        assert migrate.pending(database_url) == []
    finally:
        stop.set()
        waiter.join(5)


def test_a_stopped_worker_stops_waiting(database_url):
    import threading

    from nmos_sidecar import worker

    stop = threading.Event()
    stop.set()
    worker.wait_for_schema(database_url, stop, poll_s=0.05)  # returns at once, schema or not
