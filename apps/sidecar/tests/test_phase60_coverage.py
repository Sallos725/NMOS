"""PHASE-60 S1, S2.1: coverage reader, coverage sentence (packet-v20), and sidecar trim boundary."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import active_generation, make_client
from memeval import _sync, settings_for
from nmos_sidecar import coverage, extraction, summaries
from simchat import SimChat
from test_generations import LLM, conv_id
from test_packet_ledger import db, extract
from test_sidecar_integration import sync
from test_summaries import ON as SUMMARIES_ON, drain as drain_summaries, story_chat


def _head(url: str, client, chat: SimChat) -> tuple[UUID, UUID]:
    cid = conv_id(client, chat)
    with db(url) as conn:
        head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid,)).fetchone()["head_commit_id"]
    return cid, head


def test_contiguous_through():
    assert coverage.contiguous_through(set()) is None
    assert coverage.contiguous_through({0}) == 0
    assert coverage.contiguous_through({0, 1, 2}) == 2
    assert coverage.contiguous_through({0, 1, 3, 4}) == 1
    assert coverage.contiguous_through({1, 2, 3}) is None


def test_coverage_reader_unextracted_and_user_only(migrated):
    with make_client(migrated, **SUMMARIES_ON) as client:
        chat = SimChat()
        chat.user("First user turn with no reply yet.")
        sync(client, chat)
        cid, head = _head(migrated, client, chat)
        with db(migrated) as conn:
            cov = coverage.read(conn, cid, head, active_generation(conn, "summarize").key,
                                extractor_key=active_generation(conn, "extract").key)
        assert cov.recorded_through_turn is None
        assert cov.covered_through_turn is None
        assert cov.latest_replied_turn is None

        chat.reply("First reply arrives.")
        chat.user("Second user message.")
        sync(client, chat)
        cid, head = _head(migrated, client, chat)
        with db(migrated) as conn:
            cov = coverage.read(conn, cid, head, active_generation(conn, "summarize").key,
                                extractor_key=active_generation(conn, "extract").key)
        assert cov.recorded_through_turn is None
        assert cov.covered_through_turn is None
        assert cov.latest_replied_turn == 0


def test_coverage_reader_extractions_summaries_gaps_held_and_as_of(migrated):
    # 16 replied turns + 1 trailing user turn so all 16 replied turns (0..15) are accepted,
    # and window 0..7 is due (16 - LAG(4) = 12 >= 8 -> 1 window: 0..7).
    chat = story_chat(16)
    chat.user("Now asking a question at turn 16.")
    with make_client(migrated, **SUMMARIES_ON) as client:
        sync(client, chat)
        extract(migrated)
        cid, head = _head(migrated, client, chat)
        with db(migrated) as conn:
            ex_key = active_generation(conn, "extract").key
            sm_key = active_generation(conn, "summarize").key
            before_summaries = conn.execute("SELECT now() AS t").fetchone()["t"]
            cov_no_sum = coverage.read(conn, cid, head, sm_key, extractor_key=ex_key)
        assert cov_no_sum.recorded_through_turn == 15
        assert cov_no_sum.covered_through_turn is None
        assert cov_no_sum.latest_replied_turn == 15

        # Summarize due window 0..7.
        assert drain_summaries(migrated) >= 1
        with db(migrated) as conn:
            cov = coverage.read(conn, cid, head, sm_key, extractor_key=ex_key)
            cov_off = coverage.read(conn, cid, head, None, extractor_key=ex_key)
            cov_past = coverage.read(conn, cid, head, sm_key, extractor_key=ex_key, known_at=before_summaries)
            # upto limiting to turn 5 (messages 0..11) -> recorded through 5, window 0..7 not complete up to pos 11
            pos_turn5 = conn.execute(
                "SELECT max(position) AS p FROM active_membership WHERE commit_id = %s AND turn = 5", (head,)
            ).fetchone()["p"]
            cov_upto = coverage.read(conn, cid, head, sm_key, extractor_key=ex_key, upto=pos_turn5)
        assert cov.recorded_through_turn == 15
        assert cov.covered_through_turn == 7
        assert cov_off.recorded_through_turn == 15 and cov_off.covered_through_turn is None
        assert cov_past.recorded_through_turn == 15 and cov_past.covered_through_turn is None
        assert cov_upto.recorded_through_turn == 5 and cov_upto.latest_replied_turn == 5

        # A gap at turn 4 drops covered_through_turn to 3, while recorded_through_turn stays 15.
        with db(migrated) as conn:
            before_discard = conn.execute("SELECT now() AS t").fetchone()["t"]
            t4 = conn.execute(
                "SELECT source_revision_id AS rid, turn_hash FROM active_membership"
                " WHERE commit_id = %s AND turn = 4 AND turn_hash IS NOT NULL", (head,)
            ).fetchone()
            conn.execute(
                "UPDATE extraction SET discarded_at = now() WHERE source_revision_id = %s AND window_hash = %s",
                (t4["rid"], t4["turn_hash"]),
            )
            conn.commit()
            cov_gap = coverage.read(conn, cid, head, sm_key, extractor_key=ex_key)
            cov_before_gap = coverage.read(conn, cid, head, sm_key, extractor_key=ex_key, known_at=before_discard)
            # Restore turn 4 for the held-summary check below.
            conn.execute(
                "UPDATE extraction SET discarded_at = NULL WHERE source_revision_id = %s AND window_hash = %s",
                (t4["rid"], t4["turn_hash"]),
            )
            conn.commit()
        assert cov_gap.recorded_through_turn == 15
        assert cov_gap.covered_through_turn == 3
        assert 4 not in cov_gap.covered_turns and 5 in cov_gap.covered_turns
        assert cov_before_gap.covered_through_turn == 7

        # A held scene summary (e.g., leaks or unlisted secret) does not cover its turns.
        secret = {
            "id": 1, "turn": 2, "position": 4, "holders": ["하나"], "open": ["카이토"],
            "text": "하나 knows: Turn 0 begins / Reply 0 follows",
        }
        with db(migrated) as conn:
            cov_held = coverage.read(conn, cid, head, sm_key, extractor_key=ex_key, secrets=[secret])
        assert cov_held.recorded_through_turn == 15
        assert cov_held.covered_through_turn is None


def test_coverage_reader_counts_older_extractor_generation(migrated):
    """ADR 0014 / D20: an older generation's undiscarded extraction serves a turn when active does not."""
    chat = story_chat(6)
    chat.user("Question at turn 6.")
    with make_client(migrated, **LLM) as client:
        sync(client, chat)
        extract(migrated)
        cid, head = _head(migrated, client, chat)
    # Switch model -> new active extractor generation, nothing re-extracted yet.
    with make_client(migrated, **{**LLM, "llm_model": "model-b"}) as client:
        with db(migrated) as conn:
            active_key = active_generation(conn, "extract").key
            cov = coverage.read(conn, cid, head, None, extractor_key=active_key)
            # Confirm no row exists under the new active key, yet every turn 0..5 is served by the older generation.
            own = conn.execute("SELECT count(*) AS n FROM extraction WHERE extractor_key = %s", (active_key,)).fetchone()["n"]
        assert own == 0
        assert cov.recorded_through_turn == 5
        assert cov.served_turns == frozenset(range(6))


