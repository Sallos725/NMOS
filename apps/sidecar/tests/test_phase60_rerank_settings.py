"""PHASE-60 S5 (ADR 0084 items 4, 6, 7): the reranker's settings, its key as a credential, and the archive's refusal.

No recall wiring here: these tests only check that the reranker is configured, redacted, bound to its host and never
archived. Nothing calls a reranker."""

from __future__ import annotations

import logging

import pytest

from conftest import make_client
from nmos_sidecar import canonfacts, extraction, rerank, reveals, summaries, vectors
from nmos_sidecar.config import Settings
from nmos_sidecar.retrieval import RECORDED, RecallOptions
from simchat import SimChat
from test_archive import export, read
from test_generations import LLM
from test_phase60_pins import BASE, PINNED
from test_sidecar_integration import recall, sync

RERANK_ENV = ("NMOS_RERANK_URL", "NMOS_RERANK_MODEL", "NMOS_RERANK_API_KEY", "NMOS_RERANK_TIMEOUT_MS",
              "NMOS_RERANK_FORMAT")


@pytest.fixture
def clean_env(monkeypatch):
    for name in RERANK_ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_the_defaults_leave_the_reranker_off(clean_env):
    s = Settings()
    assert (s.rerank_url, s.rerank_model, s.rerank_api_key) == ("", "", "")
    assert s.rerank_timeout_ms == rerank.DEFAULT_TIMEOUT_MS == 600
    assert s.rerank_format == "standard"


def test_the_environment_sets_every_field(clean_env):
    clean_env.setenv("NMOS_RERANK_URL", "http://rerank.test/v1")
    clean_env.setenv("NMOS_RERANK_MODEL", "rerank-a")
    clean_env.setenv("NMOS_RERANK_API_KEY", "rk-env-0123456789")
    clean_env.setenv("NMOS_RERANK_TIMEOUT_MS", "900")
    clean_env.setenv("NMOS_RERANK_FORMAT", "standard")
    s = Settings()
    assert (s.rerank_url, s.rerank_model, s.rerank_api_key) == ("http://rerank.test/v1", "rerank-a", "rk-env-0123456789")
    assert (s.rerank_timeout_ms, s.rerank_format) == (900, "standard")


def test_an_empty_environment_value_is_the_default(clean_env):
    """The compose files pass an unset variable as an empty string."""
    clean_env.setenv("NMOS_RERANK_TIMEOUT_MS", "")
    clean_env.setenv("NMOS_RERANK_FORMAT", "")
    s = Settings()
    assert (s.rerank_timeout_ms, s.rerank_format) == (rerank.DEFAULT_TIMEOUT_MS, "standard")


@pytest.mark.parametrize("value", ["49", "5001", "0", "-1"])
def test_a_timeout_out_of_range_is_refused_at_startup(clean_env, value):
    clean_env.setenv("NMOS_RERANK_TIMEOUT_MS", value)
    with pytest.raises(ValueError, match="NMOS_RERANK_TIMEOUT_MS"):
        Settings()


@pytest.mark.parametrize("value", ["50", "5000"])
def test_the_timeout_bounds_are_accepted(clean_env, value):
    clean_env.setenv("NMOS_RERANK_TIMEOUT_MS", value)
    assert Settings().rerank_timeout_ms == int(value)


@pytest.mark.parametrize("value", ["systemone", "Standard", "other"])
def test_an_unknown_format_is_refused_at_startup(clean_env, value):
    clean_env.setenv("NMOS_RERANK_FORMAT", value)
    with pytest.raises(ValueError, match=r"NMOS_RERANK_FORMAT must be standard, not"):
        Settings()


def test_the_format_and_timeout_are_checked_for_every_settings(clean_env):
    with pytest.raises(ValueError, match="NMOS_RERANK_FORMAT"):
        Settings(rerank_format="other")
    with pytest.raises(ValueError, match="NMOS_RERANK_TIMEOUT_MS"):
        Settings(rerank_timeout_ms=10)


