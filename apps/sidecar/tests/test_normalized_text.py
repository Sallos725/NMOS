"""#9: one versioned normalized-text projection for lexical recall, embedding, extraction, excerpting."""

from __future__ import annotations

import time

from conftest import make_client
from nmos_sidecar import normtext
from simchat import SimChat
from test_sidecar_integration import recall, sync

REASONING = "<Thoughts>\nThe silver pocket watch is important.\n</Thoughts>\nHana looked out the window."


def build() -> SimChat:
    chat = SimChat()
    chat.user("Let us begin.")
    chat.reply(REASONING)
    for i in range(6):
        chat.user(f"Idle chatter {i} about clouds.")
        chat.reply(f"Idle reply {i}.")
    chat.user("next")
    return chat


def test_reasoning_block_terms_do_not_create_lexical_hit(client):
    chat = build()
    sync(client, chat)
    out = recall(client, chat, "Where is the silver pocket watch?", in_context=[])
    trace = client.get(f"/v1/trace/{out['trace_id']}").json()
    assert trace["candidates"] == [] and out["packet"]["text"] == ""


def test_visible_story_text_still_creates_lexical_hit(client):
    chat = build()
    sync(client, chat)
    out = recall(client, chat, "Hana looked out the window?", in_context=[])
    assert "Hana looked out the window." in out["packet"]["text"]
    assert "pocket watch" not in out["packet"]["text"]


def test_previous_ai_reasoning_does_not_steer_recall(client):
    chat = build()
    sync(client, chat)
    out = recall(client, chat, "clouds", in_context=[],
                 previous_ai="<think>silver pocket watch silver pocket watch</think>Okay.")
    trace = client.get(f"/v1/trace/{out['trace_id']}").json()
    assert all(c["score"] == c["user_score"] for c in trace["candidates"])  # no AI tiebreak from the dropped block


def test_raw_source_content_is_unchanged(client, db):
    chat = build()
    sync(client, chat)
    raw = db.execute("SELECT sr.content, rt.clean_content, rt.original_chars, rt.clean_chars FROM source_revision sr"
                     " JOIN revision_text rt ON rt.source_revision_id = sr.id WHERE sr.content LIKE '%%Thoughts%%'"
                     ).fetchone()
    assert raw["content"] == REASONING
    assert raw["clean_content"] == "Hana looked out the window."
    assert (raw["original_chars"], raw["clean_chars"]) == (len(REASONING), len("Hana looked out the window."))


def test_normalizer_generation_can_be_rebuilt(client, db):
    chat = build()
    sync(client, chat)
    before = db.execute("SELECT count(*) AS n FROM revision_text").fetchone()["n"]
    assert before == len(chat.messages)
    db.execute("DELETE FROM revision_text")
    assert recall(client, chat, "Hana looked out the window?", in_context=[])["packet"]["text"] == ""
    assert normtext.backfill(db, batch=3) == before  # existing chats backfill without a host re-import
    assert "Hana looked out" in recall(client, chat, "Hana looked out the window?", in_context=[])["packet"]["text"]
    assert normtext.backfill(db) == 0


def test_lexical_recall_that_exceeds_its_budget_abstains_instead_of_blocking(migrated, monkeypatch):
    """#12: a query matching nearly every message is cancelled; the request still succeeds."""
    from nmos_sidecar import retrieval

    def slow(conn, *args):
        conn.execute("SELECT pg_sleep(2)")  # stands in for scoring every message of a huge chat
        return []

    with make_client(migrated, lexical_timeout_ms=50) as c:
        chat = build()
        sync(c, chat)
        monkeypatch.setattr(retrieval, "_lexical_candidates", slow)
        started = time.perf_counter()
        out = recall(c, chat, "Hana looked out the window?", in_context=[])
        assert time.perf_counter() - started < 1.5
        trace = c.get(f"/v1/trace/{out['trace_id']}").json()
        monkeypatch.undo()
        assert trace["latency_ms"]["lexical_mode"] == "timeout" and out["packet"]["text"] == ""
        # The setting does not leak into later statements of the same connection.
        assert "Hana looked out" in recall(c, chat, "Hana looked out the window?", in_context=[])["packet"]["text"]
