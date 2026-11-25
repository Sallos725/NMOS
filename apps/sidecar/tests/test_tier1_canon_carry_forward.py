"""Owner decision 2026-11-25 on Tier 1 B7: a persona or card text without the name macros that an earlier release read
`plain` keeps that read. It stays served and stays its generation's read (no canon job, no model call) until a read
under the manifest's names exists; a text with no read at all is read under the names. Synthetic names and text only."""

from __future__ import annotations

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from conftest import active_generation, make_client
from nmos_sidecar import canonfacts, normtext
from nmos_sidecar.ids import uuid7
from simchat import SimChat
from test_canon import push
from test_canon_facts import Model, drain, view
from test_generations import LLM
from test_sidecar_integration import sync

COMPILERS = {"canon-v1": "", "canon-v2": "extract-v20"}


def chat_of(name: str) -> SimChat:
    chat = SimChat(name)
    chat.user("We walk to the mill.")
    chat.reply("Hana is in the old mill.")
    chat.user("What does Hana do?")
    return chat


def texts(persona: str = "Taku is a night walker.") -> dict:
    """The card's name, a card field and a persona, none with the name macros."""
    return {"card:name": ("Hana", {"field": "name"}), "card:desc": ("Hana is a lighthouse keeper.", {"field": "desc"}),
            "persona": (persona, {"name": "Taku"})}


def served(url: str, chat: SimChat) -> list[tuple]:
    return sorted((a["canon"], a["subject"], a.get("value")) for a in view(url, chat)["assertions"] if a.get("canon"))


def reads(db: psycopg.Connection, chat: SimChat, key: str | None = None) -> list[dict]:
    return db.execute(
        "SELECT x.id, x.source_revision_id AS rid, x.window_hash, x.extractor_key, x.coverage, x.discarded_at,"
        " so.host_logical_id FROM extraction x JOIN source_revision sr ON sr.id = x.source_revision_id"
        " JOIN source_object so ON so.id = sr.source_object_id JOIN conversation c ON c.id = so.conversation_id"
        " WHERE c.host_chat_ref = %s AND so.source_kind = 'canon' AND (%s::text IS NULL OR so.host_logical_id = %s)"
        " ORDER BY x.id", (chat.id, key and f"canon:{key}", key and f"canon:{key}")).fetchall()


def conv_of(db: psycopg.Connection, chat: SimChat):
    return db.execute("SELECT id FROM conversation WHERE host_chat_ref = %s", (chat.id,)).fetchone()["id"]


def as_released(db: psycopg.Connection, chat: SimChat) -> int:
    """Make the chat's persona and card reads what a release before Tier 1 B7 stored (cdf2c9a): window `plain`, and an
    input fingerprint without the names."""
    n = 0
    for x in reads(db, chat):
        if not (x["host_logical_id"] == "canon:persona" or x["host_logical_id"].startswith("canon:card:")):
            continue
        src = canonfacts._source(db, x["rid"])
        text = canonfacts.named(normtext.get(db, x["rid"])["clean_content"], src["character"], src["user"])
        pieces, _ = canonfacts.parts(text)
        part = int(x["window_hash"].split(":")[1])
        coverage = dict(x["coverage"])
        if "input" in coverage:
            coverage["input"] = canonfacts.input_of({**src, "wtag": "plain"}, pieces[part], part, len(pieces))
        db.execute("UPDATE extraction SET window_hash = %s, coverage = %s WHERE id = %s",
                   (f"canon:{part}:plain", Jsonb(coverage), x["id"]))
        n += 1
    db.commit()
    return n


def nothing_wanted(url: str, conv) -> None:
    with psycopg.connect(url, row_factory=dict_row) as conn:
        key = active_generation(conn, "canon").key
        assert canonfacts.schedule(conn, key, conv) == 0
        assert canonfacts.schedule(conn, key, conv, any_generation=True) == 0
        cov = canonfacts.coverage(conn, key, conv)
        assert cov["read"] == cov["wanted"] == 2 and cov["pending"] == 0