# --- runtime: editable, redacted, bound to its host ------------------------------------------------------------------

URL, MODEL, SAVED_KEY = "http://rerank.test/v1", "rerank-a", "rk-saved-0123456789"
ENV_KEY = "rk-environment-0123456789"


def view_of(c) -> dict:
    return c.get("/v1/config").json()["rerank"]


def test_unconfigured_the_view_says_off(client):
    view = view_of(client)
    assert {k: v for k, v in view.items() if k != "note"} == {
        "url": "", "model": "", "timeout_ms": 600, "format": "standard", "key_set": False, "configured": False}
    assert "sent" in view["note"] and "endpoint" in view["note"]


def test_the_panel_sets_and_resets_every_field(client):
    res = client.put("/v1/config", json={"rerank_url": URL, "rerank_model": MODEL, "rerank_api_key": SAVED_KEY,
                                         "rerank_timeout_ms": 1200, "rerank_format": "standard"})
    assert res.status_code == 200, res.text
    view = res.json()["rerank"]
    assert {k: view[k] for k in ("url", "model", "timeout_ms", "format", "key_set", "configured")} == {
        "url": URL, "model": MODEL, "timeout_ms": 1200, "format": "standard", "key_set": True, "configured": True}
    assert SAVED_KEY not in res.text  # the PUT's answer redacts it
    got = client.get("/v1/config")
    assert got.json()["rerank"]["key_set"] is True and SAVED_KEY not in got.text  # and so does GET
    reset = client.put("/v1/config", json={k: None for k in (
        "rerank_url", "rerank_model", "rerank_api_key", "rerank_timeout_ms", "rerank_format")}).json()
    assert reset["rerank"]["configured"] is False and reset["rerank"]["key_set"] is False
    assert reset["rerank"]["timeout_ms"] == 600 and reset["overridden"] == []


def test_a_url_or_a_model_alone_is_not_configured(client):
    assert client.put("/v1/config", json={"rerank_url": URL}).json()["rerank"]["configured"] is False
    assert client.put("/v1/config", json={"rerank_url": None, "rerank_model": MODEL}).json()["rerank"]["configured"] is False


def test_the_saved_settings_outlive_a_restart(migrated):
    with make_client(migrated) as c:
        c.put("/v1/config", json={"rerank_url": URL, "rerank_model": MODEL, "rerank_api_key": SAVED_KEY,
                                  "rerank_timeout_ms": 800})
    with make_client(migrated) as c:
        view = view_of(c)
        assert (view["url"], view["model"], view["timeout_ms"], view["key_set"]) == (URL, MODEL, 800, True)


def test_the_environment_configures_it(migrated):
    with make_client(migrated, rerank_url=URL, rerank_model=MODEL, rerank_api_key=ENV_KEY) as c:
        res = c.get("/v1/config")
        assert res.json()["rerank"]["configured"] is True and res.json()["rerank"]["key_set"] is True
        assert ENV_KEY not in res.text


@pytest.mark.parametrize("update", [
    {"rerank_format": "other"}, {"rerank_format": ""}, {"rerank_format": 1},
    {"rerank_timeout_ms": 49}, {"rerank_timeout_ms": 5001}, {"rerank_timeout_ms": "600"}, {"rerank_timeout_ms": 1.5},
    {"rerank_url": "ftp://rerank.test"}, {"rerank_model": 3}, {"rerank_api_key": '{"private_key": "x"}'},
])
def test_a_bad_value_is_refused_and_nothing_is_saved(client, update):
    res = client.put("/v1/config", json=update)
    assert res.status_code == 422, res.text
    assert client.get("/v1/config").json()["overridden"] == []


