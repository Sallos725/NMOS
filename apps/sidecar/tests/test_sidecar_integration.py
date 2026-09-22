"""Sidecar + Postgres integration: sync flow, idempotency, rebuild, recall, auth."""

from __future__ import annotations

import copy

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar.migrate import apply_migrations
from nmos_sidecar.rebuild import rebuild_all
from simchat import SimChat


def sync(client, chat: SimChat) -> dict:
    """Plugin flow: reconcile; if bodies are needed, post them with then_reconcile."""
    manifest = chat.manifest()
    res = client.post("/v1/sync/reconcile", json=manifest)
    assert res.status_code == 200, res.text
    out = res.json()
    if out["status"] == "needs_bodies":
        res = client.post("/v1/sync/bodies", json={"chat_id": chat.id, "bodies": chat.bodies(out["needed_bodies"]),
                                                   "then_reconcile": manifest})
        assert res.status_code == 200, res.text
        assert res.json()["ok"], res.text
        out = res.json()["reconcile"]
    assert out["status"] in ("applied", "noop"), out
    return out


def recall(client, chat: SimChat, query: str, in_context: list[str] | None = None, budget: int = 600, **extra) -> dict:
    res = client.post("/v1/retrieve", json={"chat_id": chat.id, "query": query, "in_context_ids": in_context or [],
                                             "budget_tokens": budget, **extra})
    assert res.status_code == 200, res.text
    return res.json()


def ledger_state(url: str) -> dict:
    """Logical ledger state, independent of generated uuids and timestamps."""
    with psycopg.connect(url, row_factory=dict_row) as conn:
        revisions = conn.execute(
            "SELECT c.host_chat_ref, so.host_logical_id, sr.revision_hash, sr.content, sr.lifecycle,"
            " (SELECT so2.host_logical_id || ':' || p.revision_hash FROM source_revision p"
            "   JOIN source_object so2 ON so2.id = p.source_object_id WHERE p.id = sr.lineage_parent_revision_id) AS parent"
            " FROM source_revision sr JOIN source_object so ON so.id = sr.source_object_id"
            " JOIN conversation c ON c.id = so.conversation_id ORDER BY 1, 2, 3"
        ).fetchall()
        commits = conn.execute(
            "SELECT c.host_chat_ref, w.reason, w.manifest_hash, w.delta FROM worldline_commit w"
            " JOIN conversation c ON c.id = w.conversation_id ORDER BY w.seq"
        ).fetchall()
        membership = conn.execute(
            "SELECT c.host_chat_ref, am.position, so.host_logical_id, sr.revision_hash FROM active_membership am"
            " JOIN worldline_commit w ON w.id = am.commit_id JOIN conversation c ON c.id = w.conversation_id"
            " JOIN source_revision sr ON sr.id = am.source_revision_id JOIN source_object so ON so.id = sr.source_object_id"
            " ORDER BY 1, 2"
        ).fetchall()
        convs = conn.execute(
            "SELECT host_chat_ref, head_manifest_hash, branched_from_host_chat_ref, branched_from_message_ref,"
            " (branched_from_conversation_id IS NOT NULL) AS linked FROM conversation ORDER BY 1"
        ).fetchall()
    return {"revisions": revisions, "commits": commits, "membership": membership, "conversations": convs}