@pytest.mark.parametrize("version", sorted(COMPILERS))
def test_a_plain_read_of_the_persona_and_a_card_field_is_carried_forward(migrated, db, version):
    chat, model = chat_of(f"carry-{version}"), Model()
    with make_client(migrated, **LLM, extract_compiler=COMPILERS[version]) as c:
        sync(c, chat)
        push(c, chat, texts())
        drain(migrated, model)
        assert active_generation(db, "canon").spec["version"] == version
        before, calls = served(migrated, chat), len(model.canon_calls())
        assert calls == 2 and {r[0] for r in before} == {"card:desc", "persona"}
        assert as_released(db, chat) == 2
        assert all(x["window_hash"].endswith(":plain") for x in reads(db, chat))
        assert served(migrated, chat) == before  # still served
        nothing_wanted(migrated, conv_of(db, chat))  # and no canon job queued for it
        push(c, chat, texts())  # a sync again: nothing to read
        drain(migrated, model)
        assert len(model.canon_calls()) == calls
        assert c.get(f"/v1/conversations/{conv_of(db, chat)}/coverage").json()["canon"]["read"] == 2
    # a restart (startup schedules what no generation has read whole) reads nothing either
    with make_client(migrated, **LLM, extract_compiler=COMPILERS[version]):
        drain(migrated, model)
    assert len(model.canon_calls()) == calls and served(migrated, chat) == before


def test_a_pay_once_copy_read_plain_is_carried_forward_too(migrated, db):
    a, b, model = chat_of("carry-copy-a"), chat_of("carry-copy-b"), Model()
    with make_client(migrated, **LLM) as c:
        for chat in (a, b):
            sync(c, chat)
            push(c, chat, texts())
            drain(migrated, model)
        assert len(model.canon_calls()) == 2  # b copied a's reads (PHASE-57 A1)
        assert all(x["coverage"].get("reused_from") for x in reads(db, b))
        before = {chat.id: served(migrated, chat) for chat in (a, b)}
        for chat in (a, b):
            as_released(db, chat)
        for chat in (a, b):
            assert served(migrated, chat) == before[chat.id]
            nothing_wanted(migrated, conv_of(db, chat))
        drain(migrated, model)
        assert len(model.canon_calls()) == 2
        # a third chat with the same texts and names reads under the names (no stored read of its own): one call each
        third = chat_of("carry-copy-c")
        sync(c, third)
        push(c, third, texts())
        drain(migrated, model)
        assert len(model.canon_calls()) == 4
        tag = canonfacts.names_tag([{"key": "card:name", "hash": reads_hash(db, third)},
                                    {"key": "persona", "metadata": {"name": "Taku"}}])
        assert {x["window_hash"] for x in reads(db, third)} == {f"canon:0:{tag}"}


def reads_hash(db: psycopg.Connection, chat: SimChat) -> str:
    return db.execute(
        "SELECT sr.revision_hash FROM source_revision sr JOIN source_object so ON so.id = sr.source_object_id"
        " JOIN conversation c ON c.id = so.conversation_id WHERE c.host_chat_ref = %s"
        " AND so.host_logical_id = 'canon:card:name'", (chat.id,)).fetchone()["revision_hash"]


def test_a_new_text_is_read_under_the_names_beside_a_carried_one(migrated, db):
    chat, model = chat_of("carry-new"), Model()
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        push(c, chat, texts())
        drain(migrated, model)
        as_released(db, chat)
        push(c, chat, texts(persona="Taku is a retired sailor."))  # a new persona text: no read of it yet
        drain(migrated, model)
        calls = model.canon_calls()
        assert len(calls) == 3 and "Taku is a retired sailor." in calls[-1]
        live = [x for x in reads(db, chat) if x["discarded_at"] is None]
        persona = [x["window_hash"] for x in live if x["host_logical_id"] == "canon:persona"]
        desc = [x["window_hash"] for x in live if x["host_logical_id"] == "canon:card:desc"]
        assert desc == ["canon:0:plain"]  # the card field's carried read, untouched
        assert "canon:0:plain" in persona and any(not w.endswith(":plain") for w in persona)
        assert ("persona", "Taku", "retired sailor") in served(migrated, chat)
        assert ("persona", "Taku", "night walker") not in served(migrated, chat)
        assert ("card:desc", "Hana", "lighthouse keeper") in served(migrated, chat)
        nothing_wanted(migrated, conv_of(db, chat))


