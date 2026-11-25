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
from test_source_time import clock_story  # noqa: F401 (a fixture)
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


# --- item 2: a block that restates an unconditional sentence and adds one of its own ---------------------------------

def test_evidence_partly_only_inside_a_block_is_not_served():
    import uuid

    from nmos_sidecar import canonfacts

    text = ("{{char}} is a loyal knight who serves the crown.\n"
            "{{#if {{getvar::route}}}}{{char}} is a loyal knight who serves the crown. A spy.{{/if}}")
    names = ("Hana", None)
    blocks = canonfacts.read_blocks(text, *names)
    served = {ev: canonfacts.shown(blocks, uuid.uuid4(), ev, names) for ev in (
        "Hana is a loyal knight who serves the crown.",  # unconditional: every piece is outside
        "Hana is a loyal knight who serves the crown. A spy.",  # the restated sentence and the branch's own
        "A spy.")}
    assert served == {"Hana is a loyal knight who serves the crown.": True,
                      "Hana is a loyal knight who serves the crown. A spy.": False, "A spy.": False}


# --- item 3: a secret with no value is repeated when the text names its subject too ----------------------------------

def _place(subject: str, predicate: str, obj: str, holders: list[str], kept: list[str]) -> dict[str, Any]:
    return {"text": f"{subject} {predicate.replace('_', ' ')} {obj}", "subject": subject, "predicate": predicate,
            "object": obj, "turn": 3, "position": 6, "holders": holders, "open": kept}


def test_a_common_place_or_item_named_alone_does_not_repeat_the_secret():
    room = _place("세라", "located_in", "교실", ["세라"], ["카이토"])
    near = frozenset({"카이토"})
    assert summaries.leaks("방과 후 교실에서 친구들이 떠들었다.", [room], near) == []  # the place alone
    assert summaries.leaks("세라는 몰래 교실로 들어갔다.", [room], near) == [room]
    sword = _place("도현", "possesses", "검", ["도현"], ["카이토"])  # a one-syllable object
    assert summaries.leaks("대장장이가 검을 벼렸다.", [sword], near) == []
    assert summaries.leaks("도현은 검을 품에 숨겼다.", [sword], near) == [sword]
    key = _place("김하나", "possesses", "은열쇠", ["김하나"], ["도윤"])  # Tier 1's Korean case stays caught
    assert summaries.leaks("김하나는 낡은 은열쇠를 몰래 품에 숨겼다.", [key], frozenset({"도윤"})) == [key]
    user = _place("{{user}}", "member_of", "암살단", ["{{user}}"], ["카이토"])  # a macro subject is not looked for
    assert summaries.leaks("유찬은 암살단의 일원이다.", [user], near) == [user]
    assert summaries.leaks("세라는 교실에 있다.", [{**room, "open": []}], near) == []  # no longer kept from anyone


def test_no_stored_summary_listed_under_an_earlier_key_form_is_held():
    """`secret_key` is what a summary's `coverage.secrets` lists. Before Tier 1 a valueless secret was listed by its
    whole line; since Tier 1 by its object; the registry's other valueless predicates (`lives in`, …) by their whole
    line until now. A summary listed under any of those forms is not `unlisted`."""
    forms = [
        (_place("김하나", "possesses", "은열쇠", ["김하나"], ["도윤"]), ["김하나 possesses 은열쇠", "은열쇠"]),
        (_place("서윤", "located_in", "지하감옥", ["서윤"], ["도윤"]), ["서윤 located in 지하감옥", "지하감옥"]),
        (_place("레나", "member_of", "암살단", ["레나"], ["도윤"]), ["레나 member of 암살단", "암살단"]),
        (_place("레나", "lives_in", "등대", ["레나"], ["도윤"]), ["레나 lives in 등대"]),
        (_place("레나", "contained_in", "상자", ["레나"], ["도윤"]), ["레나 contained in 상자"]),
        ({"text": "하나 knows: 편지는 위조됐다", "subject": "하나", "predicate": "knows", "turn": 3, "position": 6,
          "holders": ["하나"], "open": ["도윤"]}, ["편지는 위조됐다"]),
    ]
    for secret, stored in forms:
        for key in stored:
            row = {"last_turn": 7, "coverage": {"secrets": [key]}}
            assert summaries.unlisted(row, [secret]) == [], (secret["text"], key)
        assert summaries.unlisted({"last_turn": 7, "coverage": {"secrets": []}}, [secret]) == [secret]
    # the three Tier 1 predicates keep exactly the key Tier 1 stored
    assert [summaries.secret_key(s) for s, _ in forms[:3]] == ["은열쇠", "지하감옥", "암살단"]