def scripted_session(client, chat: SimChat, echo=None) -> SimChat:
    """Every PHASE-0 reconciliation case, in the order a user could produce them."""
    steps = [
        lambda: (chat.user("The lantern is hidden in the old archive under the harbor."), chat.reply("I will remember the archive.")),
        lambda: (chat.user("We met Hinata at the stone bridge at dawn."), chat.reply("Hinata waved from the bridge.")),
        lambda: (chat.user("The password for the vault is violet-seven."), chat.reply("Noted: violet-seven.")),
        lambda: chat.reroll("Second attempt: the vault password is violet-seven."),  # reroll
        lambda: chat.swipe(0),                                                      # swipe back
        lambda: chat.cont(" And the vault is below the chapel."),                  # continue
        lambda: chat.edit(0, "The lantern is hidden in the old archive under the north harbor."),  # edit user
        lambda: chat.edit(1, "I will remember the archive and the lantern."),     # edit AI
        lambda: chat.delete(3),                                                     # delete middle
        lambda: chat.disable(2),                                                    # disable
        lambda: (chat.user("Where was the lantern hidden again?"), chat.reply("In the archive.")),  # append + acceptance
    ]
    for action in steps:
        action()
        sync(client, chat)
        if echo:
            echo(chat)
    return chat


def test_migrations_apply_cleanly_and_are_guarded(database_url, tmp_path):
    from nmos_sidecar.migrate import migrations_dir
    expected = sorted(p.name for p in migrations_dir().glob("[0-9][0-9][0-9][0-9]_*.sql"))
    assert apply_migrations(database_url) == expected and expected[0] == "0001_source_layer.sql"
    assert apply_migrations(database_url) == []
    edited = tmp_path / "migrations"
    edited.mkdir()
    original = (migrations_dir() / "0001_source_layer.sql").read_text()
    (edited / "0001_source_layer.sql").write_text(original + "\n-- edited\n")
    with pytest.raises(RuntimeError, match="was modified"):
        apply_migrations(database_url, edited)


def test_revisions_are_immutable(client, db):
    chat = SimChat()
    chat.user("immutable evidence")
    sync(client, chat)
    rev = db.execute("SELECT id FROM source_revision").fetchone()
    with pytest.raises(psycopg.errors.RaiseException):
        db.execute("UPDATE source_revision SET content = 'tampered' WHERE id = %s", (rev["id"],))
    with pytest.raises(psycopg.errors.RaiseException):
        db.execute("DELETE FROM source_revision WHERE id = %s", (rev["id"],))
    db.execute("UPDATE source_revision SET lifecycle = 'accepted' WHERE id = %s", (rev["id"],))


def test_auth_required(migrated):
    with make_client(migrated) as c:
        assert c.get("/v1/health").status_code == 200
        c.headers["Authorization"] = "Bearer wrong"
        assert c.get("/v1/health").status_code == 401
        del c.headers["Authorization"]
        assert c.post("/v1/retrieve", json={}).status_code == 401
        pre = c.options("/v1/retrieve", headers={"Origin": "http://localhost:6101", "Access-Control-Request-Method": "POST",
                                                 "Access-Control-Request-Headers": "authorization,content-type"})
        assert pre.status_code == 200 and pre.headers["access-control-allow-origin"] == "http://localhost:6101"


def test_auth_is_optional(migrated):
    with make_client(migrated, auth_token="") as c:
        del c.headers["Authorization"]
        assert c.get("/v1/health").status_code == 200


def test_bad_body_hash_is_rejected(client):
    chat = SimChat()
    chat.user("real text")
    out = client.post("/v1/sync/reconcile", json=chat.manifest()).json()
    bodies = chat.bodies(out["needed_bodies"])
    bodies[0]["content"] = "forged text"
    res = client.post("/v1/sync/bodies", json={"chat_id": chat.id, "bodies": bodies}).json()
    assert res["ok"] is False and res["stored"] == 0


