"""PHASE-60 S6 (ADR 0085): archiving and restoring `conversation_carry` links.

Synthetic names only."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from memeval import stub_extractor
from nmos_sidecar import archive
from nmos_sidecar.ids import uuid7
from simchat import SimChat
from test_archive import play, read
from test_extraction import drain
from test_generations import conv_id
from test_restore import client, counts, export_to, reseal
from test_sidecar_integration import sync


def _source_chat() -> SimChat:
    chat = SimChat()
    for text in (
        "Hana wants to find the keeper.",
        "Kaito is in the garden.",
        "Kaito wants to become a knight.",
    ):
        chat.user(text)
        chat.reply("Noted.")
    chat.user("And then?")
    return chat


def _target_chat() -> SimChat:
    chat = SimChat()
    chat.user("Yuna arrives at the harbor.")
    chat.reply("The sea is calm.")
    chat.user("What next?")
    return chat


def _source_assertions(url: str, source_cid: str) -> list[dict]:
    with psycopg.connect(url, row_factory=dict_row) as conn:
        return conn.execute(
            "SELECT a.id, a.source_revision_id, a.predicate, a.value, e.extractor_key"
            " FROM assertion a"
            " JOIN extraction e ON e.id = a.extraction_id"
            " JOIN source_revision sr ON sr.id = a.source_revision_id"
            " JOIN source_object so ON so.id = sr.source_object_id"
            " WHERE so.conversation_id = %s ORDER BY a.id",
            (source_cid,),
        ).fetchall()


def _head_commit(url: str, cid: str) -> UUID:
    with psycopg.connect(url, row_factory=dict_row) as conn:
        row = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid,)).fetchone()
    assert row is not None and row["head_commit_id"] is not None
    return row["head_commit_id"]


def _build_snapshot(source_cid: str, assertions: list[dict]) -> dict:
    assert len(assertions) >= 3
    a0, a1, a2 = assertions[0], assertions[1], assertions[2]
    summary_id = str(uuid7())
    return {
        "shape": 1,
        "facts": [
            {
                "subject": "Kaito",
                "predicate": a0["predicate"],
                "value": a0["value"],
                "from": {
                    "conversation": source_cid,
                    "assertion": a0["id"],
                    "revision": str(a0["source_revision_id"]),
                    "generation": a0["extractor_key"],
                },
            },
            {
                "subject": "Hana",
                "predicate": "has_status",
                "value": "traveling",
                "from": {
                    "conversation": source_cid,
                    "assertion": None,
                    "revision": str(a0["source_revision_id"]),
                    "generation": a0["extractor_key"],
                },
            },
            {
                "subject": "Sera",
                "predicate": "located_in",
                "value": "harbor",
                "from": {
                    "conversation": source_cid,
                    "assertion": -7,
                    "revision": str(a0["source_revision_id"]),
                    "generation": a0["extractor_key"],
                },
            },
        ],
        "aliases": [
            {
                "name": "Kaito",
                "alias": "the lantern bearer",
                "from": {
                    "conversation": source_cid,
                    "assertion": a1["id"],
                    "revision": str(a1["source_revision_id"]),
                    "generation": a1["extractor_key"],
                },
            },
        ],
        "threads": [
            {
                "kind": "goal",
                "text": "find the keeper",
                "status": "open",
                "from": {
                    "conversation": source_cid,
                    "assertion": a2["id"],
                    "revision": str(a2["source_revision_id"]),
                    "generation": a2["extractor_key"],
                },
            },
        ],
        "story": {
            "text": "Hana set out to find the keeper while Kaito waited in the garden.",
            "from": {
                "conversation": source_cid,
                "summary": summary_id,
                "generation": "summarize-test",
            },
        },
        "characters": ["Hana", "Kaito", "Sera"],
    }


def _insert_carry(
    url: str,
    target_cid: str,
    source_cid: str,
    snapshot: dict,
    *,
    mode: str = "continue",
    entity_names: list[str] | None = None,
    cutoff_turn: int | None = 2,
    generations: dict | None = None,
    removed_at: datetime | None = None,
) -> UUID:
    link_id = uuid7()
    commit_id = _head_commit(url, source_cid)
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO conversation_carry"
            " (id, target_conversation_id, source_conversation_id, mode, entity_names,"
            "  cutoff_commit_id, cutoff_position, cutoff_turn, generations, snapshot, removed_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                link_id,
                target_cid,
                source_cid,
                mode,
                Jsonb(entity_names or []),
                commit_id,
                4,
                cutoff_turn,
                Jsonb(generations) if generations is not None else Jsonb({"extract": "extract-test"}),
                Jsonb(snapshot),
                removed_at,
            ),
        )
    return link_id


def _setup_pair(url: str) -> tuple[str, str, list[dict], dict, UUID]:
    with client(url) as c:
        src = _source_chat()
        dst = _target_chat()
        sync(c, src)
        sync(c, dst)
        drain(url, stub_extractor)
        src_id, dst_id = conv_id(c, src), conv_id(c, dst)
    assertions = _source_assertions(url, src_id)
    snapshot = _build_snapshot(src_id, assertions)
    link_id = _insert_carry(url, dst_id, src_id, snapshot)
    return src_id, dst_id, assertions, snapshot, link_id


def test_export_whole_install_and_single_chat_carry_left_out(migrated: str, tmp_path: Path) -> None:
    src_id, dst_id, _, _, link_id = _setup_pair(migrated)
    # Also add a removed link between the same pair to verify both in-force and removed links count.
    removed_id = _insert_carry(
        migrated,
        dst_id,
        src_id,
        {"shape": 1, "facts": [], "aliases": [], "threads": [], "story": None, "characters": []},
        mode="regression",
        entity_names=["Hana"],
        removed_at=datetime.now(timezone.utc),
    )

    whole = export_to(tmp_path, migrated, "whole")
    m_whole, t_whole, _ = read(whole.read_bytes())
    assert m_whole["carry_left_out"] == 0
    assert {r["id"] for r in t_whole["conversation_carry"]} == {str(link_id), str(removed_id)}

    for label, cid in (("target-only", dst_id), ("source-only", src_id)):
        partial = export_to(tmp_path, migrated, label, conversations=[cid])
        m_part, t_part, _ = read(partial.read_bytes())
        assert t_part["conversation_carry"] == [], label
        assert m_part["carry_left_out"] == 2, label


def test_single_in_force_link_left_out_count_is_one(migrated: str, tmp_path: Path) -> None:
    src_id, dst_id, _, _, _ = _setup_pair(migrated)
    for label, cid in (("target", dst_id), ("source", src_id)):
        partial = export_to(tmp_path, migrated, label, conversations=[cid])
        manifest, tables, _ = read(partial.read_bytes())
        assert tables["conversation_carry"] == [], label
        assert manifest["carry_left_out"] == 1, label


def test_archive_of_both_round_trips_link_into_fresh_db(
    migrated: str, database_url_factory, tmp_path: Path
) -> None:
    src_id, dst_id, _, _, link_id = _setup_pair(migrated)
    removed_id = _insert_carry(
        migrated,
        dst_id,
        src_id,
        {"shape": 1, "facts": [], "aliases": [], "threads": [], "story": None, "characters": ["Hana"]},
        mode="regression",
        entity_names=["Hana"],
        cutoff_turn=None,
        removed_at=datetime.now(timezone.utc),
    )
    both = export_to(tmp_path, migrated, "both", conversations=[src_id, dst_id])
    manifest, tables, _ = read(both.read_bytes())
    assert manifest["carry_left_out"] == 0
    assert {r["id"] for r in tables["conversation_carry"]} == {str(link_id), str(removed_id)}

    fresh = database_url_factory()
    done = archive.restore_file(fresh, str(both))
    assert done.renumbered == []
    assert done.rows["conversation_carry"] == 2

    with psycopg.connect(migrated, row_factory=dict_row) as orig_conn, psycopg.connect(
        fresh, row_factory=dict_row
    ) as new_conn:
        orig_rows = orig_conn.execute("SELECT * FROM conversation_carry ORDER BY created_at, id").fetchall()
        new_rows = new_conn.execute("SELECT * FROM conversation_carry ORDER BY created_at, id").fetchall()
    assert new_rows == orig_rows


def test_restore_into_occupied_install_shifts_positive_snapshot_assertion_ids(
    migrated: str, database_url_factory, tmp_path: Path
) -> None:
    src_id, dst_id, orig_assertions, orig_snapshot, link_id = _setup_pair(migrated)
    sparse_snapshot = {"shape": 1, "facts": [], "story": None, "characters": []}
    sparse_id = _insert_carry(
        migrated,
        dst_id,
        src_id,
        sparse_snapshot,
        mode="regression",
        entity_names=["Hana"],
        removed_at=datetime.now(timezone.utc),
    )
    both = export_to(tmp_path, migrated, "both", conversations=[src_id, dst_id])

    target = database_url_factory()
    with client(target) as c:
        play(c, target)  # occupies assertion ids and commit sequence numbers

    done = archive.restore_file(target, str(both))
    assert "assertion" in done.renumbered

    with psycopg.connect(target, row_factory=dict_row) as conn:
        restored = conn.execute("SELECT * FROM conversation_carry WHERE id = %s", (link_id,)).fetchone()
        assert restored is not None
        snap = restored["snapshot"]

        # Positive assertion ids in facts, aliases, and threads shifted to match restored assertion rows.
        checks = [
            (snap["facts"][0]["from"], orig_assertions[0]),
            (snap["aliases"][0]["from"], orig_assertions[1]),
            (snap["threads"][0]["from"], orig_assertions[2]),
        ]
        for ref, orig in checks:
            assert ref["assertion"] > orig["id"]
            row = conn.execute(
                "SELECT id, source_revision_id, value FROM assertion WHERE id = %s",
                (ref["assertion"],),
            ).fetchone()
            assert row is not None
            assert row["source_revision_id"] == orig["source_revision_id"]
            assert row["value"] == orig["value"]
            assert ref["conversation"] == src_id
            assert ref["revision"] == str(orig["source_revision_id"])
            assert ref["generation"] == orig["extractor_key"]

        # Null and negative assertion ids stay unchanged, and element order & other keys stay intact.
        assert snap["facts"][1]["from"]["assertion"] is None
        assert snap["facts"][1] == orig_snapshot["facts"][1]
        assert snap["facts"][2]["from"]["assertion"] == -7
        assert snap["facts"][2] == orig_snapshot["facts"][2]
        assert snap["shape"] == orig_snapshot["shape"]
        assert snap["story"] == orig_snapshot["story"]
        assert snap["characters"] == orig_snapshot["characters"]

        # Absent or empty arrays in another link's snapshot are left as they are.
        sparse_restored = conn.execute("SELECT snapshot FROM conversation_carry WHERE id = %s", (sparse_id,)).fetchone()
        assert sparse_restored is not None and sparse_restored["snapshot"] == sparse_snapshot


def test_link_naming_conversation_outside_archive_is_refused(
    migrated: str, database_url_factory, tmp_path: Path
) -> None:
    src_id, dst_id, _, _, _ = _setup_pair(migrated)
    both = export_to(tmp_path, migrated, "both", conversations=[src_id, dst_id])

    target = database_url_factory()
    with client(target) as c:
        outsider = _target_chat()
        sync(c, outsider)
        victim = conv_id(c, outsider)
    before = counts(target)

    for col in ("source_conversation_id", "target_conversation_id"):
        forged = reseal(
            both,
            tmp_path / f"forged-{col}{archive.SUFFIX}",
            "conversation_carry",
            lambda r, key=col: {**r, key: victim},
        )
        with pytest.raises(archive.ArchiveError, match="does not hold"):
            archive.restore_file(target, str(forged))
    assert counts(target) == before
