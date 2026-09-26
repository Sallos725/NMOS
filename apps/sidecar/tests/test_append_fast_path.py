"""Verified append fast path (Track A, A1): same ledger as the full path, or the full path itself.

Two sidecars, one with `append_fast_path` off, receive the same host actions in lockstep; after every
sync their logical ledgers, turn data, jobs and observations must be equal.
"""

from __future__ import annotations

import random
import uuid

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import ledger
from nmos_sidecar.canonical import manifest_hash, manifest_hashes
from nmos_sidecar.reconcile import Entry, plan, plan_append
from simchat import SimChat
from test_sidecar_integration import ledger_state, sync

LLM = {"llm_url": "http://fake-llm/v1", "llm_model": "fake", "embed_url": "http://fake-embed/v1",
       "embed_model": "fake-embed", "extract_backfill": 2}


class FullPath(Exception):
    """Raised by a patched `ledger.load_state`: the request left the fast path."""


def full_path_calls(monkeypatch) -> list[int]:
    calls: list[int] = []
    original = ledger.load_state

    def counting(conn, conv):
        calls.append(1)
        return original(conn, conv)

    monkeypatch.setattr(ledger, "load_state", counting)
    return calls


def logical(url: str) -> dict:
    out = ledger_state(url)
    with psycopg.connect(url, row_factory=dict_row) as conn:
        out["turns"] = conn.execute(
            "SELECT am.position, am.turn, am.turn_hash FROM active_membership am ORDER BY am.commit_id, am.position"
        ).fetchall()
        out["jobs"] = conn.execute(
            "SELECT j.kind, j.priority, j.status, j.payload->>'window_hash' AS turn_hash, so.host_logical_id,"
            " sr.revision_hash FROM job j JOIN source_revision sr ON sr.id = (j.payload->>'revision_id')::uuid"
            " JOIN source_object so ON so.id = sr.source_object_id ORDER BY j.id"
        ).fetchall()
        out["observations"] = conn.execute(
            "SELECT kind, manifest_hash, raw_manifest FROM host_observation ORDER BY id"
        ).fetchall()
    return out


# --- host actions -----------------------------------------------------------------------------------

def turn(chat: SimChat, rnd: random.Random) -> None:
    chat.user(f"user {rnd.random():.6f}")
    chat.reply(f"reply {rnd.random():.6f}")


def comment(chat: SimChat, rnd: random.Random) -> None:
    chat.messages.append({"role": "char", "isComment": True, "chatId": str(uuid.uuid4()), "data": f"note {rnd.random()}"})


ACTIONS = {
    "turn": (8, turn),
    "reply": (2, lambda c, r: c.reply(f"another reply {r.random():.6f}")),
    "user": (2, lambda c, r: c.user(f"lone user {r.random():.6f}")),
    "disabled_user": (1, lambda c, r: (c.user("hidden"), c.disable(-1))),
    "disabled_reply": (1, lambda c, r: (c.reply("hidden reply"), c.disable(-1))),
    "comment": (1, comment),
    "cut": (1, lambda c, r: (c.user("cut here"), c.disable(-1, "allBefore"))),
    "reroll": (1, lambda c, r: c.reroll(f"rerolled {r.random():.6f}") if c.messages[-1]["role"] == "char" else None),
    "cont": (1, lambda c, r: c.cont(" more") if c.messages[-1]["role"] == "char" else None),
    "edit_deep": (1, lambda c, r: (c.edit(r.randrange(len(c.messages)), f"edited {r.random()}"), turn(c, r))),
    "delete": (1, lambda c, r: (c.delete(r.randrange(len(c.messages) - 1)), turn(c, r))),
    "disable_old": (1, lambda c, r: (c.disable(r.randrange(len(c.messages))), turn(c, r))),
    "none": (1, lambda c, r: None),
}


@pytest.mark.parametrize("seed,turns", [(1, 3), (2, 1), (3, 2), (4, 3)])
def test_fast_path_ledger_equals_the_full_path(database_url_factory, monkeypatch, seed, turns):
    fast_url, full_url = database_url_factory(), database_url_factory()
    rnd = random.Random(seed)
    names = list(ACTIONS)
    weights = [ACTIONS[n][0] for n in names]
    calls = full_path_calls(monkeypatch)
    fast_steps = 0
    with make_client(fast_url, extract_turns=turns, **LLM) as fast, \
            make_client(full_url, extract_turns=turns, append_fast_path=False, **LLM) as full:
        chat = SimChat()
        chat.reply("greeting")
        for _ in range(3):
            turn(chat, rnd)
        for step in range(70):
            if len(chat.messages) < 2:
                turn(chat, rnd)
            action = rnd.choices(names, weights)[0]
            ACTIONS[action][1](chat, rnd)
            before = len(calls)
            sync(fast, chat)
            fast_steps += len(calls) == before
            sync(full, chat)
            assert logical(fast_url) == logical(full_url), f"step {step}: {action}"
    assert fast_steps > 20  # the fast path was actually exercised
    # Appends are replayable: rebuilding membership from commits and append rows changes nothing.
    before = logical(fast_url)
    with psycopg.connect(fast_url, row_factory=dict_row) as conn:
        conv = conn.execute("SELECT id FROM conversation").fetchone()["id"]
        ledger.rebuild_membership(conn, conv, turns)
    assert logical(fast_url) == before


