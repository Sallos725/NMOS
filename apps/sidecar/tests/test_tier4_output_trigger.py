"""PHASE-67 part 1: an output sync (`trigger: "output"`) extracts the newest reply's turn before the user continues.

Switch `extract_on_output` (NMOS_EXTRACT_ON_OUTPUT, `PUT /v1/config`, reported at `GET /v1/config`
`extraction.on_output`), on by default since the owner's decision of 2026-11-25: the tests of the early path run on the
default, the old path's tests turn it off explicitly. Synthetic chats only.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import active_generation, make_client
from nmos_sidecar import extraction
from nmos_sidecar.extraction import claim, process_extract
from simchat import SimChat
from test_extraction import fake_complete, filler, jobs_for
from test_sidecar_integration import recall, sync
from test_vectors import FakeEmbedder

from nmos_sidecar.worker import run_once

LLM = {"llm_url": "http://fake-llm/v1", "llm_model": "fake"}
EMBED = {"embedder": FakeEmbedder(), "embed_url": "http://fake/v1", "embed_model": "fake-embed"}
FACT = '<Fact kind="located_in"'


class Counting:
    """A stand-in model that counts the calls it answers (the paid calls of a real one)."""

    def __init__(self, during=None) -> None:
        self.calls = 0
        self.during = during

    def __call__(self, system: str, user: str) -> tuple[dict, str]:
        self.calls += 1
        if self.during is not None:
            during, self.during = self.during, None
            during()
        return fake_complete(system, user)


def drain(url: str, model: Counting) -> int:
    """Run every extract job (embeddings are left queued); the number of jobs run."""
    n = 0
    with psycopg.connect(url, row_factory=dict_row, autocommit=True) as conn:
        jobs = {k: v for k, v in jobs_for(conn, model).items() if k != "reveal"}
        while run_once(conn, jobs):
            n += 1
    return n


def extract_jobs(db) -> list[dict[str, Any]]:
    return db.execute("SELECT id, dedupe_key, status, priority, payload FROM job WHERE kind = 'extract' ORDER BY id"
                      ).fetchall()


def rev_of(db, text: str):
    return db.execute("SELECT id, lifecycle FROM source_revision WHERE content = %s", (text,)).fetchone()


@pytest.fixture(autouse=True)
def default_switch(monkeypatch):
    """The switch at its default: no environment value."""
    monkeypatch.delenv("NMOS_EXTRACT_ON_OUTPUT", raising=False)


@pytest.fixture
def on(migrated) -> Iterator[Any]:
    with make_client(migrated, **LLM) as c:  # the default
        yield c


def story(chat: SimChat, turns: int = 8) -> None:
    """More than 2K + 1 turns (K = 3), so the append fast path's slice does not start at turn 0."""
    filler(chat, turns)
    chat.user("Where did Akari go?")


# --- item 1: the trigger is a declared field, recorded on the observation ---------------------------------------------

def test_an_unknown_trigger_is_refused_and_none_means_request(migrated, db):
    with make_client(migrated) as c:
        chat = SimChat()
        filler(chat, 1)
        bad = c.post("/v1/sync/reconcile", json={**chat.manifest(), "trigger": "later"})
        assert bad.status_code == 422
        sync(c, chat)  # no trigger: a request sync, observed as before
        row = db.execute("SELECT raw_manifest FROM host_observation WHERE kind = 'manifest'").fetchone()
        assert "trigger" not in row["raw_manifest"]
        chat.user("More?")
        chat.reply("Akari moved to the lighthouse.")
        sync(c, chat, trigger="output")
        rows = db.execute("SELECT raw_manifest FROM host_observation WHERE kind = 'manifest' ORDER BY id").fetchall()
        assert rows[-1]["raw_manifest"]["trigger"] == "output"
        assert "appended" in rows[-1]["raw_manifest"]  # the append shape, with the trigger beside it


