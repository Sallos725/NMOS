"""PHASE-70 (ADR 0096): direct editing across memory categories and mention-triggered entity description notes.

Covers migration 0045, `entity_note` CRUD/validation/supersession/undo/batch/alias-merge/rebuild/archive/branch/delete,
mention-triggered packet injection across packet-v19/v20/v21 (Tiers 1-3, cap, overuse-rest exemption, cleaner stripping,
as-of replay), `fact_correct` with `new_subject` on `possesses`, and Explorer / Person Sheet / Inspector HTML.
Synthetic names only.
"""

from __future__ import annotations

import re
import shutil
import time

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from conftest import active_generation, make_client
from nmos_sidecar import archive, audit, branch, inspector, repairs, views
from nmos_sidecar.facts import memory_view
from nmos_sidecar.ids import uuid7
from nmos_sidecar.migrate import apply_migrations, migrations_dir
from nmos_sidecar.packet import clean_text, clean_text_v4
from simchat import SimChat
from test_extraction import drain
from test_generations import LLM, conv_id
from test_sidecar_integration import recall, sync
from test_upgrade import FIXTURES, restore

MIGRATION_0045 = "0045_entity_note.sql"
USED = {"calls": 1, "input": 100, "output": 10}
TURN_TEXT = (
    "Hana gives Kaito the silver pocket watch at the old mill. "
    "Rowan inspects the Harbor Watch seal and remembers the Fog Pact. "
    "Hana hides her secret smuggling map from Kaito."
)


def _f(subject, subject_type, predicate, value=None, obj=None, obj_type=None, **kw):
    return {
        "subject": subject, "subject_type": subject_type, "predicate": predicate,
        "object": obj, "object_type": obj_type, "value": value,
        "polarity": "positive", "modality": "actual", "source": "narration", "evidence": "",
        **kw,
    }


def _complete(system, user):
    target = user.split("TARGET turn", 1)[-1]
    if TURN_TEXT not in target:
        return {"assertions": []}, "{}", USED
    return {"assertions": [
        _f("Hana", "character", "located_in", None, "old mill", "place"),
        _f("Hana", "character", "has_status", "cautious"),
        _f("Hana", "character", "relationship", "childhood friend", "Kaito", "character"),
        _f("Kaito", "character", "feels_toward", "grateful", "Hana", "character"),
        _f("Hana", "character", "possesses", None, "은빛 회중시계", "item"),
        _f("Hana", "character", "member_of", None, "Harbor Watch", "group"),
        _f("Fog Pact", "concept", "world_fact", "an old harbor truce"),
        _f("Hana", "character", "knows", "smuggling route under the pier",
           knowledge="limited", known_by=["Hana", "Rowan"], hidden_from=["Kaito"]),
        _f("Rowan", "character", "has_status", "alert"),
        _f("Gloomfang", "character", "has_status", "lurking"),
    ]}, "{}", USED


def _view(url: str, cid: str, known_at=None) -> dict:
    with psycopg.connect(url, row_factory=dict_row) as conn:
        head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid,)).fetchone()["head_commit_id"]
        return memory_view(conn, head, active_generation(conn, "extract").key, known_at=known_at)


def _setup(client, url: str) -> tuple[str, SimChat]:
    sim = SimChat()
    sim.user("We meet at dusk.")
    sim.reply(TURN_TEXT)
    sim.user("Let's check our gear.")
    sim.reply("Everything is quiet at the pier.")
    sync(client, sim, character_name="Hana", persona_name="Rowan")
    drain(url, _complete)
    return conv_id(client, sim), sim


def _entity(v: dict, name: str, etype: str | None = None) -> dict:
    return next(e for e in v["entities"] if e["name"] == name and (etype is None or e["type"] == etype))


def _kinds_of(url: str) -> set[str]:
    with psycopg.connect(url) as conn:
        check = conn.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
            " WHERE conrelid = 'owner_repair'::regclass AND conname = 'owner_repair_kind_check'"
        ).fetchone()[0]
    return set(re.findall(r"'(\w+)'", check))


# --- 1. Migration 0045 ------------------------------------------------------------------------

