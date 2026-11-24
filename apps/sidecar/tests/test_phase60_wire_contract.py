"""PHASE-60 S1: the `/v1/retrieve` trim and coverage wire contract, seen from the plugin's side.

`test_phase60_coverage` tests the sidecar's decision; this file checks what the plugin receives. Every request is the
body `core.ts` sends (active commit and manifest hash from its sync, the previous reply, every host id in the prompt,
`trim: {keep_recent_turns: k, step: k}`). Every answer must hold the contract's keys and types. A boundary must be
a `chatId` the plugin holds (the string `trimPrompt` compares with `String(m.chatId)`), and it must be the first
message of `keep_from_turn`. Turns are counted from the host chat itself (ADR 0008, ADR 0041: a user message and the
replies that answer it are one turn, the greeting is turn 0), not read back through the sidecar's own query.
"""

from __future__ import annotations

from typing import Any

from conftest import make_client
from simchat import SimChat
from test_generations import LLM, conv_id
from test_packet_ledger import db, extract
from test_sidecar_integration import sync
from test_summaries import ON as SUMMARIES_ON, drain as drain_summaries

TRIM_KEYS = {"keep_from_id", "keep_from_turn", "reason"}
COVERAGE_KEYS = {"recorded_through_turn", "covered_through_turn"}
REASONS = {"off", "short", "uncovered", "no_summaries", "stale", "empty_packet"}
KEEP, STEP = 20, 20
TRIM = {"keep_recent_turns": KEEP, "step": STEP}
QUESTION = "세라는 은빛 나침반을 어디에 숨겼지?"


def host_turns(chat: SimChat) -> list[int]:
    """Each host message's turn, counted as ADR 0008 does for a chat without comments or disabled messages."""
    turns, n, replied = [], 0, False
    for m in chat.messages:
        if m["role"] == "user":
            n, replied = n + replied, False
        else:
            replied = True
        turns.append(n)
    return turns


def grow(chat: SimChat, now: int) -> None:
    """Answer the open user message, then add turns until the newest user message is turn `now`."""
    if chat.messages and chat.messages[-1]["role"] == "user":
        chat.reply(f"Reply {host_turns(chat)[-1]}: 카이토가 부두의 밧줄을 천천히 감았다.")
    while host_turns(chat)[-1] < now - 1:
        t = host_turns(chat)[-1] + 1
        chat.user(f"Turn {t}: 하나와 함께 항구 길을 걷는다.")
        chat.reply(f"Reply {t}: 돌담 위로 조용한 바람이 분다.")
    chat.user(QUESTION)
    assert host_turns(chat)[-1] == now


def plugin_body(chat: SimChat, synced: dict[str, Any], budget: int = 2000, **extra: Any) -> dict[str, Any]:
    """The `/v1/retrieve` body `core.ts` sends after its sync, every host message in the prompt."""
    previous = next((m["data"] for m in reversed(chat.messages[:-1]) if m["role"] != "user"), None)
    return {
        "host": "pocketrisu", "chat_id": chat.id,
        "active_commit": synced["active_commit"], "manifest_hash": synced["manifest_hash"],
        "query": chat.messages[-1]["data"], "previous_ai": previous,
        "in_context_ids": [str(m["chatId"]) for m in chat.messages], "budget_tokens": budget,
        "client_timings_ms": {"manifest": 1.0, "sync": 2.0, "before_retrieve": 3.0},
        "canon_manifest_id": None, "canon_held": [], **extra,
    }


def check_coverage(res: dict[str, Any]) -> None:
    cov = res["coverage"]
    assert isinstance(cov, dict) and set(cov) == COVERAGE_KEYS, cov
    for v in cov.values():
        assert v is None or type(v) is int, cov