def plain_copy(db: psycopg.Connection, x: dict, value: str) -> None:
    """Store beside read `x` (under the names) a `plain` read of the same revision, generation and part, saying
    `value`."""
    xid, part = uuid7(), x["window_hash"].split(":")[1]
    db.execute("INSERT INTO extraction (id, source_revision_id, window_hash, compiler_version, extractor_key, model,"
               " raw, coverage, members, hints, usage) SELECT %s, source_revision_id, %s, compiler_version,"
               " extractor_key, model, raw, coverage, members, hints, usage FROM extraction WHERE id = %s",
               (xid, f"canon:{part}:plain", x["id"]))
    cols = ", ".join(c for c in ("subject", "subject_type", "predicate", "object", "object_type", "epistemic",
                                 "confidence", "evidence", "status", "reason", "knowledge", "polarity", "modality",
                                 "source"))
    db.execute(f"INSERT INTO assertion (extraction_id, source_revision_id, value, {cols})"
               f" SELECT %s, source_revision_id, %s, {cols} FROM assertion WHERE extraction_id = %s",
               (xid, value, x["id"]))
    db.commit()


def test_a_read_under_the_names_wins_over_the_carried_one(migrated, db):
    chat, model = chat_of("carry-wins"), Model()
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        push(c, chat, texts())
        drain(migrated, model)
        named = reads(db, chat, "persona")
        assert len(named) == 1 and not named[0]["window_hash"].endswith(":plain")
        plain_copy(db, named[0], "old plain reading")
        got = served(migrated, chat)
        assert ("persona", "Taku", "night walker") in got and ("persona", "Taku", "old plain reading") not in got
        nothing_wanted(migrated, conv_of(db, chat))
        # the read under the names gone (a discarded read): the carried one serves again, and nothing is queued
        db.execute("UPDATE extraction SET discarded_at = now() WHERE id = %s", (named[0]["id"],))
        db.commit()
        got = served(migrated, chat)
        assert ("persona", "Taku", "old plain reading") in got and ("persona", "Taku", "night walker") not in got
        nothing_wanted(migrated, conv_of(db, chat))
        drain(migrated, model)
        assert len(model.canon_calls()) == 2


def test_a_carried_read_stopped_between_parts_goes_on_plain(migrated, db):
    chat, model = chat_of("carry-parts"), Model()
    long = "Taku is a night walker. " + "x" * 5000 + "\n\nTaku is a map maker. " + "y" * 3000
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        push(c, chat, texts(persona=long))
        drain(migrated, model)
        assert len(model.canon_calls()) == 3  # the card field and the persona's two parts
        as_released(db, chat)
        second = [x for x in reads(db, chat, "persona") if x["window_hash"] == "canon:1:plain"]
        assert len(second) == 1
        db.execute("DELETE FROM assertion WHERE extraction_id = %s", (second[0]["id"],))
        db.execute("DELETE FROM extraction WHERE id = %s", (second[0]["id"],))  # a job stopped between parts
        db.commit()
        conv = conv_of(db, chat)
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            key = active_generation(conn, "canon").key
            assert canonfacts.schedule(conn, key, conv) == 1
            conn.commit()
            job = conn.execute("SELECT dedupe_key FROM job WHERE kind = 'canon' AND status = 'queued'"
                               " AND conversation_id = %s", (conv,)).fetchall()
        assert [j["dedupe_key"].split(":")[2] for j in job] == ["plain"]
        drain(migrated, model)
        calls = model.canon_calls()
        assert len(calls) == 4 and "map maker" in calls[-1] and "TEXT (part 2 of 2)" in calls[-1]
        assert sorted(x["window_hash"] for x in reads(db, chat, "persona")) == ["canon:0:plain", "canon:1:plain"]
        assert {("persona", "Taku", "night walker"), ("persona", "Taku", "map maker")} <= set(served(migrated, chat))
        nothing_wanted(migrated, conv)


