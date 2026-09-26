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
