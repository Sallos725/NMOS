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


def test_decide_trim_pure_boundaries_and_reasons():
    def full_window(hi: int, lo: int = 0, uncovered: set[int] = frozenset()) -> list[tuple[int, bool]]:
        return [(t, t not in uncovered) for t in range(lo, hi + 1)]

    # Summaries off takes precedence over arithmetic.
    assert coverage.decide_trim(60, 20, 20, full_window(60), summaries_on=False) == coverage.TrimCut(None, "no_summaries")
    assert coverage.decide_trim(None, 20, 20, [], summaries_on=True) == coverage.TrimCut(None, "short")
    assert coverage.decide_trim(60, 20, 20, [], summaries_on=True) == coverage.TrimCut(None, "short")

    # Growing chat (keep=20, step=20): boundary moves only at multiples of step.
    for now in (0, 19, 20, 39):
        assert coverage.decide_trim(now, 20, 20, full_window(now), summaries_on=True) == coverage.TrimCut(None, "short")
    for now in (40, 41, 50, 59):
        assert coverage.decide_trim(now, 20, 20, full_window(now), summaries_on=True) == coverage.TrimCut(20, None)
    for now in (60, 61, 79):
        assert coverage.decide_trim(now, 20, 20, full_window(now), summaries_on=True) == coverage.TrimCut(40, None)
    assert coverage.decide_trim(80, 20, 20, full_window(80), summaries_on=True) == coverage.TrimCut(60, None)

    # An uncovered turn at 33 with raw_cut=40 lowers cut to floor(33/20)*20 = 20.
    assert coverage.decide_trim(60, 20, 20, full_window(60, uncovered={33}), summaries_on=True) == coverage.TrimCut(20, None)
    # An uncovered turn at 15 with raw_cut=20 lowers cut to 0 <= first_turn(0) -> reason="uncovered".
    assert coverage.decide_trim(40, 20, 20, full_window(40, uncovered={15}), summaries_on=True) == coverage.TrimCut(None, "uncovered")
    # Smallest uncovered turn decides (gap at 4 beats gap at 33).
    assert coverage.decide_trim(60, 20, 20, full_window(60, uncovered={4, 33}), summaries_on=True) == coverage.TrimCut(None, "uncovered")
    # Uncovered turns at or above raw_cut stay in the kept window and do not lower the boundary.
    assert coverage.decide_trim(60, 20, 20, full_window(60, uncovered={40, 55, 60}), summaries_on=True) == coverage.TrimCut(40, None)

    # Prompt window starting past turn 0 (host already trimmed turns 0..19).
    assert coverage.decide_trim(40, 20, 20, full_window(40, lo=20), summaries_on=True) == coverage.TrimCut(None, "short")
    assert coverage.decide_trim(60, 20, 20, full_window(60, lo=20), summaries_on=True) == coverage.TrimCut(40, None)
    assert coverage.decide_trim(60, 20, 20, full_window(60, lo=20, uncovered={33}), summaries_on=True) == coverage.TrimCut(None, "uncovered")
    # Unsorted input produces the same result.
    assert coverage.decide_trim(60, 20, 20, list(reversed(full_window(60, uncovered={33}))), summaries_on=True) == coverage.TrimCut(20, None)


def test_trim_validation_errors_http_422(migrated):
    with make_client(migrated, **SUMMARIES_ON) as client:
        for bad in (
            {"keep_recent_turns": 3, "step": 3},
            {"keep_recent_turns": 201, "step": 201},
            {"keep_recent_turns": 20, "step": 0},
        ):
            res = client.post("/v1/retrieve", json={
                "chat_id": "any", "query": "hi", "in_context_ids": [], "budget_tokens": 600, "trim": bad,
            })
            assert res.status_code == 422, (bad, res.status_code, res.text)