def test_migration_0045_allows_entity_note_and_rejects_unknown_kind(migrated):
    assert "entity_note" in _kinds_of(migrated)
    assert _kinds_of(migrated) == set(repairs.KINDS)
    with psycopg.connect(migrated) as conn:
        cid = conn.execute(
            "INSERT INTO conversation (id, host, host_chat_ref) VALUES (%s, 'test', %s) RETURNING id",
            (uuid7(), f"chat-{uuid7()}"),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO owner_repair (id, conversation_id, kind, target, value) VALUES (%s, %s, 'entity_note', %s, %s)",
            (uuid7(), cid, Jsonb({"entity_type": "item", "name": "은빛 회중시계"}), Jsonb({"text": "황동 태엽"})),
        )
        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.transaction():
                conn.execute(
                    "INSERT INTO owner_repair (id, conversation_id, kind, target, value)"
                    " VALUES (%s, %s, 'not_a_kind', '{}', '{}')",
                    (uuid7(), cid),
                )


@pytest.mark.parametrize("dump", FIXTURES, ids=[p.stem for p in FIXTURES])
def test_every_upgrade_fixture_applies_0045_and_keeps_existing_rows(dump, database_url, tmp_path):
    before_dir = tmp_path / "migrations"
    before_dir.mkdir()
    for path in migrations_dir().glob("[0-9][0-9][0-9][0-9]_*.sql"):
        if path.name < MIGRATION_0045:
            shutil.copy(path, before_dir / path.name)
    restore(database_url, dump)
    apply_migrations(database_url, directory=before_dir)
    assert "entity_note" not in _kinds_of(database_url)
    with psycopg.connect(database_url) as conn:
        cid = conn.execute("SELECT id FROM conversation ORDER BY id LIMIT 1").fetchone()[0]
        conn.execute(
            "INSERT INTO owner_repair (id, conversation_id, kind, target, value) VALUES (%s, %s, 'entity_pin', %s, '{}')",
            (uuid7(), cid, Jsonb({"entity_type": "character", "name": "Hana"})),
        )
        before_count = conn.execute("SELECT count(*) FROM owner_repair").fetchone()[0]
    shutil.copy(migrations_dir() / MIGRATION_0045, before_dir / MIGRATION_0045)
    assert apply_migrations(database_url, directory=before_dir) == [MIGRATION_0045]
    assert "entity_note" in _kinds_of(database_url)
    with psycopg.connect(database_url) as conn:
        assert conn.execute("SELECT count(*) FROM owner_repair").fetchone()[0] == before_count


# --- 2. entity_note CRUD, validation, update-supersede, batch, exclusions ---------------------

