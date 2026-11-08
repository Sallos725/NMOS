"""PHASE-57 A2 and A3 (ADR 0078): summaries served from an earlier generation, and a model change that carries on by
default, the owner's choice redoing the latest turns or the canon, and only that save redoing anything."""

from __future__ import annotations

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import active_generation, make_client
from nmos_sidecar import canonfacts, extraction, summaries
from nmos_sidecar.extraction import process_extract
from nmos_sidecar.worker import run_once
from test_canon import push
from test_canon_facts import CARD, Model, canon_texts
from test_generations import LLM, conv_id
from test_sidecar_integration import sync
from test_summaries import ask, lighthouse_chat, stub, story_chat, story_setup

REDO = {"mode": "recent"}


def gen_or_none(conn, kind: str):
    row = conn.execute("SELECT 1 FROM projection_generation WHERE kind = %s LIMIT 1", (kind,)).fetchone()
    return active_generation(conn, kind) if row else None


def drain(url: str, model: Model | None = None, summarize=stub) -> int:
    """Every kind the extraction model serves: turns and canon by `model`, summaries by `summarize`."""
    model = model or Model()
    n = 0
    with psycopg.connect(url, row_factory=dict_row, autocommit=True) as conn:
        ex, cg, sm = (gen_or_none(conn, k) for k in ("extract", "canon", "summarize"))
        jobs = {}
        if ex:
            jobs["extract"] = (ex.key, lambda cn, job: process_extract(cn, job, model, ex, ex.spec["context_turns"]))
        if cg:
            jobs["canon"] = (cg.key, lambda cn, job: canonfacts.process(cn, job, model, cg))
        if sm:
            jobs["summarize"] = (sm.key, lambda cn, job: summaries.process(cn, job, summarize, sm))
        while run_once(conn, jobs):
            n += 1
    return n


def queued(db) -> dict[str, int]:
    return {r["kind"]: r["n"] for r in db.execute(
        "SELECT kind, count(*) AS n FROM job WHERE status = 'queued' GROUP BY kind").fetchall()}


def served(url: str, client, chat) -> dict:
    with psycopg.connect(url, row_factory=dict_row) as conn:
        cid = conv_id(client, chat)
        head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid,)).fetchone()["head_commit_id"]
        return summaries.current(conn, cid, head, active_generation(conn, "summarize").key)


def played(migrated, c, turns: int = 30, model: Model | None = None):
    """A chat of `turns` replied turns with its canon, every job done by the first model."""
    chat = story_chat(turns)
    sync(c, chat)
    push(c, chat, canon_texts())
    drain(migrated, model)
    return chat


def test_a_model_change_carries_on_by_default_and_the_old_model_keeps_serving(migrated, db):
    with make_client(migrated, **LLM) as c:
        chat = played(migrated, c)
        old = {k: active_generation(db, k).key for k in ("extract", "summarize", "canon")}
        before = served(migrated, c, chat)
        assert before["done"] == before["due"] == 3 and before["story_current"]
        out = c.put("/v1/config", json={"llm_model": "fake-2"}).json()  # an older plugin: no choice sent
        assert out["queued_jobs"] == 0 and queued(db) == {}
        assert all(active_generation(db, k).key != v for k, v in old.items())
        after = served(migrated, c, chat)
        assert [x["summary"]["id"] for x in after["scenes"]] == [x["summary"]["id"] for x in before["scenes"]]
        assert after["story"]["id"] == before["story"]["id"] and after["story_current"]
        assert {x["summary"]["generation"] for x in after["scenes"]} == {old["summarize"]}
    with make_client(migrated, llm_url=LLM["llm_url"], llm_model="fake-2") as c:  # a restart redoes nothing
        assert queued(db) == {}