def test_all_reconciliation_cases_through_http(client, db):
    commits: list[str] = []

    def record(_chat):
        commits[:] = [r["reason"] for r in db.execute("SELECT reason FROM worldline_commit ORDER BY seq").fetchall()]

    chat = scripted_session(client, SimChat(), echo=record)
    assert commits == ["import", "reroll", "swipe", "edit", "edit", "edit", "delete", "disable"]
    rows = db.execute("SELECT content, lifecycle FROM source_revision ORDER BY recorded_at, id").fetchall()
    states = {}
    for r in rows:
        states.setdefault(r["content"], []).append(r["lifecycle"])
    # Original reply rerolled away (retracted); the same text re-entered as swipe 0 of the new message, then continued.
    assert sorted(states["Noted: violet-seven."]) == ["retracted", "superseded"]
    assert states["Second attempt: the vault password is violet-seven."] == ["superseded"]
    assert states["Noted: violet-seven. And the vault is below the chapel."] == ["accepted"]
    assert states["I will remember the archive."] == ["superseded"]
    assert states["In the archive."] == ["provisional"]  # tail reply: nobody has continued from it yet
    heads = db.execute("SELECT count(*) AS n FROM active_membership").fetchone()["n"]
    assert heads == len(chat.messages)
    parent = db.execute(
        "SELECT p.content FROM source_revision c JOIN source_revision p ON p.id = c.lineage_parent_revision_id"
        " WHERE c.content LIKE 'Noted: violet-seven. And the vault%'"
    ).fetchone()
    assert parent["content"] == "Noted: violet-seven."


def test_retry_duplicates_and_replay_are_idempotent(database_url_factory):
    """Replaying the same host history twice — every request duplicated, as H2 retries do — yields
    the same ledger as replaying it once."""
    once_url, twice_url = database_url_factory(), database_url_factory()
    chat_once, chat_twice = SimChat(chat_id="replay-chat"), SimChat(chat_id="replay-chat")
    with make_client(once_url) as once, make_client(twice_url) as twice:
        def mirror(chat):
            chat_twice.messages = copy.deepcopy(chat.messages)
            sync(twice, chat_twice)
            assert sync(twice, chat_twice)["status"] == "noop"

        scripted_session(once, chat_once, echo=mirror)
    assert ledger_state(once_url) == ledger_state(twice_url)


def test_rebuild_membership_from_commits(client, migrated, db):
    chat = scripted_session(client, SimChat())
    branch = chat.branch(1, name="Main")
    sync(client, branch)
    before = ledger_state(migrated)
    db.execute("DELETE FROM retrieval_trace")
    db.execute("DELETE FROM active_membership")
    rebuild_all(migrated)
    assert ledger_state(migrated) == before


def test_branch_records_origin(client, db):
    origin = SimChat()
    origin.user("Origin line one.")
    origin.reply("Origin reply one.")
    sync(client, origin)
    branch = origin.branch(1, name="Origin chat")
    out = sync(client, branch)
    assert out["commit_reason"] == "branch"
    row = db.execute("SELECT * FROM conversation WHERE host_chat_ref = %s", (branch.id,)).fetchone()
    assert row["branched_from_host_chat_ref"] == origin.id
    assert row["branched_from_message_ref"] == origin.messages[1]["chatId"]
    assert row["branched_from_conversation_id"] is not None


def test_recall_surfaces_out_of_context_excerpt_and_never_inactive(client):
    chat = scripted_session(client, SimChat())
    # Distractor turns so the early facts are "out of context".
    for i in range(30):
        chat.user(f"Filler turn {i} about the weather and the market stalls.")
        chat.reply(f"Filler reply {i}: clouds over the market.")
    chat.user("Remind me, where is the lantern hidden?")
    sync(client, chat)
    in_context = [m["chatId"] for m in chat.messages[-10:]]
    out = recall(client, chat, "Remind me, where is the lantern hidden?", in_context)
    text = out["packet"]["text"]
    assert out["freshness"] == "fresh"
    assert "north harbor" in text  # edited user revision (current)
    assert "under the harbor." not in text  # superseded pre-edit revision never surfaces
    assert "Second attempt" not in text  # swiped-away revision never surfaces
    assert text.startswith('<NarrativeMemory version="0" source="nmos">')
    trace = client.get(f"/v1/trace/{out['trace_id']}").json()
    assert trace["selected"] and "sidecar_total" in trace["latency_ms"]

    # Deleted / disabled / superseded / retracted content is never recalled.
    for query in ("We met Hinata at the stone bridge at dawn.", "Second attempt: the vault password is violet-seven.",
                  "I will remember the archive."):
        packet = recall(client, chat, query, in_context)["packet"]["text"]
        assert "Hinata" not in packet
        assert "Second attempt" not in packet
        assert "I will remember the archive.<" not in packet


