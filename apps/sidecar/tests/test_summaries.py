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
    assert summaries.summarizer(Settings(**LLM)) is not None  # on by default since step 5 (ADR 0042)
    assert summaries.summarizer(Settings(**LLM, summaries=False)) is None
    assert summaries.summarizer(Settings(summaries=True)) is None  # no model
    on = summaries.summarizer(Settings(**ON))
    other = summaries.summarizer(Settings(**{**ON, "llm_model": "other"}))
    assert on.kind == "summarize" and on.spec["window"] == summaries.WINDOW and on.key != other.key


def test_windows_are_due_once_complete_and_lag_turns_old():
    assert [summaries.due(n) for n in (0, 11, 12, 19, 20, 28)] == [0, 0, 1, 1, 2, 3]


def test_turned_off_nothing_is_queued(migrated, db):
    chat = story_chat(30)
    with make_client(migrated, **LLM, summaries=False) as c:
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


def test_a_long_append_queues_every_window_it_makes_due(migrated, db):
    """Found in the Phase 12 upgrade test: one sync that appends 28 messages made windows 0–7 and 8–15 due at once,
    and only the newest was queued, so the story, which waits for every window, was never written."""
    chat = story_chat(8)
    with make_client(migrated, **ON) as c:
        sync(c, chat)
        assert jobs(db) == []
        for i in range(8, 22):
            chat.user(f"Turn {i} begins.")
            chat.reply(f"Reply {i} follows.")
        sync(c, chat)  # one append: 22 replied turns, two windows due
        assert [j["payload"]["first_turn"] for j in jobs(db)] == [0, 8]
        assert drain(migrated) == 3 and view(migrated, c, chat)["story_current"]


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


def test_a_window_lists_the_secrets_stated_by_near_its_end_newest_first():
    later = {**LETTER, "text": "Hana knows: the key is fake", "turn": 20, "position": 40}  # past window 0–7 + NEAR
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


# --- step 5: packet-v8, <Story> and <Cast> (ADR 0043) ------------------------------------------------

from nmos_sidecar.packet import STORY_SHARE, Line, compile_lines, estimate_tokens  # noqa: E402


def summary(level: str, text: str, first: int = 0, last: int = 7, sid: str = "s1") -> Line:
    return summaries.summary_line(level, {"id": sid, "first_turn": first, "last_turn": last, "text": text})


def fact_line(text: str, aid: int) -> Line:
    return Line("fact", f'    <Fact kind="located_in" turn="3">{text}</Fact>', {"assertion": aid}, 3, text, text)


def test_story_comes_first_within_its_share_and_cast_groups_its_lines():
    story = [summary("story", "Hana found the key; Kaito hurt his knee."), summary("scene", "They went to the lighthouse.",
                                                                                     8, 15, "s2")]
    cast = [("Hana", [fact_line("Hana located in lighthouse", 1)])]
    out = compile_lines([], 2000, facts=[fact_line("Kaito located in market", 2)], policy="packet-v8", story=story,
                        cast=cast)
    body = out.text.splitlines()
    assert body[2] == "  <Story>" and '<Summary kind="story" turns="0–7">' in body[3]
    assert '    <Character name="Hana">' in body
    assert any(b.startswith("      <Fact") and "Hana located in lighthouse" in b for b in body)
    assert out.text.index("<Cast>") < out.text.index("<Facts>") and "A Summary tells" in out.text
    assert [e.get("section") for e in out.ledger if e["kind"] == "fact"] == ["cast", None]
    long = [summary("story", "긴 이야기가 이어졌다. " * 60)]  # over the share, within the budget
    capped = compile_lines([], 2000, policy="packet-v8", story=long, facts=[fact_line("Kaito located in market", 2)])
    assert capped.ledger[0]["why"] == "story_cap" and "<Story>" not in capped.text  # never over STORY_SHARE
    assert STORY_SHARE == 0.3 and 2000 * STORY_SHARE < estimate_tokens(long[0].xml, 1.2) < 1500
    assert "<Story>" not in compile_lines([], 2000, policy="packet-v6", facts=[fact_line("x", 3)]).text


def story_setup(migrated, chat: SimChat, complete=stub):
    from memeval import stub_extractor
    from test_extraction import drain as drain_facts

    drain_facts(migrated, stub_extractor)
    drain(migrated, complete)


def lighthouse_chat() -> SimChat:
    chat = SimChat()
    chat.user("Hana is in the chapel.")
    chat.reply("Hana keeps a secret from Kaito: the letter is forged.")
    for i in range(1, 30):
        chat.user(f"Turn {i} begins at the lighthouse keeper's door.")
        chat.reply(f"Reply {i} follows.")
    return chat


