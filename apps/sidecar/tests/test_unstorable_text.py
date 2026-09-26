"""Text PostgreSQL cannot store: lone UTF-16 surrogates (ADR 0029, audit A-01).

A browser's `JSON.stringify` sends a lone surrogate as `\\udxxx`, and the plugin hashes it that way. The
sidecar verifies the hash on the text as sent, then stores U+FFFD in its place."""

from __future__ import annotations

import json

from nmos_sidecar.canonical import storable
from simchat import SimChat


def post(client, path: str, body: dict):
    # httpx's `json=` cannot encode a lone surrogate; json.dumps escapes it as the browser does.
    return client.post(path, content=json.dumps(body), headers={"content-type": "application/json"})


def sync(client, chat: SimChat, **labels) -> dict:
    manifest = {**chat.manifest(), **labels}
    res = post(client, "/v1/sync/reconcile", manifest)
    assert res.status_code == 200, res.text
    out = res.json()
    if out["status"] == "needs_bodies":
        res = post(client, "/v1/sync/bodies", {"chat_id": chat.id, "bodies": chat.bodies(out["needed_bodies"]),
                                               "then_reconcile": manifest})
        assert res.status_code == 200, res.text
        assert res.json()["ok"], res.text
        out = res.json()["reconcile"]
    return out


def test_storable_replaces_only_lone_surrogates():
    assert storable("a\ud800b\udc00c😀") == "a�b�c😀"
    assert storable({"k": ["x\ud83d", 1, None, True]}) == {"k": ["x�", 1, None, True]}
    plain = {"k": ["x", 1]}
    assert storable(plain) == plain


def test_a_chat_with_a_broken_character_syncs_and_recalls(client, db):
    chat = SimChat()
    chat.user("The lantern \ud83d is hidden in the old archive.")
    chat.reply("I will remember where the lantern is \udc00.")["name"] = "Lu\ud800na"
    for i in range(4):
        chat.user(f"Idle chatter {i} about clouds.")
        chat.reply(f"Idle reply {i}.")
    chat.user("Where did we hide the lantern \ud800?")
    labels = {"persona_name": "Yu\ud800", "chat_name": "Chat \udc00", "character_name": "Lu\ud800na"}

    out = sync(client, chat, **labels)
    assert out["status"] == "applied"
    manifest = chat.manifest()
    stored = {r["host_logical_id"]: r for r in db.execute(
        "SELECT so.host_logical_id, sr.revision_hash, sr.content, sr.metadata FROM source_revision sr"
        " JOIN source_object so ON so.id = sr.source_object_id").fetchall()}
    # Keyed by the hash of the text as sent, holding U+FFFD where it cannot be stored.
    assert {k: r["revision_hash"] for k, r in stored.items()} == \
        {m["host_logical_id"]: m["revision_hash"] for m in manifest["messages"]}
    first, second = (m["host_logical_id"] for m in manifest["messages"][:2])
    assert stored[first]["content"] == "The lantern \ufffd is hidden in the old archive."
    assert stored[second]["content"] == "I will remember where the lantern is \ufffd."
    assert stored[second]["metadata"]["name"] == "Lu\ufffdna"
    conv = db.execute("SELECT host_persona_name, host_chat_name, host_character_name FROM conversation").fetchone()
    assert conv == {"host_persona_name": "Yu�", "host_chat_name": "Chat �", "host_character_name": "Lu�na"}

    assert sync(client, chat, **labels)["status"] == "noop"  # the host's hashes still match

    res = post(client, "/v1/retrieve", {"chat_id": chat.id, "query": "Where did we hide the lantern \ud800?",
                                        "previous_ai": "Idle reply 3 \udc00.", "in_context_ids": [],
                                        "budget_tokens": 600})
    assert res.status_code == 200, res.text
    assert "old archive" in res.json()["packet"]["text"]


def test_an_id_holding_a_lone_surrogate_is_a_422_not_a_500(client):
    chat = SimChat()
    chat.user("hello")
    manifest = chat.manifest()
    manifest["messages"][0]["host_logical_id"] = "u\ud800"
    res = post(client, "/v1/sync/reconcile", manifest)
    assert res.status_code == 422
    assert res.json()["detail"][0]["input"] == "u�"
    body = {"chat_id": chat.id, "bodies": [{"host_logical_id": "u0", "revision_hash": "0" * 64, "content": 7,
                                            "metadata": {}}]}
    assert post(client, "/v1/sync/bodies", body).status_code == 422
