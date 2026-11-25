"""Review fixes of Tier 1 wave 1 (canon, summaries, coverage, status): a secret carried by a `continue` link holds
summaries until they are written again knowing it, and trim waits for them (finding 1). Stub models only; synthetic
names 세라, 카이토, 유찬, 도현."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from conftest import active_generation, make_client
from nmos_sidecar import carry, divergence, notes, summaries
from simchat import SimChat
from test_extraction import drain as drain_extract
from test_generations import conv_id
from test_phase60_carry_take import ON, SECRET_TEXT, _build_source_chat, _keys, _stub_extract
from test_sidecar_integration import sync
from test_summaries import drain as drain_summaries

V20 = {**ON, "packet_policy": "packet-v20"}
TARGET = {"character_name": "세라", "chat_name": "새 항해", "persona_name": "유찬"}
QUERY = "항구에서 무슨 일이 있었지?"
TRIM = {"keep_recent_turns": 16, "step": 8}


class Writer:
    """A stand-in summarizer that counts its calls and keeps every prompt; it never writes a secret."""

    def __init__(self) -> None:
        self.scenes: list[str] = []
        self.stories: list[str] = []

    def __call__(self, system: str, user: str) -> tuple[dict, str]:
        if system == summaries.STORY_PROMPT:
            self.stories.append(user)
            return {"summary": "세라와 유찬은 항구에서 긴 항해를 준비했다."}, "{}"
        self.scenes.append(user)
        return {"summary": "세라와 유찬이 항구 길을 함께 걸었다."}, "{}"


def _target(c, turns: int = 40) -> SimChat:
    sim = SimChat("tgt-review")
    for i in range(turns):
        sim.user(f"턴 {i}, 항구 길을 걷는다.")
        sim.reply(f"턴 {i}의 바닷바람이 분다.")
    sync(c, sim, **TARGET)
    return sim


def _ask(c, chat: SimChat) -> dict[str, Any]:
    chat.user(QUERY)
    sync(c, chat, **TARGET)
    return c.post("/v1/retrieve", json={"chat_id": chat.id, "query": QUERY, "previous_ai": "", "budget_tokens": 2000,
                                        "in_context_ids": [m["chatId"] for m in chat.messages],
                                        "trim": TRIM}).json()


def _jobs(conn, cid: UUID) -> list[dict[str, Any]]:
    return conn.execute("SELECT status, payload->>'level' AS level FROM job WHERE kind = 'summarize'"
                        " AND conversation_id = %s ORDER BY id", (cid,)).fetchall()


def _setup(c, migrated: str, *, with_secret: bool) -> tuple[SimChat, UUID, Writer]:
    src_sim = _build_source_chat(6, with_secret=with_secret)
    sync(c, src_sim, character_name="세라", chat_name="항구의 밤", persona_name="도현")
    drain_extract(migrated, _stub_extract)
    tgt_sim = _target(c)
    drain_extract(migrated, _stub_extract)
    writer = Writer()
    drain_summaries(migrated, writer)
    src = UUID(conv_id(c, src_sim))
    return tgt_sim, src, writer


def _next_extraction(migrated: str, monkeypatch) -> int:
    """The worker's own extract handler (which runs `schedule_stale` after a job), with the stub extractor."""
    from nmos_sidecar import worker
    from nmos_sidecar.config import Settings
    from nmos_sidecar.runtime import effective, stored
    from nmos_sidecar.worker import run_once

    real = worker.process_extract
    monkeypatch.setattr(worker, "process_extract",
                        lambda conn, job, complete, gen, turns: real(conn, job, _stub_extract, gen, turns))
    n = 0
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        jobs = worker.handlers(effective(Settings(database_url=migrated, **ON), stored(conn)))
        while run_once(conn, {"extract": jobs["extract"]}):
            n += 1
    return n


