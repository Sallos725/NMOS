"""Phase 2: extraction jobs, bounded windows, fact versions, packet <Facts>."""

from __future__ import annotations

import re
import threading

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import active_generation, make_client
from nmos_sidecar.extraction import claim, process_extract
from nmos_sidecar.worker import run_once
from simchat import SimChat
from test_sidecar_integration import recall, sync

FACT = re.compile(r"(?P<who>\w+) (?:is|moved) (?:in|to) the (?P<where>[\w ]+?)\.")


def fake_complete(system: str, user: str) -> tuple[dict, str]:
    """Deterministic stand-in for the model: 'X is in the Y.' in the TARGET → located_in."""
    target = user.split("TARGET", 1)[1]
    items = [{"subject": m["who"], "subject_type": "character", "predicate": "located_in", "object": m["where"],
              "object_type": "place", "epistemic": "stated", "confidence": 0.9, "evidence": m.group(0),
              "modality": "actual"} for m in FACT.finditer(target)]
    if "SECRET" in target:
        items.append({"subject": "Mina", "subject_type": "character", "predicate": "hates_broccoli", "value": "yes"})
    return {"assertions": items}, "{}"


def jobs_for(conn, complete=fake_complete):
    gen = active_generation(conn, "extract")
    return {"extract": (gen.key, lambda cn, job: process_extract(cn, job, complete, gen, gen.spec["context_turns"]))}


def drain(url: str, complete=fake_complete) -> int:
    n = 0
    with psycopg.connect(url, row_factory=dict_row, autocommit=True) as conn:
        jobs = jobs_for(conn, complete)
        while run_once(conn, jobs):
            n += 1
    return n


@pytest.fixture
def llm_client(migrated):
    with make_client(migrated, llm_url="http://fake-llm/v1", llm_model="fake") as c:
        yield c


def facts(client, chat):
    convs = client.get("/v1/conversations").json()
    conv = next(c for c in convs if c["host_chat_ref"] == chat.id)
    return client.get(f"/v1/conversations/{conv['id']}/facts", params={"history": True}).json()


def filler(chat, n, tag=""):
    for i in range(n):
        chat.user(f"Idle chatter {tag}{i} about clouds.")
        chat.reply(f"Idle reply {tag}{i}.")


def test_no_llm_means_no_jobs(client, db):
    chat = SimChat()
    chat.user("Hinata is in the old chapel.")
    chat.reply("ok")
    chat.user("next")
    sync(client, chat)
    assert db.execute("SELECT count(*) AS n FROM job").fetchone()["n"] == 0


def test_extraction_fact_versions_and_packet(llm_client, migrated, db):
    chat = SimChat()
    chat.user("Hinata is in the old chapel.")
    chat.reply("The chapel is quiet.")
    filler(chat, 5)
    sync(llm_client, chat)
    # One job per turn the user continued from (the tail reply is still provisional, D5, ADR 0008).
    assert db.execute("SELECT count(*) AS n FROM job").fetchone()["n"] == chat.complete_turns() == 5
    drain(migrated)
    current = facts(llm_client, chat)
    assert [(f["subject"], f["object"], f["turn"]) for f in current] == [("Hinata", "old chapel", 0)]

    # A later statement supersedes the single-valued fact; history keeps both.
    chat.user("Hinata moved to the bell tower.")
    chat.reply("Bells ring.")
    filler(chat, 5, "b")
    sync(llm_client, chat)
    drain(migrated)
    current = facts(llm_client, chat)
    assert len(current) == 1 and current[0]["object"] == "bell tower" and current[0]["versions"] == 2
    assert [h["object"] for h in current[0]["history"]] == ["old chapel", "bell tower"]

    packet = recall(llm_client, chat, "Where is Hinata now?", in_context=[m["chatId"] for m in chat.messages[-4:]])
    text = packet["packet"]["text"]
    assert '<Fact kind="located_in" turn="6">Hinata located in bell tower</Fact>' in text
    assert "old chapel</Fact>" not in text

    # Editing the source masks its extraction synchronously (D8) and re-queues the new window.
    chat.edit(12, "Hinata moved to the harbor.")
    sync(llm_client, chat)
    assert all(f["object"] != "bell tower" for f in facts(llm_client, chat))
    assert facts(llm_client, chat)[0]["object"] == "old chapel"  # until the new window is extracted
    drain(migrated)
    assert facts(llm_client, chat)[0]["object"] == "harbor"

    # Deleting the source removes the fact version; the earlier one becomes current again. (Its reply
    # now continues the previous turn, whose anchor and hash change.)
    chat.delete(12)
    sync(llm_client, chat)
    assert facts(llm_client, chat)[0]["object"] == "old chapel"


def test_edit_inside_window_requeues_following_turns(llm_client, migrated, db):
    chat = SimChat()
    filler(chat, 10)
    chat.user("last")
    sync(llm_client, chat)
    drain(migrated)
    chat.edit(4, "Idle chatter changed.")
    sync(llm_client, chat)
    queued = db.execute("SELECT count(*) AS n FROM job WHERE status = 'queued'").fetchone()["n"]
    assert queued == 4  # position 4 is in turn 2: turn 2 and its K=3 successors (D7, ADR 0008)


