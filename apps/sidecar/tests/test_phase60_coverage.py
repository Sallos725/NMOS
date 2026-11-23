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


def test_coverage_note_pure():
    from nmos_sidecar import packet

    assert packet.COVERAGE_POLICIES == frozenset({"packet-v20"})
    assert packet.coverage_note(None, None) == ""
    assert packet.coverage_note(0, None) == ""
    assert packet.coverage_note(None, 0) == " Memory has not recorded this chat yet; the chat is right."
    assert packet.coverage_note(0, 1) == (
        " Memory is recorded through turn 0; where a newer message in the chat says otherwise, the chat is right."
    )
    assert packet.coverage_note(5, 6) == (
        " Memory is recorded through turn 5; where a newer message in the chat says otherwise, the chat is right."
    )
    assert packet.coverage_note(5, 5) == ""


def test_coverage_sentence_in_v20_absent_in_v19_and_replays_exact(migrated):
    """A11: coverage sentence appears under packet-v20 iff a replied turn is newer than the last served turn,
    never under packet-v19, and replays identically even after newer turns are extracted."""
    from nmos_sidecar import audit
    from nmos_sidecar.retrieval import RecallOptions

    base_settings = {k: v for k, v in settings_for("full").items() if not k.startswith("embed_")} | {"embed_backfill": 0}
    chat = SimChat()
    chat.reply("Welcome to the harbor.")
    chat.user("Hana has the silver lantern in the archive.")
    chat.reply("Hana noted the silver lantern.")
    chat.user("Kaito walked to the north pier.")
    chat.reply("Kaito waited at the pier.")
    chat.user("Where is the silver lantern?")

    # 1. Unextracted chat with replied turns -> v20 says not recorded yet; v19 omits it.
    with make_client(migrated, **(base_settings | {"packet_policy": "packet-v20"})) as c20:
        sync(c20, chat)
        unextracted_v20 = c20.post("/v1/retrieve", json={
            "chat_id": chat.id, "query": "Where is the silver lantern?",
            "in_context_ids": [chat.messages[-1]["chatId"]], "budget_tokens": 2000,
        }).json()
    assert "Memory has not recorded this chat yet; the chat is right." in unextracted_v20["packet"]["text"]
    assert unextracted_v20["coverage"] == {"recorded_through_turn": None, "covered_through_turn": None}

    with make_client(migrated, **(base_settings | {"packet_policy": "packet-v19"})) as c19:
        unextracted_v19 = c19.post("/v1/retrieve", json={
            "chat_id": chat.id, "query": "Where is the silver lantern?",
            "in_context_ids": [chat.messages[-1]["chatId"]], "budget_tokens": 2000,
        }).json()
        trace_v19 = c19.get(f"/v1/trace/{unextracted_v19['trace_id']}").json()
    assert "Memory has not recorded" not in unextracted_v19["packet"]["text"]
    assert "Memory is recorded through" not in unextracted_v19["packet"]["text"]
    assert "coverage" not in trace_v19["recall_options"]

    # 2. Extract turns 0..2, then add turn 3 (replied) + turn 4 (user) without extracting turn 3.
    extract(migrated)
    chat.reply("It is in the archive.")
    chat.user("Remind me about the silver lantern again.")
    with make_client(migrated, **(base_settings | {"packet_policy": "packet-v20"})) as c20:
        sync(c20, chat)
        partial_v20 = c20.post("/v1/retrieve", json={
            "chat_id": chat.id, "query": "Remind me about the silver lantern again.",
            "in_context_ids": [chat.messages[-1]["chatId"]], "budget_tokens": 2000,
        }).json()
        trace_partial = c20.get(f"/v1/trace/{partial_v20['trace_id']}").json()
    expected_sentence = "Memory is recorded through turn 2; where a newer message in the chat says otherwise, the chat is right."
    assert expected_sentence in partial_v20["packet"]["text"]
    assert trace_partial["recall_options"]["coverage"] == {
        "recorded_through_turn": 2, "covered_through_turn": None, "latest_replied_turn": 3,
    }

    with make_client(migrated, **(base_settings | {"packet_policy": "packet-v19"})) as c19:
        partial_v19 = c19.post("/v1/retrieve", json={
            "chat_id": chat.id, "query": "Remind me about the silver lantern again.",
            "in_context_ids": [chat.messages[-1]["chatId"]], "budget_tokens": 2000,
        }).json()
    assert "Memory is recorded through" not in partial_v19["packet"]["text"]
    # The only difference between v20 and v19 on this chat is that single Note sentence.
    assert partial_v20["packet"]["text"].replace(" " + expected_sentence, "") == partial_v19["packet"]["text"]

    # 3. Extract the pending turn 3 -> every replied turn is now served -> sentence disappears under v20.
    extract(migrated)
    with make_client(migrated, **(base_settings | {"packet_policy": "packet-v20"})) as c20:
        caught_up_v20 = c20.post("/v1/retrieve", json={
            "chat_id": chat.id, "query": "Remind me about the silver lantern again.",
            "in_context_ids": [chat.messages[-1]["chatId"]], "budget_tokens": 2000,
        }).json()
    assert "Memory is recorded through" not in caught_up_v20["packet"]["text"]
    assert "Memory has not recorded" not in caught_up_v20["packet"]["text"]
    assert caught_up_v20["coverage"]["recorded_through_turn"] == 3

    # 4. Replay of the earlier partial v20 trace STILL reproduces the exact text (with turn 2 sentence)
    # even though turn 3 has now been extracted; replaying under v19 omits it; stripping coverage omits it (D39).
    tid = UUID(partial_v20["trace_id"])
    with db(migrated) as conn:
        replayed = audit.replay(conn, tid, RecallOptions())
        as_v19 = audit.replay(conn, tid, RecallOptions(), policy="packet-v19")
        assert replayed["status"] == "ok" and replayed["reproduced"] is True
        assert replayed["text"] == partial_v20["packet"]["text"]
        assert expected_sentence in replayed["text"]
        assert as_v19["status"] == "ok" and expected_sentence not in as_v19["text"]

        conn.execute(
            "UPDATE retrieval_trace SET recall_options = recall_options - 'coverage' WHERE id = %s", (tid,)
        )
        conn.commit()
        legacy = audit.replay(conn, tid, RecallOptions(), policy="packet-v20")
        assert legacy["status"] == "ok"
        assert "Memory is recorded through" not in legacy["text"]
        assert "Memory has not recorded" not in legacy["text"]


