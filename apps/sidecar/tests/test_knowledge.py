"""#10 / D19: public, limited (known_by / hidden_from) and unknown knowledge are distinct."""

from __future__ import annotations

import shutil
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar.facts import fact_line
from nmos_sidecar.migrate import apply_migrations, migrations_dir
from nmos_sidecar.packet import PACKET_NOTE
from nmos_sidecar.predicates import knowledge
from simchat import SimChat
from test_extraction import drain, filler
from test_generations import LLM
from test_sidecar_integration import recall, sync

BASE = {"subject": "{{user}}", "predicate": "identity", "object": None, "value": "이사장의 아들", "epistemic": "stated",
        "position": 1, "host_logical_id": "x"}


def test_validation_gives_empty_knowledge_one_meaning():
    assert knowledge({}) == ("unknown", None, None, None)
    assert knowledge({"known_by": [], "hidden_from": []}) == ("unknown", None, None, None)
    assert knowledge({"knowledge": "limited"}) == ("unknown", None, None, None)  # nobody named: nothing known
    assert knowledge({"knowledge": "public", "known_by": ["하나"]}) == ("public", None, None, None)
    assert knowledge({"knowledge": "public", "hidden_from": ["카이토"]}) == ("limited", None, ["카이토"], None)
    assert knowledge({"known_by": ["하나", "하나", " "]}) == ("limited", ["하나"], None, None)


def test_contradictory_knowledge_is_dropped_and_noted():
    scope, known, hidden, note = knowledge({"known_by": ["하나", "Kaito"], "hidden_from": ["kaito", "유이"]})
    assert (scope, known, hidden) == ("limited", ["하나"], ["유이"])
    assert note == "contradictory knowledge for: Kaito"


def test_unknown_knowledge_is_not_rendered_as_not_known():
    line = fact_line({**BASE, "knowledge": "unknown", "known_by": None, "hidden_from": None})
    assert "known_by" not in line and "hidden_from" not in line and "knowledge=" not in line
    assert "unmarked fact, is unknown: do not assume either way" in PACKET_NOTE
    assert "not listed as knowing a fact do not know it" not in PACKET_NOTE


def test_public_fact_does_not_require_known_by_list():
    line = fact_line({**BASE, "knowledge": "public", "known_by": None, "hidden_from": None})
    assert 'knowledge="public"' in line and "known_by" not in line


def test_hidden_from_is_preserved():
    line = fact_line({**BASE, "knowledge": "limited", "known_by": None, "hidden_from": ["카이토"]})
    assert 'hidden_from="카이토"' in line and "known_by" not in line


def test_limited_known_by_is_rendered_consistently(migrated, db):
    replies = {
        "비밀": [{"subject": "{{user}}", "subject_type": "character", "predicate": "identity", "value": "이사장의 아들",
                "knowledge": "limited", "known_by": ["하나", "{{user}}"], "hidden_from": ["카이토"]}],
        "축제": [{"subject": "마을", "subject_type": "place", "predicate": "world_fact", "value": "축제 준비 중",
                "knowledge": "public", "known_by": [], "hidden_from": []}],
        "편지": [{"subject": "하나", "subject_type": "character", "predicate": "has_status", "value": "편지를 받음"}],
    }

    def complete(system, user):
        target = user.split("TARGET", 1)[1]
        return {"assertions": [a for word, items in replies.items() if word in target for a in items]}, "{}"

    with make_client(migrated, **LLM) as c:
        chat = SimChat()
        chat.user("하나에게만 속삭인다. 비밀인데 나 이사장 아들이야.")
        chat.reply("마을은 모두가 아는 축제 준비로 바쁘다.")
        chat.user("하나가 편지를 받았다.")
        chat.reply("ok")
        filler(chat, 4)
        sync(c, chat)
        drain(migrated, complete)
        text = recall(c, chat, "카이토, 하나, 마을 축제, 편지, 내 정체 {{user}}", in_context=[])["packet"]["text"]
    stored = {r["predicate"]: r for r in db.execute("SELECT predicate, knowledge, known_by, hidden_from FROM assertion")}
    assert stored["identity"]["knowledge"] == "limited" and stored["identity"]["hidden_from"] == ["카이토"]
    assert stored["world_fact"]["knowledge"] == "public" and stored["world_fact"]["known_by"] is None
    assert stored["has_status"]["knowledge"] == "unknown"
    assert 'known_by="하나, {{user}}" hidden_from="카이토">' in text
    assert 'knowledge="public">마을 world fact: 축제 준비 중' in text
    assert '<Fact kind="has_status" turn="1">하나 has status: 편지를 받음</Fact>' in text  # no marks


def test_existing_knowledge_rows_migrate_conservatively(database_url, tmp_path):
    before = tmp_path / "before"
    before.mkdir()
    for path in sorted(migrations_dir().glob("[0-9]*.sql")):
        if path.name < "0009":
            shutil.copy(path, before / path.name)
    apply_migrations(database_url, Path(before))
    with psycopg.connect(database_url, row_factory=dict_row, autocommit=True) as conn:
        conn.execute("INSERT INTO conversation (id, host, host_chat_ref) VALUES (gen_random_uuid(), 'h', 'c')")
        conv = conn.execute("SELECT id FROM conversation").fetchone()["id"]
        conn.execute("INSERT INTO source_object (id, conversation_id, host_logical_id) VALUES (gen_random_uuid(), %s, 'm')",
                     (conv,))
        obj = conn.execute("SELECT id FROM source_object").fetchone()["id"]
        conn.execute("INSERT INTO source_revision (id, source_object_id, revision_hash, content, metadata, lifecycle)"
                     " VALUES (gen_random_uuid(), %s, 'h', 'x', '{}', 'accepted')", (obj,))
        rev = conn.execute("SELECT id FROM source_revision").fetchone()["id"]
        conn.execute("INSERT INTO extraction (id, source_revision_id, window_hash, compiler_version, model, raw)"
                     " VALUES (gen_random_uuid(), %s, 'w', 'extract-v2', 'm', '{}')", (rev,))
        ext = conn.execute("SELECT id FROM extraction").fetchone()["id"]
        for known, hidden in ((["하나"], None), (None, ["카이토"]), (None, None)):
            conn.execute("INSERT INTO assertion (extraction_id, source_revision_id, subject, predicate, status,"
                         " known_by, hidden_from) VALUES (%s, %s, 's', 'identity', 'valid', %s, %s)",
                         (ext, rev, known, hidden))
    apply_migrations(database_url)
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        scopes = [r["knowledge"] for r in conn.execute("SELECT knowledge FROM assertion ORDER BY id")]
    assert scopes == ["limited", "limited", "unknown"]
