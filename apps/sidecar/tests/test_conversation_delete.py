"""Deleting a conversation from NMOS (ADR 0009): everything of that chat goes, nothing else does."""

from __future__ import annotations

import psycopg
import pytest

from conftest import make_client
from simchat import SimChat
from test_extraction import drain, facts, filler
from test_generations import EMB, LLM, conv_id
from test_sidecar_integration import recall, sync
from test_vectors import FakeEmbedder, drain_embeddings

# Every table with rows that belong to one conversation.
TABLES = {
    "conversation": "SELECT count(*) FROM conversation WHERE id = %(c)s",
    "host_observation": "SELECT count(*) FROM host_observation WHERE conversation_id = %(c)s",
    "observation_base": "SELECT count(*) FROM observation_base WHERE conversation_id = %(c)s",
    "source_object": "SELECT count(*) FROM source_object WHERE conversation_id = %(c)s",
    "source_revision": "SELECT count(*) FROM source_revision sr JOIN source_object so ON so.id = sr.source_object_id"
                       " WHERE so.conversation_id = %(c)s",
    "worldline_commit": "SELECT count(*) FROM worldline_commit WHERE conversation_id = %(c)s",
    "active_membership": "SELECT count(*) FROM active_membership am JOIN worldline_commit w ON w.id = am.commit_id"
                         " WHERE w.conversation_id = %(c)s",
    "retrieval_trace": "SELECT count(*) FROM retrieval_trace WHERE conversation_id = %(c)s",
    "state_observation": "SELECT count(*) FROM state_observation WHERE conversation_id = %(c)s",
    "job": "SELECT count(*) FROM job WHERE conversation_id = %(c)s",
    "extraction": "SELECT count(*) FROM extraction e JOIN source_revision sr ON sr.id = e.source_revision_id"
                  " JOIN source_object so ON so.id = sr.source_object_id WHERE so.conversation_id = %(c)s",
    "assertion": "SELECT count(*) FROM assertion a JOIN source_revision sr ON sr.id = a.source_revision_id"
                 " JOIN source_object so ON so.id = sr.source_object_id WHERE so.conversation_id = %(c)s",
    "revision_embedding": "SELECT count(*) FROM revision_embedding e JOIN source_revision sr"
                          " ON sr.id = e.source_revision_id JOIN source_object so ON so.id = sr.source_object_id"
                          " WHERE so.conversation_id = %(c)s",
    "revision_text": "SELECT count(*) FROM revision_text t JOIN source_revision sr ON sr.id = t.source_revision_id"
                     " JOIN source_object so ON so.id = sr.source_object_id WHERE so.conversation_id = %(c)s",
}


def rows(db, cid) -> dict[str, int]:
    return {t: db.execute(q, {"c": cid}).fetchone()["count"] for t, q in TABLES.items()}


def chapel_chat() -> SimChat:
    chat = SimChat()
    chat.user("Hinata is in the old chapel.")
    chat.reply("The chapel is quiet. <status>HP 10/10</status>")
    filler(chat, 2)
    chat.user("last")
    return chat


def test_delete_removes_every_row_of_the_chat_and_nothing_else(migrated, db):
    with make_client(migrated, embedder=FakeEmbedder(), **LLM, **EMB) as c:
        c.put("/v1/config", json={"parsers": {"rules": [
            {"id": "hp", "kind": "regex", "pattern": r"HP\s*(?P<value>\d+/\d+)", "key": "HP"}]}})
        gone, kept = chapel_chat(), chapel_chat()
        for chat in (gone, kept):
            sync(c, chat)
        drain(migrated)
        drain_embeddings(migrated)
        chat_edit = gone.messages[1]["data"]
        gone.edit(1, chat_edit + " edited")  # a second revision and a divergence commit
        sync(c, gone)
        recall(c, gone, "chapel")
        gid, kid = conv_id(c, gone), conv_id(c, kept)
        before_gone, before_kept = rows(db, gid), rows(db, kid)
        assert all(before_gone[t] > 0 for t in ("source_revision", "worldline_commit", "assertion",
                                                 "revision_embedding", "state_observation", "retrieval_trace",
                                                 "job", "host_observation"))

        out = c.post(f"/v1/conversations/{gid}/delete")
        assert out.status_code == 200, out.text
        deleted = out.json()["deleted"]
        assert deleted["conversation"] == 1 and deleted["revisions"] == before_gone["source_revision"]
        assert deleted["assertions"] == before_gone["assertion"]
        assert rows(db, gid) == dict.fromkeys(TABLES, 0)
        assert rows(db, kid) == before_kept
        assert [x["host_chat_ref"] for x in c.get("/v1/conversations").json()] == [kept.id]
        assert facts(c, kept) != []
        for path in ("delete", "rebuild", "extract-history", "coverage", "facts", "state"):
            method = c.get if path in ("coverage", "facts", "state") else c.post
            assert method(f"/v1/conversations/{gid}/{path}").status_code == 404, path