def ask(client, chat: SimChat, text: str) -> dict:
    chat.user(text)
    sync(client, chat)
    return client.post("/v1/retrieve", json={"chat_id": chat.id, "query": text, "previous_ai": "", "budget_tokens": 2000,
                                             "in_context_ids": [m["chatId"] for m in chat.messages[-6:]]}).json()["packet"]


def test_a_request_gets_the_story_the_scene_it_is_about_and_the_cast(migrated):
    chat = lighthouse_chat()
    with make_client(migrated, **ON, extract_backfill=100) as c:
        sync(c, chat)
        story_setup(migrated, chat)
        text = ask(c, chat, "Hana, what about the lighthouse keeper's door?")["text"]
    assert '<Summary kind="story"' in text and text.index("<Story>") < text.index("<Cast>")
    assert '<Summary kind="scene"' in text  # the message is about a scene the prompt no longer holds
    assert '<Character name="Hana">' in text and text.count("Hana located in chapel") == 1  # in <Cast>, not twice


def test_a_summary_repeating_a_kept_secret_and_a_narrator_get_no_story(migrated):
    chat = lighthouse_chat()

    def leaky(system: str, user: str) -> tuple[dict, str]:
        if system == summaries.STORY_PROMPT:
            return {"summary": "Hana read it: the letter is forged."}, "{}"
        return stub(system, user)

    with make_client(migrated, **ON, extract_backfill=100) as c:
        sync(c, chat)
        story_setup(migrated, chat, leaky)
        text = ask(c, chat, "Kaito, anything new?")["text"]
        assert '<Summary kind="story"' not in text and "the letter is forged" not in text.split("<Private>")[0]
        cid = conv_id(c, chat)
        assert c.put(f"/v1/conversations/{cid}/memory-mode", json={"narrator": "Kaito"}).status_code == 200
        assert "<Story>" not in ask(c, chat, "Hana, what about the lighthouse keeper's door?")["text"]


def test_a_secret_stated_after_a_summary_holds_it_until_it_is_written_again(migrated, db):
    """Phase 12 step 5: on the owner's chat an event was known to be kept from someone only a few turns after it, so
    the summaries of its window, written before, did not keep it."""
    from memeval import stub_extractor
    from nmos_sidecar.facts import memory_view
    from test_extraction import drain as drain_facts

    chat = story_chat(22)  # windows 0–7 and 8–15 are due
    prompts: list[str] = []

    def recording(system: str, user: str) -> tuple[dict, str]:
        prompts.append(user)
        return stub(system, user)

    with make_client(migrated, **ON) as c:
        sync(c, chat)
        drain(migrated, recording)
        chat.user("Hana keeps a secret from Kaito: the letter is forged.")  # turn 22, within NEAR of window 8–15
        chat.reply("Noted.")
        chat.user("Go on.")  # the turn is extracted once the user continues from it (ADR 0008)
        sync(c, chat)
        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            cid = conv_id(c, chat)
            head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid,)).fetchone()["head_commit_id"]
            key = active_generation(conn, "summarize").key
            drain_facts(migrated, stub_extractor)
            secrets = memory_view(conn, head, active_generation(conn, "extract").key)["secrets"]
            v = summaries.current(conn, cid, head, key, secrets)
            assert [bool(x["held"]) for x in v["scenes"]] == [False, True] and v["story_held"]  # held at once
            assert summaries.schedule_stale(conn, cid, key) == 1
        prompts.clear()
        drain(migrated, recording)
        assert "keep from Kaito: the letter is forged" in prompts[0]  # written again with it listed
        assert any("SCENES:" in p and "OPEN SECRETS" in p for p in prompts)  # and the story too
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            v = summaries.current(conn, cid, head, key, secrets)
        assert not any(x["held"] for x in v["scenes"]) and not v["story_held"] and v["story_current"]
        # the scene written again replaces the old one; the old story, made from it, is simply no longer current
        assert db.execute("SELECT count(*) AS n FROM summary WHERE discarded_at IS NOT NULL").fetchone()["n"] == 1


def test_the_settings_report_the_switch_and_a_backfill_starts_with_the_newest_chat(migrated, db):
    older, newer = story_chat(20), story_chat(20)
    with make_client(migrated, **LLM, summaries=False) as c:  # summaries off: both chats synced first
        sync(c, older)
        sync(c, newer)
        assert c.get("/v1/config").json()["extraction"]["summaries"] is False
    with make_client(migrated, **ON) as c:  # turned on: the generation's backfill of every chat (PHASE-12 Q7)
        assert c.get("/v1/config").json()["extraction"]["summaries"] is True
        first = db.execute("SELECT conversation_id FROM job WHERE kind = 'summarize' ORDER BY id LIMIT 1").fetchone()
        assert str(first["conversation_id"]) == conv_id(c, newer)