def test_after_carrying_on_new_turns_and_edits_queue_only_what_they_change(migrated, db):
    with make_client(migrated, **LLM) as c:
        chat = played(migrated, c)
        c.put("/v1/config", json={"llm_model": "fake-2"})
        turns = chat.complete_turns()
        for i in range(30, 36):
            chat.user(f"Turn {i} begins.")
            chat.reply(f"Reply {i} follows.")
            sync(c, chat)
        jobs = db.execute("SELECT kind, payload FROM job WHERE status = 'queued' ORDER BY id").fetchall()
        assert sum(j["kind"] == "extract" for j in jobs) == chat.complete_turns() - turns  # the new turns only
        assert [j["payload"]["first_turn"] for j in jobs if j["kind"] == "summarize"] == [24]  # the new window only
        drain(migrated)
        chat.edit(18, "Turn 9 was rewritten. Entirely.")  # inside window 8–15
        sync(c, chat)
        jobs = db.execute("SELECT kind, payload FROM job WHERE status = 'queued' ORDER BY id").fetchall()
        assert [j["payload"]["first_turn"] for j in jobs if j["kind"] == "summarize"] == [8]
        # turn 9 and the three after it, whose context holds it (`extract_turns`, ADR 0031): as without a switch
        assert sum(j["kind"] == "extract" for j in jobs) == 1 + 3
        # A card edit reads the changed text; the texts the old model read stay served.
        push(c, chat, canon_texts(CARD.replace("lighthouse keeper", "lamp keeper")))
        assert sum(j["kind"] == "canon" for j in db.execute(
            "SELECT kind FROM job WHERE status = 'queued'").fetchall()) == 1


def test_redo_the_latest_turns_and_read_the_canon_again(migrated, db):
    with make_client(migrated, **LLM) as c:
        chat = played(migrated, c)
        out = c.put("/v1/config", json={"llm_model": "fake-2", "extract_backfill": 10, "on_model_change": REDO})
        assert out.status_code == 200, out.text
        jobs = db.execute("SELECT kind, payload FROM job WHERE status = 'queued' ORDER BY id").fetchall()
        assert sum(j["kind"] == "extract" for j in jobs) == 9  # turns 20–28: turn 29's reply is not accepted yet
        # the windows ending in the latest ten of the 30 replied turns: 16–23 (it ends at 23 ≥ 20)
        assert [j["payload"]["first_turn"] for j in jobs if j["kind"] == "summarize"] == [16]
        assert not any(j["kind"] == "canon" for j in jobs)
        out = c.put("/v1/config", json={"llm_model": "fake-3", "on_model_change": {"mode": "continue", "canon": True}})
        jobs = db.execute("SELECT kind FROM job WHERE status = 'queued'").fetchall()
        assert [j["kind"] for j in jobs] == ["canon", "canon"]  # the card's description and the persona, as at first
        model = Model()
        drain(migrated, model)
        assert len(model.canon_calls()) == 2 and not [k for k, _ in model.calls if k == "turn"]


def test_a_choice_that_is_not_one_is_refused(client):
    for bad in ({"mode": "all"}, {"canon": "yes"}, {"mode": "recent", "other": 1}, "recent"):
        res = client.put("/v1/config", json={"llm_model": "x", "on_model_change": bad})
        assert res.status_code == 422, bad


def test_the_preview_counts_each_choice_and_changes_nothing(migrated, db):
    with make_client(migrated, **LLM) as c:
        chat = played(migrated, c)
        keys = {k: active_generation(db, k).key for k in ("extract", "summarize", "canon")}
        config = c.get("/v1/config").json()
        out = c.post("/v1/config/preview", json={"llm_model": "fake-2", "extract_backfill": 10}).json()
        assert out["model_change"] is True and out["changes"] == {"extract": "model", "summarize": "model",
                                                                    "canon": "model"}
        assert out["queued"]["continue"] == {"extract": 0, "summarize": 0, "canon": 0}
        assert out["queued"]["recent"] == {"extract": 9, "summarize": 1, "canon": 0}
        assert out["queued"]["canon"] == {"extract": 0, "summarize": 0, "canon": 2}
        assert queued(db) == {} and c.get("/v1/config").json() == config
        assert {k: active_generation(db, k).key for k in keys} == keys
        same = c.post("/v1/config/preview", json={"facts_limit": 5}).json()
        assert same["model_change"] is False and same["queued"]["recent"] == {}
        assert served(migrated, c, chat)["story_current"]


