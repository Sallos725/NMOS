"""PHASE-30: a chat seen for the first time is extracted oldest turn first, and its live turns wait behind that window."""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import extraction
from nmos_sidecar.worker import run_once
from simchat import SimChat
from test_extraction import fake_complete, filler, jobs_for
from test_sidecar_integration import sync

LLM = {"llm_url": "http://fake-llm/v1", "llm_model": "fake"}


def run(url: str) -> list[str]:
    """Drain the queue; the first line of each extracted TARGET, in the order the worker took them."""
    order: list[str] = []

    def complete(system, user):
        order.append(user.split("TARGET", 1)[1].split("\n", 2)[1])
        return fake_complete(system, user)

    with psycopg.connect(url, row_factory=dict_row, autocommit=True) as conn:
        jobs = jobs_for(conn, complete)
        while run_once(conn, jobs):
            pass
    return order


def turn_no(line: str) -> str:
    return line.split("Idle chatter ", 1)[1].split(" ", 1)[0] if "Idle chatter " in line else line


def priorities(db, chat: SimChat) -> list[int]:
    return [r["priority"] for r in db.execute(
        "SELECT j.priority FROM job j JOIN conversation c ON c.id = j.conversation_id"
        " WHERE j.kind = 'extract' AND j.status = 'queued' AND c.host_chat_ref = %s ORDER BY j.id", (chat.id,))]


def test_a_first_sight_is_extracted_oldest_first_and_each_turn_sees_the_earlier_ones(migrated, db):
    chat = SimChat()
    chat.user("Mina is in the kitchen.")
    chat.reply("The kettle hums.")
    filler(chat, 4)
    chat.user("last")
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        assert priorities(db, chat) == [extraction.FIRST_PRIORITY] * 5
        order = run(migrated)
    assert [turn_no(x) for x in order] == ["USER: Mina is in the kitchen.", "0", "1", "2", "3"]
    # The newest turn was extracted after Mina's: its KNOWN ENTITIES list her (newest first, it listed nothing).
    hints = db.execute("SELECT x.hints FROM extraction x ORDER BY x.created_at DESC LIMIT 1").fetchone()["hints"]
    assert "Mina" in [e["name"] for e in hints["entities"]]


def test_the_first_sight_window_is_unchanged(migrated, db):
    chat = SimChat()
    filler(chat, 10)
    chat.user("last")
    with make_client(migrated, extract_backfill=4, **LLM) as c:
        sync(c, chat)
        assert priorities(db, chat) == [extraction.FIRST_PRIORITY] * 4
        assert [turn_no(x) for x in run(migrated)] == ["6", "7", "8", "9"]


def test_a_live_turn_waits_behind_its_chats_first_sight_window(migrated, db):
    chat = SimChat()
    filler(chat, 3)
    chat.user("Mina is in the garden.")
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        chat.reply("Birds sing.")
        chat.user("Mina is in the attic.")
        chat.reply("Dust everywhere.")
        chat.user("next")
        sync(c, chat)
        assert priorities(db, chat) == [extraction.FIRST_PRIORITY] * 5
        order = run(migrated)
    assert [turn_no(x) for x in order] == ["0", "1", "2", "USER: Mina is in the garden.", "USER: Mina is in the attic."]


def test_a_running_first_sight_job_holds_a_live_turn_and_a_dead_one_does_not(migrated, db):
    chat = SimChat()
    filler(chat, 3)
    chat.user("next")
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        db.execute("UPDATE job SET status = 'done' WHERE kind = 'extract'")
        db.execute("UPDATE job SET status = 'running', locked_at = now()"
                   " WHERE id = (SELECT max(id) FROM job WHERE kind = 'extract')")
        filler(chat, 1, tag="b")
        chat.user("again")
        sync(c, chat)
        assert priorities(db, chat) == [extraction.FIRST_PRIORITY]  # the held turn
        db.execute("UPDATE job SET status = 'dead' WHERE kind = 'extract' AND status IN ('queued', 'running')")
        filler(chat, 1, tag="c")
        chat.user("once more")
        sync(c, chat)
        assert priorities(db, chat) == [extraction.LIVE_PRIORITY]  # a dead job waits for no retry: it holds nothing


def test_live_turns_of_a_chat_already_seen_run_first_and_newest_first(migrated, db):
    seen, new = SimChat(), SimChat()
    filler(seen, 2)
    seen.user("next")
    filler(new, 3, tag="n")
    new.user("next")
    with make_client(migrated, **LLM) as c:
        sync(c, seen)
        run(migrated)
        sync(c, new)
        filler(seen, 2, tag="s")
        seen.user("again")
        sync(c, seen)
        assert priorities(db, seen) == [extraction.LIVE_PRIORITY] * 2
        order = run(migrated)
    # The seen chat's live turns first, newest first ("next" and s0 are one turn), then the new chat's window, oldest
    # first.
    assert [turn_no(x) for x in order] == ["s1", "USER: next", "n0", "n1", "n2"]


def test_the_first_sight_lane_sits_between_live_work_and_a_generations_backfill():
    assert extraction.LIVE_PRIORITY < extraction.FIRST_PRIORITY < extraction.RECENT_PRIORITY < extraction.HISTORY_PRIORITY
    from nmos_sidecar import canonfacts, summaries, vectors
    assert extraction.FIRST_PRIORITY not in (canonfacts.PRIORITY, vectors.RECENT_PRIORITY, summaries.LIVE_PRIORITY)