# --- item 5: an empty summary never covers, and an empty reply fails its job ------------------------------------------

def test_an_empty_reply_fails_the_job_and_an_empty_summary_covers_nothing(migrated):
    from nmos_sidecar import coverage
    from nmos_sidecar.worker import run_once
    from test_packet_ledger import extract
    from test_summaries import ON as SUMMARIES_ON, story_chat

    chat = story_chat(16)
    chat.user("Now asking a question at turn 16.")
    with make_client(migrated, **SUMMARIES_ON) as c:
        sync(c, chat)
        extract(migrated)
        cid = UUID(conv_id(c, chat))
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        gen = active_generation(conn, "summarize")
        run_once(conn, {"summarize": (gen.key, lambda cn, job: summaries.process(
            cn, job, lambda s, u: ({"summary": "  "}, "{}"), gen))})
        job = conn.execute("SELECT * FROM job WHERE kind = 'summarize' AND attempts > 0").fetchone()
        assert job["status"] == "queued" and job["attempts"] == 1 and "empty" in job["last_error"]
        assert conn.execute("SELECT count(*) AS n FROM summary").fetchone()["n"] == 0
        head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid,)).fetchone()["head_commit_id"]
        # a row stored empty before this change (or a window too short to summarize) covers nothing
        conn.execute("UPDATE job SET status = 'done' WHERE id = %s", (job["id"],))
        w = summaries.windows(conn, head)[0]
        summaries._insert(conn, cid, gen, "scene", w.key, list(w.members), w.first_turn, w.last_turn, "", "", {}, None)
        assert summaries.current(conn, cid, head, gen.key)["scenes"][0]["summary"]["text"] == ""
        cov = coverage.read(conn, cid, head, gen.key, extractor_key=active_generation(conn, "extract").key)
    assert cov.recorded_through_turn == 15 and cov.covered_through_turn is None


# --- items 6–8: a pin or watch covers only a prefix the parser added for a character; consecutive windows -----------

def _window(position: int, values: dict[str, str]) -> dict[str, Any]:
    return {"position": position, "turn": position, "host_logical_id": f"m{position}", "values": values}


def test_a_bare_pin_covers_a_characters_key_and_not_a_key_with_a_dot_of_its_own():
    from nmos_sidecar import statechange

    own = {"P.ATK": "10", "Max.HP": "100", "HP": "80", "Mr. Kim": "우호"}
    assert statechange.entity_prefixes(own) == frozenset()
    for key in ("P.ATK", "Max.HP", "Mr. Kim"):
        assert not statechange.covered(key, {"ATK", "HP", "Kim"}, statechange.entity_prefixes(own)), key
    assert not statechange.covered("Mr. Kim", {"Kim"})  # a spaced dot is no separator, with or without a window
    two = {"서연.HP": "80", "민지.HP": "50", "서연.P.ATK": "10", "민지.P.ATK": "7"}
    prefixes = statechange.entity_prefixes(two)
    assert prefixes == {"서연", "민지"}
    assert statechange.covered("서연.HP", {"HP"}, prefixes) and statechange.covered("민지.P.ATK", {"P.ATK"}, prefixes)
    assert not statechange.covered("서연.P.ATK", {"ATK"}, prefixes)  # its key is `P.ATK`, not `ATK`
    # a rule that declares its dotted keys keeps them whole, even beside a partner that shares a part
    assert statechange.entity_prefixes({"P.ATK": "1", "M.ATK": "2"}, declared={"P.ATK", "M.ATK"}) == frozenset()
    assert statechange.entity_prefixes({"P.ATK": "1", "M.ATK": "2"}, declared_prefixes={"P.", "M."}) == frozenset()
    windows = [_window(1, own), _window(2, own)]
    assert {t.key for t in statechange.tell(windows, frozenset({"ATK", "HP"}))} == {"HP"}


def _entry(value: str, position: int, last: int | None = None) -> dict[str, Any]:
    return {"value": value, "position": position, "last_position": position if last is None else last,
            "turn": position, "rule_id": "s", "revision_id": position, "redone": False}


