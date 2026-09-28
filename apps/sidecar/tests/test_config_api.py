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
        c.put("/v1/config", json={"facts_limit": 3, "events_limit": 1})
    with make_client(migrated) as c:
        recall = c.get("/v1/config").json()["recall"]
        assert recall["facts_limit"] == 3 and recall["events_limit"] == 1


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
    assert '<Item key="하나.장소" as_of_turn="0">성당</Item>' in recall(client, chat, "어디?")["packet"]["text"]  # turn 0


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


def test_a_saved_key_is_sent_only_to_its_own_host(client, monkeypatch):
    """A connection test or a model list for another host does not carry the saved key there (the key is
    write-only through the API: pointing a test at your own server must not read it out)."""
    from nmos_sidecar import runtime
    from nmos_sidecar.llm import LLMError

    sent: list[tuple[str, str]] = []

    class Model:
        def __init__(self, url, model, api_key, timeout_s=60, json_mode=True):
            self.url, self.key = url, api_key

        def complete_json(self, system, user):
            sent.append((self.url, self.key))
            if not self.key:
                raise LLMError("HTTP 401")
            return {"ok": True}, None

    class Embed:
        def __init__(self, url, model, api_key):
            self.url, self.key = url, api_key

        def embed(self, texts, timeout_s):
            sent.append((self.url, self.key))
            return [[0.0, 1.0]]

    def get(url, headers, timeout):
        sent.append((url, headers.get("Authorization", "")))
        return httpx.Response(200, json={"data": [{"id": "m"}]}, request=httpx.Request("GET", url))

    import httpx
    monkeypatch.setattr(runtime, "ChatModel", Model)
    monkeypatch.setattr(runtime, "Embedder", Embed)
    monkeypatch.setattr(httpx, "get", get)
    client.put("/v1/config", json={"llm_url": "https://llm.example/v1", "llm_model": "m", "llm_api_key": "sk-saved",
                                   "embed_url": "http://emb.example:8080/v1", "embed_model": "e",
                                   "embed_api_key": "ek-saved"})

    def test(**body):
        sent.clear()
        return client.post("/v1/config/test", json=body).json(), sent[-1]

    assert test(kind="llm")[1] == ("https://llm.example/v1", "sk-saved")
    assert test(kind="llm", url="https://LLM.example:443/other/v1")[1][1] == "sk-saved"  # same host
    out, call = test(kind="llm", url="https://evil.example/v1")
    assert call == ("https://evil.example/v1", "") and out["ok"] is False
    assert "https://llm.example" in out["error"]  # says why the saved key was not used
    assert test(kind="llm", url="https://evil.example/v1", api_key="sk-typed")[1][1] == "sk-typed"
    assert test(kind="llm", url="http://llm.example/v1")[1][1] == ""  # another scheme is another host
    assert test(kind="embeddings")[1][1] == "ek-saved"
    assert test(kind="embeddings", url="http://emb.example:8081/v1")[1][1] == ""  # another port too

    def models(**body):
        sent.clear()
        client.post("/v1/config/models", json=body)
        return sent[-1][1]

    assert models(url="https://llm.example/v1") != "" and "sk-saved" in models(url="https://llm.example/v1")
    assert models(url="https://evil.example/v1") == ""
    assert models(url="https://evil.example/v1", api_key="sk-typed") == "Bearer sk-typed"
    assert models(kind="embeddings", url="http://emb.example:8080/v1") == "Bearer ek-saved"
    assert models(kind="embeddings", url="https://evil.example/v1") == ""


def test_moving_an_endpoint_to_another_host_drops_its_saved_key(client):
    """Otherwise the worker would send the saved key to whatever host the endpoint was changed to."""
    def put(**body):
        return client.put("/v1/config", json=body).json()

    assert put(llm_url="https://llm.example/v1", llm_model="m", llm_api_key="sk-saved")["llm"]["api_key_set"] is True
    assert put(llm_model="m2")["llm"]["api_key_set"] is True
    assert put(llm_url="https://llm.example/other/v1")["llm"]["api_key_set"] is True  # same host
    moved = put(llm_url="https://evil.example/v1", llm_model="m")
    assert moved["llm"]["api_key_set"] is False and moved["llm"]["url"] == "https://evil.example/v1"
    assert put(llm_url="https://llm.example/v1")["llm"]["api_key_set"] is False  # gone, not remembered
    assert put(llm_url="https://other.example/v1", llm_api_key="sk-other")["llm"]["api_key_set"] is True
    assert put(embed_url="http://emb.example/v1", embed_model="e", embed_api_key="ek")["embeddings"]["api_key_set"]
    assert put(embed_url="http://127.0.0.1:11434/v1")["embeddings"]["api_key_set"] is False


def test_an_environment_key_stays_with_the_environment_host(migrated):
    with make_client(migrated, llm_url="https://env.example/v1", llm_model="m", llm_api_key="sk-env") as c:
        away = c.put("/v1/config", json={"llm_url": "https://other.example/v1"}).json()
        assert away["llm"]["api_key_set"] is False
        back = c.put("/v1/config", json={"llm_url": "https://env.example/v1"}).json()
        assert back["llm"]["api_key_set"] is True and "llm_api_key" not in back["overridden"]
        reset = c.put("/v1/config", json={"llm_url": "https://other.example/v1"}).json()
        assert reset["llm"]["api_key_set"] is False
        assert c.put("/v1/config", json={"llm_url": None}).json()["llm"]["api_key_set"] is True  # env default


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