def test_with_facts_and_threads_off_a_story_that_repeats_a_secret_is_still_held(migrated):
    chat = lighthouse_chat()

    def leaky(system: str, user: str) -> tuple[dict, str]:
        if system == summaries.STORY_PROMPT:
            return {"summary": "Hana read it: the letter is forged."}, "{}"
        return stub(system, user)

    with make_client(migrated, **ON, extract_backfill=100, facts_limit=0, threads_limit=0) as c:
        sync(c, chat)
        story_setup(migrated, chat, leaky)
        assert "the letter is forged" not in ask(c, chat, "Kaito, anything new?")["text"]


def test_a_scene_that_repeats_a_secret_gives_the_story_none_of_its_text(migrated):
    chat = lighthouse_chat()
    prompts: list[str] = []

    def recording(system: str, user: str) -> tuple[dict, str]:
        prompts.append(user)
        if system == summaries.STORY_PROMPT:
            return {"summary": "Story."}, "{}"
        return {"summary": "Hana read it: the letter is forged." if "turn 0]" in user else "Nothing else."}, "{}"

    with make_client(migrated, **ON, extract_backfill=100) as c:
        sync(c, chat)
        story_setup(migrated, chat, recording)
    story = next(p for p in prompts if "SCENES:" in p)
    assert "(left out: it repeats a secret)" in story and "the letter is forged." not in story.split("SCENES:")[1]


def test_a_replay_from_before_a_summary_was_written_again_reads_the_one_it_used(migrated, db):
    chat = story_chat(22)
    with make_client(migrated, **ON) as c:
        sync(c, chat)
        drain(migrated)
        chat.user("Turn 3 begins, remember?")
        sync(c, chat)
        before = c.post("/v1/retrieve", json={"chat_id": chat.id, "query": "Turn 3 begins, remember?", "budget_tokens": 2000,
                                              "in_context_ids": [m["chatId"] for m in chat.messages[-6:]]}).json()
        assert "<Story>" in before["packet"]["text"]
        chat.user("Hana keeps a secret from Kaito: the letter is forged.")
        chat.reply("Noted.")
        chat.user("Go on.")
        sync(c, chat)
        from memeval import stub_extractor
        from test_extraction import drain as drain_facts

        drain_facts(migrated, stub_extractor)
        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            summaries.schedule_stale(conn, conv_id(c, chat), active_generation(conn, "summarize").key)
        drain(migrated)
        assert db.execute("SELECT count(*) AS n FROM summary WHERE discarded_at IS NOT NULL").fetchone()["n"] >= 1
        replay = c.get(f"/v1/trace/{before['trace_id']}/replay").json()
    assert replay["status"] == "ok" and replay["reproduced"] is True, replay.get("notes")


def test_with_the_character_it_is_kept_from_present_a_reworded_secret_is_held():
    """The secret gate (owner, 2026-09-28): the bar drops to LEAK_NEAR when a character the secret is kept from is in
    the scene; elsewhere a summary that only rewords it stays usable. Synthetic text."""
    plan = {"text": "하나 goal: 카이토의 훈련 모습을 몰래 훔쳐보는 작전을 성공시키는 것", "turn": 7, "position": 14,
            "holders": ["하나", "유이"], "open": ["카이토"]}
    story = "유이와 하나는 카이토를 위해 빵을 굽고, 그의 훈련 모습을 몰래 보러 가는 작전을 세웠다."
    assert summaries.LEAK_NEAR <= summaries.leak_score(plan, story) < summaries.LEAK_MIN
    assert summaries.leaks(story, [plan]) == []
    assert summaries.leaks(story, [plan], frozenset({"카이토"})) == [plan]
    assert summaries.leaks("유이와 하나는 카이토를 위해 빵을 굽고 산책을 했다.", [plan], frozenset({"카이토"})) == []


def page(client, chat: SimChat) -> str:
    return client.get(f"/inspector/c/{conv_id(client, chat)}", params={"lang": "en"}).text