def test_the_trigger_rides_on_then_reconcile_too(on, db):
    chat = SimChat()
    story(chat)
    sync(on, chat)
    chat.reply("Akari moved to the lighthouse.")
    manifest = {**chat.manifest(), "trigger": "output"}
    out = on.post("/v1/sync/reconcile", json=manifest).json()
    assert out["status"] == "needs_bodies"
    res = on.post("/v1/sync/bodies", json={"chat_id": chat.id, "bodies": chat.bodies(out["needed_bodies"]),
                                            "then_reconcile": manifest})
    assert res.status_code == 200 and res.json()["reconcile"]["status"] == "applied"
    rid = rev_of(db, "Akari moved to the lighthouse.")["id"]
    assert [j["payload"]["revision_id"] for j in extract_jobs(db) if j["payload"].get("early")] == [str(rid)]


# --- item 6: the switch -----------------------------------------------------------------------------------------------

def test_the_switch_is_on_by_default_reported_and_saved_without_queuing_anything(migrated, db):
    with make_client(migrated, **LLM) as c:
        assert c.get("/v1/config").json()["extraction"]["on_output"] is True
        keys = db.execute("SELECT key FROM projection_generation ORDER BY key").fetchall()
        res = c.put("/v1/config", json={"extract_on_output": False})
        assert res.status_code == 200, res.text
        assert res.json()["extraction"]["on_output"] is False and res.json()["queued_jobs"] == 0
        assert c.get("/v1/config").json()["extraction"]["on_output"] is False
        assert db.execute("SELECT key FROM projection_generation ORDER BY key").fetchall() == keys
        assert c.put("/v1/config", json={"extract_on_output": "sometimes"}).status_code == 422
        res = c.put("/v1/config", json={"extract_on_output": None})  # back to the environment's value
        assert res.json()["extraction"]["on_output"] is True and res.json()["queued_jobs"] == 0


def test_the_environment_turns_it_off_and_a_saved_value_wins_either_way(migrated, monkeypatch):
    from nmos_sidecar.config import Settings

    for on in (None, "", "1", "false"):  # the other switches' parser: only "0" is off (NMOS_SUMMARIES, …)
        if on is None:
            monkeypatch.delenv("NMOS_EXTRACT_ON_OUTPUT", raising=False)
        else:
            monkeypatch.setenv("NMOS_EXTRACT_ON_OUTPUT", on)
        assert Settings(database_url="postgresql://x/y").extract_on_output is True
    monkeypatch.setenv("NMOS_EXTRACT_ON_OUTPUT", "0")
    assert Settings(database_url="postgresql://x/y").extract_on_output is False
    with make_client(migrated, **LLM) as c:  # environment off, saved on
        assert c.get("/v1/config").json()["extraction"]["on_output"] is False
        assert c.put("/v1/config", json={"extract_on_output": True}).status_code == 200
    with make_client(migrated, **LLM) as c:  # a restart: the saved value is the effective one
        assert c.get("/v1/config").json()["extraction"]["on_output"] is True
    monkeypatch.delenv("NMOS_EXTRACT_ON_OUTPUT")
    with make_client(migrated, **LLM) as c:  # environment on (default), saved off
        assert c.put("/v1/config", json={"extract_on_output": False}).status_code == 200
    with make_client(migrated, **LLM) as c:
        assert c.get("/v1/config").json()["extraction"]["on_output"] is False


def _session(c, db, url, trigger: str) -> list[tuple]:
    chat = SimChat("same-chat")
    story(chat)
    sync(c, chat)
    chat.reply("Akari moved to the lighthouse.")
    sync(c, chat, trigger=trigger)
    chat.user("And then?")
    sync(c, chat)
    return [(j["status"], j["priority"], sorted(j["payload"])) for j in extract_jobs(db)] + \
        [tuple(r.values()) for r in db.execute("SELECT kind, status, priority FROM job ORDER BY id").fetchall()]