def test_a_url_on_another_host_drops_the_saved_key(client):
    client.put("/v1/config", json={"rerank_url": URL, "rerank_model": MODEL, "rerank_api_key": SAVED_KEY})
    same_host = client.put("/v1/config", json={"rerank_url": "http://rerank.test/v2"}).json()["rerank"]
    assert same_host["key_set"] is True  # the same host keeps it
    moved = client.put("/v1/config", json={"rerank_url": "http://other-rerank.test/v1"}).json()["rerank"]
    assert moved["key_set"] is False
    back = client.put("/v1/config", json={"rerank_url": URL}).json()["rerank"]
    assert back["key_set"] is False  # a dropped key does not come back


def test_the_environment_key_is_withheld_from_another_host_and_returns_with_its_host(migrated):
    with make_client(migrated, rerank_url=URL, rerank_model=MODEL, rerank_api_key=ENV_KEY) as c:
        assert c.put("/v1/config", json={"rerank_url": "http://other-rerank.test/v1"}).json()["rerank"]["key_set"] is False
        assert c.put("/v1/config", json={"rerank_url": URL}).json()["rerank"]["key_set"] is True


def test_a_reranker_changes_no_generation_key():
    """ADR 0084 consequences: the reranker reorders, it derives nothing stored."""
    keyed = dict(rerank_url=URL, rerank_model=MODEL, rerank_api_key=SAVED_KEY, rerank_timeout_ms=900)
    for compiler in ("extract-v15", "extract-v16", "extract-v17", "extract-v18"):
        assert extraction.extractor(Settings(**BASE, **keyed, extract_compiler=compiler)).key == PINNED[compiler]
    with_rerank = Settings(**BASE, **keyed)
    assert extraction.extractor(with_rerank).key == PINNED["default"]
    assert canonfacts.generation(with_rerank).key == PINNED["canon"]
    assert summaries.summarizer(with_rerank).key == PINNED["summarize"]
    assert reveals.generation(with_rerank).key == PINNED["reveal"]
    assert vectors.projection(with_rerank).key == PINNED["embed"]


def test_saving_the_reranker_queues_nothing(migrated):
    with make_client(migrated, **LLM) as c:
        before = c.get("/v1/health").json()["generations"]
        res = c.put("/v1/config", json={"rerank_url": URL, "rerank_model": MODEL, "rerank_api_key": SAVED_KEY,
                                        "rerank_timeout_ms": 700})
        assert res.status_code == 200 and res.json()["queued_jobs"] == 0
        assert c.get("/v1/health").json()["generations"] == before


def test_no_log_record_holds_the_key(client, caplog):
    caplog.set_level(logging.DEBUG)
    res = client.put("/v1/config", json={"rerank_url": URL, "rerank_model": MODEL, "rerank_api_key": SAVED_KEY})
    assert res.status_code == 200
    client.get("/v1/config")
    assert caplog.records  # the capture is live
    assert not [r for r in caplog.records if SAVED_KEY in r.getMessage() or SAVED_KEY in repr(r.args)]


# --- the request's recall options carry the configured reranker; nothing reads it yet --------------------------------

def captured_options(monkeypatch) -> list:
    from nmos_sidecar import api

    seen: list = []
    original = api.retrieve

    def spy(conn, body, options, *args, **kwargs):
        seen.append(options)
        return original(conn, body, options, *args, **kwargs)

    monkeypatch.setattr(api, "retrieve", spy)
    return seen


def one_recall(c) -> dict:
    chat = SimChat()
    chat.user("하나 keeps the brass key.")
    chat.reply("Noted.")
    chat.user("Where is the key?")
    sync(c, chat)
    return recall(c, chat, "Where is the key?")


def test_the_options_default_to_no_reranker_and_never_record_one():
    assert RecallOptions().reranker is None
    assert "reranker" not in RECORDED


def test_unconfigured_a_request_has_no_reranker(client, monkeypatch):
    seen = captured_options(monkeypatch)
    one_recall(client)
    assert seen and seen[-1].reranker is None


