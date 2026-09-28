"""PHASE-12 step 3 (ADR 0041): scene summaries and the story so far, a `summarize` projection."""

from __future__ import annotations

import re

import psycopg
from psycopg.rows import dict_row

from conftest import active_generation, make_client
from nmos_sidecar import summaries
from nmos_sidecar.config import Settings
from nmos_sidecar.worker import run_once
from simchat import SimChat
from test_generations import LLM, conv_id
from test_sidecar_integration import sync

ON = {**LLM, "summaries": True}
TURN = re.compile(r"\[turn (\d+)\] [^:]+: (.*)")


def stub(system: str, user: str) -> tuple[dict, str]:
    """A scene: the first words of each message; the story: its scenes' turn ranges."""
    if system == summaries.STORY_PROMPT:
        return {"summary": "Story of " + ", ".join(re.findall(r"\[turns (\d+–\d+)\]", user))}, "{}"
    said = [m[2].split(".")[0] for m in TURN.finditer(user)]
    return {"summary": " / ".join(said)}, "{}"


def drain(url: str, complete=stub) -> int:
    n = 0
    with psycopg.connect(url, row_factory=dict_row, autocommit=True) as conn:
        gen = active_generation(conn, "summarize")
        jobs = {"summarize": (gen.key, lambda cn, job: summaries.process(cn, job, complete, gen))}
        while run_once(conn, jobs):
            n += 1
    return n


def story_chat(turns: int) -> SimChat:
    chat = SimChat()
    for i in range(turns):
        chat.user(f"Turn {i} begins.")
        chat.reply(f"Reply {i} follows. More words here.")
    return chat


def view(url: str, client, chat: SimChat) -> dict:
    with psycopg.connect(url, row_factory=dict_row) as conn:
        cid = conv_id(client, chat)
        head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid,)).fetchone()["head_commit_id"]
        return summaries.current(conn, cid, head, active_generation(conn, "summarize").key)


def jobs(db, status: str = "queued") -> list[dict]:
    return db.execute("SELECT * FROM job WHERE kind = 'summarize' AND status = %s ORDER BY id", (status,)).fetchall()


def test_the_generation_needs_the_switch_and_a_model():
    assert summaries.summarizer(Settings(**LLM)) is None  # off by default (PHASE-12 step 3)
    assert summaries.summarizer(Settings(summaries=True)) is None  # no model
    on = summaries.summarizer(Settings(**ON))
    other = summaries.summarizer(Settings(**{**ON, "llm_model": "other"}))
    assert on.kind == "summarize" and on.spec["window"] == summaries.WINDOW and on.key != other.key


def test_windows_are_due_once_complete_and_lag_turns_old():
    assert [summaries.due(n) for n in (0, 11, 12, 19, 20, 28)] == [0, 0, 1, 1, 2, 3]


def test_off_by_default_nothing_is_queued(migrated, db):
    chat = story_chat(30)
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        assert jobs(db) == []
        assert "Summaries" not in c.get(f"/inspector/c/{conv_id(c, chat)}", params={"lang": "en"}).text


def test_scenes_then_the_story_and_the_inspector(migrated, db):
    chat = story_chat(30)  # 30 replied turns: windows 0–7, 8–15, 16–23 are due
    with make_client(migrated, **ON) as c:
        sync(c, chat)
        assert [(j["payload"]["first_turn"], j["payload"]["last_turn"]) for j in jobs(db)] == [(0, 7), (8, 15), (16, 23)]
        assert drain(migrated) == 4  # three scenes, then the story
        v = view(migrated, c, chat)
        assert [s["summary"]["text"].split(" / ")[0] for s in v["scenes"]] == ["Turn 0 begins", "Turn 8 begins",
                                                                               "Turn 16 begins"]
        assert v["story"]["text"] == "Story of 0–7, 8–15, 16–23" and v["story_current"]
        scene = v["scenes"][0]["summary"]
        assert len(scene["members"]) == 16 and scene["coverage"]["messages"] == 16  # provenance (invariant 10)
        page = c.get(f"/inspector/c/{conv_id(c, chat)}", params={"lang": "en"}).text
        assert "Story so far" in page and "Story of 0–7, 8–15, 16–23" in page and "Turn 16 begins" in page


