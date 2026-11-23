"""extract-v19's switch (PHASE-60 S7, acceptance A2; ADR 0086 item 6, ADR 0081 item 4): extract-v19 joins
`generations.ADDS`, so a change among extract-v16, -v18 and -v19 whose specs differ only in the compiler and its prompt
is `adds` in both directions and queues only turns no generation serves. Synthetic names only."""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from conftest import active_generation, make_client
from nmos_sidecar import extraction as X, generations
from nmos_sidecar.config import Settings
from nmos_sidecar.facts import memory_view
from test_extract_v18 import WARM, WARMER, chat_of, complete, feelings_of, queued_extract
from test_extraction import drain
from test_generations import LLM, conv_id
from test_phase60_pins import BASE, PINNED_EXTRACT_SPEC_FIELDS
from test_sidecar_integration import sync

CALM = "창밖으로 비가 그쳤다."


def extractor(compiler: str, **overrides) -> generations.Generation:
    return X.extractor(Settings(**(LLM | overrides), extract_compiler=compiler))


def read_by(db) -> dict[str, int]:
    """How many kept extraction rows each compiler wrote: which generation read which turns."""
    rows = db.execute("SELECT compiler_version AS c, count(*) AS n FROM extraction WHERE discarded_at IS NULL"
                      " GROUP BY 1").fetchall()
    return {r["c"]: r["n"] for r in rows}


def facts_of(url: str, client, chat) -> list[dict]:
    with psycopg.connect(url, row_factory=dict_row) as conn:
        head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s",
                            (conv_id(client, chat),)).fetchone()["head_commit_id"]
        return memory_view(conn, head, active_generation(conn, "extract").key)["facts"]


def more(chat, reply: str) -> None:
    """One more turn, and the next user message that makes it (and the turn before it) eligible."""
    chat.user("장면 더.")
    chat.reply(reply)
    chat.user("다음.")


def test_a_switch_between_v19_and_v16_or_v18_is_classified_adds(migrated, db):
    with make_client(migrated, **LLM):
        pass
    v16 = active_generation(db, "extract").key
    assert v16 == extractor("extract-v16").key
    v17, v18, v19 = extractor("extract-v17"), extractor("extract-v18"), extractor("extract-v19")
    other = {"llm_url": "http://other/v1", "llm_model": "fake-9"}

    assert generations.classify(db, v16, v19) == "adds"
    assert generations.classify(db, v16, extractor("extract-v19", **other)) == "model"
    assert generations.classify(db, v16, extractor("extract-v19", llm_model="fake-9")) == "model"
    assert generations.classify(db, v16, extractor("extract-v19", llm_url="http://other/v1")) == "model"
    assert generations.classify(db, v16, extractor("extract-v19", extract_turns=2)) == "version"

    generations.activate(db, v19)
    assert generations.classify(db, v19.key, extractor("extract-v16")) == "adds"  # and back
    assert generations.classify(db, v19.key, v18) == "adds"
    assert generations.classify(db, v19.key, extractor("extract-v16", **other)) == "model"
    assert generations.classify(db, v19.key, extractor("extract-v18", llm_url="http://other/v1")) == "model"
    assert generations.classify(db, v19.key, v17) == "version"  # extract-v17 is not one of ADDS
    assert generations.classify(db, v19.key, extractor("extract-v18", extract_turns=2)) == "version"

    generations.activate(db, v18)
    assert generations.classify(db, v18.key, v19) == "adds"
    assert generations.classify(db, v18.key, extractor("extract-v19", **other)) == "model"
    assert generations.classify(db, v18.key, extractor("extract-v19", llm_model="fake-9")) == "model"
    assert generations.classify(db, v18.key, extractor("extract-v19", extract_turns=2)) == "version"

    generations.activate(db, v17)
    assert generations.classify(db, v17.key, v19) == "version"

    turns = extractor("extract-v19", extract_turns=2)
    generations.activate(db, turns)
    assert generations.classify(db, turns.key, v19) == "version"  # a setting the key hashes, back again