@pytest.mark.parametrize("fast", [True, False])
def test_off_an_output_sync_queues_exactly_what_a_request_sync_does(database_url_factory, fast):
    """Off, the base path whatever the trigger says; and on, an older plugin that never sends `trigger: "output"`
    (request syncs only) gets the same base path."""
    seen = []
    for switch, trigger in ((False, "request"), (False, "output"), (True, "request")):
        url = database_url_factory()
        with make_client(url, extract_on_output=switch, append_fast_path=fast, **LLM, **EMBED) as c, \
                psycopg.connect(url, row_factory=dict_row, autocommit=True) as db:
            seen.append(_session(c, db, url, trigger))
            assert not any(j["payload"].get("early") for j in extract_jobs(db))
    assert seen[0] == seen[1] == seen[2]


def test_an_upgrade_with_the_switch_on_queues_nothing_by_itself(migrated, db):
    """A database with chats (one ends with a reply nobody continued from, one with the user's message) started on
    this build, switch on by default: the start queues nothing, an older plugin's output notification and request
    syncs queue nothing early; only a later output sync from the plugin does."""
    with make_client(migrated, extract_on_output=False, **LLM, **EMBED) as c:  # as the earlier build ran
        open_chat, user_tail = SimChat(), SimChat()
        story(open_chat)
        open_chat.reply("Akari moved to the lighthouse.")
        story(user_tail)
        sync(c, open_chat)
        sync(c, user_tail)
    jobs = "SELECT id, kind, dedupe_key, status, priority, payload FROM job ORDER BY id"
    before = db.execute(jobs).fetchall()
    with make_client(migrated, **LLM, **EMBED) as c:
        assert c.get("/v1/config").json()["extraction"]["on_output"] is True
        assert db.execute(jobs).fetchall() == before  # the start queued nothing
        last = open_chat.messages[-1]
        manifest = open_chat.manifest()["messages"][-1]
        assert c.post("/v1/output", json={"chat_id": open_chat.id, "host_logical_id": last["chatId"],
                                          "generation_id": last["chatId"], "revision_hash": manifest["revision_hash"],
                                          "message_index": len(open_chat.messages) - 1}).status_code == 202
        sync(c, open_chat)  # an older plugin: request syncs only (a noop here)
        user_tail.reply("Akari moved to the bakery.")
        sync(c, user_tail)  # the reply reaches the ledger through a request sync: provisional, nothing early
        assert not any(j["payload"].get("early") for j in extract_jobs(db))
        sync(c, open_chat, trigger="output")  # a noop: the ledger already holds this head
        assert not any(j["payload"].get("early") for j in extract_jobs(db))
        open_chat.reroll("Akari moved to the mill.")
        sync(c, open_chat, trigger="output")  # this plugin's output sync of a new reply: the first early job
        assert len([j for j in extract_jobs(db) if j["payload"].get("early")]) == 1


# --- items 2 and 3: early, and exactly once per reply text ------------------------------------------------------------

@pytest.mark.parametrize("fast", [True, False])
def test_an_output_sync_extracts_the_reply_once_and_the_next_request_serves_it(migrated, db, fast):
    with make_client(migrated, append_fast_path=fast, **LLM, **EMBED) as c:  # the default: on
        chat = SimChat()
        story(chat)
        sync(c, chat)
        model = Counting()
        drain(migrated, model)
        before = len(extract_jobs(db))
        chat.reply("Akari moved to the lighthouse.")
        sync(c, chat)  # a request-trigger sync of the reply (e.g. the plugin's output notification): nothing early
        assert len(extract_jobs(db)) == before
        sync(c, chat, trigger="output")  # a noop now: the ledger already holds this head
        assert len(extract_jobs(db)) == before
        # the plugin's own order: the output sync is the first to bring the reply
        chat2 = SimChat()
        story(chat2)
        sync(c, chat2)
        drain(migrated, model)
        model.calls = 0
        chat2.reply("Akari moved to the lighthouse at dusk.")
        sync(c, chat2, trigger="output")
        rid = rev_of(db, "Akari moved to the lighthouse at dusk.")["id"]
        early = [j for j in extract_jobs(db) if j["payload"].get("early")]
        assert len(early) == 1 and early[0]["payload"]["revision_id"] == str(rid)
        assert early[0]["priority"] == extraction.LIVE_PRIORITY
        embeds = db.execute("SELECT count(*) AS n FROM job WHERE kind = 'embed' AND payload->>'revision_id' = %s",
                            (str(rid),)).fetchone()["n"]
        assert embeds == 1
        assert drain(migrated, model) == 1 and model.calls == 1
        assert rev_of(db, "Akari moved to the lighthouse at dusk.")["lifecycle"] == "provisional"

        counted = "SELECT count(*) AS n FROM job WHERE kind IN ('extract', 'embed')"
        jobs_before = db.execute(counted).fetchone()["n"]
        chat2.user("Is she still there?")
        sync(c, chat2)  # the reply is accepted unchanged: its turn is not extracted again, nor embedded again
        assert rev_of(db, "Akari moved to the lighthouse at dusk.")["lifecycle"] == "accepted"
        assert db.execute(counted).fetchone()["n"] == jobs_before + 1  # the user message's embedding
        assert all(j["status"] == "done" for j in extract_jobs(db))
        assert drain(migrated, model) == 0 and model.calls == 1
        assert db.execute("SELECT count(*) AS n FROM extraction WHERE source_revision_id = %s",
                          (rid,)).fetchone()["n"] == 1
        packet = recall(c, chat2, "Where is Akari now?", in_context=[m["chatId"] for m in chat2.messages[-2:]])
        assert '<Fact kind="located_in" turn="8">Akari located in lighthouse at dusk</Fact>' in packet["packet"]["text"]