def test_entity_note_crud_all_five_types_update_supersedes_and_validation(migrated):
    with make_client(migrated, **LLM) as c:
        cid, _ = _setup(c, migrated)
        v = _view(migrated, cid)

        targets = [
            ("은빛 회중시계", "item", "뚜껑에 해바라기가 새겨진 낡은 은빛 회중시계, 3분 늦게 감"),
            ("Hana", "character", "왼쪽 손목에 얇은 흉터가 있고 밤색 코트를 즐겨 입음"),
            ("old mill", "place", "부두 동쪽의 버려진 풍차 방앗간, 바닥 판자가 삐걱거림"),
            ("Harbor Watch", "group", "항구 야간 경비대, 구리 호루라기를 신분증으로 씀"),
            ("Fog Pact", "concept", "안개 낀 밤에는 무기 소지를 금하는 항구 관습"),
            ("Rowan", "character", "검은 가죽 수첩을 항상 안주머니에 넣고 다님"),
        ]
        note_ids: dict[str, str] = {}
        for name, etype, text in targets:
            ent = _entity(v, name, etype)
            res = c.post(f"/v1/conversations/{cid}/repairs",
                         json={"kind": "entity_note", "item": str(ent["id"]), "new_value": text})
            assert res.status_code == 200, res.text
            note_ids[name] = str(res.json()["repair"]["id"])
            assert res.json()["applied"] == str(ent["id"])

        ents = {e["name"]: e for e in c.get(f"/v1/conversations/{cid}/entities").json()}
        for name, _, text in targets:
            assert ents[name]["note"]["text"] == text
            assert ents[name]["note"]["id"] == note_ids[name]

        # Updating a note supersedes the previous active row in the same transaction
        watch_id = str(_entity(v, "은빛 회중시계", "item")["id"])
        upd = c.post(f"/v1/conversations/{cid}/repairs",
                     json={"kind": "entity_note", "item": watch_id, "new_value": "금이 간 유리와 해바라기 각인, 5분 느림"})
        assert upd.status_code == 200
        new_id = str(upd.json()["repair"]["id"])
        assert new_id != note_ids["은빛 회중시계"]
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            rows = conn.execute(
                "SELECT id, removed_at, value FROM owner_repair WHERE conversation_id = %s AND kind = 'entity_note'"
                " AND target->>'name' = '은빛 회중시계' ORDER BY created_at",
                (cid,),
            ).fetchall()
        assert len(rows) == 2
        assert rows[0]["removed_at"] is not None
        assert rows[1]["removed_at"] is None and str(rows[1]["id"]) == new_id

        # Undo removes the active note
        assert c.post(f"/v1/conversations/{cid}/repairs/{new_id}/remove").status_code == 200
        ents_after = {e["name"]: e for e in c.get(f"/v1/conversations/{cid}/entities").json()}
        assert "note" not in ents_after["은빛 회중시계"]

        # Validation failures: empty, >300 chars, unknown entity
        assert c.post(f"/v1/conversations/{cid}/repairs",
                      json={"kind": "entity_note", "item": watch_id, "new_value": "   "}).status_code == 422
        assert c.post(f"/v1/conversations/{cid}/repairs",
                      json={"kind": "entity_note", "item": watch_id, "new_value": "x" * 301}).status_code == 422
        assert c.post(f"/v1/conversations/{cid}/repairs",
                      json={"kind": "entity_note", "item": "ghost_thing", "entity_type": "item",
                            "new_value": "desc"}).status_code == 422

        # Exclusion rules: scope="cast" keeps/allows note, scope="memory" suppresses and refuses
        gloom = _entity(v, "Gloomfang", "character")
        assert c.post(f"/v1/conversations/{cid}/repairs",
                      json={"kind": "entity_exclude", "item": str(gloom["id"]), "scope": "cast"}).status_code == 200
        r_cast = c.post(f"/v1/conversations/{cid}/repairs",
                        json={"kind": "entity_note", "item": str(gloom["id"]), "new_value": "검은 갈기를 가진 짐승"})
        assert r_cast.status_code == 200
        assert any(n["name"] == "Gloomfang" for n in _view(migrated, cid)["entity_notes"])

        # Switch exclusion to memory: note suppressed and new note refused
        ex_id = _view(migrated, cid)["excluded"][str(gloom["id"])]["repair"]
        assert c.post(f"/v1/conversations/{cid}/repairs/{ex_id}/remove").status_code == 200
        assert c.post(f"/v1/conversations/{cid}/repairs",
                      json={"kind": "entity_exclude", "item": str(gloom["id"]), "scope": "memory"}).status_code == 200
        assert all(n["name"] != "Gloomfang" for n in _view(migrated, cid)["entity_notes"])
        assert c.post(f"/v1/conversations/{cid}/repairs",
                      json={"kind": "entity_note", "item": str(gloom["id"]), "new_value": "blocked"}).status_code == 422

        # Batch: duplicate entity_note for the same entity in one batch is refused atomically
        dup = c.post(f"/v1/conversations/{cid}/repairs/batch", json={"items": [
            {"kind": "entity_note", "item": watch_id, "new_value": "first"},
            {"kind": "entity_note", "item": watch_id, "new_value": "second"},
        ]})
        assert dup.status_code == 422


# --- 3. Lifecycle: alias merge, rebuild, archive/restore, branch inherit, delete --------------

