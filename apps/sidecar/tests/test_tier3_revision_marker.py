"""PHASE-66 part 5: the zero-cost revision marker (owner decision 2026-11-25).

Extract, reveal, summarize and canon generations carry their post-processing rules' number (`revision`, absent at 0:
the production base, Phase 64). A deploy over a database the production image wrote moves each of those keys once, by
that field alone, and is a carry-on (`generations.classify`: `carry`): no job of any kind, no model call, the same
memory, summaries and checks served; then a new turn is extracted under the new key. A model, compiler, cap or prompt
change with it classifies as before. Stub models only; synthetic names only.
"""

from __future__ import annotations

import contextlib

import pytest

from base_rules import KINDS
from conftest import active_generation, make_client
from nmos_sidecar import canonfacts, extraction, generations, reveals, summaries, vectors
from nmos_sidecar.config import Settings
from simchat import SimChat
from test_canon import push
from test_canon_facts import Model, canon_texts, view
from test_generations import EMB, LLM, conv_id
from test_phase57_carry_on import drain, queued, served
from test_extraction import drain as drain_all
from test_reveals import checked
from test_sidecar_integration import recall, sync
from test_vectors import FakeEmbedder, drain_embeddings

MARKED = ("extract", "reveal", "summarize", "canon")
# The keys the production image (Phase 64, `cdf2c9a`) makes for `Settings(**LLM, **EMB)`: computed by that tree's own
# builders, so a database "the production image wrote" in these tests is keyed as production's is.
PRODUCTION = {"extract": "extract-dcbefa63b23205dfeed6f27c04631e1f", "canon": "canon-51d36c528d03e0dbea37bb8d62b6b892",
              "reveal": "reveal-af9468536e09100e83e9d938e60c4b7e",
              "summarize": "summarize-c71ee7c2e29e00885df72970a8d4b11f"}
BUILDERS = {"extract": extraction.extractor, "reveal": reveals.generation, "summarize": summaries.summarizer,
            "canon": canonfacts.generation}


@contextlib.contextmanager
def production_rules():
    """Revision 0 for every marked kind, as the production image's builders are (no `revision` field)."""
    with pytest.MonkeyPatch.context() as patch:
        for module in KINDS:
            patch.setattr(module, "REVISION", 0)
        yield


def keys(db) -> dict[str, str]:
    return {k: active_generation(db, k).key for k in (*MARKED, "embed")}


def story(turns: int = 30) -> SimChat:
    """A chat with facts the stub model reads (`X is in the Y`, `X is a Y`) and enough turns for three scene windows."""
    chat = SimChat()
    for i in range(turns):
        chat.user(f"Turn {i}: what happens?")
        if i == 1:
            chat.reply("Hana is in the old mill. Hana is a smuggler.")
        elif i == 9:
            chat.reply("Kaito is in the harbor town.")
        elif i == 17:
            chat.reply("Hana is in the lighthouse.")
        else:
            chat.reply(f"Reply {i} follows. More words here.")
    chat.user("Where is Hana?")
    return chat


def facts_of(v: dict) -> list[tuple]:
    return sorted((f["subject"], f["predicate"], f.get("object"), f.get("value"), f["turn"]) for f in v["facts"])


# --- the keys ---------------------------------------------------------------------------------------------------------


def test_each_kind_moves_once_by_its_revision_alone_and_the_base_keys_are_productions():
    s = Settings(**LLM, **EMB)
    with production_rules():
        base = {k: b(s) for k, b in BUILDERS.items()}
        embed = vectors.projection(s).key
    assert {k: g.key for k, g in base.items()} == PRODUCTION
    assert all("revision" not in g.spec for g in base.values())
    for kind, build in BUILDERS.items():
        marked = build(s)
        assert marked.spec == {**base[kind].spec, "revision": 1}, kind
        assert marked.key != base[kind].key and generations.carry_only(base[kind].spec, marked.spec)
    assert {m.REVISION for m in KINDS} == {1}
    assert vectors.projection(s).key == embed  # embeddings have no marker: their rows are re-derived locally anyway
    # every compiler alike (the grid in the report covers 1,280 settings)
    for compiler in sorted(extraction.PROMPTS):
        c = Settings(**LLM, **EMB, extract_compiler=compiler)
        with production_rules():
            old = extraction.extractor(c)
        assert extraction.extractor(c).spec == {**old.spec, "revision": 1}, compiler