def test_a_pruned_early_job_is_queued_again_at_accept_but_calls_no_model(on, migrated, db):
    chat = SimChat()
    story(chat)
    sync(on, chat)
    model = Counting()
    drain(migrated, model)
    chat.reply("Akari moved to the lighthouse.")
    sync(on, chat, trigger="output")
    drain(migrated, model)
    model.calls = 0
    db.execute("DELETE FROM job WHERE payload->>'early' = 'true'")  # as `worker.prune` does after 7 days
    chat.user("Is she still there?")
    sync(on, chat)
    assert drain(migrated, model) == 1 and model.calls == 0  # `load_context` finds the turn done


def test_a_user_tail_or_an_accepted_reply_has_no_open_turn(on, migrated, db):
    chat = SimChat()
    story(chat)
    sync(on, chat, trigger="output")  # the tail is the user's message: nothing to extract early
    assert not any(j["payload"].get("early") for j in extract_jobs(db))


# --- item 4: a reroll, swipe, edit or delete withdraws it -------------------------------------------------------------

def _open(c, migrated, db) -> tuple[SimChat, Counting]:
    chat = SimChat()
    story(chat)
    sync(c, chat)
    model = Counting()
    drain(migrated, model)
    model.calls = 0
    chat.reply("Akari moved to the lighthouse.")
    sync(c, chat, trigger="output")
    return chat, model


def _replace(chat: SimChat, how: str) -> None:
    if how == "reroll":
        chat.messages.pop()  # the host drops the tail before the reroll's request (H14)
    elif how == "edit":
        chat.edit(len(chat.messages) - 1, "Akari stayed in the harbor.")
    elif how == "continue":
        chat.cont(" Then she moved to the mill.")
    elif how == "user edit":
        chat.edit(len(chat.messages) - 2, "Where did Akari go tonight?")
    elif how == "swipe":
        chat.messages[-1]["swipes"] = [chat.messages[-1]["data"], "Akari stayed in the harbor."]
        chat.messages[-1]["swipeId"] = 0
        chat.swipe(1)


HOW = ["reroll", "edit", "continue", "user edit", "swipe"]


@pytest.mark.parametrize("how", HOW)
def test_a_queued_early_job_is_withdrawn_without_a_model_call(on, migrated, db, how):
    chat, model = _open(on, migrated, db)
    _replace(chat, how)
    sync(on, chat)  # the request sync of the reroll, or of the message after the swipe or edit
    assert [j["status"] for j in extract_jobs(db) if j["payload"].get("early")] == ["obsolete"]
    drain(migrated, model)
    assert db.execute("SELECT count(*) AS n FROM extraction e JOIN source_revision sr ON sr.id = e.source_revision_id"
                      " WHERE sr.content = 'Akari moved to the lighthouse.'").fetchone()["n"] == 0
    assert model.calls == 0
    packet = recall(on, chat, "Where is Akari now?", in_context=[chat.messages[-1]["chatId"]])
    assert "lighthouse" not in packet["packet"]["text"]