def test_trim_integration_growing_chat_uncovered_reasons_excerpt_and_replay(migrated):
    from nmos_sidecar import audit
    from nmos_sidecar.retrieval import RecallOptions

    base_settings = {**SUMMARIES_ON, "packet_policy": "packet-v20"}
    chat = SimChat()
    for i in range(39):
        if i == 2:
            chat.user("Turn 2 begins. 세라는 오래된 등대 아래에 은빛 나침반을 숨겼다.")
            chat.reply("Reply 2 follows. 세라가 은빛 나침반을 숨긴 자리를 기억해 두었다.")
        else:
            chat.user(f"Turn {i} walk along the harbor road.")
            chat.reply(f"Reply {i} quiet breeze over the stones.")

    def first_msg_id_of_turn(url: str, head: UUID, turn: int) -> str:
        with db(url) as conn:
            return conn.execute(
                "SELECT so.host_logical_id FROM active_membership am"
                " JOIN source_revision sr ON sr.id = am.source_revision_id"
                " JOIN source_object so ON so.id = sr.source_object_id"
                " WHERE am.commit_id = %s AND am.turn = %s ORDER BY am.position ASC LIMIT 1",
                (head, turn),
            ).fetchone()["host_logical_id"]

    with make_client(migrated, **base_settings) as client:
        # now = 39 (replied 0..38, user at turn 39) -> raw_cut = floor((39-20)/20)*20 = 0 -> short
        chat.user("은빛 나침반은 어디 숨겼어?")
        sync_39 = sync(client, chat)
        extract(migrated)
        drain_summaries(migrated)
        all_39 = [m["chatId"] for m in chat.messages]
        res_39 = client.post("/v1/retrieve", json={
            "chat_id": chat.id, "query": "은빛 나침반은 어디 숨겼어?",
            "in_context_ids": all_39, "budget_tokens": 2000,
            "trim": {"keep_recent_turns": 20, "step": 20},
        })
        assert res_39.status_code == 200
        assert res_39.json()["trim"] == {"keep_from_id": None, "keep_from_turn": None, "reason": "short"}

        # Grow to now = 40 -> raw_cut = 20, turns 0..31 covered -> cut = 20
        chat.reply("Reply 39 quiet evening.")
        chat.user("은빛 나침반은 어디 숨겼어?")
        sync_40 = sync(client, chat)
        extract(migrated)
        drain_summaries(migrated)
        cid, head_40 = _head(migrated, client, chat)
        turn20_id = first_msg_id_of_turn(migrated, head_40, 20)
        all_40 = [m["chatId"] for m in chat.messages]

        # Without trim: no trim field in response, turn 2 is excluded_in_context, no excerpt of 은빛 나침반.
        no_trim = client.post("/v1/retrieve", json={
            "chat_id": chat.id, "query": "은빛 나침반은 어디 숨겼어?",
            "in_context_ids": all_40, "budget_tokens": 2000,
        }).json()
        assert "trim" not in no_trim
        trace_no_trim = client.get(f"/v1/trace/{no_trim['trace_id']}").json()
        assert "trim" not in trace_no_trim["recall_options"]
        assert "은빛 나침반" not in no_trim["packet"]["text"]
        assert "<Excerpt" not in no_trim["packet"]["text"]
        assert any(e["host_logical_id"] == chat.messages[4]["chatId"] for e in trace_no_trim["excluded_in_context"])

        # With trim at now=40: cut = 20, turn 2 is removed from in_context and now eligible as an excerpt!
        trimmed_40 = client.post("/v1/retrieve", json={
            "chat_id": chat.id, "query": "은빛 나침반은 어디 숨겼어?",
            "in_context_ids": all_40, "budget_tokens": 2000,
            "trim": {"keep_recent_turns": 20, "step": 20},
        }).json()
        assert trimmed_40["trim"] == {"keep_from_id": turn20_id, "keep_from_turn": 20, "reason": None}
        assert "은빛 나침반" in trimmed_40["packet"]["text"]
        assert "<Excerpt" in trimmed_40["packet"]["text"]
        trace_40 = client.get(f"/v1/trace/{trimmed_40['trace_id']}").json()
        assert chat.messages[4]["chatId"] not in trace_40["in_context"]
        assert turn20_id in trace_40["in_context"]
        assert trace_40["recall_options"]["trim"] == {
            "keep_recent_turns": 20, "step": 20, "now": 40, "cut": 20, "keep_from_id": turn20_id, "reason": None,
        }

        # Stale request -> reason="stale"
        stale_res = client.post("/v1/retrieve", json={
            "chat_id": chat.id, "query": "은빛 나침반은 어디 숨겼어?",
            "active_commit": sync_39["active_commit"], "manifest_hash": sync_39["manifest_hash"],
            "in_context_ids": all_40, "budget_tokens": 2000,
            "trim": {"keep_recent_turns": 20, "step": 20},
        }).json()
        assert stale_res["freshness"] == "stale"
        assert stale_res["trim"] == {"keep_from_id": None, "keep_from_turn": None, "reason": "stale"}

        # Empty packet (tiny budget) -> reason="empty_packet" and unmodified in_context in trace
        empty_res = client.post("/v1/retrieve", json={
            "chat_id": chat.id, "query": "은빛 나침반은 어디 숨겼어?",
            "in_context_ids": all_40, "budget_tokens": 5,
            "trim": {"keep_recent_turns": 20, "step": 20},
        }).json()
        assert empty_res["packet"]["text"] == ""
        assert empty_res["trim"] == {"keep_from_id": None, "keep_from_turn": None, "reason": "empty_packet"}
        trace_empty = client.get(f"/v1/trace/{empty_res['trace_id']}").json()
        assert set(trace_empty["in_context"]) == set(all_40)
        assert trace_empty["recall_options"]["trim"]["reason"] == "empty_packet"
        assert trace_empty["recall_options"]["trim"]["cut"] is None

        # Grow to now = 45 (still cut 20), then now = 60 (cut 40).
        chat.reply("Reply 40.")
        for i in range(41, 45):
            chat.user(f"Turn {i} walk along the harbor road.")
            chat.reply(f"Reply {i} quiet breeze over the stones.")
        chat.user("은빛 나침반은 어디 숨겼어?")
        sync(client, chat)
        extract(migrated)
        drain_summaries(migrated)
        res_45 = client.post("/v1/retrieve", json={
            "chat_id": chat.id, "query": "은빛 나침반은 어디 숨겼어?",
            "in_context_ids": [m["chatId"] for m in chat.messages], "budget_tokens": 2000,
            "trim": {"keep_recent_turns": 20, "step": 20},
        }).json()
        assert res_45["trim"] == {"keep_from_id": turn20_id, "keep_from_turn": 20, "reason": None}

        chat.reply("Reply 45.")
        for i in range(46, 60):
            chat.user(f"Turn {i} walk along the harbor road.")
            chat.reply(f"Reply {i} quiet breeze over the stones.")
        chat.user("은빛 나침반은 어디 숨겼어?")
        sync(client, chat)
        extract(migrated)
        drain_summaries(migrated)
        _, head_60 = _head(migrated, client, chat)
        turn40_id = first_msg_id_of_turn(migrated, head_60, 40)
        all_60 = [m["chatId"] for m in chat.messages]
        res_60 = client.post("/v1/retrieve", json={
            "chat_id": chat.id, "query": "은빛 나침반은 어디 숨겼어?",
            "in_context_ids": all_60, "budget_tokens": 2000,
            "trim": {"keep_recent_turns": 20, "step": 20},
        }).json()
        assert res_60["trim"] == {"keep_from_id": turn40_id, "keep_from_turn": 40, "reason": None}

        # Uncovered turn at 33 lowers cut 40 -> floor(33/20)*20 = 20.
        with db(migrated) as conn:
            t33 = conn.execute(
                "SELECT source_revision_id AS rid, turn_hash FROM active_membership"
                " WHERE commit_id = %s AND turn = 33 AND turn_hash IS NOT NULL", (head_60,)
            ).fetchone()
            conn.execute(
                "UPDATE extraction SET discarded_at = now() WHERE source_revision_id = %s AND window_hash = %s",
                (t33["rid"], t33["turn_hash"]),
            )
            conn.commit()
        res_gap33 = client.post("/v1/retrieve", json={
            "chat_id": chat.id, "query": "은빛 나침반은 어디 숨겼어?",
            "in_context_ids": all_60, "budget_tokens": 2000,
            "trim": {"keep_recent_turns": 20, "step": 20},
        }).json()
        assert res_gap33["trim"] == {"keep_from_id": turn20_id, "keep_from_turn": 20, "reason": None}

        # Uncovered turn at 5 lowers cut -> 0 <= first_turn(0) -> reason="uncovered".
        with db(migrated) as conn:
            t5 = conn.execute(
                "SELECT source_revision_id AS rid, turn_hash FROM active_membership"
                " WHERE commit_id = %s AND turn = 5 AND turn_hash IS NOT NULL", (head_60,)
            ).fetchone()
            conn.execute(
                "UPDATE extraction SET discarded_at = now() WHERE source_revision_id = %s AND window_hash = %s",
                (t5["rid"], t5["turn_hash"]),
            )
            conn.commit()
        res_gap5 = client.post("/v1/retrieve", json={
            "chat_id": chat.id, "query": "은빛 나침반은 어디 숨겼어?",
            "in_context_ids": all_60, "budget_tokens": 2000,
            "trim": {"keep_recent_turns": 20, "step": 20},
        }).json()
        assert res_gap5["trim"] == {"keep_from_id": None, "keep_from_turn": None, "reason": "uncovered"}

    # Replay of the earlier trimmed trace (trace_40) reproduces identically even after turn 5 & 33 were discarded!
    with db(migrated) as conn:
        replayed = audit.replay(conn, UUID(trimmed_40["trace_id"]), RecallOptions())
        replayed_empty = audit.replay(conn, UUID(empty_res["trace_id"]), RecallOptions())
    assert replayed["status"] == "ok" and replayed["reproduced"] is True
    assert replayed["text"] == trimmed_40["packet"]["text"]
    assert replayed_empty["status"] == "ok" and replayed_empty["reproduced"] is True
    assert replayed_empty["text"] == ""

    # Summaries off -> reason="no_summaries".
    with make_client(migrated, **{**LLM, "summaries": False, "packet_policy": "packet-v20"}) as client_no_sum:
        res_no_sum = client_no_sum.post("/v1/retrieve", json={
            "chat_id": chat.id, "query": "은빛 나침반은 어디 숨겼어?",
            "in_context_ids": all_60, "budget_tokens": 2000,
            "trim": {"keep_recent_turns": 20, "step": 20},
        }).json()
    assert res_no_sum["trim"] == {"keep_from_id": None, "keep_from_turn": None, "reason": "no_summaries"}


def test_without_trim_v19_and_v20_omit_trim_and_match_null_trim(migrated):
    chat = story_chat(16)
    chat.user("Question about Turn 0?")
    for policy in ("packet-v19", "packet-v20"):
        with make_client(migrated, **{**SUMMARIES_ON, "packet_policy": policy}) as client:
            sync(client, chat)
            extract(migrated)
            drain_summaries(migrated)
            base_body = {
                "chat_id": chat.id, "query": "Question about Turn 0?",
                "in_context_ids": [m["chatId"] for m in chat.messages[-4:]], "budget_tokens": 2000,
            }
            absent = client.post("/v1/retrieve", json=base_body).json()
            explicit_null = client.post("/v1/retrieve", json={**base_body, "trim": None}).json()
            assert "trim" not in absent
            assert "trim" not in explicit_null
            assert absent["packet"] == explicit_null["packet"]
            assert absent["coverage"] == explicit_null["coverage"] == {
                "recorded_through_turn": 15, "covered_through_turn": 7,
            }
