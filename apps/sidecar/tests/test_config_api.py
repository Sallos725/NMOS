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


def test_runtime_config_accepts_real_json_boolean_false(client):
    assert client.put("/v1/config", json={"llm_json_mode": False}).json()["llm"]["json_mode"] is False
    assert client.put("/v1/config", json={"llm_json_mode": True}).json()["llm"]["json_mode"] is True


def test_runtime_config_rejects_ambiguous_boolean_string(client):
    for value in ("false", "0", "no", 0, 1):
        bad = client.put("/v1/config", json={"llm_json_mode": value})
        assert bad.status_code == 422 and "llm_json_mode: expected a JSON boolean" in bad.json()["detail"][0]
    assert client.get("/v1/config").json()["llm"]["json_mode"] is True  # nothing was saved


def test_runtime_config_rejects_wrong_scalar_types(client):
    bad = client.put("/v1/config", json={"recall_top_k": 3.5, "facts_limit": True, "extract_backfill": "12",
                                         "recall_threshold": "0.5", "llm_model": 123, "embed_model": ["x"]})
    assert bad.status_code == 422 and len(bad.json()["detail"]) == 6
    ok = client.put("/v1/config", json={"recall_top_k": 4.0, "recall_threshold": 1, "vector_min_sim": 0.5}).json()
    assert ok["recall"]["top_k"] == 4 and ok["recall"]["threshold"] == 1.0 and ok["recall"]["vector_min_sim"] == 0.5
    assert client.put("/v1/config", json={"recall_top_k": 21}).status_code == 422  # ranges unchanged


def test_runtime_config_null_still_resets_to_environment_default(migrated):
    with make_client(migrated, llm_json_mode=False, recall_top_k=7) as c:
        c.put("/v1/config", json={"llm_json_mode": True, "recall_top_k": 2})
        view = c.put("/v1/config", json={"llm_json_mode": None, "recall_top_k": None}).json()
        assert view["llm"]["json_mode"] is False and view["recall"]["top_k"] == 7 and view["overridden"] == []


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


def test_raising_extraction_backfill_queues_older_turns_without_restart(migrated, db):
    from conftest import make_client
    with make_client(migrated, llm_url="http://fake-llm/v1", llm_model="fake", extract_backfill=2) as c:
        chat = SimChat()
        for i in range(6):
            chat.user(f"line {i}")
            chat.reply(f"reply {i}")
        chat.user("last")
        sync(c, chat)
        assert db.execute("SELECT count(*) AS n FROM job WHERE kind = 'extract'").fetchone()["n"] == 2
        assert c.put("/v1/config", json={"extract_backfill": 5}).json()["queued_jobs"] == 3
        assert c.put("/v1/config", json={"extract_backfill": 1}).json()["queued_jobs"] == 0
    assert db.execute("SELECT count(*) AS n FROM job WHERE kind = 'extract'").fetchone()["n"] == 5