def test_a_watch_compares_only_consecutive_windows_of_a_key():
    from nmos_sidecar.statewatch import detect

    quiet = {2: "둘은 말없이 걸었다.", 3: "둘은 말없이 걸었다."}
    # bare at 1, two characters at 2, bare again at 3: HP 80 → 60 spans a window without `HP`
    gap = {"HP": [_entry("80", 1), _entry("60", 3)], "서연.HP": [_entry("70", 2)], "민지.HP": [_entry("50", 2)]}
    assert detect(gap, {"s": frozenset({"HP"})}, quiet) == []
    # the same values in consecutive windows are flagged as before
    flagged = detect({"HP": [_entry("80", 1), _entry("60", 2)]}, {"s": frozenset({"HP"})}, quiet)
    assert [(f["key"], f["old"], f["new"]) for f in flagged] == [("HP", "80", "60")]
    # a key with a dot of its own is not watched by its last part
    assert detect({"Max.HP": [_entry("100", 1), _entry("90", 2)]}, {"s": frozenset({"HP"})}, quiet) == []


def test_flags_of_reads_only_the_watched_keys_by_their_last_part(migrated, monkeypatch, tmp_path):
    import json

    from nmos_sidecar import statewatch

    rules = tmp_path / "rules.json"
    rules.write_text(json.dumps({"rules": [{"card": "세라", "id": "s", "kind": "shape", "role": "char",
                                            "keys": ["HP", "MP", "기분"], "watch": ["HP"]}]}), encoding="utf-8")
    chat = SimChat()
    for hp in (80, 60):
        chat.user("계속.")
        chat.reply(f"둘은 말없이 걸었다.\n[서연 | HP: {hp} | MP: 30 | 기분: 맑음]\n[민지 | HP: 50 | MP: 10 | 기분: 흐림]")
    chat.user("다음.")
    asked: list[Any] = []
    real = statewatch.history
    monkeypatch.setattr(statewatch, "history", lambda *a, **k: asked.append(k.get("keys")) or real(*a, **k))
    with make_client(migrated, parsers_file=str(rules), packet_policy="packet-v18") as c:
        sync(c, chat, character_name="세라")
        conv = c.get("/v1/conversations").json()[0]["id"]
        html = c.get(f"/v1/inspector/c/{conv}?lang=en").json()["html"]
    assert "서연.HP: 80 → 60" in html and "민지.HP" not in html.split("state_dismiss:")[0][-200:]
    assert asked and all(sorted(k) == ["민지.HP", "서연.HP"] for k in asked)  # never the whole history


# --- item 9: the bare clock key first; the two new cues only as questions ---------------------------------------------

def test_cues_that_narration_uses_do_not_ask_for_the_clock():
    from nmos_sidecar import source_time

    for q in ("오늘 몇 일차야?", "지금 3일차지?", "그게 어느 날이었지?", "어느 날에 있었던 일이야?"):
        assert source_time.CUE.search(q), q
    for narration in ("어느 날 갑자기 비가 쏟아졌다.", "일차적으로 세라가 책임을 졌다."):
        assert not source_time.CUE.search(narration), narration


def test_a_bare_clock_key_is_preferred_to_a_dotted_one(migrated, clock_story):  # noqa: F811
    from nmos_sidecar import source_time
    from nmos_sidecar.parsers import load_rules

    path, chat, _ = clock_story
    with make_client(migrated, parsers_file=str(path)) as c:
        sync(c, chat, character_name="Clock test")
        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            head = conn.execute("SELECT head_commit_id FROM conversation WHERE host_chat_ref=%s",
                                (chat.id,)).fetchone()["head_commit_id"]
            rid = str(conn.execute("SELECT source_revision_id FROM active_membership WHERE commit_id=%s AND position=1",
                                   (head,)).fetchone()["source_revision_id"])
            version = load_rules(str(path)).version
            conn.execute("INSERT INTO state_observation (conversation_id,source_revision_id,rules_version,rule_id,key,value)"
                         " SELECT conversation_id,source_revision_id,rules_version,rule_id,'Quest.Date','D-3'"
                         " FROM state_observation WHERE source_revision_id=%s AND key='Date'", (rid,))
            clock = source_time.read(conn, head, version, [rid], 16, -1)[rid]
    assert [(k, v) for k, v, _ in clock.fields] == [("Date", "0712-03-01"), ("Time", "07:05")]
