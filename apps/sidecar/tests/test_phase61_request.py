"""PHASE-61 S3 (A1b, A2, A6): the request `ChatModel` sends with the extra body and the temperature switch, the
settings test that sends the body under test, and the unchanged error path. Stub transports only: no model call."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from nmos_sidecar import llm
from test_phase61_pins import PINNED_BODY_JSON, capture

EFFORT = {"reasoning": {"effort": "low"}, "provider": {"order": ["a", "b"]}, "max_tokens": 900}


def sent_body(monkeypatch, **kwargs: Any) -> dict[str, Any]:
    sent = capture(monkeypatch)
    llm.ChatModel("http://llm.test/v1", "model-a", "sk-test", 42.0, kwargs.pop("json_mode", True),
                  **kwargs).complete_metered("SYS", "사용자")
    (call,) = sent
    assert json.loads(call["content"]) == call["json"]
    return call["json"]


def test_the_defaults_and_an_empty_body_send_the_pinned_bytes(monkeypatch):
    for kwargs in ({}, {"extra_body": {}}, {"extra_body": None}, {"no_temperature": False}):
        sent = capture(monkeypatch)
        llm.ChatModel("http://llm.test/v1", "model-a", "sk-test", 42.0, True, **kwargs).complete_metered("SYS", "사용자")
        assert sent[0]["content"] == PINNED_BODY_JSON, kwargs


def test_the_body_is_merged_at_the_top_level_after_the_own_fields(monkeypatch):
    body = sent_body(monkeypatch, extra_body=EFFORT)
    assert list(body) == ["model", "temperature", "messages", "response_format", "reasoning", "provider", "max_tokens"]
    assert body["response_format"] == {"type": "json_object"} and body["temperature"] == 0
    assert {k: body[k] for k in EFFORT} == EFFORT


def test_the_switch_sends_no_temperature(monkeypatch):
    body = sent_body(monkeypatch, no_temperature=True)
    assert "temperature" not in body and list(body) == ["model", "messages", "response_format"]
    both = sent_body(monkeypatch, extra_body=EFFORT, no_temperature=True, json_mode=False)
    assert "temperature" not in both and "response_format" not in both and both["reasoning"] == {"effort": "low"}


def test_the_model_keeps_its_own_copy_of_the_body(monkeypatch):
    extra = {"reasoning": {"effort": "low"}}
    model = llm.ChatModel("http://llm.test/v1", "model-a", extra_body=extra)
    extra["model"] = "other"  # a later change of the caller's dict is not sent
    sent = capture(monkeypatch)
    model.complete_metered("SYS", "사용자")
    assert sent[0]["json"]["model"] == "model-a" and "other" not in sent[0]["content"].decode()


@pytest.mark.parametrize("name", ["model", "messages", "response_format", "temperature", "stream"])
def test_a_body_naming_an_own_field_never_reaches_the_request(name):
    with pytest.raises(ValueError, match=name):
        llm.ChatModel("http://llm.test/v1", "model-a", extra_body={name: 1})


def test_a_provider_that_rejects_the_body_fails_the_call_once(monkeypatch):
    """S3: the error path is the one before Phase 61; nothing is sent again without the body."""
    calls: list[dict[str, Any]] = []

    def post(url, json, headers, timeout):
        calls.append(json)
        return httpx.Response(400, json={"error": {"message": "reasoning.effort: unknown value"}})

    monkeypatch.setattr(llm.httpx, "post", post)
    with pytest.raises(llm.ReplyError, match="HTTP 400") as info:
        llm.ChatModel("http://llm.test/v1", "model-a", extra_body=EFFORT).complete_metered("SYS", "사용자")
    assert len(calls) == 1 and calls[0]["reasoning"] == {"effort": "low"}
    assert "unknown value" in str(info.value) and info.value.usage["calls"] == 1


# --- the settings test sends the body and the switch under test (A6) -------------------------------------------------

LLM_SET = {"llm_url": "http://llm.test/v1", "llm_model": "model-a"}


def settings_test(client, monkeypatch, **body: Any) -> tuple[Any, list[dict[str, Any]]]:
    sent = capture(monkeypatch)
    res = client.post("/v1/config/test", json={"kind": "llm", **body})
    return res, sent


def test_the_settings_test_sends_the_body_under_test(client, monkeypatch):
    assert client.put("/v1/config", json=LLM_SET).status_code == 200
    res, sent = settings_test(client, monkeypatch, extra_body=EFFORT, no_temperature=True)
    assert res.status_code == 200 and res.json()["ok"] is True
    body = sent[0]["json"]
    assert {k: body[k] for k in EFFORT} == EFFORT and "temperature" not in body
    assert body["response_format"] == {"type": "json_object"}
    assert client.get("/v1/config").json()["overridden"] == ["llm_model", "llm_url"]  # the test saved nothing


def test_without_the_fields_the_settings_test_sends_the_saved_ones(client, monkeypatch):
    saved = LLM_SET | {"llm_extra_body": EFFORT, "llm_no_temperature": True}
    assert client.put("/v1/config", json=saved).status_code == 200
    _, sent = settings_test(client, monkeypatch)
    assert sent[0]["json"]["reasoning"] == {"effort": "low"} and "temperature" not in sent[0]["json"]
    # an empty body and the switch off under test are tested as such, not replaced by the saved ones
    _, sent = settings_test(client, monkeypatch, extra_body={}, no_temperature=False)
    assert list(sent[0]["json"]) == ["model", "temperature", "messages", "response_format"]


def test_the_settings_test_at_the_defaults_sends_the_pinned_body(client, monkeypatch):
    assert client.put("/v1/config", json=LLM_SET).status_code == 200
    _, sent = settings_test(client, monkeypatch)
    assert list(sent[0]["json"]) == ["model", "temperature", "messages", "response_format"]
    assert sent[0]["json"]["temperature"] == 0


@pytest.mark.parametrize(("body", "detail"), [
    ({"extra_body": [1]}, ["extra_body: must be a JSON object"]),
    ({"extra_body": None}, ["extra_body: must be a JSON object"]),
    ({"extra_body": {"temperature": 1}}, ["extra_body: may not set 'temperature': the request sets it itself"]),
    ({"extra_body": {"provider": {"api_key": "sk-made-up-0123456789"}}},
     ["extra_body: may not hold a credential-like key (provider.api_key): an API key belongs in the key field, which"
      " is never shown or archived"]),
    ({"no_temperature": "yes"}, ["no_temperature: expected a JSON boolean"]),
    ({"extra_body": "x", "no_temperature": 1},
     ["extra_body: must be a JSON object", "no_temperature: expected a JSON boolean"]),
])
def test_the_settings_test_refuses_what_a_save_refuses(client, monkeypatch, body, detail):
    assert client.put("/v1/config", json=LLM_SET).status_code == 200
    res, sent = settings_test(client, monkeypatch, **body)
    assert res.status_code == 422 and res.json()["detail"] == detail
    assert sent == [] and "sk-made-up" not in res.text


def test_the_settings_test_shows_a_provider_s_rejection(client, monkeypatch):
    assert client.put("/v1/config", json=LLM_SET).status_code == 200

    def post(url, json, headers, timeout):
        return httpx.Response(400, json={"error": {"message": "unsupported parameter: reasoning"}})

    monkeypatch.setattr(llm.httpx, "post", post)
    res = client.post("/v1/config/test", json={"kind": "llm", "extra_body": EFFORT})
    assert res.status_code == 200
    out = res.json()
    assert out["ok"] is False and "HTTP 400" in out["error"] and "unsupported parameter" in out["error"]

