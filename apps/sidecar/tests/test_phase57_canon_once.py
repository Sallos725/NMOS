"""PHASE-57 A1 (ADR 0079): a canon part read once for every chat that sends the model the same input, copied into
each chat; a rebuild reads its own chat again."""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from conftest import make_client
from simchat import SimChat
from test_canon import push
from test_canon_facts import CARD, Model, canon_texts, drain, view
from test_generations import LLM
from test_sidecar_integration import recall, sync


def chat_of(name: str) -> SimChat:
    chat = SimChat(name)
    chat.user("We walk to the mill.")
    chat.reply("Hana is in the old mill.")
    chat.user("What does Hana do?")
    return chat


def canon_rows(url: str, chat: SimChat) -> list[tuple]:
    v = view(url, chat)
    return sorted((a["subject"], a["predicate"], a.get("object"), a.get("value"))
                  for a in v["assertions"] if a.get("canon"))


def extractions(db, chat: SimChat) -> list[dict]:
    return db.execute(
        "SELECT x.id, x.window_hash, x.coverage, x.raw, x.discarded_at FROM extraction x"
        " JOIN source_revision sr ON sr.id = x.source_revision_id JOIN source_object so ON so.id = sr.source_object_id"
        " JOIN conversation c ON c.id = so.conversation_id WHERE c.host_chat_ref = %s AND so.source_kind = 'canon'"
        " ORDER BY x.id", (chat.id,)).fetchall()


def cid_of(db, chat: SimChat):
    return db.execute("SELECT id FROM conversation WHERE host_chat_ref = %s", (chat.id,)).fetchone()["id"]


def test_a_second_chat_of_the_same_bot_reads_its_canon_without_a_call(migrated, db):
    a, b, model = chat_of("bot-a"), chat_of("bot-b"), Model()
    with make_client(migrated, **LLM) as c:
        sync(c, a)
        push(c, a, canon_texts())
        drain(migrated, model)
        assert len(model.canon_calls()) == 2  # the card's description and the persona
        sync(c, b)
        push(c, b, canon_texts())
        drain(migrated, model)
        assert len(model.canon_calls()) == 2  # none for the second chat
        assert canon_rows(migrated, b) == canon_rows(migrated, a) != []
        copies = extractions(db, b)
        assert len(copies) == 2 and all(x["coverage"].get("reused_from") for x in copies)
        assert {x["raw"]["reused_from"] for x in copies} == {str(x["id"]) for x in extractions(db, a)}
        cov = c.get(f"/v1/conversations/{cid_of(db, b)}/coverage").json()["canon"]
        assert cov["reused"] == 2 and cov["read"] == cov["wanted"] == 2
        usage = db.execute("SELECT usage FROM extraction WHERE id = ANY(%s)", ([x["id"] for x in copies],)).fetchall()
        assert {u["usage"]["calls"] for u in usage} == {0}  # no model call is counted for a copy


def test_another_persona_reads_the_macro_texts_again_and_copies_the_plain_ones(migrated):
    a, b, model = chat_of("persona-a"), chat_of("persona-b"), Model()
    other = {**canon_texts(), "persona": ("{{user}} is a traveler.", {"name": "Yuki"})}
    with make_client(migrated, **LLM) as c:
        for chat, texts in ((a, canon_texts()), (b, other)):
            sync(c, chat)
            out = push(c, chat, texts)
            drain(migrated, model)
            recall(c, chat, "Where is Kaito?", canon_manifest_id=out["manifest_id"], canon_held=["lore:kaito"])
            drain(migrated, model)
        calls = model.canon_calls()
        # chat a: description, persona, Kaito's entry; chat b: description and persona again (their names
        # differ), Kaito's entry ("Kaito is a squire.", no macro) copied
        assert len(calls) == 5 and sum("Kaito is a squire." in u for u in calls) == 1
        assert "USER: Yuki" in calls[3] and "USER: Yuki" in calls[4]


