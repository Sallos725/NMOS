"""PHASE-60 S8 (ADR 0087): the owner pins a character, the store side. A pin is an owner repair (`entity_pin`,
migration 0038): stored, listed, undone, archived, kept by rebuilds and deleted with the chat like every repair. Nothing
here reads a pin into a packet. Synthetic names only."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import psycopg
import pytest
from psycopg.types.json import Jsonb

from conftest import make_client
from nmos_sidecar import inspector, repairs
from nmos_sidecar.ids import uuid7
from nmos_sidecar.migrate import apply_migrations, migrations_dir
from test_entity_exclude import complete, exclude, setup, view
from test_extraction import drain
from test_generations import LLM
from test_upgrade import FIXTURES, restore

PIN = "0038_entity_pin.sql"
TABLES = ("owner_repair", "conversation", "assertion")
# The kind list of 0031 (the newest migration that set it) and the pin.
KINDS = {"thread_close", "thread_reopen", "secret_found_out", "secret_keep", "fact_retract", "fact_correct",
         "name_split", "fact_lock", "fact_restore", "state_dismiss", "entity_exclude", "entity_pin"}


def kinds_of(url: str) -> set[str]:
    with psycopg.connect(url) as conn:
        check = conn.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
            " WHERE conrelid = 'owner_repair'::regclass AND conname = 'owner_repair_kind_check'").fetchone()[0]
    return set(re.findall(r"'(\w+)'", check))


def a_conversation(conn: psycopg.Connection) -> object:
    return conn.execute("INSERT INTO conversation (id, host, host_chat_ref) VALUES (%s, 'test', %s) RETURNING id",
                        (uuid7(), f"chat-{uuid7()}")).fetchone()[0]


def test_an_entity_pin_inserts_and_an_unknown_kind_is_still_refused(migrated):
    assert kinds_of(migrated) == KINDS
    with psycopg.connect(migrated) as conn:
        cid = a_conversation(conn)
        conn.execute("INSERT INTO owner_repair (id, conversation_id, kind, target, value) VALUES (%s, %s, 'entity_pin',"
                     " %s, '{}')", (uuid7(), cid, Jsonb({"entity_type": "character", "name": "세라"})))
        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.transaction():
                conn.execute("INSERT INTO owner_repair (id, conversation_id, kind, target, value) VALUES"
                             " (%s, %s, 'entity_star', '{}', '{}')", (uuid7(), cid))
        assert conn.execute("SELECT count(*) FROM owner_repair WHERE kind = 'entity_pin'").fetchone()[0] == 1


def state(url: str) -> dict[str, tuple[int, str | None]]:
    """Row count and id hash of each table the migration must leave as it was (A4)."""
    with psycopg.connect(url) as conn:
        return {t: conn.execute(f"SELECT count(*), md5(string_agg(id::text, ',' ORDER BY id)) FROM {t}").fetchone()
                for t in TABLES}


@pytest.mark.parametrize("dump", FIXTURES, ids=[p.stem for p in FIXTURES])
def test_every_upgrade_fixture_applies_0038_and_keeps_its_rows(dump, database_url, tmp_path):
    """A4: each earlier release's database, migrated up to the migration before 0038, then 0038 alone."""
    before_dir = tmp_path / "migrations"
    before_dir.mkdir()
    for path in migrations_dir().glob("[0-9][0-9][0-9][0-9]_*.sql"):
        if path.name < PIN:
            shutil.copy(path, before_dir / path.name)
    restore(database_url, dump)
    apply_migrations(database_url, directory=before_dir)
    assert "entity_pin" not in kinds_of(database_url)
    before = state(database_url)
    assert before["conversation"][0] > 0 and before["assertion"][0] > 0
    assert apply_migrations(database_url) == [PIN]
    assert state(database_url) == before
    assert kinds_of(database_url) == KINDS


def test_the_migration_says_where_it_comes_from():
    text = (Path(migrations_dir()) / PIN).read_text()
    assert "PHASE-60" in text and "ADR 0087" in text


# The store and the read of a pin (step 2). A pin is written here as the API writes it (step 3 takes it over HTTP).

def pin_row(url: str, cid: str, name: str, entity_type: str = "character") -> str:
    with psycopg.connect(url) as conn:
        return str(conn.execute(
            "INSERT INTO owner_repair (id, conversation_id, kind, target, value) VALUES (%s, %s, 'entity_pin', %s, '{}')"
            " RETURNING id", (uuid7(), cid, Jsonb({"entity_type": entity_type, "name": name}))).fetchone()[0])


def entity_id(v: dict, name: str) -> str:
    return str(next(e["id"] for e in v["entities"] if e["name"] == name))


