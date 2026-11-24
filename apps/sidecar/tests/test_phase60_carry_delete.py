"""PHASE-60 S6 (ADR 0085): deleting a conversation deletes its carry links (target or source).

Synthetic names only."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from psycopg.types.json import Jsonb

from conftest import make_client
from nmos_sidecar.ids import uuid7
from simchat import SimChat
from test_conversation_delete import rows
from test_generations import conv_id
from test_sidecar_integration import sync

MINIMAL_SNAPSHOT = {
    "shape": 1,
    "facts": [],
    "aliases": [],
    "threads": [],
    "story": None,
    "characters": [],
}


def _chat(line: str) -> SimChat:
    chat = SimChat()
    chat.user(line)
    chat.reply("Noted.")
    chat.user("And then?")
    return chat


def _head_commit(db, cid: str) -> UUID:
    row = db.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid,)).fetchone()
    assert row is not None and row["head_commit_id"] is not None
    return row["head_commit_id"]


def _insert_carry(db, target_id: str, source_id: str, *, removed_at: datetime | None = None) -> UUID:
    link_id = uuid7()
    db.execute(
        "INSERT INTO conversation_carry"
        " (id, target_conversation_id, source_conversation_id, mode, cutoff_commit_id, cutoff_position,"
        "  snapshot, removed_at)"
        " VALUES (%s, %s, %s, 'continue', %s, 0, %s, %s)",
        (link_id, target_id, source_id, _head_commit(db, source_id), Jsonb(MINIMAL_SNAPSHOT), removed_at),
    )
    return link_id


def test_delete_conversation_removes_its_carry_links_and_keeps_others(migrated: str, db) -> None:
    with make_client(migrated) as c:
        chat_a = _chat("Hana visits the chapel.")
        chat_b = _chat("Kaito holds the lantern.")
        chat_c = _chat("Sera waits by the gate.")
        for chat in (chat_a, chat_b, chat_c):
            sync(c, chat)

        aid, bid, cid = conv_id(c, chat_a), conv_id(c, chat_b), conv_id(c, chat_c)
        before_a = rows(db, aid)
        before_c = rows(db, cid)

        link_ab = _insert_carry(db, aid, bid)  # A -> B in force
        link_cb_removed = _insert_carry(db, cid, bid, removed_at=datetime.now(timezone.utc))  # C -> B removed
        link_ca = _insert_carry(db, cid, aid)  # C -> A in force
        assert link_ab != link_cb_removed != link_ca

        # Deleting B deletes A->B (source=B) and removed C->B (source=B), leaving C->A.
        res_b = c.post(f"/v1/conversations/{bid}/delete")
        assert res_b.status_code == 200, res_b.text
        assert res_b.json()["deleted"]["carry_links"] == 2
        remaining = [r["id"] for r in db.execute("SELECT id FROM conversation_carry").fetchall()]
        assert remaining == [link_ca]
        assert rows(db, aid) == before_a
        assert rows(db, cid) == before_c

        # Deleting A deletes C->A (source=A) and leaves no carry rows; C's own rows stay intact.
        res_a = c.post(f"/v1/conversations/{aid}/delete")
        assert res_a.status_code == 200, res_a.text
        assert res_a.json()["deleted"]["carry_links"] == 1
        assert db.execute("SELECT count(*) FROM conversation_carry").fetchone()["count"] == 0
        assert rows(db, cid) == before_c


def test_delete_target_conversation_removes_its_carry_link_and_keeps_source(migrated: str, db) -> None:
    with make_client(migrated) as c:
        target = _chat("Yuna opens the door.")
        source = _chat("Hana reads the letter.")
        sync(c, target)
        sync(c, source)
        tid, sid = conv_id(c, target), conv_id(c, source)
        before_source = rows(db, sid)

        _insert_carry(db, tid, sid)
        res = c.post(f"/v1/conversations/{tid}/delete")
        assert res.status_code == 200, res.text
        assert res.json()["deleted"]["carry_links"] == 1
        assert db.execute("SELECT count(*) FROM conversation_carry").fetchone()["count"] == 0
        assert rows(db, sid) == before_source