def test_entity_note_survives_rebuild_archive_branch_and_deletes_with_chat(migrated, tmp_path):
    with make_client(migrated, **LLM) as c:
        cid, sim = _setup(c, migrated)
        v = _view(migrated, cid)
        watch = _entity(v, "은빛 회중시계", "item")
        res = c.post(f"/v1/conversations/{cid}/repairs",
                     json={"kind": "entity_note", "item": str(watch["id"]),
                           "new_value": "뚜껑에 해바라기 각인, 3분 느림"})
        assert res.status_code == 200

        # Rebuild keeps owner_repair entity_note intact
        rb = c.post(f"/v1/conversations/{cid}/rebuild")
        assert rb.status_code == 200
        drain(migrated, _complete)
        v_rebuilt = _view(migrated, cid)
        assert any(n["name"] == "은빛 회중시계" and "해바라기" in n["text"] for n in v_rebuilt["entity_notes"])

        # Archive export includes owner_repair; round-trip after deleting conversation restores it
        zip_path = tmp_path / "export.nmos.zip"
        with zip_path.open("wb") as fh, psycopg.connect(migrated, row_factory=dict_row) as conn:
            archive.write_archive(conn, fh, [cid])
        assert c.post(f"/v1/conversations/{cid}/delete").status_code == 200
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            assert conn.execute("SELECT count(*) AS n FROM owner_repair WHERE conversation_id = %s", (cid,)).fetchone()["n"] == 0
        archive.restore_archive(migrated, archive.check_archive(str(zip_path)))
        v_restored = _view(migrated, cid)
        assert any(n["name"] == "은빛 회중시계" and "해바라기" in n["text"] for n in v_restored["entity_notes"])

        # Branch inherits entity_note automatically on first sync (and via backfill) without extra LLM calls
        branched = sim.branch(len(sim.messages) - 1)
        branched.user("A new branch turn.")
        branched.reply("Branch reply.")
        sync(c, branched, character_name="Hana", persona_name="Rowan")
        bcid = conv_id(c, branched)
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            b_notes = conn.execute(
                "SELECT value FROM owner_repair WHERE conversation_id = %s AND kind = 'entity_note' AND removed_at IS NULL",
                (bcid,),
            ).fetchall()
        assert len(b_notes) == 1 and "해바라기" in b_notes[0]["value"]["text"]


# --- 4. Mention-triggered packet recall, cap, overuse rest, cleaner, replay -------------------