def refused(name: str, v: dict, **kw) -> str:
    with pytest.raises(repairs.RepairError) as e:
        repairs.plan("entity_pin", name, v, None, **kw)
    return str(e.value)


def test_a_pin_is_planned_by_name_or_id_and_refused_where_it_cannot_hold(migrated):
    with make_client(migrated, **LLM) as c:
        cid = setup(c, migrated)
        v = view(migrated, cid)
        assert repairs.plan("entity_pin", "Kaito", v, None) == ({"entity_type": "character", "name": "Kaito"}, {})
        # the panel names it by its id; the chat's own character may be pinned too
        assert repairs.plan("entity_pin", entity_id(v, "Hana"), v, None)[0] == {"entity_type": "character", "name": "Hana"}
        assert "not mentioned" in refused("Nobody", v)
        assert "persona" in refused("Rowan", v)
        assert "only a character" in refused("village", v, entity_type="place")
        assert "only a character" in refused(entity_id(v, "village"), v)
        exclude(c, cid, "Gloomfang")
        pin_row(migrated, cid, "Kaito")
        v = view(migrated, cid)
        assert "not a character" in refused("Gloomfang", v)
        assert "already" in refused("Kaito", v)


def test_pins_resolve_now_newest_first_one_a_character_and_an_exclusion_wins(migrated):
    assert repairs.pins([], None) == []
    with make_client(migrated, **LLM) as c:
        cid = setup(c, migrated)
        assert view(migrated, cid)["pins"] == []
        first = pin_row(migrated, cid, "Kaito")
        hana = pin_row(migrated, cid, "Hana")
        again = pin_row(migrated, cid, "Kaito")  # the store takes it; the read keeps the newer of the two
        monster = pin_row(migrated, cid, "Gloomfang")
        v = view(migrated, cid)
        assert [(p["name"], str(p["repair"])) for p in v["pins"]] == [("Gloomfang", monster), ("Kaito", again),
                                                                       ("Hana", hana)]
        assert all(set(p) == {"entity_id", "name", "repair", "created_at"} for p in v["pins"])
        assert {p["name"]: str(p["entity_id"]) for p in v["pins"]}["Kaito"] == entity_id(v, "Kaito")
        applied = {str(r["id"]): r["applied"] for r in v["repairs"]}
        assert str(applied[first]) == str(applied[again]) == entity_id(v, "Kaito")  # both pin Kaito
        for scope in ("cast", "memory"):
            rid = exclude(c, cid, "Gloomfang", scope).json()["repair"]["id"]
            v = view(migrated, cid)
            assert [p["name"] for p in v["pins"]] == ["Kaito", "Hana"], scope
            assert {str(r["id"]): r["applied"] for r in v["repairs"]}[monster] is None
            assert c.post(f"/v1/conversations/{cid}/repairs/{rid}/remove").status_code == 200
        assert [p["name"] for p in view(migrated, cid)["pins"]][0] == "Gloomfang"
        with psycopg.connect(migrated) as conn:
            conn.execute("UPDATE owner_repair SET removed_at = now() WHERE id = %s", (monster,))
        assert [p["name"] for p in view(migrated, cid)["pins"]] == ["Kaito", "Hana"]


def test_a_live_pin_needs_no_attention_and_the_repairs_table_names_it(migrated):
    with make_client(migrated, **LLM) as c:
        cid = setup(c, migrated)
        before = view(migrated, cid)
        rows_before = inspector._attention(before, before["repairs"], 1, "en")
        pin_row(migrated, cid, "Kaito")
        after = view(migrated, cid)
        assert inspector._attention(after, after["repairs"], 1, "en") == rows_before
        for lang, label in (("en", "pinned"), ("ko", "고정")):
            page = c.get(f"/inspector/c/{cid}", params={"lang": lang}).text
            assert f'<span class="chip" title="entity_pin">{label}</span>' in page


def test_a_rebuild_keeps_the_pin_and_deleting_the_chat_deletes_it(migrated):
    from nmos_sidecar.rebuild import rebuild_all
    with make_client(migrated, **LLM) as c:
        cid = setup(c, migrated)
        pin_row(migrated, cid, "Kaito")
        rebuild_all(migrated)
        drain(migrated, complete)
        assert [p["name"] for p in view(migrated, cid)["pins"]] == ["Kaito"]
        assert c.post(f"/v1/conversations/{cid}/delete").status_code == 200
    with psycopg.connect(migrated) as conn:
        assert conn.execute("SELECT count(*) FROM owner_repair WHERE conversation_id = %s", (cid,)).fetchone()[0] == 0