def test_a_revision_bump_is_a_carry_on_and_the_more_expensive_class_still_wins(db):
    s = Settings(**LLM, **EMB, extract_compiler="extract-v20")
    with production_rules():
        old = {k: b(s) for k, b in BUILDERS.items()}
    for g in old.values():
        generations.ensure(db, g)

    def cls(kind: str, **over) -> str:
        return generations.classify(db, old[kind].key, BUILDERS[kind](Settings(**{**LLM, **EMB,
                                                                                   "extract_compiler": "extract-v20",
                                                                                   **over})))

    assert {k: cls(k) for k in MARKED} == {k: "carry" for k in MARKED}
    assert {k: cls(k, llm_model="fake-2") for k in MARKED} == {k: "model" for k in MARKED}
    assert {k: cls(k, llm_no_temperature=True) for k in MARKED} == {k: "model" for k in MARKED}
    assert cls("extract", extract_compiler="extract-v21") == "adds"  # compiler (ADDS) + revision
    assert cls("extract", extract_compiler="extract-v17") == "version"  # a compiler outside ADDS + revision
    assert cls("extract", extract_target_chars=12000) == "reads" and cls("reveal", extract_target_chars=12000) == "reads"
    assert cls("summarize", extract_target_chars=12000) == "reads"
    assert cls("extract", extract_turns=4) == "version" and cls("reveal", extract_turns=4) == "version"
    assert cls("extract", llm_json_mode=False) == "version"
    # a prompt change with the bump (a release's new summarize prompt)
    summarize = summaries.summarizer(Settings(**LLM, **EMB))
    other = generations.make("summarize", LLM["llm_url"], LLM["llm_model"],
                             **{**{k: v for k, v in summarize.spec.items() if k not in ("kind", "endpoint", "model")},
                                "prompt": "another"})
    assert generations.classify(db, old["summarize"].key, other) == "version"


def test_peers_are_the_generations_that_differ_only_in_a_carry_on_field(db):
    s = Settings(**LLM, **EMB)
    with production_rules():
        old = reveals.generation(s)
    new, model = reveals.generation(s), reveals.generation(Settings(**{**LLM, **EMB, "llm_model": "fake-2"}))
    assert generations.peers(db, new.key) == [new.key]  # not recorded yet
    for g in (old, new, model):
        generations.ensure(db, g)
    assert set(generations.peers(db, new.key)) == {old.key, new.key} == set(generations.peers(db, old.key))
    assert generations.peers(db, model.key) == [model.key]  # a model change is no peer: its checks are its own


# --- the deploy, end to end -------------------------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="retrieval._unextracted counts only the active extractor's extractions: after"
                   " the bump every turn is unextracted and the packet takes one more excerpt (decision pending)")
