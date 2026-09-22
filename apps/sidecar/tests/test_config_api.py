"""Runtime configuration API used by the plugin settings UI."""

from __future__ import annotations

from conftest import make_client
from simchat import SimChat
from test_sidecar_integration import recall, sync


def test_config_roundtrip_masks_secrets_and_validates(client):
    view = client.get("/v1/config").json()
    assert view["llm"]["url"] == "" and view["llm"]["api_key_set"] is False
    bad = client.put("/v1/config", json={"llm_url": "ftp://x", "recall_threshold": 3, "nope": 1})
    assert bad.status_code == 422 and len(bad.json()["detail"]) == 3
    ok = client.put("/v1/config", json={"llm_url": "http://llm.example/v1", "llm_model": "m", "llm_api_key": "sk-secret",
                                         "recall_threshold": 0.5}).json()
    assert ok["llm"] == {"url": "http://llm.example/v1", "model": "m", "api_key_set": True, "json_mode": True}
    assert "sk-secret" not in str(ok) and ok["recall"]["threshold"] == 0.5
    assert client.get("/v1/health").json()["features"]["extraction"] is True
    reset = client.put("/v1/config", json={"llm_url": None, "llm_model": None, "llm_api_key": None}).json()
    assert reset["llm"]["url"] == "" and reset["llm"]["api_key_set"] is False


def test_config_persists_across_restarts(migrated):
    with make_client(migrated) as c:
        c.put("/v1/config", json={"facts_limit": 3})
    with make_client(migrated) as c:
        assert c.get("/v1/config").json()["recall"]["facts_limit"] == 3


def test_parsers_from_ui_rebuild_state(client):
    chat = SimChat()
    chat.user("start")
    chat.reply("<status>\n[하나]\n장소: 성당\n</status>")
    chat.user("go on")
    sync(client, chat)
    bad = client.put("/v1/config", json={"parsers": "{not json"})
    assert bad.status_code == 422
    rules = {"rules": [{"id": "r", "kind": "block", "start": "<status>", "end": "</status>",
                        "entity_line": r"\[(?P<entity>[^\]]+)\]"}]}
    view = client.put("/v1/config", json={"parsers": rules}).json()
    assert view["parsers"]["source"] == "ui" and view["parsers"]["active_rules"] == 1
    assert '<Item key="하나.장소" as_of_turn="1">성당</Item>' in recall(client, chat, "어디?")["packet"]["text"]


def test_enabling_embeddings_backfills_existing_chats(client, db):
    chat = SimChat()
    for i in range(4):
        chat.user(f"line {i}")
        chat.reply(f"reply {i}")
    chat.user("last")
    sync(client, chat)
    assert db.execute("SELECT count(*) AS n FROM job").fetchone()["n"] == 0
    out = client.put("/v1/config", json={"embed_url": "http://emb.example/v1", "embed_model": "e", "extract_backfill": 3}).json()
    # Embeddings cover the whole (short) history; the LLM backfill limit does not apply to them.
    assert out["queued_jobs"] == len(chat.messages) - 0 and db.execute(
        "SELECT count(*) AS n FROM job WHERE kind = 'embed'").fetchone()["n"] == len(chat.messages)


def test_connection_tests_report_failures_cleanly(client):
    llm = client.post("/v1/config/test", json={"kind": "llm", "url": "http://127.0.0.1:9/v1", "model": "x"}).json()
    emb = client.post("/v1/config/test", json={"kind": "embeddings", "url": "http://127.0.0.1:9/v1", "model": "x"}).json()
    models = client.post("/v1/config/models", json={"url": "http://127.0.0.1:9/v1"}).json()
    assert llm["ok"] is False and "error" in llm
    assert emb["ok"] is False and models["ok"] is False and models["models"] == []


def test_cors_preflight_allows_settings_put_from_allowed_origin_only(client):
    """The settings panel saves with a direct cross-origin PUT when the sidecar is on localhost (#11)."""
    headers = {"Access-Control-Request-Method": "PUT", "Access-Control-Request-Headers": "content-type,authorization"}
    ok = client.options("/v1/config", headers={"Origin": "http://localhost:6101", **headers})
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == "http://localhost:6101"
    assert "PUT" in ok.headers["access-control-allow-methods"]
    assert {h.strip().lower() for h in ok.headers["access-control-allow-headers"].split(",")} >= {"content-type",
                                                                                                  "authorization"}
    denied = client.options("/v1/config", headers={"Origin": "http://evil.example", **headers})
    assert denied.status_code == 400 and "access-control-allow-origin" not in denied.headers
    put = client.put("/v1/config", json={"facts_limit": 4}, headers={"Origin": "http://localhost:6101"})
    assert put.status_code == 200 and put.headers["access-control-allow-origin"] == "http://localhost:6101"