def test_v19s_spec_differs_from_v16s_and_v18s_in_the_compiler_and_its_prompt_alone():
    spec = {c: X.extractor(Settings(**BASE, extract_compiler=c)).spec
            for c in ("extract-v16", "extract-v18", "extract-v19")}
    v16, v18, v19 = spec["extract-v16"], spec["extract-v18"], spec["extract-v19"]
    assert sorted(v19) == sorted(v18) == sorted(v16) == PINNED_EXTRACT_SPEC_FIELDS["extract-v18"]
    assert {k for k in v18 if v18[k] != v19[k]} == {"compiler", "prompt"}
    assert {k for k in v16 if v16[k] != v19[k]} == {"compiler", "prompt"}
    assert set(generations.ADDS_FIELDS) == {"compiler", "prompt"}
    assert {"extract-v16", "extract-v18", "extract-v19"} <= generations.ADDS


def test_switching_among_v16_v18_and_v19_on_a_covered_chat_queues_nothing(migrated, db):
    chat = chat_of(WARM, CALM)
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        sync(c, chat)
        drain(migrated, complete)
        before = facts_of(migrated, c, chat)
    assert before and read_by(db) == {"extract-v16": 2}  # every turn the chat has is served
    for compiler in ("extract-v19", "extract-v18", "extract-v19", "extract-v16"):
        with make_client(migrated, **LLM, extract_backfill=100, extract_compiler=compiler) as c:
            assert active_generation(db, "extract").key == extractor(compiler).key
            assert queued_extract(db) == 0, compiler
            assert facts_of(migrated, c, chat) == before, compiler
    assert read_by(db) == {"extract-v16": 2}


def test_the_production_chain_v16_then_v18_then_v19_queues_nothing(migrated, db):
    """What the copy check C1 meets: turns read by extract-v16, later turns by extract-v18, then extract-v19."""
    chat = chat_of(WARM, CALM)
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        sync(c, chat)
        drain(migrated, complete)
    assert read_by(db) == {"extract-v16": 2}
    with make_client(migrated, **LLM, extract_backfill=100, extract_compiler="extract-v18") as c:
        assert queued_extract(db) == 0
        more(chat, WARMER)
        sync(c, chat)
        assert queued_extract(db) == 2  # the earlier last turn and the new one
        drain(migrated, complete)
        before = facts_of(migrated, c, chat)
    assert read_by(db) == {"extract-v16": 2, "extract-v18": 2}
    [f] = [f for f in before if f["predicate"] == "feels_toward"]
    assert f["feeling"]["intensity"] == "strong" and "feeling" not in f["history"][0]  # a v18 row over a v16 one
    with make_client(migrated, **LLM, extract_backfill=100, extract_compiler="extract-v19") as c:
        assert active_generation(db, "extract").key == extractor("extract-v19").key
        assert queued_extract(db) == 0
        assert facts_of(migrated, c, chat) == before
    assert read_by(db) == {"extract-v16": 2, "extract-v18": 2}


def test_a_partial_chat_queues_only_its_unserved_turns_and_back_to_v18_queues_nothing(migrated, db):
    chat = chat_of(WARM)
    with make_client(migrated, **LLM, extract_backfill=100, extract_compiler="extract-v18") as c:
        sync(c, chat)
        drain(migrated, complete)
    assert read_by(db) == {"extract-v18": 1}
    with make_client(migrated) as c:  # no extraction model: the new turns stay unread
        more(chat, WARMER)
        sync(c, chat)
    assert queued_extract(db) == 0
    with make_client(migrated, **LLM, extract_backfill=100, extract_compiler="extract-v19") as c:
        assert queued_extract(db) == 2  # the two turns no generation serves, no turn extract-v18 read
        drain(migrated, complete)
        [f] = feelings_of(migrated, c, chat)
    assert read_by(db) == {"extract-v18": 1, "extract-v19": 2}
    assert f["feeling"]["intensity"] == "strong" and f["history"][0]["feeling"]["intensity"] == "clear"
    with make_client(migrated, **LLM, extract_backfill=100, extract_compiler="extract-v18") as c:
        assert queued_extract(db) == 0
        assert feelings_of(migrated, c, chat) == [f]  # the turn only extract-v19 read is still served by it
    assert read_by(db) == {"extract-v18": 1, "extract-v19": 2}
