"""ADR 0008: one extraction per turn, with the turn's messages as target and previous turns as context."""

from __future__ import annotations

from conftest import active_generation, make_client
from nmos_sidecar.facts import fact_versions
from simchat import SimChat
from test_extraction import drain, fake_complete, facts, filler
from test_generations import LLM
from test_sidecar_integration import sync


def recording():
    prompts: list[str] = []

    def complete(system: str, user: str):
        prompts.append(user)
        return fake_complete(system, user)
    return prompts, complete


def test_turn_is_extracted_once_with_user_message_and_reply(migrated, db):
    prompts, complete = recording()
    with make_client(migrated, **LLM) as c:
        chat = SimChat()
        chat.reply("Welcome to the village.")
        chat.user("I walk to the chapel.")
        chat.reply("Hinata is in the old chapel.")
        chat.user("I say hello.")
        sync(c, chat)
        drain(migrated, complete)
        assert len(prompts) == 2  # greeting (turn 0) and the first exchange (turn 1), not four messages
        prompt = next(p for p in prompts if "TARGET turn 1:" in p)
        target = prompt.split("TARGET turn 1:", 1)[1]
        assert "USER: I walk to the chapel." in target and "CHARACTER: Hinata is in the old chapel." in target
        assert "[turn 0] CHARACTER: Welcome to the village." in prompt.split("TARGET", 1)[0]
        assert [(f["object"], f["turn"]) for f in facts(c, chat)] == [("old chapel", 1)]
    # Provenance reaches every member of the turn (invariant 10).
    rows = db.execute("SELECT members, coverage FROM extraction ORDER BY cardinality(members)").fetchall()
    assert [(len(r["members"]), r["coverage"]["target_messages"]) for r in rows] == [(1, 1), (2, 2)]


def test_turn_waits_for_the_user_to_continue(migrated, db):
    with make_client(migrated, **LLM) as c:
        chat = SimChat()
        chat.user("Hinata is in the old chapel.")
        sync(c, chat)
        chat.reply("Quiet.")
        sync(c, chat)
        assert db.execute("SELECT count(*) AS n FROM job").fetchone()["n"] == 0  # reply still provisional (D5)
        chat.reroll("Silent.")
        sync(c, chat)
        chat.user("Next.")
        sync(c, chat)
        assert db.execute("SELECT count(*) AS n FROM job WHERE kind = 'extract'").fetchone()["n"] == 1


def test_second_reply_moves_the_anchor_and_the_turn_is_extracted_as_a_whole(migrated, db):
    prompts, complete = recording()
    with make_client(migrated, **LLM) as c:
        chat = SimChat()
        chat.user("Go on.")
        chat.reply("Hinata is in the old chapel.")
        sync(c, chat)
        chat.reply("Mina is in the kitchen.")  # a second reply to the same input
        chat.user("And then?")
        sync(c, chat)
        drain(migrated, complete)
        assert len(prompts) == 1 and "Mina is in the kitchen." in prompts[0].split("TARGET", 1)[1]
        assert sorted(f["subject"] for f in facts(c, chat)) == ["Hinata", "Mina"]


def test_facts_of_a_per_message_generation_stay_readable(migrated, db):
    """A generation compiled before turns (message window hash) keeps its facts while it is active, e.g.
    with extraction switched off after the upgrade."""
    with make_client(migrated) as c:
        chat = SimChat()
        chat.user("Hinata is in the old chapel.")
        chat.reply("ok")
        filler(chat, 2)
        chat.user("last")
        sync(c, chat)
    member = db.execute("SELECT am.commit_id, am.source_revision_id, am.window_hash FROM active_membership am"
                        " WHERE am.position = 0").fetchone()
    db.execute("INSERT INTO projection_generation (key, kind, model, endpoint, spec)"
               " VALUES ('extract-legacy', 'extract', 'm', 'http://x', '{}')")
    db.execute("INSERT INTO extraction (id, source_revision_id, window_hash, compiler_version, extractor_key, model, raw)"
               " VALUES (gen_random_uuid(), %s, %s, 'extract-v3', 'extract-legacy', 'm', '{}')",
               (member["source_revision_id"], member["window_hash"]))
    db.execute("INSERT INTO assertion (extraction_id, source_revision_id, subject, predicate, object, status)"
               " SELECT id, source_revision_id, 'Hinata', 'located_in', 'old chapel', 'valid' FROM extraction")
    current = fact_versions(db, member["commit_id"], "extract-legacy")
    assert [(f["object"], f["position"], f["turn"]) for f in current] == [("old chapel", 0, 0)]


def test_first_sight_backfill_counts_turns(migrated, db):
    with make_client(migrated, extract_backfill=3, **LLM) as c:
        chat = SimChat()
        filler(chat, 8)
        chat.user("last")
        sync(c, chat)
    jobs = db.execute("SELECT count(*) AS n FROM job WHERE kind = 'extract'").fetchone()["n"]
    assert jobs == 3  # the latest three of eight complete turns, not three messages
    gen = active_generation(db, "extract")
    assert gen.spec["unit"] == "turn" and gen.spec["context_turns"] == 3 and "window" not in gen.spec
