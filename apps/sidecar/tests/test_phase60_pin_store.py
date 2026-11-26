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
from test_entity_exclude import TURN, complete, exclude, setup, view
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


# PHASE-67 part 4: migration 0043 widened the check again, additively (the owner's new repairs).
KINDS_0043 = {"fact_add", "told_retract", "fact_hidden", "attention_dismiss"}
# PHASE-70 (ADR 0096): migration 0045 widened the check additively for mention-triggered entity notes.
KINDS_0045 = {"entity_note"}


def test_an_entity_pin_inserts_and_an_unknown_kind_is_still_refused(migrated):
    assert kinds_of(migrated) == KINDS | KINDS_0043 | KINDS_0045 == set(repairs.KINDS)
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
    """A4: each earlier release's database, migrated up to the migration before 0038, then 0038 alone. The fixtures
    hold no repair, so one of each earlier kind is written first: the check added again must accept every one."""
    before_dir = tmp_path / "migrations"
    before_dir.mkdir()
    for path in migrations_dir().glob("[0-9][0-9][0-9][0-9]_*.sql"):
        if path.name < PIN:
            shutil.copy(path, before_dir / path.name)
    restore(database_url, dump)
    apply_migrations(database_url, directory=before_dir)
    assert "entity_pin" not in kinds_of(database_url)
    with psycopg.connect(database_url) as conn:
        cid = conn.execute("SELECT id FROM conversation ORDER BY id LIMIT 1").fetchone()[0]
        for kind in sorted(KINDS - {"entity_pin"}):
            conn.execute("INSERT INTO owner_repair (id, conversation_id, kind, target) VALUES (%s, %s, %s, '{}')",
                         (uuid7(), cid, kind))
    before = state(database_url)
    assert before["conversation"][0] > 0 and before["assertion"][0] > 0
    assert before["owner_repair"][0] == len(KINDS) - 1
    shutil.copy(migrations_dir() / PIN, before_dir / PIN)  # 0038 alone, whatever later migrations come
    assert apply_migrations(database_url, directory=before_dir) == [PIN]
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


# The API (step 3): the repair route takes a pin as it takes an exclusion, with no preview; undo is the plain removal.

def pin(c, cid: str, item: str, **kw):
    return c.post(f"/v1/conversations/{cid}/repairs", json={"kind": "entity_pin", "item": item, **kw})


def entities(c, cid: str) -> dict[str, dict]:
    return {e["name"]: e for e in c.get(f"/v1/conversations/{cid}/entities").json()}


def test_the_api_pins_lists_marks_and_takes_a_pin_back(migrated):
    with make_client(migrated, **LLM) as c:
        cid = setup(c, migrated)
        kaito = entity_id(view(migrated, cid), "Kaito")
        assert not any("pinned" in e for e in entities(c, cid).values())
        res = pin(c, cid, "Kaito", note="every scene")
        assert res.status_code == 200, res.text
        made = res.json()
        assert made["repair"]["kind"] == "entity_pin" and made["repair"]["value"] == {}
        assert made["repair"]["target"] == {"entity_type": "character", "name": "Kaito"}
        assert str(made["applied"]) == kaito
        rid = str(made["repair"]["id"])
        row = next(r for r in c.get(f"/v1/conversations/{cid}/repairs").json()["repairs"] if str(r["id"]) == rid)
        assert str(row["applied"]) == kaito and row["removed_at"] is None and "hidden" not in row
        marked = entities(c, cid)
        assert marked["Kaito"]["pinned"] == rid and not any("pinned" in e for n, e in marked.items() if n != "Kaito")
        assert [(p["name"], str(p["repair"])) for p in view(migrated, cid)["pins"]] == [("Kaito", rid)]
        assert c.get(f"/v1/views/c/{cid}/person/{kaito}").status_code == 200
        by_id = pin(c, cid, entity_id(view(migrated, cid), "Hana"))  # the panel names it by its id
        assert by_id.status_code == 200 and by_id.json()["repair"]["target"]["name"] == "Hana"
        # a pin has no preview of its own: it is made, and taken back, at once
        assert c.post(f"/v1/conversations/{cid}/repairs/preview",
                      json={"kind": "entity_pin", "item": "Kaito"}).status_code == 422
        assert c.post(f"/v1/conversations/{cid}/repairs/{rid}/remove").status_code == 200
        assert [p["name"] for p in view(migrated, cid)["pins"]] == ["Hana"] and "pinned" not in entities(c, cid)["Kaito"]
        row = next(r for r in c.get(f"/v1/conversations/{cid}/repairs").json()["repairs"] if str(r["id"]) == rid)
        assert row["removed_at"] is not None
        assert pin(c, cid, "Kaito").status_code == 200  # pinned again after the undo


