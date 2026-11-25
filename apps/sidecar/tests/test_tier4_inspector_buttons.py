"""Tests for Wave 4 Inspector UI markers, labels, and /messages endpoint:
branch_inherit marker, attention_dismiss markers, told_retract markers, rk.* labels, and GET /messages."""

from __future__ import annotations

from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import inspector, memorymap
from simchat import SimChat
from test_sidecar_integration import sync


def test_inspector_meta_emits_branch_inherit_marker_only_for_branched_chat():
    cid = uuid4()
    plain = {"id": cid, "host_chat_ref": "c1", "head_commit_id": uuid4(), "branched_from_host_chat_ref": None}
    branched = {**plain, "branched_from_host_chat_ref": "origin-1", "branched_from_message_ref": "m-4"}
    assert "branch_inherit" not in inspector._meta(plain, "ko")
    html = inspector._meta(branched, "ko")
    assert f'data-repair="branch_inherit:{cid}"' in html


def test_inspector_attention_emits_attention_dismiss_and_skips_dismissed_unmatched():
    ends = {
        "held": [{"id": 101, "predicate": "role_toward", "subject": "세라", "object": "카이토", "value": "기사",
                  "turn": 4, "reason": "held: not confirmed", "evidence": "그만뒀다"}],
        "aliases_held": [{"id": 102, "subject": "세라", "value": "은빛 기사", "turn": 5,
                          "reason": "held: both named", "evidence": "세라와 은빛 기사"}],
    }
    dismissed_rep = {"id": uuid4(), "kind": "attention_dismiss", "applied": False, "removed_at": None,
                     "target": {"what": "role_held", "turn": 2, "text": "old"}}
    rows = inspector._attention({"endings": ends}, [dismissed_rep], 10, "ko")
    assert len(rows) == 2
    assert 'data-repair="attention_dismiss:101:role_held"' in rows[0][3]
    assert 'data-repair="attention_dismiss:102:alias_held"' in rows[1][3]
    assert "&quot;attention&quot;: &quot;role_held&quot;" in rows[0][3]
    assert "&quot;attention&quot;: &quot;alias_held&quot;" in rows[1][3]


def test_inspector_told_section_emits_told_retract_for_story_rows_only():
    rows = [
        {"id": 55, "predicate": "told", "subject": "세라", "object": "카이토", "value": "지도는 가짜다", "turn": 3},
        {"id": 56, "predicate": "told", "subject": "유나", "object": "하나", "value": "열쇠가 없다", "turn": -1, "carried": True},
    ]
    # default memorymap.told_chains keeps exact keys without id
    plain = memorymap.told_chains(rows)
    assert all("id" not in link for chain in plain for link in chain)

    html = inspector.told_section(rows, "ko")
    assert 'data-repair="told_retract:55"' in html
    assert "told_retract:56" not in html


def test_inspector_repairs_table_labels_new_repair_kinds_and_fact_hidden_sign():
    now = "2026-11-25T10:00:00Z"
    reps = [
        {"id": uuid4(), "kind": "fact_add", "target": {"turn": 2, "text": "세라 located in 항구"},
         "value": {}, "note": None, "created_at": now, "applied": True, "removed_at": None},
        {"id": uuid4(), "kind": "told_retract", "target": {"turn": 3, "text": "세라 told 카이토"},
         "value": {}, "note": None, "created_at": now, "applied": True, "removed_at": None},
        {"id": uuid4(), "kind": "fact_hidden", "target": {"turn": 4, "text": "세라 identity: 밀수꾼"},
         "value": {"character": "카이토", "hidden": True}, "note": None, "created_at": now, "applied": True, "removed_at": None},
        {"id": uuid4(), "kind": "fact_hidden", "target": {"turn": 4, "text": "세라 identity: 밀수꾼"},
         "value": {"character": "유나", "hidden": False}, "note": None, "created_at": now, "applied": True, "removed_at": None},
        {"id": uuid4(), "kind": "attention_dismiss", "target": {"turn": 5, "text": "세라 role_toward 카이토"},
         "value": {}, "note": None, "created_at": now, "applied": True, "removed_at": None},
    ]
    ko = inspector._repairs_table(reps, "ko")
    for label in ("사실 추가", "전달 철회", "비밀 대상 변경", "확인 표시 넘김", "+ 카이토", "− 유나"):
        assert label in ko
    en = inspector._repairs_table(reps, "en")
    for label in ("add a fact", "retract a told line", "change hidden-from", "dismiss attention item"):
        assert label in en


def test_conversation_messages_endpoint_returns_newest_head_messages(migrated: str):
    chat = SimChat("w4-msg-picker")
    chat.user("첫 번째 메시지")
    chat.reply("첫 번째 응답")
    chat.user("두 번째 메시지")
    chat.reply("두 번째 응답")
    with make_client(migrated) as c:
        sync(c, chat)
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            cid = conn.execute("SELECT id FROM conversation WHERE host_chat_ref = %s", (chat.id,)).fetchone()["id"]
        r = c.get(f"/v1/conversations/{cid}/messages?limit=2", headers={"X-NMOS-Token": "test-token"})
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 2
        assert rows[0]["position"] > rows[1]["position"]
        assert rows[0]["host_logical_id"] == chat.messages[-1]["chatId"]
        assert "두 번째 응답" in rows[0]["preview"]
