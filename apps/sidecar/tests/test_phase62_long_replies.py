"""PHASE-62 (ADR 0090): the cap on each message the extraction model is shown, as a setting.

At the default nothing moves (the pins of Phases 60 and 61 run unchanged; the ones here pin 24,000). Another cap is
another extract, reveal and summarize generation whose activation queues nothing; "read the cut turns again" reads
whole what an earlier cap cut. Stub models only; synthetic names only."""

from __future__ import annotations

import dataclasses
import re

import psycopg
import pytest
from psycopg.rows import dict_row

from base_rules import base_rules  # noqa: F401 -- autouse: the base's keys, without the revision marker (PHASE-66 part 5)
from conftest import active_generation, make_client
from nmos_sidecar import canonfacts, extraction, generations, readmodel, reveals, summaries
from nmos_sidecar.config import Settings
from nmos_sidecar.worker import run_once
from simchat import SimChat
from test_generations import LLM, conv_id
from test_phase57_carry_on import gen_or_none, queued
from test_phase61_pins import BASE, PINNED
from test_sidecar_integration import recall, sync

CAP = 24000
FILLER = "The rain kept falling on the harbor wall. "
TAIL = "Mira has the lantern."
SPOKEN = '"We leave at dawn," Mira said.'

# Computed at this phase's build for BASE with the cap at 24,000. Literal strings, never recomputed.
PINNED_24K = {
    "extract-v16": "extract-0e662ad0cbd5cccc00c0e223336acacc",
    "extract-v19": "extract-f0b18e8aea5008b379c9293c3db5513d",
    "reveal": "reveal-ea2583f47a7f34a61cd8042b39c8db75",
    "summarize": "summarize-cb68202a894cbe59cf86ed9794ec370f",
}