def test_a_sync_that_leaves_the_open_turn_as_it_is_keeps_its_early_job(on, migrated, db):
    chat, model = _open(on, migrated, db)
    chat.edit(0, "Idle chatter edited, long before the open turn.")  # outside the open turn's K-turn context
    assert sync(on, chat)["commit_reason"] == "edit"
    assert [j["status"] for j in extract_jobs(db) if j["payload"].get("early")] == ["queued"]
    drain(migrated, model)
    calls = model.calls
    chat.user("Is she still there?")
    sync(on, chat)
    assert drain(migrated, model) == 0 and model.calls == calls  # the early extraction is the turn's


def test_a_running_early_job_stores_nothing_once_the_reply_is_rerolled(on, migrated, db):
    chat, _ = _open(on, migrated, db)
    gen = active_generation(db, "extract")
    job = claim(db, {"extract": gen.key})
    assert job["payload"].get("early")

    def reroll():
        chat.messages.pop()
        sync(on, chat)

    model = Counting(during=reroll)
    assert process_extract(db, job, model, gen, gen.spec["context_turns"]) == "obsolete"
    assert model.calls == 1  # the call was in flight: paid, thrown away
    assert db.execute("SELECT count(*) AS n FROM extraction WHERE source_revision_id = %s",
                      (job["payload"]["revision_id"],)).fetchone()["n"] == 0


@pytest.mark.parametrize("how", ["reroll", "edit", "swipe"])
def test_a_finished_early_extraction_never_serves_once_the_reply_is_replaced(on, migrated, db, how):
    chat, model = _open(on, migrated, db)
    drain(migrated, model)
    assert model.calls == 1
    old = rev_of(db, "Akari moved to the lighthouse.")["id"]
    _replace(chat, how)
    if how == "reroll":
        sync(on, chat)  # the reroll's request: the tail is retracted (H14)
        chat.reply("Akari moved to the bakery.")
        assert not any(j["payload"].get("early") and j["status"] == "queued" for j in extract_jobs(db))
        sync(on, chat, trigger="output")  # the new reply's own output sync
        assert drain(migrated, model) == 1 and model.calls == 2  # the new reply's own early extraction
    chat.user("Is she still there?")
    sync(on, chat)
    drain(migrated, model)
    assert rev_of(db, "Akari moved to the lighthouse.")["lifecycle"] in ("retracted", "superseded")
    # retracted by membership, as any extraction whose source left the head (D8); kept for a revision that comes back
    assert db.execute("SELECT discarded_at FROM extraction WHERE source_revision_id = %s",
                      (old,)).fetchone()["discarded_at"] is None
    packet = recall(on, chat, "Where is Akari now?", in_context=[m["chatId"] for m in chat.messages[-2:]])
    assert "lighthouse" not in packet["packet"]["text"]


def test_a_second_reply_in_the_same_turn_moves_the_anchor_and_is_extracted_once_more(on, migrated, db):
    chat, model = _open(on, migrated, db)
    drain(migrated, model)
    chat.reply("Akari moved to the bakery.")  # a second reply answering the same user message
    sync(on, chat, trigger="output")
    drain(migrated, model)
    chat.user("Is she still there?")
    sync(on, chat)
    assert drain(migrated, model) == 0 and model.calls == 2
    packet = recall(on, chat, "Where is Akari now?", in_context=[m["chatId"] for m in chat.messages[-2:]])
    assert "bakery" in packet["packet"]["text"]


def _e(name: str, role: str, rev: str = "r", **kw) -> Any:
    from nmos_sidecar.reconcile import Entry

    return Entry(name, f"{name}-{rev}", role, **kw)


