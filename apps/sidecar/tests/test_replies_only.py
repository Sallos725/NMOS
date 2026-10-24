"""PHASE-48 step 2: a chat that remembers the AI's replies only. With the flag on, no user message is a recall
candidate on any route; with it off, every route is as before; another chat is unchanged; switching queues nothing.
Synthetic text only; no model, so the packet holds excerpts only."""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from conftest import make_client
from simchat import SimChat
from test_generations import conv_id
from test_sidecar_integration import recall, sync

ASK = "What was the password bluefinch about?"


def story(tag: str) -> SimChat:
    chat = SimChat()
    chat.user(f"I whisper the password to the guard: bluefinch {tag}. Write it long.")
    chat.reply("The guard nods and steps aside; the gate of the old mill creaks open.")
    chat.user("Go on to the next scene.")
    chat.reply("Inside, the miller counts sacks of grain by lantern light; bluefinch is painted on one of them.")
    chat.user("Keep going.")
    return chat


def texts(c, chat) -> str:
    return recall(c, chat, ASK, budget=2000)["packet"]["text"]


def test_the_flag_defaults_off_and_is_set_per_chat(migrated):
    with make_client(migrated) as c:
        chat = story("a")
        sync(c, chat)
        cid = conv_id(c, chat)
        assert c.get(f"/v1/conversations/{cid}/replies-only").json() == {"on": False}
        assert c.put(f"/v1/conversations/{cid}/replies-only", json={"on": True}).json() == {"on": True}
        assert c.get(f"/v1/conversations/{cid}/replies-only").json() == {"on": True}
        missing = "0190f3a4-1b2c-7d3e-8f40-00000000000a"
        assert c.get(f"/v1/conversations/{missing}/replies-only").status_code == 404
        assert c.put(f"/v1/conversations/{missing}/replies-only", json={"on": True}).status_code == 404


def test_on_leaves_every_user_message_out_and_another_chat_unchanged(migrated):
    with make_client(migrated) as c:
        one, two = story("one"), story("two")
        sync(c, one)
        sync(c, two)
        before_one, before_two = texts(c, one), texts(c, two)
        assert "whisper the password" in before_one  # the user's message is an excerpt today
        c.put(f"/v1/conversations/{conv_id(c, one)}/replies-only", json={"on": True})
        after_one, after_two = texts(c, one), texts(c, two)
        assert "whisper the password" not in after_one and "Write it long" not in after_one
        assert "painted on one of them" in after_one  # the reply that says it is still found
        assert after_two == before_two  # one chat's switch changes no other chat
        c.put(f"/v1/conversations/{conv_id(c, one)}/replies-only", json={"on": False})
        assert texts(c, one) == before_one  # off again: as before, at once


def test_the_quote_route_and_named_turns_leave_user_messages_out_too(migrated):
    with make_client(migrated) as c:
        chat = SimChat()
        chat.user('I say "bluefinch is the word we agreed on" and wait.')
        chat.reply('The guard answers, "bluefinch, you may pass," and opens the gate.')
        chat.user("Next.")
        sync(c, chat)
        q = "turn 0: what did they say about bluefinch?"
        on_before = recall(c, chat, q, budget=2000)["packet"]["text"]
        assert "we agreed on" in on_before
        c.put(f"/v1/conversations/{conv_id(c, chat)}/replies-only", json={"on": True})
        after = recall(c, chat, q, budget=2000)["packet"]["text"]
        assert "we agreed on" not in after and "you may pass" in after


def test_switching_queues_nothing_and_the_trace_records_it(migrated):
    with make_client(migrated) as c:
        chat = story("q")
        sync(c, chat)
        cid = conv_id(c, chat)
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            jobs = conn.execute("SELECT count(*) AS n FROM job").fetchone()["n"]
        c.put(f"/v1/conversations/{cid}/replies-only", json={"on": True})
        out = recall(c, chat, ASK, budget=2000)
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            assert conn.execute("SELECT count(*) AS n FROM job").fetchone()["n"] == jobs
            trace = conn.execute("SELECT recall_options FROM retrieval_trace WHERE id = %s", (out["trace_id"],)).fetchone()
        assert trace["recall_options"]["replies_only"] is True
        replay = c.get(f"/v1/trace/{out['trace_id']}/replay").json()
        assert replay.get("reproduced") is True  # the replay reads the flag the request had


def test_an_archive_carries_the_flag(migrated, database_url_factory, tmp_path):
    from nmos_sidecar import archive
    with make_client(migrated) as c:
        chat = story("x")
        sync(c, chat)
        c.put(f"/v1/conversations/{conv_id(c, chat)}/replies-only", json={"on": True})
    path = tmp_path / f"a{archive.SUFFIX}"
    archive.export_file(migrated, str(path))
    target = database_url_factory()
    archive.restore_file(target, str(path))
    with psycopg.connect(target, row_factory=dict_row) as conn:
        assert conn.execute("SELECT replies_only FROM conversation").fetchone()["replies_only"] is True