def test_a_release_redoes_the_latest_turns_summaries_only(migrated, db, monkeypatch):
    """Q5 (a): a new summarizer version from a release writes the windows of the latest `extract_backfill` turns;
    an earlier generation serves the rest."""
    with make_client(migrated, **LLM) as c:
        chat = played(migrated, c)
    monkeypatch.setattr(summaries, "VERSION", "summarize-next")
    with make_client(migrated, **LLM, extract_backfill=10) as c:
        jobs = db.execute("SELECT kind, payload FROM job WHERE status = 'queued' ORDER BY id").fetchall()
        assert [(j["kind"], j["payload"]["first_turn"]) for j in jobs] == [("summarize", 16)]
        drain(migrated)
        v = served(migrated, c, chat)
        new = active_generation(db, "summarize").key
        assert [x["summary"]["generation"] == new for x in v["scenes"]] == [False, False, True]
        assert v["story_current"] and v["story"]["generation"] == new  # made from the served scenes, mixed


def test_extract_all_history_brings_the_chat_to_the_new_summarizer(migrated, db):
    with make_client(migrated, **LLM) as c:
        chat = played(migrated, c)
        c.put("/v1/config", json={"llm_model": "fake-2"})
        cid = conv_id(c, chat)
        page = c.get(f"/inspector/c/{cid}", params={"lang": "en"}).text
        assert page.count("written by an earlier model") == 4  # three scenes and the story
        assert c.get(f"/v1/conversations/{cid}/coverage").json()["summaries"]["older"] == 3
        out = c.post(f"/v1/conversations/{cid}/extract-history").json()
        assert out["queued"]["summarize"] == 3
        drain(migrated)
        assert "written by an earlier model" not in c.get(f"/inspector/c/{cid}", params={"lang": "en"}).text


def test_switching_back_serves_each_window_from_the_model_that_wrote_it(migrated, db):
    with make_client(migrated, **LLM) as c:
        chat = played(migrated, c)
        a = active_generation(db, "summarize").key
        c.put("/v1/config", json={"llm_model": "fake-2"})
        b = active_generation(db, "summarize").key
        for i in range(30, 36):
            chat.user(f"Turn {i} begins.")
            chat.reply(f"Reply {i} follows.")
        sync(c, chat)
        drain(migrated)  # model B writes window 24–31 and a story of the four scenes
        out = c.put("/v1/config", json={"llm_model": LLM["llm_model"]}).json()
        assert active_generation(db, "summarize").key == a and out["queued_jobs"] == 0 and queued(db) == {}
        v = served(migrated, c, chat)
        assert [x["summary"]["generation"] for x in v["scenes"]] == [a, a, a, b]
        assert v["story_current"] and v["story"]["generation"] == b


@pytest.mark.parametrize("leaky", [False, True])
def test_a_summary_an_earlier_model_wrote_is_held_for_its_secret_as_before(migrated, leaky):
    chat = lighthouse_chat()

    def complete(system: str, user: str) -> tuple[dict, str]:
        if leaky and system == summaries.STORY_PROMPT:
            return {"summary": "Hana read it: the letter is forged."}, "{}"
        return stub(system, user)

    with make_client(migrated, summaries=True, extract_backfill=100, **LLM) as c:
        sync(c, chat)
        story_setup(migrated, chat, complete)
        assert c.put("/v1/config", json={"llm_model": "fake-2"}).json()["queued_jobs"] == 0
        text = ask(c, chat, "Kaito, anything new?")["text"]
        if leaky:
            assert '<Summary kind="story"' not in text and "the letter is forged" not in text.split("<Private>")[0]
        else:
            assert '<Summary kind="story"' in text  # served by the earlier model's summary


def test_a_save_that_changes_no_model_queues_as_before(migrated, db):
    with make_client(migrated, **LLM) as c:
        played(migrated, c)
        out = c.put("/v1/config", json={"facts_limit": 5}).json()
        assert out["queued_jobs"] == 0 and queued(db) == {}


def test_the_generation_change_is_classified_against_the_recorded_one(migrated, db):
    from nmos_sidecar import generations
    from nmos_sidecar.config import Settings

    with make_client(migrated, **LLM):
        pass
    prev = active_generation(db, "extract").key
    same = extraction.extractor(Settings(**LLM))
    model = extraction.extractor(Settings(llm_url="http://other/v1", llm_model="fake-9"))
    turns = extraction.extractor(Settings(**LLM, extract_turns=2))
    assert generations.classify(db, prev, same) == "same"
    assert generations.classify(db, None, same) == "new"
    assert generations.classify(db, prev, model) == "model"
    assert generations.classify(db, prev, turns) == "version"