def check_trim(res: dict[str, Any], chat: SimChat | None = None) -> dict[str, Any]:
    """The contract's shape of an answer to a trim request (checks 1, 2, 3, 5); returns its `trim`."""
    check_coverage(res)
    trim = res["trim"]
    assert isinstance(trim, dict) and set(trim) == TRIM_KEYS, trim
    kid, kturn, reason = trim["keep_from_id"], trim["keep_from_turn"], trim["reason"]
    assert kid is None or (type(kid) is str and kid), trim
    assert kturn is None or type(kturn) is int, trim
    assert reason is None or type(reason) is str, trim
    if kid is None:
        assert kturn is None and reason in REASONS, trim
        return trim
    assert reason is None and kturn is not None, trim
    assert res["freshness"] == "fresh", res["freshness"]
    assert chat is not None
    ids = [str(m["chatId"]) for m in chat.messages]
    assert ids.count(kid) == 1, "keep_from_id is not exactly one message the plugin holds"
    b = ids.index(kid)
    turns = host_turns(chat)
    latest_user = max(i for i, m in enumerate(chat.messages) if m["role"] == "user")
    assert b <= latest_user  # trimPrompt refuses a boundary after the latest user message
    assert turns[b] == kturn and (b == 0 or turns[b - 1] < kturn), "not the first message of keep_from_turn"
    assert all(t < kturn for t in turns[:b]) and all(t >= kturn for t in turns[b:])
    assert kturn % STEP == 0
    return trim


def ask(client, chat: SimChat, synced: dict[str, Any], **extra: Any) -> dict[str, Any]:
    res = client.post("/v1/retrieve", json=plugin_body(chat, synced, **extra))
    assert res.status_code == 200, res.text
    return res.json()


def refresh(url: str, client, chat: SimChat) -> dict[str, Any]:
    """Sync as the plugin does, then let the stub workers extract and summarize."""
    synced = sync(client, chat)
    extract(url)
    drain_summaries(url)
    return synced


