"""PHASE-12 step 3 (ADR 0042): scene summaries and the story so far, a `summarize` projection."""

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


# --- step 4: secrets (PHASE-12 Q3) -----------------------------------------------------------------

LETTER = {"text": "Hana knows: the letter is forged", "turn": 1, "position": 2, "holders": ["Hana", "{{user}}"],
          "open": ["Kaito"]}


def test_a_summary_that_repeats_a_kept_secret_leaks_it():
    assert summaries.content(LETTER) == "the letter is forged"
    assert summaries.leaks("Hana hid a note. The letter is forged, she knew.", [LETTER]) == [LETTER]
    assert summaries.leaks("Hana kept something from Kaito and baked bread.", [LETTER]) == []
    assert summaries.leaks("The letter is forged.", [{**LETTER, "open": []}]) == []  # found out by everyone: no secret


def test_a_window_lists_the_secrets_stated_by_its_end_newest_first():
    later = {**LETTER, "text": "Hana knows: the key is fake", "turn": 12, "position": 24}
    gone = {**LETTER, "text": "Hana knows: old news", "open": []}
    assert summaries.window_secrets([LETTER, later, gone], 7) == [LETTER]
    assert summaries.window_secrets([LETTER, later, gone], 15) == [later, LETTER]
    assert "- Hana, {{user}} keep from Kaito: the letter is forged" in summaries.secrets_block([LETTER])


def test_the_prompt_lists_kept_secrets_and_a_summary_repeating_one_is_held(migrated, db):
    from memeval import stub_extractor
    from nmos_sidecar.facts import memory_view
    from test_extraction import drain as drain_facts

    chat = SimChat()
    chat.user("Hana keeps a secret from Kaito: the letter is forged.")
    chat.reply("Noted.")
    for i in range(1, 22):
        chat.user(f"Turn {i} begins.")
        chat.reply(f"Reply {i} follows.")
    prompts = []

    def leaky(system: str, user: str) -> tuple[dict, str]:
        prompts.append(user)
        return {"summary": "Hana read it: the letter is forged." if "turn 0]" in user else "Nothing else."}, "{}"

    with make_client(migrated, **ON) as c:
        sync(c, chat)
        drain_facts(migrated, stub_extractor)
        drain(migrated, leaky)
        assert "OPEN SECRETS" in prompts[0] and "keep from Kaito: the letter is forged" in prompts[0]
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            cid = conv_id(c, chat)
            head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid,)).fetchone()["head_commit_id"]
            secrets = memory_view(conn, head, active_generation(conn, "extract").key)["secrets"]
            v = summaries.current(conn, cid, head, active_generation(conn, "summarize").key, secrets)
        assert [bool(x["held"]) for x in v["scenes"]] == [True, False]
        assert "held back: repeats a secret" in c.get(f"/inspector/c/{cid}", params={"lang": "en"}).text


def test_the_leak_check_is_about_the_secret_not_its_setting():
    """Measured in the real-model tier (docs/perf/summaries.md, synthetic scene): a summary that left the kiss out but
    kept the scene's names and setting scored 0.68 before names were left out, above the check then set."""
    kiss = {"text": "하나 event: 소라가 잠든 사이 카이토와 입을 맞췄다", "turn": 0, "position": 0,
            "holders": ["하나", "카이토"], "open": ["소라"]}
    left_out = "소라가 잠든 사이 하나와 카이토는 부엌에서 만났다. 두 사람은 서로의 마음을 확인하며 소라에게는 비밀로 하기로 했다."
    copied = "소라가 잠든 사이, 하나와 카이토는 부엌에서 입을 맞췄다. 카이토는 이를 소라에게 비밀로 하자고 했다."
    assert summaries.leaks(left_out, [kiss]) == [] and summaries.leaks(copied, [kiss]) == [kiss]


def test_the_settings_report_the_switch_and_a_backfill_starts_with_the_newest_chat(migrated, db):
    older, newer = story_chat(20), story_chat(20)
    with make_client(migrated, **LLM) as c:  # summaries off: both chats synced first
        sync(c, older)
        sync(c, newer)
        assert c.get("/v1/config").json()["extraction"]["summaries"] is False
    with make_client(migrated, **ON) as c:  # turned on: the generation's backfill of every chat (PHASE-12 Q7)
        assert c.get("/v1/config").json()["extraction"]["summaries"] is True
        first = db.execute("SELECT conversation_id FROM job WHERE kind = 'summarize' ORDER BY id LIMIT 1").fetchone()
        assert str(first["conversation_id"]) == conv_id(c, newer)