def test_the_same_text_described_otherwise_is_read_again(migrated):
    a, b, model = chat_of("desc-a"), chat_of("desc-b"), Model()
    moved = {**canon_texts(), "lore:kaito": ("Kaito is a squire.", {"keys": ["Kaito", "squire"], "scope": "character",
                                                                    "mode": "normal"})}
    with make_client(migrated, **LLM) as c:
        for chat, texts in ((a, canon_texts()), (b, moved)):
            sync(c, chat)
            out = push(c, chat, texts)
            recall(c, chat, "Where is Kaito?", canon_manifest_id=out["manifest_id"], canon_held=["lore:kaito"])
            drain(migrated, model)
        assert sum("Kaito is a squire." in u for u in model.canon_calls()) == 2  # its keys are in the prompt


def test_a_rebuild_reads_its_own_chat_again_and_leaves_the_other(migrated, db):
    a, b, model = chat_of("rebuild-a"), chat_of("rebuild-b"), Model()
    with make_client(migrated, **LLM) as c:
        for chat in (a, b):
            sync(c, chat)
            push(c, chat, canon_texts())
            drain(migrated, model)
        before_a = extractions(db, a)
        out = c.post(f"/v1/conversations/{cid_of(db, b)}/rebuild").json()
        assert out["queued"]["canon"] == 2
        drain(migrated, model)
        assert len(model.canon_calls()) == 4  # chat b called the model for its own canon
        assert extractions(db, a) == before_a  # chat a's rows are as they were
        fresh = [x for x in extractions(db, b) if x["discarded_at"] is None]
        assert len(fresh) == 2 and not any(x["coverage"].get("reused_from") for x in fresh)
        # a third chat copies the newest read: chat b's fresh one
        third = chat_of("rebuild-c")
        sync(c, third)
        push(c, third, canon_texts())
        drain(migrated, model)
        assert len(model.canon_calls()) == 4
        assert {x["coverage"]["reused_from"] for x in extractions(db, third)} == {str(x["id"]) for x in fresh}


def test_a_discarded_read_is_no_source(migrated, db):
    a, b, model = chat_of("discard-a"), chat_of("discard-b"), Model()
    with make_client(migrated, **LLM) as c:
        sync(c, a)
        push(c, a, canon_texts())
        drain(migrated, model)
        db.execute("UPDATE extraction SET discarded_at = now() WHERE id = ANY(%s)", ([x["id"] for x in extractions(db, a)],))
        sync(c, b)
        push(c, b, canon_texts())
        drain(migrated, model)
        assert len(model.canon_calls()) == 4


def test_a_repair_in_one_chat_does_not_reach_the_other(migrated, db):
    a, b, model = chat_of("repair-a"), chat_of("repair-b"), Model()
    with make_client(migrated, **LLM) as c:
        for chat in (a, b):
            sync(c, chat)
            push(c, chat, canon_texts())
            drain(migrated, model)
        (rel,) = [f for f in view(migrated, b)["facts"] if f["predicate"] == "relationship" and f.get("canon")]
        res = c.post(f"/v1/conversations/{cid_of(db, b)}/repairs", json={"kind": "fact_retract", "item": str(rel["id"])})
        assert res.status_code == 200, res.text
        assert not [f for f in view(migrated, b)["facts"] if f["predicate"] == "relationship" and f.get("canon")]
        assert [f for f in view(migrated, a)["facts"] if f["predicate"] == "relationship" and f.get("canon")]


def test_a_long_text_is_copied_part_by_part(migrated):
    long_card = CARD + "\n\n" + "\n".join(f"Line {i} of the old harbor tale goes on and on." for i in range(200))
    a, b, model = chat_of("long-a"), chat_of("long-b"), Model()
    with make_client(migrated, **LLM) as c:
        for chat in (a, b):
            sync(c, chat)
            push(c, chat, canon_texts(long_card))
            drain(migrated, model)
        parts = [u for u in model.canon_calls() if "card's description" in u]
        assert len(parts) == 2 and "part 1 of 2" in parts[0]  # read once, in two parts, for both chats