def test_the_plugin_gets_the_contract_over_a_growing_chat(migrated):
    chat = SimChat()
    chat.reply("세라가 낡은 등대 앞에서 손을 흔든다. 오늘은 항구가 조용하다.")  # the greeting: turn 0
    chat.user("Turn 1: 세라는 오래된 등대 아래에 은빛 나침반을 숨겼다.")
    chat.reply("Reply 1: 세라가 은빛 나침반을 숨긴 자리를 기억해 두었다.")
    with make_client(migrated, **{**SUMMARIES_ON, "packet_policy": "packet-v20"}) as client:
        # 6: now 39 -> nothing before the first possible step.
        grow(chat, 39)
        synced_39 = refresh(migrated, client, chat)
        res = ask(client, chat, synced_39, trim=TRIM)
        assert check_trim(res, chat) == {"keep_from_id": None, "keep_from_turn": None, "reason": "short"}

        # 6: now 40 -> 20; 2 and 3: the boundary is turn 20's user message, a chatId the plugin holds.
        grow(chat, 40)
        synced = refresh(migrated, client, chat)
        res = ask(client, chat, synced, trim=TRIM)
        assert check_trim(res, chat)["keep_from_turn"] == 20
        assert res["trim"]["keep_from_id"] == str(chat.messages[host_turns(chat).index(20)]["chatId"])
        assert chat.messages[host_turns(chat).index(20)]["role"] == "user"
        # The chat-side turn count is the sidecar's (ADR 0041), checked once against its membership.
        with db(migrated) as conn:
            head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s",
                                (conv_id(client, chat),)).fetchone()["head_commit_id"]
            rows = conn.execute(
                "SELECT so.host_logical_id AS id, am.turn FROM active_membership am"
                " JOIN source_revision sr ON sr.id = am.source_revision_id"
                " JOIN source_object so ON so.id = sr.source_object_id WHERE am.commit_id = %s", (head,)).fetchall()
        assert {r["id"]: r["turn"] for r in rows} == {str(m["chatId"]): t for m, t in zip(chat.messages, host_turns(chat))}

        # 5: an unknown chat and a stale head still answer a trim request with a trim object, never a boundary.
        unknown = client.post("/v1/retrieve", json={**plugin_body(chat, synced, trim=TRIM), "chat_id": "no-such-chat",
                                                    "active_commit": None, "manifest_hash": None}).json()
        assert unknown["freshness"] == "unknown_conversation"
        assert check_trim(unknown)["reason"] == "stale"
        stale = ask(client, chat, synced_39, trim=TRIM)
        assert stale["freshness"] == "stale" and check_trim(stale, chat)["reason"] == "stale"
        empty = ask(client, chat, synced, budget=5, trim=TRIM)
        assert empty["packet"]["text"] == "" and check_trim(empty, chat)["reason"] == "empty_packet"

        # 6: now 59 -> still 20; now 60 -> 40.
        grow(chat, 59)
        synced = refresh(migrated, client, chat)
        assert check_trim(ask(client, chat, synced, trim=TRIM), chat)["keep_from_turn"] == 20
        grow(chat, 60)
        synced = refresh(migrated, client, chat)
        res = ask(client, chat, synced, trim=TRIM)
        assert check_trim(res, chat)["keep_from_turn"] == 40
        assert res["coverage"]["covered_through_turn"] >= 39

        # 6: a scene window that is not summarized (turns 24..31) lowers the boundary to the step below it.
        cid = conv_id(client, chat)
        with db(migrated) as conn:
            n = conn.execute("UPDATE summary SET discarded_at = now() WHERE conversation_id = %s AND level = 'scene'"
                             " AND first_turn = 24 AND discarded_at IS NULL", (cid,)).rowcount
        assert n >= 1
        res = ask(client, chat, synced, trim=TRIM)
        assert res["coverage"]["covered_through_turn"] == 23
        assert check_trim(res, chat)["keep_from_turn"] == 20
        with db(migrated) as conn:
            conn.execute("UPDATE summary SET discarded_at = NULL WHERE conversation_id = %s AND level = 'scene'"
                         " AND first_turn = 24", (cid,))
        assert check_trim(ask(client, chat, synced, trim=TRIM), chat)["keep_from_turn"] == 40

        # 6: an extraction gap (turn 37) lowers it the same way; a gap at the boundary or after it does not.
        with db(migrated) as conn:
            def gap(turn: int, on: bool) -> None:
                t = conn.execute("SELECT source_revision_id AS rid, turn_hash FROM active_membership"
                                 " WHERE commit_id = %s AND turn = %s AND turn_hash IS NOT NULL", (head_60, turn)).fetchone()
                conn.execute("UPDATE extraction SET discarded_at = " + ("now()" if on else "NULL")
                             + " WHERE source_revision_id = %s AND window_hash = %s", (t["rid"], t["turn_hash"]))
            head_60 = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid,)).fetchone()["head_commit_id"]
            gap(40, True)
            assert check_trim(ask(client, chat, synced, trim=TRIM), chat)["keep_from_turn"] == 40
            gap(37, True)
            assert check_trim(ask(client, chat, synced, trim=TRIM), chat)["keep_from_turn"] == 20
            gap(7, True)
            res = ask(client, chat, synced, trim=TRIM)
            assert check_trim(res, chat) == {"keep_from_id": None, "keep_from_turn": None, "reason": "uncovered"}
            for t in (7, 37, 40):
                gap(t, False)

    # 5: summaries off -> no_summaries.
    with make_client(migrated, **{**LLM, "summaries": False, "packet_policy": "packet-v20"}) as client:
        res = ask(client, chat, synced, trim=TRIM)
        assert check_trim(res, chat) == {"keep_from_id": None, "keep_from_turn": None, "reason": "no_summaries"}

    # 4: without trim, or with trim null, the answer has no trim key and is otherwise the same, under both policies.
    for policy in ("packet-v19", "packet-v20"):
        with make_client(migrated, **{**SUMMARIES_ON, "packet_policy": policy}) as client:
            absent = ask(client, chat, synced)
            null = ask(client, chat, synced, trim=None)
            trimmed = ask(client, chat, synced, trim=TRIM)
        for res in (absent, null):
            assert "trim" not in res and res["freshness"] == "fresh"
            check_coverage(res)
        assert absent["packet"]["text"] == null["packet"]["text"]
        assert {k: v for k, v in absent.items() if k != "trace_id"} == {k: v for k, v in null.items() if k != "trace_id"}
        assert check_trim(trimmed, chat)["keep_from_turn"] == 40, policy