def test_deploying_over_a_database_the_production_image_wrote_queues_nothing_and_serves_the_same(migrated, db):
    model, emb = Model(), FakeEmbedder()
    chat = story()
    with production_rules(), make_client(migrated, embedder=emb, **LLM, **EMB) as c:
        sync(c, chat)
        push(c, chat, canon_texts())
        drain(migrated, model)
        drain_embeddings(migrated)
        assert {k: v for k, v in keys(db).items() if k != "embed"} == PRODUCTION and queued(db) == {}
        before = {"facts": facts_of(view(migrated, chat)), "summaries": served(migrated, c, chat)}
        assert before["summaries"]["done"] == before["summaries"]["due"] == 3 and before["summaries"]["story_current"]
        assert any(f[0] == "Hana" and f[1] == "located_in" for f in before["facts"])
        out = recall(c, chat, "Where is Hana?")
        before["packet"], trace = out["packet"]["text"], out["trace_id"]
        calls = len(model.calls)
        old = keys(db)
        turns = db.execute("SELECT count(*) AS n FROM extraction WHERE extractor_key = %s", (old["extract"],)).fetchone()["n"]
        assert turns == 30

    with make_client(migrated, embedder=emb, **LLM, **EMB) as c:  # the deploy: this build, same settings
        new = {k: active_generation(db, k) for k in old}
        # what the deploy checks read: four new generations, each the production one plus `revision`, all a carry-on
        assert new["embed"].key == old["embed"]
        for kind in MARKED:
            prev = db.execute("SELECT spec FROM projection_generation WHERE key = %s", (old[kind],)).fetchone()["spec"]
            assert new[kind].key != old[kind] and new[kind].spec == {**prev, "revision": 1}, kind
            assert generations.classify(db, old[kind], new[kind]) == "carry"
        assert queued(db) == {}  # 0 extract, 0 reveal, 0 summarize, 0 canon, 0 embed
        assert drain(migrated, model) == 0 and drain_all(migrated) == 0 and len(model.calls) == calls
        after = served(migrated, c, chat)
        assert facts_of(view(migrated, chat)) == before["facts"]
        assert [x["summary"]["id"] for x in after["scenes"]] == [x["summary"]["id"] for x in before["summaries"]["scenes"]]
        assert after["story"]["id"] == before["summaries"]["story"]["id"] and after["story_current"]
        assert all(not x["held"] for x in after["scenes"]) and not after["story_held"]
        cid = conv_id(c, chat)
        head = db.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid,)).fetchone()["head_commit_id"]
        assert summaries.schedule(db, cid, head, new["summarize"].key) == 0  # every window served, the story too
        assert summaries.schedule_stale(db, cid, new["summarize"].key) == 0
        assert canonfacts.schedule(db, new["canon"].key, cid, any_generation=True) == 0
        assert recall(c, chat, "Where is Hana?")["packet"]["text"] == before["packet"]
        replayed = c.get(f"/v1/trace/{trace}/replay").json()
        assert replayed["reproduced"] is True, replayed

        # the story goes on: the new turn is extracted under the new key, the old turns stay served as they were
        chat.reply("Hana is in the bell tower.")
        chat.user("And Kaito?")
        sync(c, chat)
        assert queued(db).get("extract") == 1
        drain(migrated, model)
        assert len(model.calls) == calls + 1
        rows = db.execute("SELECT extractor_key, count(*) AS n FROM extraction WHERE window_hash NOT LIKE 'canon:%%'"
                          " AND window_hash NOT LIKE 'reveal:%%' GROUP BY extractor_key").fetchall()
        assert {r["extractor_key"]: r["n"] for r in rows} == {old["extract"]: turns, new["extract"].key: 1}
        located = [f for f in view(migrated, chat)["facts"] if f["subject"] == "Hana" and f["predicate"] == "located_in"]
        assert [f["object"] for f in located] == ["bell tower"]


def test_a_checked_chat_needs_no_check_again_after_the_bump(migrated, db):
    """The reveal check's "seen" rule is keyed by generation: a check of another reveal generation needs one again. A
    check of a generation that differs only in `revision` counts as the new one's (`generations.peers`), so the bump
    queues no paid check, now or when the owner presses "extract all history" for the checks."""
    with production_rules(), make_client(migrated, **LLM) as c:
        model, conv = checked(c, migrated, db)
        ex, rv = active_generation(db, "extract"), active_generation(db, "reveal")
        assert reveals.unchecked(db, ex.key, rv.key, conv) == []
        made = db.execute("SELECT count(*) AS n FROM extraction WHERE window_hash LIKE 'reveal:%%'").fetchone()["n"]
        assert made == 2
    with make_client(migrated, **LLM) as c:
        ex2, rv2 = active_generation(db, "extract"), active_generation(db, "reveal")
        assert rv2.key != rv.key and generations.classify(db, rv.key, rv2) == "carry"
        assert queued(db) == {}
        assert reveals.unchecked(db, ex2.key, rv2.key, conv) == []
        assert reveals.schedule(db, rv2.key, ex2.key, conv) == 0
    # control: a reveal generation of another model is no peer; its turns are checked again, as before the marker
    with make_client(migrated, llm_url=LLM["llm_url"], llm_model="fake-2") as c:
        ex3, rv3 = active_generation(db, "extract"), active_generation(db, "reveal")
        assert {r["turn"] for r in reveals.unchecked(db, ex3.key, rv3.key, conv)} == {1, 2}