def test_pure_append_skips_load_state_and_divergence_falls_back(client, monkeypatch):
    chat = SimChat()
    chat.reply("greeting")
    for i in range(6):
        chat.user(f"u{i}")
        chat.reply(f"r{i}")
    sync(client, chat)  # first sight: full path
    calls = full_path_calls(monkeypatch)

    chat.user("next")
    chat.reply("answer")
    assert sync(client, chat)["status"] == "applied" and calls == []
    assert sync(client, chat)["status"] == "noop" and calls == []  # duplicate request (H2 retry)

    for divergent in (lambda: chat.edit(2, "deep edit"), lambda: chat.delete(3), lambda: chat.disable(4),
                      lambda: chat.reroll("rerolled")):
        divergent()
        chat.user("and then")
        chat.reply("more")
        sync(client, chat)
        assert calls, "a divergence plus append must not take the fast path"
        calls.clear()


def test_new_cut_and_repeated_ids_fall_back(client, monkeypatch):
    chat = SimChat()
    for i in range(4):
        chat.user(f"u{i}")
        chat.reply(f"r{i}")
    sync(client, chat)
    calls = full_path_calls(monkeypatch)

    chat.user("cut")
    chat.disable(-1, "allBefore")
    sync(client, chat)
    assert calls
    calls.clear()

    # Not something the host produces (H6), but a matching prefix must not make it an append.
    manifest = chat.manifest()
    manifest["messages"].append(dict(manifest["messages"][0]))

    def refuse(conn, conv):
        raise FullPath

    monkeypatch.setattr(ledger, "load_state", refuse)
    with pytest.raises(FullPath):
        client.post("/v1/sync/reconcile", json=manifest)


def test_fast_path_survives_a_sidecar_restart(migrated, monkeypatch):
    chat = SimChat()
    for i in range(3):
        chat.user(f"u{i}")
        chat.reply(f"r{i}")
    with make_client(migrated) as first:
        sync(first, chat)
    calls = full_path_calls(monkeypatch)
    chat.user("after restart")
    chat.reply("still here")
    with make_client(migrated) as second:
        assert sync(second, chat)["status"] == "applied"
    assert calls == []


def test_missing_bodies_resume_over_several_requests(client, monkeypatch):
    chat = SimChat()
    for i in range(3):
        chat.user(f"u{i}")
        chat.reply(f"r{i}")
    sync(client, chat)
    calls = full_path_calls(monkeypatch)
    chat.user("new")
    chat.reply("reply")
    first = client.post("/v1/sync/reconcile", json=chat.manifest()).json()
    assert first["status"] == "needs_bodies" and len(first["needed_bodies"]) == 2
    # The plugin ran out of time after uploading one body; the next request asks only for the other.
    res = client.post("/v1/sync/bodies", json={"chat_id": chat.id, "bodies": chat.bodies(first["needed_bodies"][:1]),
                                               "then_reconcile": None})
    assert res.json()["ok"]
    second = client.post("/v1/sync/reconcile", json=chat.manifest()).json()
    assert second["needed_bodies"] == first["needed_bodies"][1:]
    assert sync(client, chat)["status"] == "applied" and calls == []


def test_failed_append_leaves_the_prior_head(client, db, monkeypatch):
    chat = SimChat()
    for i in range(3):
        chat.user(f"u{i}")
        chat.reply(f"r{i}")
    sync(client, chat)
    before = db.execute("SELECT head_commit_id, head_manifest_hash FROM conversation").fetchone()
    members = db.execute("SELECT count(*) AS n FROM active_membership").fetchone()["n"]
    original = ledger.apply_append

    def broken(conn, *args, **kwargs):
        original(conn, *args, **kwargs)
        raise RuntimeError("disk full")

    monkeypatch.setattr(ledger, "apply_append", broken)
    chat.user("lost")
    chat.reply("lost too")
    with pytest.raises(RuntimeError):
        sync(client, chat)
    assert db.execute("SELECT head_commit_id, head_manifest_hash FROM conversation").fetchone() == before
    assert db.execute("SELECT count(*) AS n FROM active_membership").fetchone()["n"] == members
    monkeypatch.setattr(ledger, "apply_append", original)
    assert sync(client, chat)["status"] == "applied"


# --- pure parts ---------------------------------------------------------------------------------------

def test_split_manifest_hashes_match_the_plain_hash():
    entries = [(str(uuid.uuid4()), f"{i:064x}") for i in range(7)] + [("한글 ID́", "x")]
    for split in range(1, len(entries)):
        assert manifest_hashes(entries, split) == (manifest_hash(entries[:split]), manifest_hash(entries))


def e(i: int, role: str, **kw) -> Entry:
    return Entry(f"m{i}", f"h{i}", role, **kw)


def test_plan_append_equals_plan_on_acceptance_edge_cases():
    head = [e(0, "char"), e(1, "user"), e(2, "char"), e(3, "user", disabled=True), e(4, "char"),
            e(5, "char", is_comment=True)]
    lifecycle = {x.key: ("accepted" if x.role == "user" or x.is_comment or i < 2 else "provisional")
                 for i, x in enumerate(head)}
    for suffix in ([e(6, "user"), e(7, "char")], [e(6, "char")], [e(6, "user", disabled=True)],
                   [e(6, "user", is_comment=True), e(7, "user")]):
        manifest = head + suffix
        known = {x.key for x in manifest}
        full = plan(head, manifest_hash([x.key for x in head]), manifest, known, lifecycle)
        for start in (0, 1, 2):  # the tail must hold every member that is not accepted (m2, m4)
            fast = plan_append(start, head[start:], manifest[start:], full.manifest_hash, lifecycle)
            assert (fast.kind, fast.lifecycle, fast.ops, fast.changes, fast.commit_reason, fast.lineage) == \
                (full.kind, full.lifecycle, full.ops, full.changes, full.commit_reason, full.lineage)