def test_the_api_refuses_what_a_pin_cannot_name(migrated):
    with make_client(migrated, **LLM) as c:
        cid = setup(c, migrated)
        assert exclude(c, cid, "Gloomfang").status_code == 200
        assert pin(c, cid, "Kaito").status_code == 200
        for item, why, kw in (("Rowan", "persona", {}), ("Nobody", "not mentioned", {}),
                              ("Gloomfang", "not a character", {}), ("Kaito", "already", {}),
                              ("village", "only a character", {"entity_type": "place"})):
            res = pin(c, cid, item, **kw)
            assert res.status_code == 422 and why in res.json()["detail"], (item, res.text)
        with psycopg.connect(migrated) as conn:
            assert conn.execute("SELECT count(*) FROM owner_repair WHERE kind = 'entity_pin'").fetchone()[0] == 1


def test_a_pin_in_a_batch_and_a_pin_ages_a_preview_as_any_repair_does(migrated):
    with make_client(migrated, **LLM) as c:
        cid = setup(c, migrated)
        done = c.post(f"/v1/conversations/{cid}/repairs/batch", json={"items": [{"kind": "entity_pin", "item": "Hana"}]})
        assert done.status_code == 200 and done.json()["counts"] == {"entity_pin": 1}, done.text
        assert [p["name"] for p in view(migrated, cid)["pins"]] == ["Hana"]
        assert c.post(f"/v1/conversations/{cid}/repairs/batch/{done.json()['batch']}/remove").status_code == 200
        assert view(migrated, cid)["pins"] == []
        # memory changed since a preview: the repair ids its fingerprint holds now include the pin
        seen = c.post(f"/v1/conversations/{cid}/repairs/preview",
                      json={"kind": "entity_exclude", "item": "Gloomfang"}).json()["fingerprint"]
        assert pin(c, cid, "Kaito").status_code == 200
        assert exclude(c, cid, "Gloomfang", expect=seen).status_code == 409


# The setting (step 4): `pin_at_mentions`, off by default, editable like every runtime switch; nothing reads it yet.

@pytest.mark.parametrize("env, on", [(None, False), ("", False), ("0", False), ("1", True)])
def test_pin_at_mentions_is_off_unless_the_environment_says_1(env, on, monkeypatch):
    from nmos_sidecar.config import Settings
    monkeypatch.delenv("NMOS_PIN_AT_MENTIONS", raising=False)
    if env is not None:
        monkeypatch.setenv("NMOS_PIN_AT_MENTIONS", env)
    assert Settings().pin_at_mentions is on


def test_the_switch_is_a_runtime_setting_that_queues_nothing(migrated):
    from nmos_sidecar.retrieval import RECORDED, RecallOptions
    assert RecallOptions().pin_at_mentions is False and "pin_at_mentions" not in RECORDED  # the pins are recorded
    with make_client(migrated, **LLM) as c:
        setup(c, migrated)

        def generations():
            with psycopg.connect(migrated) as conn:
                return (conn.execute("SELECT count(*) FROM job").fetchone()[0],
                        conn.execute("SELECT key, activated_at FROM projection_generation ORDER BY key").fetchall())

        assert c.get("/v1/config").json()["recall"]["pin_at_mentions"] is False
        before = generations()
        on = c.put("/v1/config", json={"pin_at_mentions": True})
        assert on.status_code == 200 and on.json()["recall"]["pin_at_mentions"] is True, on.text
        assert c.get("/v1/config").json()["recall"]["pin_at_mentions"] is True
        assert "pin_at_mentions" in c.get("/v1/config").json()["overridden"]
        assert generations() == before  # no generation key moves, no job is queued
        assert c.put("/v1/config", json={"pin_at_mentions": "true"}).status_code == 422
        assert c.put("/v1/config", json={"pin_at_mentions": None}).json()["recall"]["pin_at_mentions"] is False
    with make_client(migrated, **LLM) as c:  # saved: a restart keeps it
        c.put("/v1/config", json={"pin_at_mentions": True})
    with make_client(migrated, **LLM) as c:
        assert c.get("/v1/config").json()["recall"]["pin_at_mentions"] is True