def test_an_append_queues_the_window_it_makes_due_and_the_story_follows(migrated, db):
    chat = story_chat(30)
    with make_client(migrated, **ON) as c:
        sync(c, chat)
        drain(migrated)
        for i in range(30, 36):
            chat.user(f"Turn {i} begins.")
            chat.reply(f"Reply {i} follows.")
            sync(c, chat)
        assert [(j["payload"]["first_turn"]) for j in jobs(db)] == [24]  # 36 replied turns: window 24–31 is due
        v = view(migrated, c, chat)
        assert v["done"] == 3 and v["due"] == 4 and v["story"]["text"] == "Story of 0–7, 8–15, 16–23"  # still serves
        drain(migrated)
        v = view(migrated, c, chat)
        assert v["story"]["text"] == "Story of 0–7, 8–15, 16–23, 24–31" and v["story_current"]


def test_an_edit_inside_a_window_masks_its_summary_and_the_story(migrated, db):
    chat = story_chat(30)
    with make_client(migrated, **ON) as c:
        sync(c, chat)
        drain(migrated)
        chat.edit(2, "Turn 1 was rewritten. Entirely.")  # turn 1's user message, inside window 0–7
        sync(c, chat)
        v = view(migrated, c, chat)
        assert v["scenes"][0]["summary"] is None and v["scenes"][1]["summary"] is not None  # masked at once
        assert v["story"] is None  # it was made from the old scene
        assert [j["payload"]["first_turn"] for j in jobs(db)] == [0]
        drain(migrated)
        v = view(migrated, c, chat)
        assert "Turn 1 was rewritten" in v["scenes"][0]["summary"]["text"] and v["story_current"]


def test_a_job_for_a_window_the_head_no_longer_shows_is_obsolete(migrated, db):
    chat = story_chat(30)
    with make_client(migrated, **ON) as c:
        sync(c, chat)
        chat.edit(2, "Turn 1 was rewritten.")
        sync(c, chat)  # window 0 has another key now: its first job no longer matches
    drain(migrated)
    assert [j["payload"]["first_turn"] for j in jobs(db, "obsolete")] == [0]
    assert db.execute("SELECT count(*) AS n FROM summary WHERE level = 'scene'").fetchone()["n"] == 3


def test_a_reply_without_a_summary_fails_the_job(migrated, db):
    with make_client(migrated, **ON) as c:
        sync(c, story_chat(20))
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        gen = active_generation(conn, "summarize")
        run_once(conn, {"summarize": (gen.key, lambda cn, job: summaries.process(
            cn, job, lambda s, u: ({"text": "not the field"}, "{}"), gen))})
    job = db.execute("SELECT * FROM job WHERE kind = 'summarize' AND attempts > 0").fetchone()
    assert job["status"] == "queued" and job["attempts"] == 1 and "summary" in job["last_error"]
    assert db.execute("SELECT count(*) AS n FROM summary").fetchone()["n"] == 0


def test_turning_it_off_stops_queued_jobs_and_deleting_the_chat_removes_them(migrated, db):
    chat = story_chat(30)
    with make_client(migrated, **ON) as c:
        sync(c, chat)
        drain(migrated)
        chat.edit(2, "Turn 1 was rewritten.")
        sync(c, chat)
        assert len(jobs(db)) == 1
        assert c.put("/v1/config", json={"summaries": False}).status_code == 200
        assert jobs(db) == []
        assert c.post(f"/v1/conversations/{conv_id(c, chat)}/delete").json()["deleted"]["summaries"] == 4
    assert db.execute("SELECT count(*) AS n FROM summary").fetchone()["n"] == 0