def test_trim_request_and_response_models():
    from pydantic import ValidationError
    from uuid import uuid4

    from nmos_sidecar.models import CoverageResponse, MemoryFit, Packet, RetrieveRequest, RetrieveResponse, TrimRequest, TrimResponse

    base = {"chat_id": "c1", "query": "hi", "budget_tokens": 600}
    assert RetrieveRequest(**base).trim is None
    assert RetrieveRequest(**base, trim=None).trim is None
    req = RetrieveRequest(**base, trim={"keep_recent_turns": 20, "step": 20})
    assert req.trim == TrimRequest(keep_recent_turns=20, step=20)
    assert RetrieveRequest(**base, trim={"keep_recent_turns": 16}).trim == TrimRequest(keep_recent_turns=16, step=16)
    assert RetrieveRequest(**base, trim={"keep_recent_turns": 4, "step": 1}).trim.keep_recent_turns == 4
    assert RetrieveRequest(**base, trim={"keep_recent_turns": 200, "step": 200}).trim.keep_recent_turns == 200

    for bad in (
        {"keep_recent_turns": 3, "step": 3},
        {"keep_recent_turns": 201, "step": 201},
        {"keep_recent_turns": 20, "step": 0},
        {"keep_recent_turns": 20, "step": -5},
    ):
        with pytest.raises(ValidationError):
            RetrieveRequest(**base, trim=bad)

    resp_no_trim = RetrieveResponse(
        trace_id=uuid4(), freshness="fresh", packet=Packet(text="", token_estimate=0, excerpt_count=0),
        memory=MemoryFit(offered=1, cut=0, fits_at=None),
        coverage=CoverageResponse(recorded_through_turn=None, covered_through_turn=None),
    )
    dumped_no_trim = resp_no_trim.model_dump()
    assert "trim" not in dumped_no_trim
    assert dumped_no_trim["memory"] == {"offered": 1, "cut": 0, "fits_at": None}
    assert dumped_no_trim["coverage"] == {"recorded_through_turn": None, "covered_through_turn": None}

    resp_with_trim = RetrieveResponse(
        trace_id=uuid4(), freshness="fresh", packet=Packet(text="", token_estimate=0, excerpt_count=0),
        coverage=CoverageResponse(recorded_through_turn=10, covered_through_turn=7),
        trim=TrimResponse(keep_from_id=None, keep_from_turn=None, reason="short"),
    )
    assert resp_with_trim.model_dump()["trim"] == {
        "keep_from_id": None, "keep_from_turn": None, "reason": "short",
    }
