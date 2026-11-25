"""Migration 0037 and read carry-through for `when_happened` and `story_clock` (PHASE-60 S7, A4, A5, ADR 0086).

Verifies schema shape and constraints, upgrade preservation across every upgrade fixture, archive round-trip, and
that fact reads carry `when_happened` only on rows that have a value while held role endings drop it.
Synthetic names only."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import active_generation, make_client
from nmos_sidecar import archive, endings, extraction as X, facts
from nmos_sidecar.migrate import apply_migrations, migration_files
from simchat import SimChat
from test_archive import read
from test_extraction import drain
from test_generations import LLM, conv_id
from test_role_end_review import client as role_client, story as role_story
from test_sidecar_integration import sync
from test_upgrade import FIXTURES, LATEST, restore

USED = {"calls": 1, "input": 100, "output": 10}
TURN_TEXT = "하나는 어제 등대 앞에서 카이토와 만났던 일을 떠올리며 항구에 머물렀다."
WHEN = "4월 11일"
CLOCK = "4월 12일 오후"

UPGRADE_TABLES: tuple[tuple[str, str], ...] = (
    ("assertion", "id"),
    ("extraction", "id"),
    ("source_revision", "id"),
    ("conversation", "id"),
    ("projection_generation", "key"),
)


def complete(system: str, user: str) -> tuple[dict[str, Any], str, dict[str, int]]:
    """Stub extractor: emits one event and one location on TURN_TEXT."""
    target = user.split("TARGET turn", 1)[1] if "TARGET turn" in user else ""
    if TURN_TEXT in target:
        return {
            "assertions": [
                {
                    "subject": "하나",
                    "subject_type": "character",
                    "predicate": "event",
                    "value": "등대 앞에서 카이토와 만남",
                    "salience": "major",
                    "polarity": "positive",
                    "modality": "actual",
                    "source": "narration",
                    "evidence": "등대 앞에서 카이토와 만났던 일",
                },
                {
                    "subject": "하나",
                    "subject_type": "character",
                    "predicate": "located_in",
                    "object": "항구",
                    "object_type": "place",
                    "polarity": "positive",
                    "modality": "actual",
                    "source": "narration",
                    "evidence": "항구에 머물렀다",
                },
            ]
        }, "{}", USED
    return {"assertions": []}, "{}", USED


def extract_story(url: str) -> tuple[SimChat, str]:
    chat = SimChat()
    chat.user("장면 0.")
    chat.reply(TURN_TEXT)
    chat.user("다음.")
    chat.reply("잔잔한 오후였다.")
    with make_client(url, **LLM) as c:
        sync(c, chat)
        drain(url, complete)
        cid = conv_id(c, chat)
    return chat, cid


def _snapshot(conn: psycopg.Connection) -> dict[str, tuple[int, str | None]]:
    out: dict[str, tuple[int, str | None]] = {}
    for table, key_col in UPGRADE_TABLES:
        exists = conn.execute("SELECT to_regclass(%s) IS NOT NULL AS ok", (table,)).fetchone()["ok"]
        if not exists:
            continue
        row = conn.execute(
            f"SELECT count(*) AS n, md5(string_agg({key_col}::text, ',' ORDER BY {key_col})) AS h FROM {table}"
        ).fetchone()
        out[table] = (row["n"], row["h"])
    return out


def test_migration_0037_columns_and_check_constraint(migrated: str, db: psycopg.Connection) -> None:
    """Schema shape, nullable text types, ASSERTION_COLUMNS placement, and 1..80 char_length CHECK."""
    cols = {
        (r["table_name"], r["column_name"]): (r["data_type"], r["is_nullable"])
        for r in db.execute(
            "SELECT table_name, column_name, data_type, is_nullable FROM information_schema.columns"
            " WHERE table_schema = 'public'"
            " AND ((table_name = 'assertion' AND column_name = 'when_happened')"
            " OR (table_name = 'extraction' AND column_name = 'story_clock'))"
        ).fetchall()
    }
    assert cols == {
        ("assertion", "when_happened"): ("text", "YES"),
        ("extraction", "story_clock"): ("text", "YES"),
    }
    assert "when_happened" in X.ASSERTION_COLUMNS
    assert "when_happened" not in X.JSON_COLUMNS

    extract_story(migrated)
    row_id = db.execute("SELECT id FROM assertion ORDER BY id LIMIT 1").fetchone()["id"]

    with psycopg.connect(migrated, row_factory=dict_row, autocommit=False) as conn:
        for invalid in ("", "가" * 81, "x" * 81):
            with pytest.raises(psycopg.errors.CheckViolation):
                with conn.transaction():
                    conn.execute("UPDATE assertion SET when_happened = %s WHERE id = %s", (invalid, row_id))

        exact_80 = "가" * 80
        conn.execute("UPDATE assertion SET when_happened = %s WHERE id = %s", (exact_80, row_id))
        assert conn.execute("SELECT when_happened FROM assertion WHERE id = %s", (row_id,)).fetchone()[
            "when_happened"
        ] == exact_80

        conn.execute("UPDATE assertion SET when_happened = NULL WHERE id = %s", (row_id,))
        assert conn.execute("SELECT when_happened FROM assertion WHERE id = %s", (row_id,)).fetchone()[
            "when_happened"
        ] is None
        conn.rollback()


@pytest.mark.parametrize("dump", FIXTURES, ids=[p.stem for p in FIXTURES])
def test_upgrade_fixtures_apply_0037_without_changing_existing_rows(
    dump: Path, database_url: str, tmp_path: Path
) -> None:
    """A4: every upgrade fixture preserves table counts and id hashes across migration 0037 with nulls on old rows."""
    restore(database_url, dump)
    pre_dir = tmp_path / "migrations_to_0035"
    pre_dir.mkdir()
    for path in migration_files():
        if path.name <= "0035_feeling.sql":
            shutil.copy(path, pre_dir / path.name)

    apply_migrations(database_url, directory=pre_dir)
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        before = _snapshot(conn)

    applied = apply_migrations(database_url)
    assert "0037_when_happened.sql" in applied

    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        after = _snapshot(conn)
        assert after == before
        assert conn.execute("SELECT count(*) AS n FROM assertion WHERE when_happened IS NOT NULL").fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM extraction WHERE story_clock IS NOT NULL").fetchone()["n"] == 0


def test_archive_round_trips_when_happened_and_story_clock(
    migrated: str, database_url_factory, tmp_path: Path
) -> None:
    """A5: archive export/restore preserves assertion.when_happened and extraction.story_clock."""
    extract_story(migrated)
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        ev = conn.execute(
            "SELECT id, extraction_id FROM assertion WHERE predicate = 'event' ORDER BY id LIMIT 1"
        ).fetchone()
        assert ev is not None
        conn.execute("UPDATE assertion SET when_happened = %s WHERE id = %s", (WHEN, ev["id"]))
        conn.execute("UPDATE extraction SET story_clock = %s WHERE id = %s", (CLOCK, ev["extraction_id"]))

    source = tmp_path / f"a{archive.SUFFIX}"
    archive.export_file(migrated, str(source))
    assert read(source.read_bytes())[0]["schema"]["level"] == LATEST >= "0037_when_happened.sql"

    target = database_url_factory()
    archive.restore_file(target, str(source))

    with psycopg.connect(migrated, row_factory=dict_row) as a, psycopg.connect(target, row_factory=dict_row) as b:
        a_rows = a.execute("SELECT id, when_happened FROM assertion ORDER BY id").fetchall()
        b_rows = b.execute("SELECT id, when_happened FROM assertion ORDER BY id").fetchall()
        assert a_rows == b_rows
        assert any(r["id"] == ev["id"] and r["when_happened"] == WHEN for r in b_rows)
        assert any(r["id"] != ev["id"] and r["when_happened"] is None for r in b_rows)

        a_ext = a.execute("SELECT id, story_clock FROM extraction ORDER BY id").fetchall()
        b_ext = b.execute("SELECT id, story_clock FROM extraction ORDER BY id").fetchall()
        assert a_ext == b_ext
        assert any(r["id"] == ev["extraction_id"] and r["story_clock"] == CLOCK for r in b_ext)


def test_reads_carry_when_happened_only_where_set_and_drop_it_from_held_endings(
    migrated: str, database_url_factory
) -> None:
    """S7: served_assertions and memory_view expose when_happened only when set; endings.held drops the key."""
    _, cid = extract_story(migrated)
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        ev = conn.execute(
            "SELECT id FROM assertion WHERE predicate = 'event' ORDER BY id LIMIT 1"
        ).fetchone()
        assert ev is not None
        conn.execute("UPDATE assertion SET when_happened = %s WHERE id = %s", (WHEN, ev["id"]))

        head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid,)).fetchone()[
            "head_commit_id"
        ]
        key = active_generation(conn, "extract").key

        served = facts.served_assertions(conn, head, key)
        assert len(served) >= 2
        by_id = {r["id"]: r for r in served}
        assert by_id[ev["id"]]["when_happened"] == WHEN
        for row_id, row in by_id.items():
            if row_id != ev["id"]:
                assert "when_happened" not in row

        view = facts.memory_view(conn, head, key)
        ev_facts = [f for f in view["facts"] if f["id"] == ev["id"]]
        other_facts = [f for f in view["facts"] if f["id"] != ev["id"]]
        assert len(ev_facts) == 1 and len(other_facts) >= 1
        assert ev_facts[0]["when_happened"] == WHEN
        assert ev_facts[0]["history"][-1]["when_happened"] == WHEN
        for f in other_facts:
            assert "when_happened" not in f
            assert all("when_happened" not in h for h in f["history"])

    held_url = database_url_factory()
    with role_client(held_url) as c:
        _, held_cid = role_story(c, held_url, "no")
    with psycopg.connect(held_url, row_factory=dict_row, autocommit=True) as conn:
        head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (held_cid,)).fetchone()[
            "head_commit_id"
        ]
        key = active_generation(conn, "extract").key
        view = facts.memory_view(conn, head, key)
        held_rows = endings.held(conn, head, key, view)
        assert len(held_rows) == 1
        assert "when_happened" not in held_rows[0]
        # Even if a pending row carried a value, endings.held strips the key.
        conn.execute("UPDATE assertion SET when_happened = %s WHERE id = %s", (WHEN, held_rows[0]["id"]))
        stripped_rows = endings.held(conn, head, key, view)
        assert len(stripped_rows) == 1
        assert "when_happened" not in stripped_rows[0]