def test_a_model_change_carries_on_and_a_rollback_serves_its_own_carried_read(migrated, db):
    chat, model = chat_of("carry-switch"), Model()
    with make_client(migrated, **LLM) as c:  # canon-v1
        sync(c, chat)
        push(c, chat, texts())
        drain(migrated, model)
        v1 = active_generation(db, "canon").key
    as_released(db, chat)
    before, conv = served(migrated, chat), conv_of(db, chat)
    # A model change carries on (PHASE-57 A3): the carried read is a read some generation made whole, so nothing is
    # read, and it is served under the new generation (the newest activated one that read it).
    with make_client(migrated, **{**LLM, "llm_model": "fake-2"}):
        m2 = active_generation(db, "canon").key
        assert m2 != v1
        drain(migrated, model)
        assert len(model.canon_calls()) == 2 and served(migrated, chat) == before
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            assert canonfacts.schedule(conn, m2, conv, any_generation=True) == 0
    # A canon version change (canon-v2, PHASE-64) reads the canon in force again, as it did before: under the names,
    # since canon-v2 has no read of its own to carry.
    with make_client(migrated, **LLM, extract_compiler="extract-v20"):
        v2 = active_generation(db, "canon").key
        drain(migrated, model)
        assert len(model.canon_calls()) == 4
        assert {x["window_hash"].endswith(":plain") for x in reads(db, chat) if x["extractor_key"] == v2} == {False}
        assert served(migrated, chat) == before  # the same facts, from canon-v2's reads
    # Back to canon-v1: its carried plain read is its read again, ahead of canon-v2's under the names (the active
    # generation's read first, as always), and nothing is queued.
    with make_client(migrated, **LLM):
        assert active_generation(db, "canon").key == v1
        drain(migrated, model)
        assert len(model.canon_calls()) == 4
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            assert canonfacts.schedule(conn, v1, conv) == 0
            assert canonfacts.schedule(conn, v1, conv, any_generation=True) == 0
            got = conn.execute(canonfacts.ROWS, {"conv": conv, "mid": mid_of(conn, conv), "gen": v1,
                                                 "macro": canonfacts.MACRO_SQL, "at": None}).fetchall()
        assert {r["generation"] for r in got} == {v1}
        assert served(migrated, chat) == before


def mid_of(conn: psycopg.Connection, conv) -> str:
    return conn.execute("SELECT canon_manifest_id FROM conversation WHERE id = %s", (conv,)).fetchone()["canon_manifest_id"]


# The owner's read-only count (item 5 of the decision): carried `plain` reads of a persona or card text without the
# macros, still a generation's read (no read of it under the chat's current names), by whether the names the model was
# shown (`hints` of the read itself, or of the read a Phase 57 copy was copied from) are the chat's names now. `other`
# is the mix-up B7 closes for new reads; `unknown` has no recorded names (the copied-from read is gone, or no hints).
CARRIED_NAMES = """
WITH chats AS (
    SELECT c.id AS conv, m.entries, """ + canonfacts.NAMES_TAG.format(e="m.entries") + """ AS tag,
           (SELECT btrim(sr.content) FROM source_object so JOIN source_revision sr ON sr.source_object_id = so.id
            WHERE so.conversation_id = c.id AND so.host_logical_id = 'canon:card:name' AND so.source_kind = 'canon'
              AND sr.revision_hash = (SELECT y->>'hash' FROM jsonb_array_elements(m.entries) y
                                      WHERE y->>'key' = 'card:name' LIMIT 1)) AS character,
           nullif((SELECT y->'metadata'->>'name' FROM jsonb_array_elements(m.entries) y
                   WHERE y->>'key' = 'persona' LIMIT 1), '') AS usr
    FROM conversation c JOIN canon_manifest m ON m.conversation_id = c.id AND m.id = c.canon_manifest_id
),
carried AS (
    SELECT ch.conv, e->>'key' AS key, x.extractor_key, x.window_hash, ch.character, ch.usr,
           CASE WHEN x.coverage ? 'reused_from' THEN root.hints ELSE x.hints END AS shown
    FROM chats ch CROSS JOIN LATERAL jsonb_array_elements(ch.entries) e
    JOIN source_object so ON so.conversation_id = ch.conv AND so.host_logical_id = 'canon:' || (e->>'key')
                         AND so.source_kind = 'canon'
    JOIN source_revision sr ON sr.source_object_id = so.id AND sr.revision_hash = e->>'hash'
    JOIN extraction x ON x.source_revision_id = sr.id AND x.discarded_at IS NULL
                     AND split_part(x.window_hash, ':', 3) = 'plain'
    LEFT JOIN extraction root ON root.id = (x.coverage->>'reused_from')::uuid
    WHERE (e->>'key' = 'persona' OR (e->>'key' LIKE 'card:%%' AND e->>'key' <> 'card:name'))
      AND NOT coalesce((sr.metadata->>'named')::boolean, sr.content ~* %(macro)s)
      AND NOT EXISTS (SELECT 1 FROM extraction y WHERE y.source_revision_id = sr.id
                        AND y.extractor_key = x.extractor_key AND y.discarded_at IS NULL
                        AND split_part(y.window_hash, ':', 3) = ch.tag)
)
SELECT CASE WHEN shown IS NULL OR NOT shown ? 'character' THEN 'unknown'
            WHEN shown->>'character' IS NOT DISTINCT FROM character AND shown->>'user' IS NOT DISTINCT FROM usr
            THEN 'same' ELSE 'other' END AS names,
       count(DISTINCT (conv, key)) AS texts, count(DISTINCT conv) AS chats, count(*) AS parts
FROM carried GROUP BY 1 ORDER BY 1
"""