def test_every_policy_compiles_the_same_packet_with_the_switch_on(migrated):
    """Nothing reads the switch yet: under every policy a packet is byte for byte the one it is with the switch off.
    Resting (packet-v14) is set far off, so the repeated requests are alike."""
    from nmos_sidecar.packet import POLICIES
    from simchat import SimChat
    from test_sidecar_integration import recall, sync
    sim = SimChat()
    sim.user("We set out.")
    sim.reply(TURN)
    sim.user("Where is @Kaito and what does Hana feel about Gloomfang?")
    query = "Where is @Kaito and what does Hana feel about Gloomfang?"
    with make_client(migrated, **LLM) as c:
        sync(c, sim, character_name="Hana", persona_name="Rowan")
        drain(migrated, complete)
    for policy in POLICIES:
        with make_client(migrated, **LLM, packet_policy=policy, rest_after=10**6) as c:
            off = recall(c, sim, query, budget=2000)
            assert c.put("/v1/config", json={"pin_at_mentions": True}).status_code == 200
            on = recall(c, sim, query, budget=2000)
            assert c.put("/v1/config", json={"pin_at_mentions": None}).status_code == 200
        assert off["packet"]["text"] == on["packet"]["text"], policy
        if policy in ("packet-v19", "packet-v20"):
            assert "Kaito" in off["packet"]["text"], policy  # a packet with something in it
    with psycopg.connect(migrated) as conn:
        used = {r[0] for r in conn.execute("SELECT policy FROM retrieval_trace").fetchall()}
        assert used == set(POLICIES)
        assert not conn.execute("SELECT count(*) FROM retrieval_trace WHERE recall_options ? 'pin_at_mentions'"
                                ).fetchone()[0]


# The archive (step 5, A5): a pin made through the API comes back with a whole install's archive and a chat's.

def pin_rows(url: str) -> list[tuple]:
    with psycopg.connect(url) as conn:
        return conn.execute("SELECT id, kind, target, value, note, created_at, removed_at FROM owner_repair"
                            " WHERE kind = 'entity_pin' ORDER BY id").fetchall()


@pytest.mark.parametrize("whole", [True, False], ids=["install", "one-chat"])
def test_an_archive_round_trips_a_pin(whole, migrated, database_url_factory, tmp_path):
    from nmos_sidecar import archive
    from test_restore import export_to
    with make_client(migrated, **LLM) as c:
        cid = setup(c, migrated)
        assert pin(c, cid, "Kaito", note="every scene").status_code == 200
        assert c.put("/v1/config", json={"pin_at_mentions": True}).status_code == 200
        taken = pin(c, cid, "Hana").json()["repair"]["id"]
        assert c.post(f"/v1/conversations/{cid}/repairs/{taken}/remove").status_code == 200  # kept for audit
    source = export_to(tmp_path, migrated, "pins", **({} if whole else {"conversations": [cid]}))
    target = database_url_factory()
    done = archive.restore_file(target, str(source))
    assert [str(x["id"]) for x in done.conversations] == [cid]
    assert len(pin_rows(migrated)) == 2 and pin_rows(target) == pin_rows(migrated)
    assert [p["name"] for p in view(target, cid)["pins"]] == ["Kaito"]
    with psycopg.connect(target) as conn:  # a plain setting: with the install only, never with one chat
        setting = conn.execute("SELECT value FROM app_config WHERE key = 'pin_at_mentions'").fetchone()
    assert setting == ((True,) if whole else None)