def test_plain_deletes_of_raw_revisions_are_still_refused(migrated, db):
    with make_client(migrated) as c:
        one, two = chapel_chat(), chapel_chat()
        sync(c, one)
        sync(c, two)
        oid = conv_id(c, one)
    with pytest.raises(psycopg.errors.RaiseException, match="never deleted"):
        db.execute("DELETE FROM source_revision")
    # The guard opens only for the conversation named by the delete in progress.
    with psycopg.connect(migrated) as conn, pytest.raises(psycopg.errors.RaiseException, match="never deleted"):
        conn.execute("SELECT set_config('nmos.delete_conversation', %s, true)", (oid,))
        conn.execute("DELETE FROM source_revision sr USING source_object so WHERE so.id = sr.source_object_id"
                     " AND so.conversation_id <> %s", (oid,))


def test_a_chat_synced_again_after_deletion_starts_over(migrated, db):
    with make_client(migrated, extract_backfill=1, **LLM) as c:
        chat = chapel_chat()
        sync(c, chat)
        old = conv_id(c, chat)
        c.post(f"/v1/conversations/{old}/delete")
        chat.user("again")
        assert sync(c, chat)["commit_reason"] == "import"  # first sight, like a chat NMOS never saw
        new = conv_id(c, chat)
        assert new != old
        assert rows(db, new)["source_revision"] == len(chat.messages)
        # Only the first-sight backfill is extracted again (D22), like any chat NMOS has not seen.
        assert db.execute("SELECT count(*) FROM job WHERE conversation_id = %s AND kind = 'extract'",
                          (new,)).fetchone()["count"] == 1


def test_deleting_a_branch_origin_keeps_the_branch(client, db):
    origin = chapel_chat()
    sync(client, origin)
    branch = origin.branch(1, name="Origin chat")
    sync(client, branch)
    linked = "SELECT branched_from_conversation_id FROM conversation WHERE host_chat_ref = %s"
    assert db.execute(linked, (branch.id,)).fetchone()["branched_from_conversation_id"] is not None
    client.post(f"/v1/conversations/{conv_id(client, origin)}/delete")
    row = db.execute("SELECT * FROM conversation WHERE host_chat_ref = %s", (branch.id,)).fetchone()
    assert row["branched_from_conversation_id"] is None and row["branched_from_host_chat_ref"] == origin.id
    assert rows(db, row["id"])["source_revision"] > 0


def test_a_job_running_while_its_chat_is_deleted_fails_quietly(migrated, db):
    """The worker holds no lock during a model call; its write after the delete must not resurrect rows."""
    with make_client(migrated, **LLM) as c:
        chat = chapel_chat()
        sync(c, chat)
        cid = conv_id(c, chat)

        def complete(system, user):
            from test_extraction import fake_complete
            with psycopg.connect(migrated) as other:
                from nmos_sidecar.ledger import delete_conversation
                assert delete_conversation(other, cid) is not None
            return fake_complete(system, user)

        drain(migrated, complete)
    assert rows(db, cid) == dict.fromkeys(TABLES, 0)
    assert db.execute("SELECT count(*) FROM extraction").fetchone()["count"] == 0
