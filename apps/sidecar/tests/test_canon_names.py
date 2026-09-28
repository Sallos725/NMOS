"""Names from canon (Phase 14 step 4, PHASE-14 Q6, ADR 0046): a lorebook entry's keys name one thing, so a given name
the lorebook lists becomes a mention of that character (K31), with the guard that an entry naming two known entities
joins nothing, the persona never takes a canon alias, and the owner's splits apply."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import canon
from nmos_sidecar.entities import resolve
from simchat import SimChat
from test_canon import entry, push
from memeval import stub_extractor
from test_extraction import drain
from test_generations import LLM
from test_sidecar_integration import recall, sync

FULL, GIVEN = "한서윤", "서윤"


def row(subject: str, kind: str = "character", **more) -> dict:
    return {"subject": subject, "subject_type": kind, "predicate": "has_trait", "value": "x", "modality": "actual", **more}


def test_an_entry_naming_one_known_character_gives_it_the_other_keys_as_aliases():
    rows = [row(FULL), row("카이토"), row("등대", "place")]
    r = resolve(uuid.uuid4(), rows, canon=[{"key": "lore:seoyun", "names": [FULL, GIVEN, "한 대리"]}])
    assert r.entity("character", GIVEN)["id"] == r.entity("character", FULL)["id"]
    assert r.entity("character", "한 대리")["id"] == r.entity("character", FULL)["id"]
    aliases = r.entity("character", FULL)["aliases"]
    assert {(a["other"], a["canon"]) for a in aliases} == {(GIVEN, "lore:seoyun"), ("한 대리", "lore:seoyun")}


def test_the_guard_two_known_names_another_kind_the_persona_nothing_known():
    rows = [row(FULL), row("카이토"), row("등대", "place"), row("{{user}}")]
    both = resolve(uuid.uuid4(), rows, canon=[{"key": "lore:pair", "names": [FULL, "카이토", GIVEN]}])
    assert both.status("character", GIVEN) == "unresolved"  # two known characters: joins nothing
    place = resolve(uuid.uuid4(), rows, canon=[{"key": "lore:x", "names": [FULL, "등대", GIVEN]}])
    assert place.status("character", GIVEN) == "unresolved"  # a key names a known place
    persona = resolve(uuid.uuid4(), rows, persona=["타쿠미"], canon=[{"key": "lore:me", "names": ["타쿠미", "타쿠"]}])
    assert persona.status("character", "타쿠") == "unresolved"  # the persona's names are never a mention (ADR 0023)
    unknown = resolve(uuid.uuid4(), rows, canon=[{"key": "lore:z", "names": ["마르타", "마르"]}])
    assert unknown.status("character", "마르") == "unresolved"  # no key the head mentions
    # two entries give one alias to two characters: the alias is ambiguous, not joined to either
    twice = resolve(uuid.uuid4(), rows, canon=[{"key": "lore:a", "names": [FULL, "대리"]},
                                               {"key": "lore:b", "names": ["카이토", "대리"]}])
    assert twice.status("character", "대리") == "ambiguous"


def test_the_owner_splits_a_canon_alias():
    rows = [row(FULL)]
    split = {"id": uuid.uuid4(), "entity_type": "character", "name": FULL, "other": GIVEN,
             "created_at": datetime.now(timezone.utc)}
    r = resolve(uuid.uuid4(), rows, splits=[split], canon=[{"key": "lore:seoyun", "names": [FULL, GIVEN]}])
    assert r.entity("character", GIVEN) is None or r.entity("character", GIVEN)["id"] != r.entity("character", FULL)["id"]


def test_a_given_name_the_lorebook_lists_brings_the_character_s_facts_and_a_replay_keeps_its_canon(migrated):
    chat = SimChat("canon-names")
    chat.user(f"{FULL}의 특징: 정산 창구를 맡고 있다.")
    chat.reply("알겠다.")
    chat.user("계속.")
    chat.reply("좋다.")
    chat.user(f"{GIVEN}의 일은 뭐였지?")
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        drain(migrated, stub_extractor)
        before = recall(c, chat, f"{GIVEN}의 일은 뭐였지?", budget=2000)
        assert "정산 창구" not in before["packet"]["text"]  # K31: the given name alone is no mention
        lore = entry("lore:seoyun", f"{FULL}은 항구 협회의 대리다.", keys=[FULL, GIVEN], scope="character", mode="normal")
        manifest = canon.manifest_id([lore])
        push(c, chat, {"lore:seoyun": (f"{FULL}은 항구 협회의 대리다.", {"keys": [FULL, GIVEN], "scope": "character",
                                                                          "mode": "normal"})})
        after = recall(c, chat, f"{GIVEN}의 일은 뭐였지?", budget=2000, canon_manifest_id=manifest)
        assert "정산 창구" in after["packet"]["text"]
        cid = c.get("/v1/conversations").json()[0]["id"]
        page = c.get(f"/inspector/c/{cid}", params={"lang": "en"}).text
        assert "canon" in page[page.index('id="s-entities"'):]
        # the lorebook entry goes away; the recorded request still replays with its own canon
        push(c, chat, {})
        assert "정산 창구" not in recall(c, chat, f"{GIVEN}의 일은 뭐였지?", budget=2000)["packet"]["text"]
        replay = c.get(f"/v1/trace/{after['trace_id']}/replay").json()
        assert replay["status"] == "ok" and replay["reproduced"] is True, replay
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        assert canon.names(conn, cid) == []
        assert canon.names(conn, cid, mid=manifest) == [{"key": "lore:seoyun", "names": [FULL, GIVEN]}]