@pytest.mark.parametrize("policy", ["packet-v20", "packet-v21"])
def test_entity_note_packet_injection_tiers_cap_rest_and_cleaner(migrated, policy):
    pkt = lambda r: (r.get("packet") or {}).get("text") or ""
    with make_client(migrated, **LLM, packet_policy=policy) as c:
        cid, sim = _setup(c, migrated)
        v = _view(migrated, cid)

        # Baseline before any note: zero entity_note lines
        base = recall(c, sim, "은빛 회중시계를 꺼내 시간을 확인한다.", character_name="Hana", persona_name="Rowan")
        assert 'kind="entity_note"' not in pkt(base)

        # Attach notes to item + place + group + concept + characters
        watch = _entity(v, "은빛 회중시계", "item")
        mill = _entity(v, "old mill", "place")
        hana = _entity(v, "Hana", "character")
        group = _entity(v, "Harbor Watch", "group")
        pact = _entity(v, "Fog Pact", "concept")
        kaito = _entity(v, "Kaito", "character")
        rowan = _entity(v, "Rowan", "character")

        r_watch = c.post(f"/v1/conversations/{cid}/repairs", json={
            "kind": "entity_note", "item": str(watch["id"]),
            "new_value": "뚜껑에 해바라기 각인이 있고 항상 3분 늦게 가는 낡은 은시계",
        })
        assert r_watch.status_code == 200
        watch_note_id = str(r_watch.json()["repair"]["id"])

        assert c.post(f"/v1/conversations/{cid}/repairs", json={
            "kind": "entity_note", "item": str(mill["id"]),
            "new_value": "지붕이 반쯤 무너진 붉은 벽돌 방앗간",
        }).status_code == 200

        # Unrelated query mentioning no noted entity -> 0 entity_note lines injected
        unrelated = recall(c, sim, "오늘 저녁은 따뜻한 수프로 할까?", character_name="Hana", persona_name="Rowan")
        assert 'kind="entity_note"' not in pkt(unrelated)

        # Tier 1: explicit mention in query -> required entity_note injected
        t1 = recall(c, sim, "은빛 회중시계를 열어 시침을 살핀다.", character_name="Hana", persona_name="Rowan")
        t1_text = pkt(t1)
        assert 'kind="entity_note" source="owner" locked="true" type="item"' in t1_text
        assert "해바라기 각인" in t1_text
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            t1_audit = audit.audit(conn, t1["trace_id"])
        note_entry = next(x for x in t1_audit["lines"] if (x.get("ref") or {}).get("repair") == watch_note_id)
        assert note_entry["label"] == "required" and note_entry["placed"] is True

        # Cleaner stripping: clean-v3 and clean-v4 strip the injected block completely
        wrapped = f"Hello\n{t1_text}\nWorld"
        assert "해바라기 각인" not in clean_text(wrapped)
        assert "해바라기 각인" not in clean_text_v4(wrapped)

        # Tier 2: mentioned in previous_ai only (user says something generic right after AI mentioned old mill)
        sim.user("Where should we hide?")
        sim.reply("Let's meet inside the old mill before midnight.")
        sync(c, sim, character_name="Hana", persona_name="Rowan")
        t2 = recall(c, sim, "알겠어, 곧 갈게.", character_name="Hana", persona_name="Rowan",
                    previous_ai="Let's meet inside the old mill before midnight.")
        assert 'type="place">old mill: 지붕이 반쯤 무너진 붉은 벽돌 방앗간</Fact>' in pkt(t2)

        # Tier 3: Hana holds 은빛 회중시계 (positive possesses) -> mentioning Hana brings in her held item's note
        sim.user("Where is Hana?")
        sim.reply("She is walking near the pier.")
        sync(c, sim, character_name="Hana", persona_name="Rowan")
        t3 = recall(c, sim, "Hana에게 다가가 말을 건다.", character_name="Hana", persona_name="Rowan")
        assert "은빛 회중시계:" in pkt(t3)

        # Overuse rest exemption: 4 consecutive queries mentioning 은빛 회중시계 with replies that never echo the note
        for i in range(4):
            sim.user(f"은빛 회중시계를 만지작거린다 ({i}).")
            sync(c, sim, character_name="Hana", persona_name="Rowan")
            r_rep = recall(c, sim, f"은빛 회중시계를 만지작거린다 ({i}).", character_name="Hana", persona_name="Rowan")
            assert "해바라기 각인" in pkt(r_rep), f"entity_note was rested on iteration {i}"
            sim.reply(f"바람이 불어온다 ({i}).")
            sync(c, sim, character_name="Hana", persona_name="Rowan")

        # ENTITY_NOTES_MAX = 5 cap: attach notes to 7 entities and mention all 7
        for ent, txt in [
            (hana, "밤색 코트"), (group, "구리 호루라기"), (pact, "야간 무장 금지"),
            (kaito, "항구 정비공"), (rowan, "검은 가죽 수첩"),
        ]:
            assert c.post(f"/v1/conversations/{cid}/repairs",
                          json={"kind": "entity_note", "item": str(ent["id"]), "new_value": txt}).status_code == 200
        all7 = recall(
            c, sim,
            "Hana, Kaito, Rowan, 은빛 회중시계, old mill, Harbor Watch, Fog Pact 모두 확인하자.",
            character_name="Hana", persona_name="Rowan",
        )
        assert pkt(all7).count('kind="entity_note"') <= 5

        # As-of replay: trace before note stays without note; trace during note v1 keeps v1 after update/undo
        time.sleep(0.02)
        upd = c.post(f"/v1/conversations/{cid}/repairs", json={
            "kind": "entity_note", "item": str(watch["id"]), "new_value": "완전히 바뀐 v2 설명",
        })
        assert upd.status_code == 200
        assert c.post(f"/v1/conversations/{cid}/repairs/{upd.json()['repair']['id']}/remove").status_code == 200

        rep_base = c.get(f"/v1/trace/{base['trace_id']}/replay").json()
        assert rep_base["status"] == "ok" and rep_base["reproduced"] is True
        assert 'kind="entity_note"' not in rep_base["text"]
        rep_t1 = c.get(f"/v1/trace/{t1['trace_id']}/replay").json()
        assert rep_t1["status"] == "ok" and rep_t1["reproduced"] is True
        assert "해바라기 각인" in rep_t1["text"]
        assert "완전히 바뀐 v2 설명" not in rep_t1["text"]
        assert watch_note_id  # referenced cleanly