def test_unknown_predicates_are_pending_never_injected(llm_client, migrated, db):
    chat = SimChat()
    chat.user("SECRET: Mina is in the kitchen.")
    chat.reply("ok")
    filler(chat, 4)
    sync(llm_client, chat)
    drain(migrated)
    statuses = {r["predicate"]: r["status"] for r in db.execute("SELECT predicate, status FROM assertion").fetchall()}
    assert statuses == {"located_in": "valid", "hates_broccoli": "pending"}
    text = recall(llm_client, chat, "What about Mina and broccoli?", in_context=[])["packet"]["text"]
    facts_part = text.split("<Facts>")[1].split("</Facts>")[0] if "<Facts>" in text else ""
    assert "broccoli" not in facts_part


def test_backfill_limit_on_first_sight(migrated, db):
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake", extract_backfill=4) as c:
        chat = SimChat()
        filler(chat, 10)
        chat.user("last")
        sync(c, chat)
    assert db.execute("SELECT count(*) AS n FROM job").fetchone()["n"] == 4


def test_skip_locked_claims_are_exclusive(llm_client, migrated):
    chat = SimChat()
    filler(chat, 10)
    chat.user("last")
    sync(llm_client, chat)
    claimed: list[int] = []
    lock = threading.Lock()

    def worker():
        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            handled = {"extract": active_generation(conn, "extract").key}
            while (job := claim(conn, handled)) is not None:
                with lock:
                    claimed.append(job["id"])

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(claimed) == len(set(claimed)) == chat.complete_turns()


def test_prune_keeps_recent_and_unfinished(llm_client, migrated, db):
    from nmos_sidecar.worker import prune
    chat = SimChat()
    filler(chat, 3)
    chat.user("last")
    sync(llm_client, chat)
    recall(llm_client, chat, "clouds")
    db.execute("UPDATE job SET status = 'done', updated_at = now() - interval '8 days' WHERE id = (SELECT min(id) FROM job)")
    db.execute("UPDATE retrieval_trace SET created_at = now() - interval '40 days'")
    before = db.execute("SELECT count(*) AS n FROM job").fetchone()["n"]
    prune(db, 30)
    assert db.execute("SELECT count(*) AS n FROM job").fetchone()["n"] == before - 1
    assert db.execute("SELECT count(*) AS n FROM retrieval_trace").fetchone()["n"] == 0
    assert "Background jobs:" in llm_client.get("/inspector?lang=en").text


def test_knowledge_annotations_reach_the_packet(migrated, db):
    def complete(system, user):
        if "비밀" not in user.split("TARGET", 1)[1]:
            return {"assertions": []}, "{}"
        return {"assertions": [{"subject": "{{user}}", "subject_type": "character", "predicate": "identity",
                                "value": "이사장의 아들", "known_by": ["하나", "{{user}}"], "hidden_from": ["카이토"],
                                "modality": "actual"}]}, "{}"
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake") as c:
        chat = SimChat()
        chat.user("하나에게만 속삭인다. 비밀인데 나 이사장 아들이야.")
        chat.reply("하나는 고개를 끄덕였다.")
        filler(chat, 5)
        sync(c, chat)
        drain(migrated, complete)
        text = recall(c, chat, "카이토, 내 정체 알아? {{user}}", in_context=[])["packet"]["text"]
    assert 'known_by="하나, {{user}}" hidden_from="카이토"' in text
    assert "do not know it" in text


def test_secret_hidden_from_addressed_character_is_selected():
    from nmos_sidecar.facts import relevant_facts
    base = {"object": None, "epistemic": "stated", "host_logical_id": "x", "known_by": None, "hidden_from": None}
    facts = [
        {**base, "subject": "{{user}}", "predicate": "identity", "value": "이사장의 아들", "position": 1,
         "known_by": ["하나", "{{user}}"], "hidden_from": ["카이토", "유이"]},
        {**base, "subject": "카이토", "predicate": "goal", "value": "새 별 발견", "position": 3},
        {**base, "subject": "마을", "predicate": "world_fact", "value": "축제", "position": 5},
    ]
    picked = relevant_facts(facts, "카이토, 혹시 내 정체에 대해 뭐 들은 거 있어?", "", set(), 8)
    assert [f["predicate"] for f in picked][:2] == ["identity", "goal"]
    assert all(f["subject"] != "마을" for f in picked)