def test_the_open_turn_is_kept_only_when_its_prefix_and_anchor_stay():
    from nmos_sidecar.extraction import open_turn_kept

    head = [_e("u0", "user"), _e("a0", "char"), _e("u1", "user"), _e("a1", "char")]
    life = {e.key: "accepted" for e in head[:3]} | {head[3].key: "provisional"}
    assert open_turn_kept(head, life, head + [_e("u2", "user")])  # the user continued: the common request sync
    assert open_turn_kept(head, life, head + [_e("c", "char", is_comment=True), _e("u2", "user")])
    assert not open_turn_kept(head, life, head + [_e("a1b", "char")])  # a second reply: the anchor moves
    assert not open_turn_kept(head, life, head[:3])  # rerolled (H14)
    assert not open_turn_kept(head, life, head[:3] + [_e("a1", "char", "edited")])  # edit, swipe, continue
    assert not open_turn_kept(head, life, [_e("u0", "user", "edited")] + head[1:])  # an edit before it: checked
    assert not open_turn_kept(head, life, head + [_e("x", "user", disabled="allBefore")])
    assert open_turn_kept(head, {e.key: "accepted" for e in head}, head[:3])  # no open turn: nothing early
    assert open_turn_kept(head[:3], life, head)  # the previous head ended with the user: nothing early yet
    assert open_turn_kept(None, {}, head)  # first sight


def test_an_append_after_the_open_turn_does_not_scan_the_job_table(on, migrated, db, monkeypatch):
    chat, _ = _open(on, migrated, db)
    scans = []
    real = extraction.withdraw_early
    monkeypatch.setattr(extraction, "withdraw_early", lambda *a, **k: scans.append(a) or real(*a, **k))
    chat.user("Is she still there?")
    sync(on, chat)
    assert scans == []
    chat.reply("She is.")
    sync(on, chat, trigger="output")  # the previous head ended with the user's message: nothing to withdraw
    assert scans == []
    chat.messages.pop()
    sync(on, chat)  # a reroll of the open turn: the scan runs
    assert len(scans) == 1


# --- item 5: provisional stays provisional for memory selection -------------------------------------------------------

def test_until_the_user_continues_the_reply_serves_nothing_of_its_own(on, migrated, db):
    chat, model = _open(on, migrated, db)
    drain(migrated, model)
    # A request whose tail is still the reply (Continue, or a reply rewritten in place keeps it): the sync is a noop and
    # the reply stays provisional; its facts are not served and it is not recalled, extracted or not.
    sync(on, chat)
    packet = recall(on, chat, "Where is Akari now? lighthouse", in_context=[])
    assert FACT not in packet["packet"]["text"] and "lighthouse" not in packet["packet"]["text"]
    chat.user("Is she still there?")
    sync(on, chat)
    packet = recall(on, chat, "Where is Akari now?", in_context=[m["chatId"] for m in chat.messages[-2:]])
    assert "Akari located in lighthouse" in packet["packet"]["text"]


def _seen(c, chat: SimChat) -> tuple[dict, list]:
    """What a request and the panel see now: the retrieve answer (no trace id) and the chat's facts."""
    out = recall(c, chat, "Where is Akari now? lighthouse", in_context=[chat.messages[-1]["chatId"]])
    out.pop("trace_id")
    conv = next(x for x in c.get("/v1/conversations").json() if x["host_chat_ref"] == chat.id)
    return out, c.get(f"/v1/conversations/{conv['id']}/facts", params={"history": True}).json()


def test_a_finished_early_extraction_and_embedding_change_nothing_a_request_sees_before_acceptance(migrated, db):
    from test_vectors import drain_embeddings

    with make_client(migrated, **LLM, **EMBED) as c:  # the default: on
        chat = SimChat()
        story(chat)
        sync(c, chat)
        drain(migrated, Counting())
        drain_embeddings(migrated)
        chat.reply("Akari moved to the lighthouse.")
        sync(c, chat, trigger="output")
        before = _seen(c, chat)
        model = Counting()
        assert drain(migrated, model) == 1 and model.calls == 1
        assert drain_embeddings(migrated) == 1
        rid = rev_of(db, "Akari moved to the lighthouse.")["id"]
        assert db.execute("SELECT count(*) AS n FROM revision_embedding WHERE source_revision_id = %s",
                          (rid,)).fetchone()["n"] > 0
        assert _seen(c, chat) == before  # extracted and embedded, still provisional: the same packet and facts
        assert "lighthouse" not in before[0]["packet"]["text"]