def test_a_configured_reranker_reaches_the_request_and_stays_out_of_its_trace(client, monkeypatch):
    seen = captured_options(monkeypatch)
    client.put("/v1/config", json={"rerank_url": URL, "rerank_model": MODEL, "rerank_api_key": SAVED_KEY,
                                   "rerank_timeout_ms": 900})
    out = one_recall(client)
    assert seen[-1].reranker == rerank.Reranker(url=URL, model=MODEL, api_key=SAVED_KEY, timeout_ms=900,
                                                format="standard")
    trace = client.get(f"/v1/trace/{out['trace_id']}")
    assert trace.status_code == 200 and SAVED_KEY not in trace.text
    client.put("/v1/config", json={"rerank_model": None})  # a URL alone is off again
    one_recall(client)
    assert seen[-1].reranker is None


def test_a_blank_model_from_the_environment_is_off(migrated, monkeypatch):
    seen = captured_options(monkeypatch)
    with make_client(migrated, rerank_url=URL, rerank_model="  ") as c:
        one_recall(c)
        assert c.get("/v1/config").json()["rerank"]["configured"] is False
    assert seen[-1].reranker is None


# --- the archive: the key is a credential (D60); the other four settings archive like any other ----------------------

def pasted(c, secret: str) -> None:
    chat = SimChat()
    chat.user(f"세라 said the code was {secret}, keep it")  # a key pasted into a chat by mistake
    chat.reply("Noted.")
    sync(c, chat)


def refused(c, secret: str) -> None:
    res = c.get("/v1/archive")
    assert res.status_code == 409 and "credential" in res.json()["detail"]
    assert secret not in res.text  # the refusal names no value


def test_a_saved_key_anywhere_refuses_the_export(client):
    assert client.put("/v1/config", json={"rerank_url": URL, "rerank_model": MODEL,
                                         "rerank_api_key": SAVED_KEY}).status_code == 200
    pasted(client, SAVED_KEY)
    refused(client, SAVED_KEY)


def test_the_environment_key_anywhere_refuses_the_export(migrated):
    with make_client(migrated, rerank_url=URL, rerank_model=MODEL, rerank_api_key=ENV_KEY) as c:
        pasted(c, ENV_KEY)
        refused(c, ENV_KEY)


def test_an_environment_key_replaced_in_the_panel_is_still_looked_for(migrated):
    with make_client(migrated, rerank_url=URL, rerank_model=MODEL, rerank_api_key=ENV_KEY) as c:
        assert c.put("/v1/config", json={"rerank_api_key": SAVED_KEY}).status_code == 200
        pasted(c, ENV_KEY)
        refused(c, ENV_KEY)


def test_the_key_is_never_an_archived_setting_and_the_other_four_are(client):
    assert client.put("/v1/config", json={"rerank_url": URL, "rerank_model": MODEL, "rerank_api_key": SAVED_KEY,
                                         "rerank_timeout_ms": 800, "rerank_format": "standard"}).status_code == 200
    _, tables, raw = read(export(client))
    settings = {r["key"]: r["value"] for r in tables["app_config"]}
    assert "rerank_api_key" not in settings
    assert {k: settings[k] for k in ("rerank_url", "rerank_model", "rerank_timeout_ms", "rerank_format")} == {
        "rerank_url": URL, "rerank_model": MODEL, "rerank_timeout_ms": 800, "rerank_format": "standard"}
    assert not any(SAVED_KEY.encode() in body for body in raw.values())


def test_a_rerank_endpoint_that_may_carry_a_key_is_left_out(client):
    url = "https://rerank.example/v1?key=abc"
    assert client.put("/v1/config", json={"rerank_url": url, "rerank_model": MODEL}).status_code == 200
    manifest, tables, raw = read(export(client))
    settings = {r["key"]: r["value"] for r in tables["app_config"]}
    assert "rerank_url" not in settings and settings["rerank_model"] == MODEL
    assert manifest["omitted_settings"] == ["rerank_url"]
    assert not any(b"key=abc" in body for body in raw.values())
