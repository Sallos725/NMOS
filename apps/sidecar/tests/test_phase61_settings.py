"""PHASE-61 S1, S1b, S3 (A4): the extra request body and the temperature switch as settings.

The environment, the panel's save (422 with the setting and the reason, nothing saved), a saved value the startup
would refuse (ignored with one warning), and the view. No model is called here."""

from __future__ import annotations

import logging

import psycopg
import pytest
from psycopg.types.json import Jsonb

from conftest import make_client
from nmos_sidecar import config, runtime
from nmos_sidecar.config import EXTRA_BODY_MAX_BYTES, RESERVED_BODY_KEYS, Settings, extra_body_error

ENV = ("NMOS_LLM_EXTRA_BODY", "NMOS_LLM_NO_TEMPERATURE")
EFFORT = {"reasoning": {"effort": "low"}}
CREDENTIAL = "sk-or-v1-0123456789abcdef"  # a made-up key value: never echoed anywhere


@pytest.fixture
def clean_env(monkeypatch):
    for name in ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


# --- the pure check --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("body", [
    {},
    EFFORT,
    {"max_tokens": 800},
    {"max_completion_tokens": 800},
    {"reasoning": {"max_tokens": 2000, "exclude": True}},
    {"provider": {"order": ["a", "b"], "allow_fallbacks": False}},
    {"top_k": 20, "seed": 7, "stop": None, "top_p": 0.9},
    {"metadata": {"note": "세라와 카이토"}},
    {"tokenizer": "x", "tokens_per_second": 1},  # a "token" inside a longer name is not a credential
    {"a": "x" * (EXTRA_BODY_MAX_BYTES - 8)},  # exactly the limit: '{"a":"' + N + '"}'
])
def test_these_bodies_are_accepted(body):
    assert extra_body_error(body) is None


@pytest.mark.parametrize("body", [None, [], [EFFORT], "{}", 1, True, 1.5])
def test_a_body_that_is_not_an_object_is_refused(body):
    assert extra_body_error(body) == "must be a JSON object"


@pytest.mark.parametrize("name", sorted(RESERVED_BODY_KEYS))
def test_every_reserved_name_is_refused_at_the_top_level(name):
    reason = extra_body_error({name: 1})
    assert reason is not None and repr(name) in reason
    assert extra_body_error({"provider": {name: 1}}) is None  # inside another object it is the provider's own field


def test_the_reserved_names_are_the_specs():
    assert RESERVED_BODY_KEYS == {"model", "messages", "stream", "response_format", "temperature", "n", "tools",
                                  "tool_choice", "functions", "function_call"}


@pytest.mark.parametrize("key", [
    "api_key", "apikey", "apiKey", "API-KEY", "x-api-key", "openrouter_api_key",
    "authorization", "Authorization", "proxy_authorization",
    "token", "TOKEN", "access_token", "accessToken", "auth_token", "auth-token", "api_token", "bearer_token",
    "refresh_token", "id_token", "session_token",
    "secret", "client_secret", "secretKey", "password", "db_password",
])
def test_a_credential_like_key_is_refused_at_any_depth(key):
    for body in ({key: CREDENTIAL}, {"provider": {key: CREDENTIAL}}, {"list": [{"deeper": [{key: CREDENTIAL}]}]}):
        reason = extra_body_error(body)
        assert reason is not None and "credential-like" in reason, body
        assert CREDENTIAL not in reason


def test_the_credential_rule_is_on_the_key_not_the_value():
    assert extra_body_error({"user": "token"}) is None
    assert extra_body_error({"note": CREDENTIAL}) is None  # a value is not inspected (the key field is the place)