def long_text(chars: int = 9000) -> str:
    """A reply whose last sentences, a fact and a quoted line, lie past character 6,000."""
    return (FILLER * (chars // len(FILLER) + 1))[:chars].rstrip() + " " + SPOKEN + " " + TAIL


def long_chat(turns: int = 3) -> SimChat:
    chat = SimChat()
    for i in range(turns):
        chat.user(f"Turn {i} begins.")
        chat.reply(long_text())
    return chat


def packet_of(c, chat: SimChat) -> str:
    """The packet a request about the lantern gets, apart from the trace it recorded."""
    return recall(c, chat, "Where is Mira's lantern now?", budget=2000)["packet"]["text"]


def builders(**overrides) -> dict[str, generations.Generation]:
    s = Settings(**(BASE | overrides))
    return {"extract": extraction.extractor(s), "reveal": reveals.generation(s), "summarize": summaries.summarizer(s),
            "canon": canonfacts.generation(s)}


def diff(a: dict, b: dict) -> set[str]:
    return {k for k in a.keys() | b.keys() if a.get(k, "absent") != b.get(k, "absent")}


# --- the setting and the keys ----------------------------------------------------------------------------------------

def test_the_default_is_the_cap_it_always_was_and_keeps_every_pinned_key(monkeypatch):
    monkeypatch.delenv("NMOS_EXTRACT_TARGET_CHARS", raising=False)
    assert Settings(database_url="x").extract_target_chars == extraction.TARGET_CHARS == summaries.MESSAGE_CHARS == 6000
    monkeypatch.setenv("NMOS_EXTRACT_TARGET_CHARS", "")  # a compose file passes an unset variable as empty
    assert Settings(database_url="x").extract_target_chars == 6000
    explicit = builders(extract_target_chars=6000)
    assert explicit["extract"].key == PINNED[("", True)] and explicit["reveal"].key == PINNED[("reveal", True)]
    assert explicit["summarize"].key == PINNED[("summarize", True)] and explicit["canon"].key == PINNED[("canon", True)]


def test_the_environment_sets_it(monkeypatch):
    monkeypatch.setenv("NMOS_EXTRACT_TARGET_CHARS", "24000")
    assert Settings(database_url="x").extract_target_chars == 24000


@pytest.mark.parametrize("bad", [5999, 36001, 0, -1, True, 6000.5, "24000"])
def test_a_cap_out_of_range_is_refused_at_startup(bad):
    with pytest.raises(ValueError, match="NMOS_EXTRACT_TARGET_CHARS"):
        Settings(database_url="x", extract_target_chars=bad)


def test_another_cap_is_another_generation_differing_in_the_cap_alone():
    base, capped = builders(), builders(extract_target_chars=CAP)
    assert diff(base["extract"].spec, capped["extract"].spec) == {"target_chars"}
    assert diff(base["reveal"].spec, capped["reveal"].spec) == {"target_chars"}
    assert diff(base["summarize"].spec, capped["summarize"].spec) == {"message_chars"}
    assert capped["extract"].spec["target_chars"] == capped["reveal"].spec["target_chars"] == CAP
    assert capped["summarize"].spec["message_chars"] == CAP
    assert base["canon"].key == capped["canon"].key  # canon reads in parts of its own (PART_CHARS)
    assert len({g.key for g in base.values()} | {g.key for k, g in capped.items() if k != "canon"}) == 7


@pytest.mark.parametrize("name", sorted(PINNED_24K))
def test_the_keys_at_24000_are_pinned(name):
    s = Settings(**(BASE | {"extract_target_chars": CAP}))
    made = {"reveal": reveals.generation, "summarize": summaries.summarizer}.get(
        name, lambda x: extraction.extractor(dataclasses.replace(x, extract_compiler=name)))(s)
    assert made.key == PINNED_24K[name]


# --- classify ---------------------------------------------------------------------------------------------------------

def extractor(compiler: str = "", **overrides) -> generations.Generation:
    return extraction.extractor(Settings(**(LLM | overrides), extract_compiler=compiler))


def test_a_change_of_the_cap_alone_reads_in_both_directions(migrated, db):
    with make_client(migrated, **LLM):
        pass
    v16 = active_generation(db, "extract").key
    capped = extractor("extract-v16", extract_target_chars=CAP)
    assert generations.classify(db, v16, capped) == "reads"
    generations.activate(db, capped)
    assert generations.classify(db, capped.key, extractor("extract-v16")) == "reads"  # back: the rollback's first step
    assert generations.classify(db, capped.key, extractor("extract-v16", extract_target_chars=12000)) == "reads"
    assert generations.classify(db, capped.key, capped) == "same"


def test_with_a_compiler_of_adds_it_reads_and_with_the_model_it_is_a_model_change(migrated, db):
    with make_client(migrated, **LLM):
        pass
    v16 = active_generation(db, "extract").key
    assert generations.classify(db, v16, extractor("extract-v19")) == "adds"  # as before
    assert generations.classify(db, v16, extractor("extract-v19", extract_target_chars=CAP)) == "reads"
    assert generations.classify(db, v16, extractor("extract-v16", extract_target_chars=CAP, llm_model="fake-9")) == "model"
    assert generations.classify(db, v16, extractor("extract-v19", extract_target_chars=CAP, llm_model="fake-9")) == "model"
    assert generations.classify(db, v16, extractor("extract-v16", extract_target_chars=CAP,
                                                   llm_extra_body={"reasoning": {"effort": "low"}})) == "model"
    # anything else the key hashes is still a version change, with or without the cap
    assert generations.classify(db, v16, extractor("extract-v16", extract_target_chars=CAP, extract_turns=2)) == "version"
    assert generations.classify(db, v16, extractor("extract-v17", extract_target_chars=CAP)) == "version"
    assert generations.classify(db, v16, extractor("extract-v15", extract_target_chars=CAP)) == "version"
    assert generations.classify(db, v16, extractor("extract-v17")) == "version"  # as before


def test_the_summarizer_and_the_reveal_check_classify_the_same_way(migrated, db):
    with make_client(migrated, **LLM):
        pass
    capped = Settings(**LLM, extract_target_chars=CAP)
    for kind, build in (("summarize", summaries.summarizer), ("reveal", reveals.generation)):
        prev = active_generation(db, kind).key
        assert generations.classify(db, prev, build(capped)) == "reads", kind
        assert generations.classify(db, prev, build(dataclasses.replace(capped, llm_model="fake-9"))) == "model", kind
        assert generations.classify(db, prev, build(Settings(**LLM))) == "same", kind
    prev = active_generation(db, "canon").key
    assert generations.classify(db, prev, canonfacts.generation(capped)) == "same"


# --- what is shown to the model --------------------------------------------------------------------------------------

def ctx_of(text: str) -> dict:
    return {"target": {"turn": 3}, "context": [{"turn": 2, "metadata": {"role": "char"}, "content": text}],
            "members": [{"metadata": {"role": "user"}, "content": "Turn 3 begins."},
                        {"metadata": {"role": "char"}, "content": text}]}


def test_every_reader_of_the_target_follows_the_contexts_cap():
    text = long_text()
    assert len(text) > 6000 and text.index(TAIL) > 6000
    plain, capped = ctx_of(text), ctx_of(text) | {"target_chars": CAP}
    assert extraction.target_cap(plain) == 6000 and extraction.target_cap(capped) == CAP
    for build in (extraction.build_prompt, extraction.shown_target, lambda c: "\n".join(extraction._scene(c))):
        assert TAIL not in build(plain) and SPOKEN not in build(plain)
        assert TAIL in build(capped) and SPOKEN in build(capped)
    assert extraction.target_quotes(plain) == [] and extraction.target_quotes(capped) == ["We leave at dawn,"]
    assert extraction.coverage_of(plain) == {"target_chars": 14 + len(text), "target_used": 14 + 6000,
                                             "target_messages": 2, "context_messages": 1, "context_truncated": 1}
    assert extraction.coverage_of(capped) == {"target_chars": 14 + len(text), "target_used": 14 + len(text),
                                              "target_messages": 2, "context_messages": 1, "context_truncated": 1,
                                              "target_cap": CAP}
    # CONTEXT keeps its own cut, whatever the cap
    context = extraction.build_prompt(capped).split("TARGET turn", 1)[0]
    assert TAIL not in context and len(context) < 1200


def test_the_cap_comes_from_the_generation_not_the_settings():
    gen = extraction.extractor(Settings(**LLM, extract_target_chars=CAP))
    assert extraction.with_cap(ctx_of("x"), gen)["target_chars"] == CAP
    old = generations.Generation("extract", "m", "e", {"kind": "extract"}, "extract-old")  # a spec from before the field
    assert extraction.with_cap(ctx_of("x"), old)["target_chars"] == 6000


def test_a_scene_summary_is_shown_each_message_up_to_its_generations_cap():
    rows = [{"turn": 0, "metadata": {"role": "char"}, "content": long_text()}]
    w = summaries.Window(0, 0, 7, (), "k")
    assert TAIL not in summaries.scene_prompt(rows, w) and TAIL in summaries.scene_prompt(rows, w, None, CAP)


# --- through the worker: the evidence check, the switch, the cut turns ----------------------------------------------

class Says:
    """An extraction model that always states the tail's fact, quoting it, whether or not it was shown it."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def __call__(self, system: str, user: str) -> tuple[dict, str]:
        self.prompts.append(user)
        return {"assertions": [{"subject": "Mira", "subject_type": "character", "predicate": "possesses",
                                "object": "lantern", "object_type": "item", "modality": "actual", "source": "narration",
                                "epistemic": "stated", "confidence": 0.9, "evidence": TAIL, "knowledge": "unknown"}]}, "{}"


def scenes(system: str, user: str) -> tuple[dict, str]:
    if system == summaries.STORY_PROMPT:
        return {"summary": "Story."}, "{}"
    return {"summary": "tail seen" if TAIL in user else "tail not seen"}, "{}"


def drain(url: str, model=None, summarize=scenes) -> int:
    model = model or Says()
    n = 0
    with psycopg.connect(url, row_factory=dict_row, autocommit=True) as conn:
        ex, sm = active_generation(conn, "extract"), gen_or_none(conn, "summarize")
        jobs = {"extract": (ex.key, lambda cn, job: extraction.process_extract(cn, job, model, ex, ex.spec["context_turns"]))}
        if sm:
            jobs["summarize"] = (sm.key, lambda cn, job: summaries.process(cn, job, summarize, sm))
        while run_once(conn, jobs):
            n += 1
    return n


def lantern(db) -> list[dict]:
    return db.execute("SELECT a.status, a.reason, x.extractor_key, x.coverage, x.discarded_at FROM assertion a"
                      " JOIN extraction x ON x.id = a.extraction_id WHERE a.predicate = 'possesses' ORDER BY a.id").fetchall()


def test_the_switch_queues_nothing_and_read_the_cut_turns_again_reads_them_whole(migrated, db):
    chat = long_chat(4)  # three turns the user continued from
    with make_client(migrated, **LLM, summaries=False) as c:
        sync(c, chat)
        said = Says()
        assert drain(migrated, said) == 3 and all(TAIL not in p for p in said.prompts)
        cid = conv_id(c, chat)
        before = lantern(db)
        assert [(r["status"], r["reason"]) for r in before] == [("pending", "evidence not in the turn")] * 3
        assert all("target_cap" not in r["coverage"] and r["coverage"]["target_used"] < r["coverage"]["target_chars"]
                   for r in before)
        assert c.get(f"/v1/conversations/{cid}/cut-turns").json() == {"cap": 6000, "extract": {
            "turns": 0, "pending": 0, "failed": 0, "characters": 0, "input_tokens": [0, 0]}}
        assert "has-cut" not in c.get(f"/v1/inspector/c/{cid}").json()["html"]
        old_key = active_generation(db, "extract").key
        rows = db.execute("SELECT count(*) AS n FROM extraction").fetchone()["n"]
        packet = packet_of(c, chat)
        assert "lantern" in packet  # not an empty comparison

    with make_client(migrated, **LLM, summaries=False, extract_target_chars=CAP) as c:
        assert queued(db) == {}  # the switch: nothing queued, nothing changed
        gen = active_generation(db, "extract")
        assert gen.key != old_key and gen.spec["target_chars"] == CAP
        assert db.execute("SELECT count(*) AS n FROM extraction").fetchone()["n"] == rows
        assert drain(migrated) == 0
        assert packet_of(c, chat) == packet  # the same memory until a turn is read at the new cap
        view = c.get(f"/v1/conversations/{cid}/cut-turns").json()
        assert view["cap"] == CAP and view["extract"]["turns"] == 3 and view["extract"]["pending"] == 0
        more = sum(r["coverage"]["target_chars"] - r["coverage"]["target_used"] for r in before)
        assert view["extract"]["characters"] == more
        low, high = view["extract"]["input_tokens"]
        assert 0 < low < high
        page = c.get(f"/v1/inspector/c/{cid}").json()["html"]
        assert 'class="has-cut"' in page and "24,000" in page  # the note and the cap in the facts row
        # the member whose turn an earlier cap read shows what that extraction read, not the cap now
        head = db.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid,)).fetchone()["head_commit_id"]
        assert {m["extracted_chars"] for m in readmodel.membership(db, head, old_key) if m["role"] == "char"
                and m["extracted_chars"] is not None} == {6000}

        out = c.post(f"/v1/conversations/{cid}/read-cut", json={}).json()
        assert out["queued"] == {"extract": 3} and queued(db) == {"extract": 3}
        pending = c.get(f"/v1/conversations/{cid}/cut-turns").json()["extract"]
        assert pending["turns"] == 0 and pending["pending"] == 3
        assert c.post(f"/v1/conversations/{cid}/read-cut", json={}).json()["queued"] == {"extract": 0}  # a second press
        said = Says()
        assert drain(migrated, said) == 3 and all(TAIL in p for p in said.prompts)
        after = lantern(db)
        new = [r for r in after if r["extractor_key"] == gen.key]
        assert [(r["status"], r["reason"]) for r in new] == [("valid", None)] * 3  # the evidence is in what was shown
        assert all(r["coverage"]["target_cap"] == CAP and r["coverage"]["target_used"] == r["coverage"]["target_chars"]
                   for r in new)
        assert all(r["discarded_at"] is None for r in after) and len(after) == 6  # the earlier readings stay
        done = c.get(f"/v1/conversations/{cid}/cut-turns").json()["extract"]
        assert done["turns"] == done["pending"] == 0 and "has-cut" not in c.get(f"/v1/inspector/c/{cid}").json()["html"]
        assert c.post(f"/v1/conversations/{cid}/read-cut", json={}).json()["queued"] == {"extract": 0}
        assert {m["extracted_chars"] for m in readmodel.membership(db, head, gen.key) if m["role"] == "char"
                and m["extracted_chars"] is not None} == {len(long_text())}

        # a turn that comes due after the switch is read at the new cap
        chat.user("Turn 4 begins.")
        chat.reply(long_text())
        sync(c, chat)
        said = Says()
        assert drain(migrated, said) == 1 and TAIL in said.prompts[0]

    with make_client(migrated, **LLM, summaries=False) as c:  # back to the default: nothing queued either
        assert queued(db) == {} and active_generation(db, "extract").key == old_key
        assert c.get(f"/v1/conversations/{cid}/cut-turns").json()["extract"]["turns"] == 0
        assert db.execute("SELECT count(*) AS n FROM extraction WHERE discarded_at IS NULL").fetchone()["n"] == rows + 4


def test_read_the_cut_turns_again_needs_extraction_and_a_known_chat(migrated, db):
    chat = long_chat(2)
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        cid = conv_id(c, chat)
        assert c.get("/v1/conversations/00000000-0000-0000-0000-000000000000/cut-turns").status_code == 404
        assert c.post("/v1/conversations/00000000-0000-0000-0000-000000000000/read-cut", json={}).status_code == 404
    with make_client(migrated) as c:
        assert c.post(f"/v1/conversations/{cid}/read-cut", json={}).status_code == 409
        assert c.get(f"/v1/conversations/{cid}/cut-turns").json() == {"cap": 6000}


def test_scene_summaries_follow_the_cap_and_the_switch_writes_none_again(migrated, db):
    chat = long_chat(13)  # one window of 8 turns is due
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        drain(migrated)
        cid = conv_id(c, chat)
        first = db.execute("SELECT text, coverage, generation FROM summary WHERE level = 'scene'").fetchall()
        assert [r["text"] for r in first] == ["tail not seen"] and "cap" not in first[0]["coverage"]
        assert first[0]["coverage"]["used"] < first[0]["coverage"]["chars"]
        assert "summarize" not in c.get(f"/v1/conversations/{cid}/cut-turns").json() or \
            c.get(f"/v1/conversations/{cid}/cut-turns").json()["summarize"]["windows"] == 0

    with make_client(migrated, **LLM, extract_target_chars=CAP) as c:
        assert queued(db) == {}  # no summary, no story, no extraction
        sm = active_generation(db, "summarize")
        assert sm.key != first[0]["generation"] and sm.spec["message_chars"] == CAP
        view = c.get(f"/v1/conversations/{cid}/cut-turns").json()
        assert view["summarize"]["windows"] == 1 and view["summarize"]["characters"] > 0
        assert 0 < view["summarize"]["input_tokens"][0] < view["summarize"]["input_tokens"][1]
        assert 'class="has-cut"' in c.get(f"/v1/inspector/c/{cid}").json()["html"]
        assert "summarize" not in c.post(f"/v1/conversations/{cid}/read-cut", json={}).json()["queued"]  # not asked
        assert queued(db).get("summarize") is None
        out = c.post(f"/v1/conversations/{cid}/read-cut", json={"summaries": True}).json()
        assert out["queued"]["summarize"] == 1
        assert c.post(f"/v1/conversations/{cid}/read-cut", json={"summaries": True}).json()["queued"]["summarize"] == 0
        drain(migrated)
        mine = db.execute("SELECT text, coverage FROM summary WHERE level = 'scene' AND generation = %s"
                          " AND discarded_at IS NULL", (sm.key,)).fetchall()
        assert [r["text"] for r in mine] == ["tail seen"]
        assert mine[0]["coverage"]["cap"] == CAP and mine[0]["coverage"]["used"] == mine[0]["coverage"]["chars"]
        assert db.execute("SELECT count(*) AS n FROM summary WHERE level = 'scene' AND discarded_at IS NULL"
                          ).fetchone()["n"] == 2  # the earlier one stays
        assert c.get(f"/v1/conversations/{cid}/cut-turns").json()["summarize"]["windows"] == 0


def test_a_reveal_check_reads_the_target_at_its_own_generations_cap(migrated, db, monkeypatch):
    seen: list[int] = []
    real = reveals.build_prompt
    monkeypatch.setattr(reveals, "build_prompt", lambda ctx, *a, **k: seen.append(ctx["target_chars"]) or real(ctx, *a, **k))
    monkeypatch.setattr(reveals, "secret_hints",  # **kw: the check also passes a carry link's rows (review F7)
                        lambda ctx, rows, **kw: [{"id": "S1", "turn": 0, "text": "t", "holders": ["A"],
                                                  "kept_from": ["B"], "subject": "A"}])
    chat = long_chat(3)
    with make_client(migrated, **LLM, summaries=False, extract_target_chars=CAP) as c:
        sync(c, chat)
        drain(migrated)
        cid = conv_id(c, chat)
        rv = active_generation(db, "reveal")
        x = db.execute("SELECT x.id, x.source_revision_id, x.window_hash FROM extraction x ORDER BY x.created_at LIMIT 1"
                       ).fetchone()
        job = {"id": 0, "conversation_id": cid, "payload": {
            "generation": rv.key, "extraction_id": str(x["id"]), "revision_id": str(x["source_revision_id"]),
            "window_hash": x["window_hash"]}}
        assert reveals.process(db, job, lambda s, u: ({"secrets": []}, "{}"), rv, 3) == "done"
        assert seen == [CAP]
        check = db.execute("SELECT coverage FROM extraction WHERE extractor_key = %s", (rv.key,)).fetchone()
        assert check["coverage"]["target_cap"] == CAP