def test_the_inspector_says_why_a_scene_has_no_summary(migrated, db):
    """PHASE-12 step 6: the generation, a scene changed by an edit, its job queued or failed, the story waiting, and
    summaries turned off."""
    chat = story_chat(30)
    with make_client(migrated, **ON) as c:
        sync(c, chat)
        drain(migrated)
        key = active_generation(db, "summarize").key
        text = page(c, chat)
        assert "Summary generation" in text and key[:20] in text and "Story of 0–7, 8–15, 16–23" in text
        assert "scenes 1–3 of 3" in text and "not in it yet" not in text
        chat.edit(2, "Turn 1 was rewritten.")
        sync(c, chat)
        text = page(c, chat)
        assert "scene changed: written again" in text and ">queued<" in text
        assert "Written once every scene has a summary (2 of 3)." in text
        db.execute("UPDATE job SET status = 'dead', last_error = 'the model said no' WHERE kind = 'summarize'"
                   " AND status = 'queued'")
        text = page(c, chat)
        assert ">failed<" in text and "the model said no" in text
        assert c.put("/v1/config", json={"summaries": False}).status_code == 200
        assert "Scene summaries are off" in page(c, chat)


def test_the_inspector_names_the_secret_that_holds_a_summary():
    from nmos_sidecar import inspector
    from nmos_sidecar.summaries import Window

    secret = {"text": "Hana keeps from Kaito: the letter is forged", "holders": ["Hana"], "open": ["Kaito"]}
    row = {"text": "Hana reads the letter.", "members": [], "last_turn": 7}
    w = Window(0, 0, 7, (), "k")
    held = inspector._summary_state({"window": w, "summary": row, "leaks": [secret], "unlisted": [], "near": [],
                                     "job": None}, "en")
    assert "held back: repeats a secret" in held and "the letter is forged" in held
    near = inspector._summary_state({"window": w, "summary": row, "leaks": [], "unlisted": [], "near": [secret],
                                     "job": None}, "en")
    assert ">current<" in near and "not used while Kaito is in the scene" in near
    again = inspector._summary_state({"window": w, "summary": row, "leaks": [], "unlisted": [secret], "near": [],
                                      "job": {"status": "queued"}}, "en")
    assert "a secret stated after it, written again" in again and ">queued<" in again


def test_a_character_page_shows_what_cast_says_of_them(migrated, db):
    from memeval import stub_extractor
    from nmos_sidecar.facts import memory_view
    from test_extraction import drain as drain_facts

    chat = SimChat()
    chat.user("Hana is in the chapel.")
    chat.reply("Hana takes the lantern. Hana wants to find the keeper.")
    chat.user("Go on.")
    chat.reply("Kaito is in the garden.")
    chat.user("Next.")
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        sync(c, chat)
        drain_facts(migrated, stub_extractor)
        cid = conv_id(c, chat)
        head = db.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid,)).fetchone()["head_commit_id"]
        entities = memory_view(db, head, active_generation(db, "extract").key)["entities"]
        by_name = {e["name"]: e["id"] for e in entities}
        hana = c.get(f"/inspector/c/{cid}/e/{by_name['Hana']}", params={"lang": "en"}).text
        lantern = c.get(f"/inspector/c/{cid}/e/{by_name['lantern']}", params={"lang": "en"}).text
    assert "Current state (&lt;Cast&gt;)" in hana and "<Cast>" not in hana
    start = hana.index("Current state (&lt;Cast&gt;)")
    state = hana[start:hana.index("</details>", start)]
    for said in ("Place", "Hana located in chapel", "Carries", "Hana possesses lantern", "Open goal", "find the keeper"):
        assert said in state
    assert "Current state" not in lantern  # an item has no <Cast> group


def test_an_edit_inside_a_window_leaves_no_stale_summary_in_the_packet(migrated):
    chat = story_chat(30)
    with make_client(migrated, **ON) as c:
        sync(c, chat)
        drain(migrated)
        assert '<Summary kind="scene" turns="0–7">' in ask(c, chat, "What happened when Turn 1 begins?")["text"]
        chat.edit(2, "Turn 1 was rewritten.")
        stale = ask(c, chat, "What happened when Turn 1 begins?")["text"]
        drain(migrated)
        fresh = ask(c, chat, "What happened when Turn 1 was rewritten?")["text"]
    story = stale[stale.index("<Story>"):stale.index("</Story>")]  # the question itself is an excerpt
    assert "Turn 1 begins" not in story and 'turns="0–7"' not in story  # masked at once
    assert '<Summary kind="story"' not in story  # its story was made from the old scene
    assert '<Summary kind="scene" turns="0–7">' in fresh and "Turn 1 was rewritten" in fresh