def test_entity_note_triggers_via_linked_alias(migrated):
    with make_client(migrated, **LLM, packet_policy="packet-v21") as c:
        sim = SimChat()
        sim.user("Found two clues.")
        sim.reply("Hana holds the 은빛 회중시계. Later Kaito also mentions the Silver Watch.")
        sim.user("Ok.")
        sync(c, sim, character_name="Hana", persona_name="Rowan")

        def comp(system, user):
            if "Silver Watch" not in user.split("TARGET turn", 1)[-1]:
                return {"assertions": []}, "{}", USED
            return {"assertions": [
                _f("Hana", "character", "possesses", None, "은빛 회중시계", "item"),
                _f("Silver Watch", "item", "world_fact", "ticking softly"),
            ]}, "{}", USED

        drain(migrated, comp)
        cid = conv_id(c, sim)
        v = _view(migrated, cid)
        watch = _entity(v, "은빛 회중시계", "item")
        assert c.post(f"/v1/conversations/{cid}/repairs", json={
            "kind": "entity_note", "item": str(watch["id"]), "new_value": "태엽이 헐거운 해바라기 시계",
        }).status_code == 200
        # Link Silver Watch -> 은빛 회중시계
        pv = c.post(f"/v1/conversations/{cid}/entity-links/preview",
                    json={"entity_type": "item", "name": "은빛 회중시계", "same_as": "Silver Watch"}).json()
        assert c.post(f"/v1/conversations/{cid}/entity-links",
                      json={"entity_type": "item", "name": "은빛 회중시계", "same_as": "Silver Watch",
                            "expect": pv["fingerprint"]}).status_code == 200
        # Mentioning the alias "Silver Watch" triggers the merged entity's note!
        r = recall(c, sim, "Tell me about the Silver Watch.", character_name="Hana", persona_name="Rowan")
        assert "태엽이 헐거운 해바라기 시계" in ((r.get("packet") or {}).get("text") or "")


def test_entity_note_leaves_frozen_packet_v19_untouched(migrated):
    with make_client(migrated, **LLM, packet_policy="packet-v19") as c:
        cid, sim = _setup(c, migrated)
        v = _view(migrated, cid)
        watch = _entity(v, "은빛 회중시계", "item")
        assert c.post(f"/v1/conversations/{cid}/repairs", json={
            "kind": "entity_note", "item": str(watch["id"]), "new_value": "해바라기 각인",
        }).status_code == 200
        r = recall(c, sim, "은빛 회중시계를 꺼낸다.", character_name="Hana", persona_name="Rowan")
        assert 'kind="entity_note"' not in ((r.get("packet") or {}).get("text") or "")


# --- 5. Stage 1: fact_correct with new_subject on possesses -----------------------------------

def test_fact_correct_new_subject_on_possesses_and_cross_key_refusal(migrated):
    with make_client(migrated, **LLM) as c:
        cid, _ = _setup(c, migrated)
        v = _view(migrated, cid)
        poss = next(f for f in v["facts"] if f["predicate"] == "possesses")
        status = next(f for f in v["facts"] if f["predicate"] == "has_status" and f["subject"] == "Hana")
        assert poss["subject"] == "Hana" and poss["object"] == "은빛 회중시계"

        # Later-turn new_subject on has_status is refused (version_key changes)
        bad = c.post(f"/v1/conversations/{cid}/repairs", json={
            "kind": "fact_correct", "item": str(status["id"]), "new_subject": "Kaito", "turn": 1,
        })
        assert bad.status_code == 422

        # Later-turn new_subject on possesses is allowed (version_key is item-keyed)
        ok_later = c.post(f"/v1/conversations/{cid}/repairs", json={
            "kind": "fact_correct", "item": str(poss["id"]), "new_subject": "Kaito", "turn": 1,
        })
        assert ok_later.status_code == 200
        v_after = _view(migrated, cid)
        cur_poss = next(f for f in v_after["facts"] if f["predicate"] == "possesses" and f["object"] == "은빛 회중시계")
        assert cur_poss["subject"] == "Kaito"
        assert cur_poss.get("owner") is True

        # Undo and test in-place (turn=None) holder correction as well
        assert c.post(f"/v1/conversations/{cid}/repairs/{ok_later.json()['repair']['id']}/remove").status_code == 200
        v_reset = _view(migrated, cid)
        poss2 = next(f for f in v_reset["facts"] if f["predicate"] == "possesses")
        ok_inplace = c.post(f"/v1/conversations/{cid}/repairs", json={
            "kind": "fact_correct", "item": str(poss2["id"]), "new_subject": "Rowan",
        })
        assert ok_inplace.status_code == 200
        v_after2 = _view(migrated, cid)
        cur_poss2 = next(f for f in v_after2["facts"] if f["predicate"] == "possesses" and f["object"] == "은빛 회중시계")
        assert cur_poss2["subject"] == "Rowan"