def test_retrieve_always_returns_coverage(migrated):
    with make_client(migrated, **SUMMARIES_ON) as client:
        # Unknown conversation
        unknown = client.post("/v1/retrieve", json={
            "chat_id": "missing-chat", "query": "hello", "in_context_ids": [], "budget_tokens": 600,
        })
        assert unknown.status_code == 200
        assert unknown.json()["freshness"] == "unknown_conversation"
        assert unknown.json()["coverage"] == {"recorded_through_turn": None, "covered_through_turn": None}

        # Unextracted chat
        chat = story_chat(16)
        chat.user("Question about Turn 0?")
        first = sync(client, chat)
        res = client.post("/v1/retrieve", json={
            "chat_id": chat.id, "query": "Question about Turn 0?",
            "in_context_ids": [m["chatId"] for m in chat.messages[-4:]], "budget_tokens": 600,
        })
        assert res.status_code == 200
        assert res.json()["coverage"] == {"recorded_through_turn": None, "covered_through_turn": None}

        # Extracted, not yet summarized
        extract(migrated)
        res = client.post("/v1/retrieve", json={
            "chat_id": chat.id, "query": "Question about Turn 0?",
            "in_context_ids": [m["chatId"] for m in chat.messages[-4:]], "budget_tokens": 600,
        })
        assert res.status_code == 200
        assert res.json()["coverage"] == {"recorded_through_turn": 15, "covered_through_turn": None}

        # Summarized (window 0..7 covered)
        assert drain_summaries(migrated) >= 1
        res = client.post("/v1/retrieve", json={
            "chat_id": chat.id, "query": "Question about Turn 0?",
            "in_context_ids": [m["chatId"] for m in chat.messages[-4:]], "budget_tokens": 600,
        })
        assert res.status_code == 200
        assert res.json()["coverage"] == {"recorded_through_turn": 15, "covered_through_turn": 7}

        # Stale request still carries coverage
        chat.reply("New reply.")
        chat.user("Another question.")
        sync(client, chat)
        stale = client.post("/v1/retrieve", json={
            "chat_id": chat.id, "query": "Another question.",
            "active_commit": first["active_commit"], "manifest_hash": first["manifest_hash"],
            "in_context_ids": [m["chatId"] for m in chat.messages[-4:]], "budget_tokens": 600,
        })
        assert stale.status_code == 200
        assert stale.json()["freshness"] == "stale"
        assert stale.json()["coverage"] == {"recorded_through_turn": 15, "covered_through_turn": 7}