def test_a_branch_sees_only_its_own_summaries(migrated):
    chat = story_chat(30)
    with make_client(migrated, **ON) as c:
        sync(c, chat)
        drain(migrated)
        other = chat.branch(19)  # after turn 9's reply
        for i in range(10, 30):
            other.user(f"Desert {i} begins.")
            other.reply(f"Sand {i} follows.")
        sync(c, other)
        drain(migrated)
        mine, theirs = view(migrated, c, other), view(migrated, c, chat)
    said = [x["summary"]["text"] for x in mine["scenes"]]
    assert len(said) == 3 and "Desert 16 begins" in said[2] and not any("Turn 16" in s for s in said)
    assert mine["story"] is not None and not any("Desert" in x["summary"]["text"] for x in theirs["scenes"])


def test_in_strict_mode_a_story_that_repeats_a_secret_is_not_told(migrated):
    chat = lighthouse_chat()

    def leaky(system: str, user: str) -> tuple[dict, str]:
        if system == summaries.STORY_PROMPT:
            return {"summary": "Hana read it: the letter is forged."}, "{}"
        return stub(system, user)

    with make_client(migrated, **ON, extract_backfill=100) as c:
        sync(c, chat)
        story_setup(migrated, chat, leaky)
        cid = conv_id(c, chat)
        assert c.put(f"/v1/conversations/{cid}/memory-mode", json={"strict": True}).status_code == 200
        text = ask(c, chat, "Kaito and Hana, what about the lighthouse keeper's door?")["text"]
    assert '<Summary kind="story"' not in text and "the letter is forged" not in text.split("<Private>")[0]
    assert '<Summary kind="scene"' in text  # the scene without the secret is still told


def test_the_inspector_shows_the_job_that_would_replace_a_summary_and_its_error():
    """Copilot review of #137: a story behind the newest scene hid its replacement's queued or failed job."""
    from nmos_sidecar import inspector
    from nmos_sidecar.summaries import Window

    w = Window(0, 0, 7, (), "k")
    story = {"id": "s", "text": "The story.", "members": ["a"], "last_turn": 7, "coverage": {}}
    view = {"scenes": [{"window": w, "summary": dict(story, text="A scene."), "leaks": [], "unlisted": [], "near": [],
                        "job": None, "changed": False}],
            "story": story, "due": 2, "done": 1, "story_current": False,
            "story_why": {"leaks": [], "unlisted": [], "near": []},
            "story_job": {"status": "dead", "last_error": "the model said no"}}
    text = inspector._summaries_section(view, "en")
    story_part = text[:text.index("<table")]
    assert ">current<" in story_part and ">failed<" in story_part and "the model said no" in story_part
    view.update(story=None, story_job={"status": "dead", "last_error": "still no"})
    story_part = inspector._summaries_section(view, "en").split("<table")[0]
    assert ">failed<" in story_part and "still no" in story_part


def test_a_request_keeps_its_own_trigrams_when_another_clears_the_cache():
    """Copilot review of #139: the shared cache, cleared by another request, could lose a scene in the middle."""
    class Rows:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

    class Conn:
        def execute(self, sql, params):
            return Rows([{"id": i, "text": f"scene {i}"} for i in params[0]])

    summaries._GRAMS.clear()
    summaries._GRAMS["a"] = {"cached"}
    grams = summaries._scene_grams(Conn(), [{"id": "a"}, {"id": "b"}])
    summaries._GRAMS.clear()  # another request crossing the cap
    assert grams["a"] == {"cached"} and grams["b"] and set(grams) == {"a", "b"}


def test_a_summary_moved_to_an_earlier_window_is_judged_by_that_window(migrated, db):
    """Codex review of #139: deleting a whole window's turns moves the later summaries to earlier windows (their members
    are unchanged). Whether a scene is older than the prompt is a question about the window it is current for now, not
    the turns it was written at."""
    chat = story_chat(30)
    with make_client(migrated, **ON) as c:
        sync(c, chat)
        drain(migrated)
        for _ in range(16):  # the first eight turns
            chat.delete(0)
        sync(c, chat)
        in_context = [m["chatId"] for m in chat.messages[24:]]  # from the current turn 12 on
        text = c.post("/v1/retrieve", json={"chat_id": chat.id, "query": "What happened when Turn 9 begins?",
                                            "previous_ai": "", "budget_tokens": 2000,
                                            "in_context_ids": in_context}).json()["packet"]["text"]
        v = view(migrated, c, chat)
    assert v["scenes"][0]["summary"]["first_turn"] == 8  # written for turns 8–15, current now for window 0–7
    assert "Turn 9 begins" in text[text.index("<Story>"):text.index("</Story>")]