# --- 6. Stage 1 + Stage 2: Explorer, Person Sheet, Inspector HTML -----------------------------

def test_explorer_person_sheet_and_inspector_expose_edits_and_entity_notes_safely(migrated):
    with make_client(migrated, **LLM) as c:
        cid, _ = _setup(c, migrated)
        v = _view(migrated, cid)
        watch = _entity(v, "은빛 회중시계", "item")
        hana = _entity(v, "Hana", "character")
        xss_note = '<script>alert("xss")</script> 은빛 각인'
        res = c.post(f"/v1/conversations/{cid}/repairs", json={
            "kind": "entity_note", "item": str(watch["id"]), "new_value": xss_note,
        })
        assert res.status_code == 200
        note_rid = str(res.json()["repair"]["id"])

        # Explorer view: inline edits on pairs, secrets, items, entities; escaped note; no tables
        exp = c.get(f"/v1/views/c/{cid}/explore", params={"lang": "ko"}).json()["html"]
        assert "<table" not in exp
        assert "<script>" not in exp
        assert "&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;" in exp
        assert 'class="v-note-box"' in exp
        # Pairs drawer has fact_correct/fact_retract
        pairs_sec = exp.split('id="s-pairs"', 1)[1].split('id="s-threads"', 1)[0]
        assert 'class="v-edit"' in pairs_sec
        assert 'data-repair="fact_correct:' in pairs_sec and ':value"' in pairs_sec
        assert 'data-repair="fact_retract:' in pairs_sec
        # Secrets drawer has underlying fact repairs + secret_found_out
        epi_sec = exp.split('id="s-epistemic"', 1)[1].split('id="s-items"', 1)[0]
        assert 'data-repair="secret_found_out:' in epi_sec
        assert 'data-repair="fact_correct:' in epi_sec
        assert 'data-repair="fact_hidden:' in epi_sec
        # Items drawer has possesses subject/object edit + entity_note edit + undo + link to item entity page
        items_sec = exp.split('id="s-items"', 1)[1].split('id="s-entities"', 1)[0]
        assert f'href="/inspector/c/{cid}/e/{watch["id"]}"' in items_sec
        assert f'data-repair="entity_note:{watch["id"]}:edit"' in items_sec
        assert f'data-repair="undo:{note_rid}"' in items_sec
        assert ':subject"' in items_sec
        # Entities drawer has entity_note add for unnoted Hana and edit for noted watch
        ent_sec = exp.split('id="s-entities"', 1)[1]
        assert f'data-repair="entity_note:{hana["id"]}:add"' in ent_sec
        assert f'data-repair="entity_note:{watch["id"]}:edit"' in ent_sec

        # Rich Person Sheet shows entity note and relationship edit drawers
        assert c.post(f"/v1/conversations/{cid}/repairs", json={
            "kind": "entity_note", "item": str(hana["id"]), "new_value": "밤색 롱코트와 파란 머플러",
        }).status_code == 200
        person_rich = c.get(f"/v1/views/c/{cid}/person/{hana['id']}", params={"rich": "1", "lang": "ko"}).json()["html"]
        assert "밤색 롱코트와 파란 머플러" in person_rich
        assert 'class="v-note-box"' in person_rich
        assert 'data-repair="fact_correct:' in person_rich

        # Inspector entity page shows note for noted entity and omits label for unnoted entity
        insp_watch = c.get(f"/inspector/c/{cid}/e/{watch['id']}", params={"lang": "ko"}).text
        assert "설명 메모" in insp_watch and "<script>" not in insp_watch
        mill = _entity(v, "old mill", "place")
        insp_mill = c.get(f"/inspector/c/{cid}/e/{mill['id']}", params={"lang": "ko"}).text
        assert "설명 메모" not in insp_mill
