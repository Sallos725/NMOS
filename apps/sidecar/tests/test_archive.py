"""NMOS Archive export (Phase 16 step 3, ADR 0050): what an archive holds and what it never holds.

Synthetic names only."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime

import psycopg
import pytest

from conftest import make_client
from memeval import stub_extractor
from nmos_sidecar import archive
from simchat import SimChat
from test_canon import push
from test_extraction import drain
from test_generations import EMB, LLM, conv_id
from test_sidecar_integration import recall, sync
from test_summaries import drain as drain_summaries
from test_vectors import FakeEmbedder, drain_embeddings

KEY = "sk-archive-test-0123456789"


def story() -> SimChat:
    chat = SimChat()
    for text in ("Hana wants to find the keeper.", "Hana keeps a secret from Kaito: the letter is forged.",
                 "Kaito is in the garden.", "Kaito wants to become a knight."):
        chat.user(text)
        chat.reply("Noted.")
    for i in range(14):  # enough turns for a scene summary (ADR 0042)
        chat.user(f"Turn {i} goes on.")
        chat.reply(f"Reply {i} follows.")
    chat.user("Go on.")
    return chat


def play(c, url: str) -> tuple[SimChat, SimChat]:
    """A chat with every kind of history and owner input, and a branch of it: edits, a swipe, a deleted message,
    canon, a repair, an entity link, a memory mode, embeddings and recorded requests."""
    chat = story()
    sync(c, chat)
    drain(url, stub_extractor)
    drain_embeddings(url)
    cid = conv_id(c, chat)
    recall(c, chat, "keeper", budget=2000)
    chat.edit(4, "Kaito is in the orchard.")
    chat.reroll("Noted, again.")
    chat.reroll("Noted, a third time.")
    chat.swipe(0)
    chat.delete(6)
    chat.user("And then?")
    sync(c, chat)
    push(c, chat, {"card:desc": ("Hana is the lighthouse keeper's daughter.", {"field": "desc"})})
    drain(url, stub_extractor)
    drain_embeddings(url)
    drain_summaries(url)
    goal = next(t for t in c.get(f"/v1/conversations/{cid}/threads").json() if t["text"] == "find the keeper")
    assert c.post(f"/v1/conversations/{cid}/repairs", json={"kind": "thread_close", "item": str(goal["id"])}).status_code == 200
    link = c.post(f"/v1/conversations/{cid}/entity-links",
                  json={"entity_type": "character", "name": "Kaito", "same_as": "Hana"})
    assert link.status_code == 200, link.text
    assert c.put(f"/v1/conversations/{cid}/memory-mode", json={"strict": True}).status_code == 200
    recall(c, chat, "garden", budget=2000)
    chat.reply("Fine.")  # appended to an unchanged head: the fast path (ADR 0010)
    chat.user("More.")
    sync(c, chat)
    branch = chat.branch(3, "Side")
    branch.user("A different path.")
    sync(c, branch)
    recall(c, branch, "path", budget=2000)
    return chat, branch


def read(data: bytes) -> tuple[dict, dict[str, list[dict]], dict[str, bytes]]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        assert names[-1] == "manifest.json"
        manifest = json.loads(zf.read("manifest.json"))
        raw = {n: zf.read(n) for n in names if n != "manifest.json"}
    tables = {n.removeprefix("tables/").removesuffix(".jsonl"): [json.loads(x) for x in b.splitlines()]
              for n, b in raw.items()}
    return manifest, tables, raw


def export(c, **params) -> bytes:
    res = c.get("/v1/archive", params=params)
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/zip"
    assert archive.SUFFIX in res.headers["content-disposition"]
    return res.content


def count(db, sql: str, *args) -> int:
    return db.execute(sql, args).fetchone()["count"]


def test_the_whole_install_holds_the_ledger_projections_and_settings_but_no_key(migrated, db):
    with make_client(migrated, embedder=FakeEmbedder(), **LLM, **EMB) as c:
        assert c.put("/v1/config", json={"llm_api_key": KEY, "recall_top_k": 7}).status_code == 200
        chat, branch = play(c, migrated)
        other = story()
        sync(c, other)
        data = export(c)
    manifest, tables, raw = read(data)
    assert KEY.encode() not in data
    assert manifest["format"] == "nmos-archive" and manifest["format_version"] == 1
    assert manifest["scope"] == "install"
    assert manifest["contents"] == {"ledger": True, "settings": True, "projections": True, "embeddings": False}
    assert manifest["schema"]["level"] == manifest["schema"]["migrations"][-1]["version"]
    assert {c["host_chat_ref"] for c in manifest["conversations"]} == {chat.id, branch.id, other.id}
    assert next(c for c in manifest["conversations"] if c["host_chat_ref"] == branch.id)["branched_from"]
    # Every file as the manifest lists it; nothing else.
    listed = {f["path"]: f for f in manifest["files"]}
    assert set(listed) == set(raw)
    for path, body in raw.items():
        assert listed[path]["sha256"] == hashlib.sha256(body).hexdigest()
        assert listed[path]["bytes"] == len(body) and listed[path]["rows"] == len(body.splitlines())
    assert not set(tables) & set(archive.NEVER)
    assert "revision_embedding" not in tables
    # Every row of every archived table.
    for table in tables:
        if table != "app_config":
            assert len(tables[table]) == count(db, f"SELECT count(*) FROM {table}"), table
    for table in ("extraction", "assertion", "retrieval_trace", "owner_repair", "entity_link", "canon_manifest",
                  "canon_applied", "worldline_append", "active_membership", "summary"):
        assert tables[table], table
    # Settings: kept but the key.
    settings = {r["key"]: r["value"] for r in tables["app_config"]}
    assert settings["recall_top_k"] == 7 and "llm_api_key" not in settings
    # Rows as named columns, values as stored.
    conv = next(r for r in tables["conversation"] if r["host_chat_ref"] == chat.id)
    assert conv["memory_strict"] is True
    stored = db.execute("SELECT created_at FROM conversation WHERE id = %s", (conv["id"],)).fetchone()["created_at"]
    assert datetime.fromisoformat(conv["created_at"]) == stored  # to the microsecond


def test_one_conversation_holds_only_its_rows_and_no_settings(migrated, db):
    with make_client(migrated, embedder=FakeEmbedder(), **LLM, **EMB) as c:
        chat, branch = play(c, migrated)
        cid = conv_id(c, chat)
        manifest, tables, _ = read(export(c, conversation=cid, embeddings=True))
        assert c.get("/v1/archive", params={"conversation": "00000000-0000-0000-0000-000000000000"}).status_code == 404
        assert c.get("/v1/archive", params={"conversation": "nope"}).status_code == 422
    assert manifest["scope"] == "conversations" and [x["id"] for x in manifest["conversations"]] == [cid]
    assert manifest["contents"]["settings"] is False and "app_config" not in tables
    assert {r["id"] for r in tables["conversation"]} == {cid}
    assert {r["conversation_id"] for r in tables["retrieval_trace"]} == {cid}
    revs = {r["id"] for r in db.execute(
            "SELECT sr.id::text AS id FROM source_revision sr JOIN source_object so ON so.id = sr.source_object_id"
            " WHERE so.conversation_id = %s", (cid,)).fetchall()}
    assert {r["id"] for r in tables["source_revision"]} == revs
    assert {r["source_revision_id"] for r in tables["assertion"]} <= revs
    assert tables["revision_embedding"] and {r["source_revision_id"] for r in tables["revision_embedding"]} <= revs
    vector = tables["revision_embedding"][0]["embedding"]
    assert isinstance(vector, str) and vector.startswith("[")
    # The generations every archived row names are in it.
    keys = {r["key"] for r in tables["projection_generation"]}
    assert {r["extractor_key"] for r in tables["extraction"]} <= keys


def test_without_projections_only_the_ledger(migrated):
    with make_client(migrated, embedder=FakeEmbedder(), **LLM, **EMB) as c:
        play(c, migrated)
        manifest, tables, _ = read(export(c, projections=False))
    assert manifest["contents"]["projections"] is False
    assert not {"extraction", "assertion", "summary", "revision_embedding"} & set(tables)
    assert tables["retrieval_trace"] and tables["source_revision"]


def test_the_same_state_gives_the_same_files(migrated):
    with make_client(migrated, embedder=FakeEmbedder(), **LLM, **EMB) as c:
        play(c, migrated)
        first, second = read(export(c, embeddings=True)), read(export(c, embeddings=True))
    assert first[2] == second[2]
    assert first[0]["files"] == second[0]["files"]


def test_a_credential_anywhere_refuses_the_export(migrated):
    with make_client(migrated, **LLM) as c:
        assert c.put("/v1/config", json={"llm_api_key": KEY}).status_code == 200
        chat = SimChat()
        chat.user(f"my key is {KEY}, keep it")  # pasted into a chat by mistake
        chat.reply("Noted.")
        sync(c, chat)
        res = c.get("/v1/archive")
        assert res.status_code == 409 and "credential" in res.json()["detail"]
    with make_client(migrated, auth_token="token-archive-0123456789") as c:  # the token too
        c.headers["Authorization"] = "Bearer token-archive-0123456789"
        chat = SimChat()
        chat.user("the token is token-archive-0123456789")
        sync(c, chat)
        assert c.get("/v1/archive", params={"conversation": conv_id(c, chat)}).status_code == 409


def test_an_endpoint_that_may_carry_a_key_is_left_out(migrated):
    with make_client(migrated) as c:
        url = "https://llm.example/v1?key=abc"
        assert c.put("/v1/config", json={"llm_url": url, "llm_model": "m", "embed_url": "http://emb.example/v1"}
                     ).status_code == 200
        manifest, tables, raw = read(export(c))
    settings = {r["key"]: r["value"] for r in tables["app_config"]}
    assert "llm_url" not in settings and settings["embed_url"] == "http://emb.example/v1"
    assert manifest["omitted_settings"] == ["llm_url"]
    assert not any(b"key=abc" in body for body in raw.values())


def test_the_command_writes_the_same_archive(migrated, tmp_path, monkeypatch):
    with make_client(migrated, embedder=FakeEmbedder(), **LLM, **EMB) as c:
        chat, _ = play(c, migrated)
        cid = conv_id(c, chat)
        api = read(export(c, conversation=cid))
    monkeypatch.setenv("NMOS_DATABASE_URL", migrated)
    out = tmp_path / "one.nmos.zip"
    assert archive.main(["export", "--conversation", cid, "-o", str(out)]) == 0
    cli = read(out.read_bytes())
    assert cli[2] == api[2]
    assert list(tmp_path.iterdir()) == [out]  # no partial file left
    assert archive.main(["export", "--conversation", "00000000-0000-0000-0000-000000000000",
                         "-o", str(tmp_path / "x.nmos.zip")]) == 2
    assert list(tmp_path.iterdir()) == [out]


def test_an_install_without_migrations_is_refused(database_url):
    with psycopg.connect(database_url) as conn:
        conn.execute("CREATE TABLE schema_migrations (version text PRIMARY KEY, checksum text NOT NULL)")
        conn.commit()
        with pytest.raises(archive.ArchiveError, match="no applied migrations"):
            archive.write_archive(conn, io.BytesIO())


def test_the_command_names_the_file_when_not_told(migrated, tmp_path, monkeypatch):
    monkeypatch.setenv("NMOS_DATABASE_URL", migrated)
    monkeypatch.chdir(tmp_path)
    assert archive.main(["export"]) == 0
    [written] = list(tmp_path.iterdir())
    assert written.name.startswith("nmos-all-") and written.name.endswith(archive.SUFFIX)