def test_in_context_exclusion_threshold_and_budget(client):
    chat = SimChat()
    chat.user("The comet returns every seventy six years to the observatory.")
    chat.reply("The observatory keeps a log of the comet.")
    chat.user("Unrelated question about bread.")
    sync(client, chat)
    q = "When does the comet return to the observatory?"
    out = recall(client, chat, q, in_context=[m["chatId"] for m in chat.messages])
    assert out["packet"]["text"] == ""
    trace = client.get(f"/v1/trace/{out['trace_id']}").json()
    assert trace["excluded_in_context"]
    assert recall(client, chat, "zzqx vvkw ppjj")["packet"]["text"] == ""
    small = recall(client, chat, q, budget=40)["packet"]
    assert small["token_estimate"] <= 40
    tiny = recall(client, chat, q, budget=5)["packet"]
    assert tiny["text"] == "" and tiny["token_estimate"] == 0


def test_stale_commit_gets_no_packet(client):
    chat = SimChat()
    chat.user("The comet returns every seventy six years to the observatory.")
    first = sync(client, chat)
    chat.reply("The observatory keeps a log.")
    chat.user("next")
    sync(client, chat)
    out = recall(client, chat, "comet observatory", active_commit=first["active_commit"],
                 manifest_hash=first["manifest_hash"])
    assert out["freshness"] == "stale" and out["packet"]["text"] == ""


def test_all_before_cut_is_inactive(client):
    chat = SimChat()
    chat.user("The ruby is kept in the lighthouse.")
    chat.reply("Lighthouse noted.")
    chat.user("Let us talk about something else.")
    chat.disable(2, "allBefore")
    chat.reply("Sure.")
    chat.user("Where is the ruby kept?")
    sync(client, chat)
    assert "lighthouse" not in recall(client, chat, "Where is the ruby kept?")["packet"]["text"].lower()


def test_output_notification_is_idempotent(client, db):
    body = {"chat_id": "c-out", "host_logical_id": "m1", "generation_id": "m1", "revision_hash": "a" * 64, "message_index": 3}
    assert client.post("/v1/output", json=body).status_code == 202
    assert client.post("/v1/output", json=body).status_code == 202
    assert db.execute("SELECT count(*) AS n FROM host_observation WHERE kind = 'output'").fetchone()["n"] == 1


def test_live_reroll_flow_retracts_and_never_recalls(client, db):
    chat = SimChat()
    chat.user("Tell me a secret.")
    chat.reply("The dragon sleeps beneath the frozen lake of Varn.")
    chat.user("Continue please.")
    sync(client, chat)  # the reply above is now accepted (a user turn follows)
    chat.reply("Unique discarded answer: the crown is melted into bells.")
    sync(client, chat)
    discarded = chat.messages.pop()  # host drops the tail before the reroll request (HOST-FACTS S2)
    out = sync(client, chat)
    assert out["commit_reason"] == "reroll"
    chat.messages.append({"role": "char", "data": "New answer.", "chatId": "regen-1", "generationInfo": {"generationId": "regen-1"},
                          "swipes": [discarded["data"], "New answer."], "swipeId": 1})
    chat.user("What was melted into bells?")
    sync(client, chat)
    state = db.execute("SELECT lifecycle FROM source_revision WHERE content = %s", (discarded["data"],)).fetchone()
    assert state["lifecycle"] == "retracted"
    assert "melted" not in recall(client, chat, "What was melted into bells?", in_context=[chat.messages[-1]["chatId"]])["packet"]["text"]