def test_the_size_limit_is_counted_as_compact_utf8_json():
    over = extra_body_error({"a": "x" * (EXTRA_BODY_MAX_BYTES - 7)})
    assert over == f"must be at most {EXTRA_BODY_MAX_BYTES} bytes as compact JSON"
    korean = "세" * ((EXTRA_BODY_MAX_BYTES - 8) // 3)  # three bytes each in UTF-8
    assert extra_body_error({"a": korean}) is None
    assert extra_body_error({"a": korean + "세"}) is not None
    assert config.canonical_body({"b": 1, "a": [1, {"d": 2, "c": 3}]}) == '{"a":[1,{"c":3,"d":2}],"b":1}'


@pytest.mark.parametrize("body", [
    {"a": float("nan")}, {"a": [float("inf")]}, {"a": "\x00"}, {"a\x00": 1}, {"a": "\ud800"},
    {"a": object()}, {"a": {1: 2}}, {"a": (1, 2)},
])
def test_a_value_json_or_the_database_cannot_carry_is_refused(body):
    assert extra_body_error(body) is not None


def test_deep_nesting_is_refused_not_a_recursion_error():
    deep: object = 1
    for _ in range(5000):
        deep = [deep]
    assert "nested deeper" in extra_body_error({"a": deep})
    shallow: object = 1
    for _ in range(config.EXTRA_BODY_MAX_DEPTH - 1):
        shallow = [shallow]
    assert extra_body_error({"a": shallow}) is None


# --- the environment -------------------------------------------------------------------------------------------------

def test_the_defaults_are_empty_and_off(clean_env):
    s = Settings()
    assert s.llm_extra_body == {} and s.llm_no_temperature is False


@pytest.mark.parametrize("text", ["", "  "])
def test_an_empty_environment_value_is_the_default(clean_env, text):
    clean_env.setenv("NMOS_LLM_EXTRA_BODY", text)
    clean_env.setenv("NMOS_LLM_NO_TEMPERATURE", "")
    s = Settings()
    assert s.llm_extra_body == {} and s.llm_no_temperature is False


def test_the_environment_sets_both(clean_env):
    clean_env.setenv("NMOS_LLM_EXTRA_BODY", '{"reasoning": {"effort": "low"}, "max_tokens": 900}')
    clean_env.setenv("NMOS_LLM_NO_TEMPERATURE", "1")
    s = Settings()
    assert s.llm_extra_body == {"reasoning": {"effort": "low"}, "max_tokens": 900} and s.llm_no_temperature is True


@pytest.mark.parametrize(("value", "on"), [("0", False), ("1", True), ("true", True)])
def test_the_switch_reads_as_the_other_switches(clean_env, value, on):
    clean_env.setenv("NMOS_LLM_NO_TEMPERATURE", value)
    assert Settings().llm_no_temperature is on


@pytest.mark.parametrize("text", [
    "{not json", "[1, 2]", '"text"', "null", '{"model": "x"}', '{"temperature": 1}',
    '{"api_key": "' + CREDENTIAL + '"}',
    '{"a": NaN}', "[" * 3000 + "]" * 3000, '{"a": "' + "x" * EXTRA_BODY_MAX_BYTES + '"}',
])
def test_an_invalid_environment_body_refuses_startup_naming_the_setting(clean_env, text):
    clean_env.setenv("NMOS_LLM_EXTRA_BODY", text)
    with pytest.raises(ValueError, match="NMOS_LLM_EXTRA_BODY") as info:
        Settings()
    assert CREDENTIAL not in str(info.value)


def test_settings_made_in_code_are_checked_too(clean_env):
    with pytest.raises(ValueError, match="NMOS_LLM_EXTRA_BODY may not set 'messages'"):
        Settings(llm_extra_body={"messages": []})
    with pytest.raises(ValueError, match="NMOS_LLM_NO_TEMPERATURE"):
        Settings(llm_no_temperature="1")  # type: ignore[arg-type]


# --- the panel: editable, refused with 422, viewed -------------------------------------------------------------------

def llm_view(c) -> dict:
    return c.get("/v1/config").json()["llm"]


def test_the_view_holds_both_at_their_defaults(client):
    view = llm_view(client)
    assert view["extra_body"] == {} and view["no_temperature"] is False


def test_the_panel_sets_and_resets_both(client):
    body = {"reasoning": {"effort": "low"}, "provider": {"order": ["a"]}, "max_tokens": 1000}
    res = client.put("/v1/config", json={"llm_extra_body": body, "llm_no_temperature": True})
    assert res.status_code == 200, res.text
    assert res.json()["llm"]["extra_body"] == body and res.json()["llm"]["no_temperature"] is True
    assert llm_view(client)["extra_body"] == body
    assert {"llm_extra_body", "llm_no_temperature"} <= set(res.json()["overridden"])
    empty = client.put("/v1/config", json={"llm_extra_body": {}, "llm_no_temperature": False}).json()["llm"]
    assert empty["extra_body"] == {} and empty["no_temperature"] is False
    reset = client.put("/v1/config", json={"llm_extra_body": None, "llm_no_temperature": None}).json()
    assert reset["llm"]["extra_body"] == {} and reset["overridden"] == []


def test_the_saved_body_outlives_a_restart(migrated):
    with make_client(migrated) as c:
        assert c.put("/v1/config", json={"llm_extra_body": EFFORT, "llm_no_temperature": True}).status_code == 200
    with make_client(migrated) as c:
        assert llm_view(c)["extra_body"] == EFFORT and llm_view(c)["no_temperature"] is True


@pytest.mark.parametrize(("update", "reason"), [
    ({"llm_extra_body": [1]}, "must be a JSON object"),
    ({"llm_extra_body": "{}"}, "must be a JSON object"),
    ({"llm_extra_body": 1}, "must be a JSON object"),
    ({"llm_extra_body": {"model": "other"}}, "may not set 'model'"),
    ({"llm_extra_body": {"temperature": 0.7}}, "may not set 'temperature'"),
    ({"llm_extra_body": {"response_format": {"type": "text"}}}, "may not set 'response_format'"),
    ({"llm_extra_body": {"stream": True}}, "may not set 'stream'"),
    ({"llm_extra_body": {"provider": {"api_key": CREDENTIAL}}}, "credential-like key (provider.api_key)"),
    ({"llm_extra_body": {"Authorization": f"Bearer {CREDENTIAL}"}}, "credential-like key (Authorization)"),
    ({"llm_extra_body": {"a": "x" * EXTRA_BODY_MAX_BYTES}}, f"at most {EXTRA_BODY_MAX_BYTES} bytes"),
    ({"llm_no_temperature": "1"}, "expected a JSON boolean"),
    ({"llm_no_temperature": 1}, "expected a JSON boolean"),
])
def test_a_refused_value_is_a_422_naming_the_setting_and_nothing_is_saved(client, update, reason):
    res = client.put("/v1/config", json=update | {"recall_top_k": 7})  # a valid key in the same save is not saved
    assert res.status_code == 422, res.text
    (detail,) = res.json()["detail"]
    (key,) = update
    assert detail.startswith(f"{key}: ") and reason in detail
    assert CREDENTIAL not in res.text
    assert client.get("/v1/config").json()["overridden"] == []


def test_a_preview_refuses_the_same_values(client):
    res = client.post("/v1/config/preview", json={"llm_extra_body": {"messages": []}})
    assert res.status_code == 422 and res.json()["detail"] == [
        "llm_extra_body: may not set 'messages': the request sets it itself"]


def test_both_are_editable_and_neither_is_secret():
    assert runtime.EDITABLE["llm_extra_body"] is dict and runtime.EDITABLE["llm_no_temperature"] is bool
    assert not {"llm_extra_body", "llm_no_temperature"} & runtime.SECRET
    assert {"llm_extra_body", "llm_no_temperature"} <= set(runtime.STARTUP_CHECKED)


# --- a saved value the startup check would refuse (a restored row, a downgrade) is ignored ---------------------------

@pytest.mark.parametrize(("key", "value"), [
    ("llm_extra_body", {"model": "other"}), ("llm_extra_body", {"token": CREDENTIAL}), ("llm_extra_body", [1]),
    ("llm_extra_body", "text"), ("llm_no_temperature", "1"), ("llm_no_temperature", 1),
])
def test_a_saved_value_the_startup_would_refuse_is_ignored_with_one_warning(migrated, caplog, key, value):
    with psycopg.connect(migrated, autocommit=True) as conn:  # as a restore writes app_config: unvalidated
        conn.execute("INSERT INTO app_config (key, value, updated_at) VALUES (%s, %s, now())", (key, Jsonb(value)))
    runtime._ignored.clear()
    caplog.set_level(logging.WARNING, logger="nmos.runtime")
    env = {"llm_extra_body": {"provider": {"sort": "price"}}, "llm_no_temperature": True}
    with make_client(migrated, **env) as c:
        view = llm_view(c)
        assert view["extra_body"] == env["llm_extra_body"] and view["no_temperature"] is True
        assert c.put("/v1/config", json={key: value}).status_code == 422  # the panel still refuses it
        assert c.put("/v1/config", json={"recall_top_k": 6}).status_code == 200  # other saves work
        assert llm_view(c)["extra_body"] == env["llm_extra_body"]
    warned = [r for r in caplog.records if r.name == "nmos.runtime" and key in r.getMessage()]
    assert len(warned) == 1
    assert CREDENTIAL not in caplog.text