def test_events_do_not_take_every_fact_slot():
    """PHASE-7 Q4 (evidence case): a main character's newest events filled all 8 slots, so an older fact
    about them came back only when the query repeated its words."""
    from nmos_sidecar.facts import relevant_facts
    base = {"object": None, "host_logical_id": "x", "known_by": None, "hidden_from": None}
    facts = [{**base, "subject": "하나", "predicate": "promised", "object": "{{user}}",
              "value": "비가 그치면 등대 앞에서 만나기", "position": 20}]
    facts += [{**base, "subject": "하나", "predicate": "event", "value": f"사소한 일 {i}", "position": i}
              for i in range(30, 400, 2)]
    uncapped = relevant_facts(facts, "하나야, 오랜만이야.", "", set(), 8)
    assert [f["predicate"] for f in uncapped] == ["event"] * 8
    picked = relevant_facts(facts, "하나야, 오랜만이야.", "", set(), 8, events_limit=3)
    assert [f["predicate"] for f in picked] == ["event"] * 3 + ["promised"]
    assert [f["position"] for f in picked[:3]] == [398, 396, 394]  # still the newest events
    assert [f["predicate"] for f in relevant_facts(facts, "하나야", "", set(), 8, events_limit=0)] == ["promised"]


def test_major_events_first_and_minor_events_need_the_query():
    """PHASE-7 Q4, ADR 0020."""
    from nmos_sidecar.facts import relevant_facts
    base = {"object": None, "host_logical_id": "x", "known_by": None, "hidden_from": None, "subject": "하나",
            "predicate": "event"}
    major = {**base, "value": "카이토를 배신했다", "position": 20, "salience": "major"}
    minors = [{**base, "value": f"사소한 일 {i}", "position": i, "salience": "minor"} for i in range(30, 60, 2)]
    unlabeled = [{**base, "value": f"옛날 일 {i}", "position": i} for i in (5, 7)]
    picked = relevant_facts([major, *minors, *unlabeled], "하나야, 오랜만이야.", "", set(), 8, events_limit=3)
    # The major event first; minor ones only by mention do not come; unlabeled ones rank as before.
    assert [f["value"] for f in picked] == ["카이토를 배신했다", "옛날 일 7", "옛날 일 5"]
    # A minor event the query is about still comes.
    picked = relevant_facts([major, *minors], "하나, 사소한 일 40 기억나?", "", set(), 8, events_limit=3)
    assert "사소한 일 40" in [f["value"] for f in picked]


GIVE = re.compile(r"(?P<who>\w+) (?:has|takes|gets) the (?P<item>\w+)\.")


def holder_complete(system: str, user: str) -> tuple[dict, str]:
    """'X has the Y.' in the TARGET → X possesses Y."""
    target = user.split("TARGET", 1)[1]
    return {"assertions": [{"subject": m["who"], "subject_type": "character", "predicate": "possesses",
                            "object": m["item"], "object_type": "item", "epistemic": "stated", "confidence": 0.9,
                            "evidence": m.group(0), "modality": "actual"} for m in GIVE.finditer(target)]}, "{}"


def test_an_item_has_one_current_holder_and_keeps_its_history(llm_client, migrated):
    """ADR 0011: A → B → C. Before, `possesses` accumulated per holder, so all three stayed current."""
    chat = SimChat()
    for who in ("Yujin", "Hana", "Kaito"):
        chat.user(f"{who} has the map.")
        chat.reply("Noted.")
    chat.user("Mina has the key.")
    chat.reply("ok")
    chat.user("Mina gets the map.")  # a second item for the same holder must not merge with the first
    chat.reply("ok")
    chat.user("next")
    sync(llm_client, chat)
    drain(migrated, holder_complete)
    held = {f["object"]: f for f in facts(llm_client, chat) if f["predicate"] == "possesses"}
    assert held["map"]["subject"] == "Mina" and held["key"]["subject"] == "Mina"
    assert [h["subject"] for h in held["map"]["history"]] == ["Yujin", "Hana", "Kaito", "Mina"]
    assert [h["subject"] for h in held["key"]["history"]] == ["Mina"]
    packet = recall(llm_client, chat, "Who has the map now?")["packet"]["text"]
    assert "Mina possesses map" in packet and "Kaito possesses map" not in packet


def test_an_unexpected_job_error_fails_the_job_and_the_worker_goes_on(llm_client, migrated, db):
    """A handler bug or odd provider reply (e.g. TypeError) used to escape `run_once` and end the worker
    thread while the process lived on (audit A-04). It must fail that job and leave the rest claimable."""
    chat = SimChat()
    chat.user("Hinata is in the old chapel.")
    chat.reply("ok")
    filler(chat, 2)
    sync(llm_client, chat)
    total = chat.complete_turns()
    calls = {"n": 0}

    def flaky(system: str, user: str) -> tuple[dict, str]:
        calls["n"] += 1
        if calls["n"] == 1:
            raise TypeError("'NoneType' object is not subscriptable")
        return fake_complete(system, user)

    assert drain(migrated, flaky) == total  # every job was handled, none stopped the loop
    rows = db.execute("SELECT status, last_error FROM job ORDER BY last_error NULLS LAST").fetchall()
    assert rows[0]["status"] == "queued" and "TypeError" in rows[0]["last_error"]  # retried later (backoff)
    assert [r["status"] for r in rows[1:]] == ["done"] * (total - 1)
