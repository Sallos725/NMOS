"""PHASE-60 S6 review fixes on the link store (ADR 0085): a replaced link's `removed_at` is its successor's
`created_at`, however links to one target race (F3); a link that loses a lock to another writer answers 409, try
again, and writes nothing (F4). Stub extractor only; synthetic names only."""

from __future__ import annotations

import threading
from typing import Any
from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import carry
from test_phase60_carry import _connect, _source, _target
from test_phase60_carry_take import ON, _keys


def _intervals(conn: psycopg.Connection, tgt: UUID) -> list[dict[str, Any]]:
    return conn.execute("SELECT id, created_at, removed_at FROM conversation_carry WHERE target_conversation_id = %s"
                        " ORDER BY created_at, id", (tgt,)).fetchall()


def _assert_one_after_another(rows: list[dict[str, Any]]) -> None:
    """Every link was in force from its `created_at` to its `removed_at`, the replaced one until its successor began,
    and only the newest is in force (`carry.as_of` answers one link at every instant)."""
    assert rows and rows[-1]["removed_at"] is None
    for older, newer in zip(rows, rows[1:]):
        assert older["removed_at"] is not None and older["removed_at"] >= older["created_at"], (older, newer)
        assert older["removed_at"] == newer["created_at"], (older, newer)


def test_a_link_whose_transaction_began_before_another_link_still_replaces_it_after_it(migrated: str) -> None:
    """`now()` is a transaction's start: a link whose transaction began before another link was made must not stamp
    the link it replaces as removed before it was created."""
    with make_client(migrated, **ON) as c:
        _, src = _source(c, migrated)
        tgt = _target(c)
    with psycopg.connect(migrated, row_factory=dict_row) as early, _connect(migrated) as conn:
        keys = _keys(conn, with_summary=False)
        early.execute("SELECT 1")  # its transaction (and its now()) begins here
        carry.link(conn, tgt, src, "continue", [], keys)
        carry.link(early, tgt, src, "continue", [], keys)
        early.commit()
        rows = _intervals(conn, tgt)
    assert len(rows) == 2
    _assert_one_after_another(rows)


def test_concurrent_links_to_one_target_keep_one_link_after_another(migrated: str) -> None:
    with make_client(migrated, **ON) as c:
        _, src = _source(c, migrated)
        tgt = _target(c)
    with _connect(migrated) as conn:
        keys = _keys(conn, with_summary=False)
    errors: list[str] = []
    for _ in range(4):
        barrier = threading.Barrier(3)

        def work() -> None:
            with _connect(migrated) as conn:
                conn.execute("SET lock_timeout = '20s'")
                barrier.wait()
                try:
                    carry.link(conn, tgt, src, "continue", [], keys)
                except Exception as exc:  # noqa: BLE001 - reported below
                    errors.append(f"{type(exc).__name__}: {exc}")

        threads = [threading.Thread(target=work) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    assert errors == []
    with _connect(migrated) as conn:
        rows = _intervals(conn, tgt)
    assert len(rows) == 12
    _assert_one_after_another(rows)


@pytest.mark.parametrize("error", [psycopg.errors.DeadlockDetected, psycopg.errors.LockNotAvailable])
def test_a_link_that_loses_a_lock_answers_409_try_again_and_writes_nothing(migrated: str, monkeypatch, error) -> None:
    """A link racing another writer of the same chats (a delete of a branched chat) can lose a lock: the owner is
    told to try again (409), and the link in force is the one before."""
    with make_client(migrated, **ON) as c:
        _, src = _source(c, migrated)
        tgt = _target(c)
        body = {"source_conversation_id": str(src), "mode": "continue"}
        first = c.post(f"/v1/conversations/{tgt}/carry", json=body)
        assert first.status_code == 200, first.text
        with _connect(migrated) as conn:
            before = _intervals(conn, tgt)

        def lose(*args: Any, **kwargs: Any) -> None:  # inside the link's transaction, after its locks
            raise error("lost a lock")

        monkeypatch.setattr(carry, "take_reading", lose)
        res = c.post(f"/v1/conversations/{tgt}/carry", json=body)
        assert res.status_code == 409, res.text
        assert "try again" in res.json()["detail"]
        with _connect(migrated) as conn:
            assert _intervals(conn, tgt) == before
        assert c.get(f"/v1/conversations/{tgt}/carry").json()["in_force"]["id"] == first.json()["link"]["id"]
