"""PHASE-68: preview and bulk deletion of conversations missing from the host (H22, ADR 0009).

Synthetic names only."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import UUID

import psycopg
import pytest
from psycopg.types.json import Jsonb

from conftest import make_client
from nmos_sidecar.ids import uuid7
from simchat import SimChat
from test_conversation_delete import TABLES, rows
from test_extraction import drain, filler
from test_generations import EMB, LLM, conv_id
from test_phase60_carry_delete import MINIMAL_SNAPSHOT, _insert_carry
from test_sidecar_integration import recall, sync
from test_vectors import FakeEmbedder, drain_embeddings


def _chat(line: str) -> SimChat:
    chat = SimChat()
    chat.user(line)
    chat.reply("Understood.")
    filler(chat, 1)
    chat.user("Next.")
    return chat


def test_orphan_preview_finds_missing_chats_stubs_and_carry_warnings(migrated: str, db) -> None:
    with make_client(migrated) as c:
        live = _chat("Hana visits the harbor.")
        orphan_a = _chat("Kaito lights the lantern.")
        orphan_b = _chat("Sera checks the tower.")
        branch_child = orphan_a.branch(1, name="Orphan A")
        for chat, ch, title in (
            (live, "Hana", "Harbor"),
            (orphan_a, "Kaito", "Lantern"),
            (orphan_b, "Sera", "Tower"),
            (branch_child, "Kaito", "Lantern (Branch)"),
        ):
            sync(c, chat, character_name=ch, chat_name=title)
        recall(c, orphan_a, "lantern")

        live_id = conv_id(c, live)
        oa_id = conv_id(c, orphan_a)
        ob_id = conv_id(c, orphan_b)
        br_id = conv_id(c, branch_child)

        # Insert an empty stub conversation (head_commit_id IS NULL, Q2 a) and another host's conversation.
        stub_id = uuid7()
        other_host_id = uuid7()
        db.execute(
            "INSERT INTO conversation (id, host, host_chat_ref, host_character_name, host_chat_name)"
            " VALUES (%s, 'pocketrisu', 'stub-chat-ref', 'Ghost', 'Empty stub')",
            (stub_id,),
        )
        db.execute(
            "INSERT INTO conversation (id, host, host_chat_ref, host_character_name)"
            " VALUES (%s, 'other_host', 'other-chat-ref', 'Other')",
            (other_host_id,),
        )

        # Active carry: live -> orphan_a (target active), orphan_b -> orphan_a (target missing),
        # and a removed carry: live -> orphan_b (must NOT be flagged).
        _insert_carry(db, live_id, oa_id)
        _insert_carry(db, ob_id, oa_id)
        _insert_carry(db, live_id, ob_id, removed_at=datetime.now(timezone.utc))

        res = c.post(
            "/v1/conversations/orphans/preview",
            json={"host": "pocketrisu", "active_chat_refs": [live.id, branch_child.id]},
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["host"] == "pocketrisu"
        assert data["total_host_conversations"] == 5  # live, oa, ob, branch_child, stub (excludes other_host)
        assert data["matched_active"] == 2
        by_id = {o["id"]: o for o in data["orphans"]}
        assert set(by_id) == {oa_id, ob_id, str(stub_id)}

        # orphan_a: messages > 0, last_retrieval set, 1 branch child, 2 active carry targets (1 live, 1 missing)
        oa = by_id[oa_id]
        assert oa["character"] == "Kaito" and oa["chat"] == "Lantern"
        assert oa["messages"] == len(orphan_a.messages)
        assert oa["last_retrieval"] is not None
        assert oa["branch_children"] == 1
        carried = {x["id"]: x for x in oa["carried_by"]}
        assert set(carried) == {live_id, ob_id}
        assert carried[live_id]["target_missing"] is False
        assert carried[live_id]["mode"] == "continue"
        assert carried[ob_id]["target_missing"] is True

        # orphan_b: removed carry link must NOT appear
        assert by_id[ob_id]["carried_by"] == []

        # stub: head_commit_id IS NULL -> messages == 0
        assert by_id[str(stub_id)]["messages"] == 0
        assert by_id[str(stub_id)]["host_chat_ref"] == "stub-chat-ref"


def test_orphan_preview_exceeds_200_conversation_list_cap(migrated: str, db) -> None:
    """Preview inspects every conversation for the host, not just the 200-row list_conversations slice."""
    with make_client(migrated) as c:
        with db.cursor() as cur:
            cur.executemany(
                "INSERT INTO conversation (id, host, host_chat_ref) VALUES (%s, 'pocketrisu', %s)",
                [(uuid7(), f"chat-{i:03d}") for i in range(215)],
            )
        active = [f"chat-{i:03d}" for i in range(10)]
        res = c.post("/v1/conversations/orphans/preview", json={"host": "pocketrisu", "active_chat_refs": active})
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["total_host_conversations"] == 215
        assert data["matched_active"] == 10
        assert len(data["orphans"]) == 205


def test_delete_batch_removes_selected_preserves_others_and_guards_trigger(migrated: str, db) -> None:
    with make_client(migrated, embedder=FakeEmbedder(), **LLM, **EMB) as c:
        kept = _chat("Hana stays in the library.")
        gone_1 = _chat("Kaito walks to the bridge.")
        gone_2 = _chat("Sera locks the workshop.")
        for chat in (kept, gone_1, gone_2):
            sync(c, chat)
        drain(migrated)
        drain_embeddings(migrated)
        recall(c, gone_1, "bridge")

        kid, g1, g2 = conv_id(c, kept), conv_id(c, gone_1), conv_id(c, gone_2)
        before_kept = rows(db, kid)
        before_g1, before_g2 = rows(db, g1), rows(db, g2)
        _insert_carry(db, kid, g1)  # kept carries from gone_1

        missing_id = str(uuid7())
        # Duplicate g1 + g2 + missing_id -> deduplicated, missing reported in not_found
        res = c.post("/v1/conversations/delete-batch", json={"ids": [g1, g2, g1, missing_id]})
        assert res.status_code == 200, res.text
        body = res.json()
        assert [x["id"] for x in body["deleted"]] == [g1, g2]
        assert body["not_found"] == [missing_id]
        assert body["totals"]["conversations"] == 2
        assert body["totals"]["revisions"] == before_g1["source_revision"] + before_g2["source_revision"]
        assert body["totals"]["carry_links"] == 1

        assert rows(db, g1) == dict.fromkeys(TABLES, 0)
        assert rows(db, g2) == dict.fromkeys(TABLES, 0)
        assert rows(db, kid) == before_kept
        assert db.execute("SELECT count(*) FROM conversation_carry").fetchone()["count"] == 0

    # Migration 0012's raw-revision delete guard still refuses plain DELETE outside delete_conversation.
    with pytest.raises(psycopg.errors.RaiseException, match="never deleted"):
        db.execute("DELETE FROM source_revision")


def test_delete_batch_origin_preserves_branch_inherited_rows(migrated: str, db) -> None:
    """Deleting a branch origin via delete-batch leaves branch_inherit copies untouched (migration 0042)."""
    with make_client(migrated, **LLM) as c:
        origin = _chat("Hana opens the north gate.")
        sync(c, origin)
        drain(migrated)
        branch_chat = origin.branch(1, name="Origin")
        sync(c, branch_chat)
        oid = conv_id(c, origin)
        bid = conv_id(c, branch_chat)

        before_branch = rows(db, bid)
        assert before_branch["extraction"] > 0

        res = c.post("/v1/conversations/delete-batch", json={"ids": [oid]})
        assert res.status_code == 200, res.text
        assert res.json()["totals"]["conversations"] == 1

        row = db.execute("SELECT branched_from_conversation_id, branched_from_host_chat_ref, branch_inherit"
                         " FROM conversation WHERE id = %s", (bid,)).fetchone()
        assert row["branched_from_conversation_id"] is None
        assert row["branched_from_host_chat_ref"] == origin.id
        assert rows(db, bid) == before_branch


def test_orphan_routes_enforce_auth_and_validation(migrated: str) -> None:
    with make_client(migrated, auth_token="secret-token") as c:
        # Unauthenticated rejected
        assert c.post("/v1/conversations/orphans/preview", json={"active_chat_refs": []}).status_code == 401
        assert c.post("/v1/conversations/delete-batch", json={"ids": [str(uuid7())]}).status_code == 401

        hdr = {"Authorization": "Bearer secret-token"}
        # Empty ids / oversized ids / bad uuid -> 422
        assert c.post("/v1/conversations/delete-batch", headers=hdr, json={"ids": []}).status_code == 422
        assert c.post("/v1/conversations/delete-batch", headers=hdr, json={"ids": ["not-a-uuid"]}).status_code == 422
        too_many = [str(uuid7()) for _ in range(501)]
        assert c.post("/v1/conversations/delete-batch", headers=hdr, json={"ids": too_many}).status_code == 422

        # NUL byte and lone surrogate in host / active_chat_refs -> 422 (D40), never 500
        assert c.post("/v1/conversations/orphans/preview", headers=hdr,
                      json={"host": "pocket\x00risu", "active_chat_refs": []}).status_code == 422
        assert c.post("/v1/conversations/orphans/preview", headers=hdr,
                      json={"host": "pocketrisu", "active_chat_refs": ["bad\x00id"]}).status_code == 422
        raw_surrogate = json.dumps({"host": "pocketrisu", "active_chat_refs": ["bad\ud800id"]}, ensure_ascii=True)
        res = c.post("/v1/conversations/orphans/preview",
                     headers={**hdr, "Content-Type": "application/json"}, content=raw_surrogate)
        assert res.status_code == 422

        # Authorized empty DB preview succeeds
        ok = c.post("/v1/conversations/orphans/preview", headers=hdr, json={"active_chat_refs": ["c-1"]})
        assert ok.status_code == 200
        assert ok.json() == {"host": "pocketrisu", "total_host_conversations": 0, "matched_active": 0, "orphans": []}