def test_a_carried_secret_holds_the_summaries_until_they_are_written_again_and_trim_waits(migrated, monkeypatch):
    with make_client(migrated, **V20) as c:
        tgt_sim, src, writer = _setup(c, migrated, with_secret=True)
        tgt = UUID(conv_id(c, tgt_sim))
        before = _ask(c, tgt_sim)
        assert '<Summary kind="story"' in before["packet"]["text"] and before["trim"]["keep_from_turn"] is not None
        written = (len(writer.scenes), len(writer.stories))
        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            carry.link(conn, tgt, src, "continue", [], _keys(conn))
            queued_at_link = [j for j in _jobs(conn, tgt) if j["status"] == "queued"]
        assert queued_at_link == []  # the link alone queues nothing: the next extraction does

        held = _ask(c, tgt_sim)
        text = held["packet"]["text"]
        assert "<Summary" not in text  # every summary is held: none of them listed the carried secret
        assert held["trim"]["keep_from_turn"] is None and held["trim"]["reason"] == "uncovered"
        assert held["coverage"]["covered_through_turn"] is None

        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            key = active_generation(conn, "summarize").key
            due = len(summaries.current(conn, tgt, conn.execute(
                "SELECT head_commit_id FROM conversation WHERE id = %s", (tgt,)).fetchone()["head_commit_id"],
                key)["scenes"])
        tgt_sim.reply("턴 40의 바닷바람이 분다.")
        sync(c, tgt_sim, **TARGET)
        assert _next_extraction(migrated, monkeypatch) >= 1  # the next extraction queues the rewrite
        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            jobs_once = _jobs(conn, tgt)
            # one job per scene summary (turns 0–31 of 41); the story follows them
            assert due == 4 and [j["level"] for j in jobs_once if j["status"] == "queued"] == ["scene"] * 4
            summaries.schedule_stale(conn, tgt, key)  # the next extraction again: the same keys, nothing new
            assert _jobs(conn, tgt) == jobs_once
        drain_summaries(migrated, writer)
        scene_calls, story_calls = len(writer.scenes) - written[0], len(writer.stories) - written[1]
        assert scene_calls == 4 and story_calls == 1  # the rewrite: four scenes, then one story
        assert all(SECRET_TEXT in p for p in writer.scenes[written[0]:])  # each rewrite knew the carried secret
        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            jobs = _jobs(conn, tgt)
            assert summaries.schedule_stale(conn, tgt, key) == 0  # nothing more: no loop
        # the rewrite's jobs: four scenes, and a story after each (the scene ids change), three of which end obsolete
        # without a call (the scenes changed again) and one is written
        rewrite = [(j["level"], j["status"]) for j in jobs[5:]]
        assert rewrite == [("scene", "done")] * 4 + [("story", "obsolete")] * 3 + [("story", "done")]

        after = _ask(c, tgt_sim)
        text = after["packet"]["text"]
        assert '<Summary kind="story"' in text and SECRET_TEXT not in text
        assert after["trim"]["keep_from_turn"] is not None and after["coverage"]["covered_through_turn"] is not None


def test_a_link_with_no_open_secret_changes_nothing(migrated):
    with make_client(migrated, **V20) as c:
        tgt_sim, src, writer = _setup(c, migrated, with_secret=False)
        tgt = UUID(conv_id(c, tgt_sim))
        before = _ask(c, tgt_sim)
        calls = (len(writer.scenes), len(writer.stories))
        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            carry.link(conn, tgt, src, "continue", [], _keys(conn))
            assert summaries.schedule_stale(conn, tgt, active_generation(conn, "summarize").key) == 0
        drain_summaries(migrated, writer)
        after = _ask(c, tgt_sim)
    assert (len(writer.scenes), len(writer.stories)) == calls
    assert '<Summary kind="story"' in after["packet"]["text"]
    assert before["trim"]["keep_from_turn"] is not None and after["trim"]["keep_from_turn"] is not None


def test_the_note_reads_threads_and_facts_while_every_summary_is_held():
    """While the rewrite is pending the note's chronicle reads the threads and NOW facts (`early`), and the diverged
    part compares the setting with the story's facts: neither is left with nothing."""
    secret = {"id": 1, "text": f"세라 knows: {SECRET_TEXT}", "turn": -1, "position": -5, "holders": ["세라"],
              "open": ["카이토"]}
    scene = {"id": "s1", "level": "scene", "first_turn": 0, "last_turn": 7, "text": "세라가 항구를 걸었다.",
             "coverage": {"secrets": []}}
    told = {"scenes": [{"summary": scene}], "story": None}
    assert summaries.unlisted(scene, [secret]) == [secret]  # held: it never listed the carried secret
    now = {"subject": "세라", "predicate": "located_in", "object": "항구", "turn": 12, "position": 24}
    thread = {"id": 9, "status": "open", "subject": "세라", "predicate": "goal", "value": "등대를 고친다", "turn": 10,
              "position": 20}
    out = notes._story(told, [thread], [now], [secret], False, 39)
    assert out["held"] == 1 and out["newest"] == [] and out["early"] is True and out["now"] and out["shown"]
    story, spans, held = divergence.story_input([{**now, "polarity": "positive"}], told, [secret], False)
    assert held == 1 and spans == [(12, 12)] and "[t12]" in story