def test_the_owner_can_count_carried_reads_shown_other_names(migrated, db):
    chat, model = chat_of("carry-count"), Model()
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        push(c, chat, texts())
        drain(migrated, model)
        as_released(db, chat)
        count = lambda: {r["names"]: (r["texts"], r["chats"], r["parts"])  # noqa: E731
                         for r in db.execute(CARRIED_NAMES, {"macro": canonfacts.MACRO_SQL}).fetchall()}
        assert count() == {"same": (2, 1, 2)}
        # the card renamed: the card field and the persona keep their revisions, so their carried reads still serve,
        # read under the old card name (the mix-up): counted, not read again
        renamed = {**texts(), "card:name": ("Hanna", {"field": "name"})}
        push(c, chat, renamed)
        drain(migrated, model)
        assert len(model.canon_calls()) == 2
        assert ("card:desc", "Hana", "lighthouse keeper") in served(migrated, chat)
        assert count() == {"other": (2, 1, 2)}


# One read per (revision, generation) (review of 47a020a, finding 1): the names read when it is complete (every part
# the text has under the names) or there is no `plain` read, else the carried `plain` one. Never both (duplicate facts),
# never neither: a names read that started and died beside a complete `plain` one (a build with B7 and without the carry
# forward, never deployed, could leave one) took the facts of the parts it had not read.
TWO_PARTS = "Taku is a night walker. " + "x" * 5000 + "\n\nTaku is a map maker. " + "y" * 3000
NAMES_READ = {("persona", "Taku", "night walker"), ("persona", "Taku", "map maker")}
PLAIN_READ = {("persona", "Taku", "plain walker"), ("persona", "Taku", "plain maker")}


def two_parts(migrated: str, db: psycopg.Connection, name: str, model: Model) -> tuple[SimChat, list[dict]]:
    """A chat whose two-part persona (no macros) is read under the names, and a complete `plain` read of it beside."""
    chat = chat_of(name)
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        push(c, chat, texts(persona=TWO_PARTS))
        drain(migrated, model)
    named = sorted(reads(db, chat, "persona"), key=lambda x: x["window_hash"])
    assert [x["window_hash"].split(":")[1] for x in named] == ["0", "1"]
    assert not any(x["window_hash"].endswith(":plain") for x in named)
    for x, value in zip(named, ("plain walker", "plain maker")):
        plain_copy(db, x, value)
    assert len(model.canon_calls()) == 3  # the card field and the persona's two parts
    return chat, named


def drop(db: psycopg.Connection, xs: list[dict]) -> None:
    for x in xs:
        db.execute("DELETE FROM assertion WHERE extraction_id = %s", (x["id"],))
        db.execute("DELETE FROM extraction WHERE id = %s", (x["id"],))
    db.commit()


def died(db: psycopg.Connection, x: dict) -> str:
    """The job that read `x` (under the names) died before its last part; its dedupe key."""
    key = f"canon:{x['rid']}:{x['window_hash'].split(':')[2]}:{x['extractor_key']}"
    assert db.execute("UPDATE job SET status = 'dead' WHERE dedupe_key = %s", (key,)).rowcount == 1
    db.commit()
    return key


def retried(db: psycopg.Connection, key: str) -> None:
    """The owner retries a dead job."""
    db.execute("UPDATE job SET status = 'queued', attempts = 0, run_after = now(), locked_at = NULL"
               " WHERE dedupe_key = %s", (key,))
    db.commit()