# --- switching off withdraws queued early work; the accept path still extracts it -------------------------------------

def test_switching_off_withdraws_queued_early_jobs_and_the_accept_queues_them_again(on, migrated, db):
    chat, model = _open(on, migrated, db)
    res = on.put("/v1/config", json={"extract_on_output": False})
    assert res.status_code == 200 and res.json()["queued_jobs"] == 0
    assert [j["status"] for j in extract_jobs(db) if j["payload"].get("early")] == ["obsolete"]
    assert drain(migrated, model) == 0
    chat.user("Is she still there?")
    sync(on, chat)  # ADR 0008 as before: the accepted turn is queued (the obsolete row is revived)
    assert drain(migrated, model) == 1 and model.calls == 1


def test_switching_off_keeps_an_early_job_whose_reply_was_accepted(on, migrated, db):
    chat, model = _open(on, migrated, db)
    chat.user("Is she still there?")
    sync(on, chat)  # accepted before the early job ran: that job is the turn's extraction
    on.put("/v1/config", json={"extract_on_output": False})
    assert [j["status"] for j in extract_jobs(db) if j["payload"].get("early")] == ["queued"]
    assert drain(migrated, model) == 1 and model.calls == 1


# --- item 7: fail-open ------------------------------------------------------------------------------------------------

def test_a_scheduling_error_is_swallowed_and_the_sync_applies(on, migrated, db, monkeypatch, caplog):
    def broken(conn, *args, **kwargs):
        conn.execute("SELECT 1/0")  # a failed statement: only its savepoint is rolled back, not the sync

    monkeypatch.setattr(extraction, "enqueue_open_turn", broken)
    chat = SimChat()
    story(chat)
    sync(on, chat)
    chat.reply("Akari moved to the lighthouse.")
    assert sync(on, chat, trigger="output")["status"] == "applied"
    assert "early extraction not scheduled" in caplog.text
    assert rev_of(db, "Akari moved to the lighthouse.") is not None  # the sync's own writes are kept
    assert recall(on, chat, "Where is Akari now?")["packet"] is not None
    assert db.execute("SELECT count(*) AS n FROM host_observation WHERE raw_manifest->>'trigger' = 'output'"
                      ).fetchone()["n"] == 1  # committed with the sync
    chat.user("Is she still there?")
    assert sync(on, chat)["status"] == "applied"
    assert rev_of(db, "Akari moved to the lighthouse.")["lifecycle"] == "accepted"
    model = Counting()
    drain(migrated, model)
    packet = recall(on, chat, "Where is Akari now?", in_context=[m["chatId"] for m in chat.messages[-2:]])
    assert "Akari located in lighthouse" in packet["packet"]["text"]


# --- item 6: the cost rule, measured ----------------------------------------------------------------------------------

@pytest.mark.parametrize("case, calls", [("accepted", 1), ("reroll before the debounce", 1),
                                         ("reroll after the debounce", 2)])
def test_the_cost_of_a_turn_with_the_switch_on(on, migrated, db, case, calls):
    chat = SimChat()
    story(chat)
    sync(on, chat)
    model = Counting()
    drain(migrated, model)
    model.calls = 0
    chat.reply("Akari moved to the lighthouse.")
    if case != "reroll before the debounce":  # a reroll inside the 20 s cancels the plugin's output sync
        sync(on, chat, trigger="output")
        drain(migrated, model)
    if case != "accepted":
        chat.messages.pop()
        sync(on, chat)
        chat.reply("Akari moved to the bakery.")
        sync(on, chat, trigger="output")
        drain(migrated, model)
    chat.user("Is she still there?")
    sync(on, chat)
    drain(migrated, model)
    assert model.calls == calls