def persona(got: list[tuple]) -> set[tuple]:
    return {r for r in got if r[0] == "persona"}


def test_a_complete_plain_read_serves_beside_a_partial_names_read(migrated, db):
    model = Model()
    chat, named = two_parts(migrated, db, "carry-one-partial", model)
    conv = conv_of(db, chat)
    drop(db, named[1:])  # the names read stopped after its first part
    job = died(db, named[0])
    assert persona(served(migrated, chat)) == PLAIN_READ  # nothing vanishes, and nothing is served twice
    nothing_wanted(migrated, conv)
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        key = active_generation(conn, "canon").key
        rid = named[0]["rid"]
        # the read in force is the `plain` one: its window suffix for the worker, the input it fingerprints, coverage
        assert canonfacts._source(conn, rid, key)["wtag"] == "plain"
        cov = canonfacts.coverage(conn, key, conv)
        assert cov["keys"]["persona"] == {"calls": 2, "job": None} and cov["failed"] == 0
    # the dead names job retried by the owner: it reads nothing, as the read in force is complete
    retried(db, job)
    tag = named[0]["window_hash"].split(":")[2]
    drain(migrated, model)
    assert len(model.canon_calls()) == 3
    assert sorted(x["window_hash"].split(":")[1:] for x in reads(db, chat, "persona")) == sorted([
        ["0", "plain"], ["0", tag], ["1", "plain"]])
    assert persona(served(migrated, chat)) == PLAIN_READ


def test_a_complete_names_read_serves_alone_beside_a_plain_one(migrated, db):
    model = Model()
    chat, _ = two_parts(migrated, db, "carry-both-complete", model)
    assert persona(served(migrated, chat)) == NAMES_READ
    nothing_wanted(migrated, conv_of(db, chat))
    drain(migrated, model)
    assert len(model.canon_calls()) == 3


def test_a_partial_names_read_without_a_plain_one_goes_on_under_the_names(migrated, db):
    model = Model()
    chat, named = two_parts(migrated, db, "carry-names-partial", model)
    conv = conv_of(db, chat)
    drop(db, [x for x in reads(db, chat, "persona") if x["window_hash"].endswith(":plain")] + named[1:])
    job = died(db, named[0])
    assert persona(served(migrated, chat)) == {("persona", "Taku", "night walker")}  # as before the review
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        key = active_generation(conn, "canon").key
        assert canonfacts.schedule(conn, key, conv) == 0  # a dead job waits for the owner, as before
        cov = canonfacts.coverage(conn, key, conv)
        assert cov["keys"]["persona"] == {"calls": 1, "job": "dead"} and cov["failed"] == 1
    retried(db, job)
    drain(migrated, model)
    calls = model.canon_calls()
    assert len(calls) == 4 and "TEXT (part 2 of 2)" in calls[-1]
    assert persona(served(migrated, chat)) == NAMES_READ
    nothing_wanted(migrated, conv)


def test_a_partial_plain_read_beside_a_partial_names_read_goes_on_plain(migrated, db):
    model = Model()
    chat, named = two_parts(migrated, db, "carry-both-partial", model)
    conv = conv_of(db, chat)
    plain = sorted((x for x in reads(db, chat, "persona") if x["window_hash"].endswith(":plain")),
                   key=lambda x: x["window_hash"])
    drop(db, [plain[1], named[1]])  # each stopped after its first part
    died(db, named[0])
    assert persona(served(migrated, chat)) == {("persona", "Taku", "plain walker")}
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        key = active_generation(conn, "canon").key
        assert canonfacts.schedule(conn, key, conv) == 1
        conn.commit()
        jobs = conn.execute("SELECT dedupe_key FROM job WHERE kind = 'canon' AND status = 'queued'"
                            " AND conversation_id = %s", (conv,)).fetchall()
    assert [j["dedupe_key"].split(":")[2] for j in jobs] == ["plain"]
    drain(migrated, model)
    calls = model.canon_calls()
    assert len(calls) == 4 and "TEXT (part 2 of 2)" in calls[-1]
    assert persona(served(migrated, chat)) == {("persona", "Taku", "plain walker"), ("persona", "Taku", "map maker")}
    nothing_wanted(migrated, conv)
