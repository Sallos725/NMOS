"""OpenAI-compatible chat replies: every malformed shape is an LLMError the worker retries."""

from __future__ import annotations

import json

import httpx
import pytest

from nmos_sidecar import llm


@pytest.mark.parametrize("reply", [
    {"choices": [{"message": None}]},
    {"choices": None},
    {"choices": [{"message": {"content": [{"type": "text", "text": "{}"}]}}]},
    {"choices": []},
    {},
    [],
])
def test_malformed_chat_replies_are_llm_errors(monkeypatch, reply):
    monkeypatch.setattr(llm.httpx, "post", lambda url, json, headers, timeout: httpx.Response(200, json=reply))
    with pytest.raises(llm.LLMError, match="unexpected response shape"):
        llm.ChatModel("http://fake-llm/v1", "fake").complete_json("s", "u")


def test_empty_content_is_no_json_object(monkeypatch):
    reply = {"choices": [{"message": {"content": None}}]}
    monkeypatch.setattr(llm.httpx, "post", lambda url, json, headers, timeout: httpx.Response(200, json=reply))
    with pytest.raises(llm.LLMError, match="no JSON object"):
        llm.ChatModel("http://fake-llm/v1", "fake").complete_json("s", "u")


def test_a_lone_surrogate_in_a_reply_becomes_storable(monkeypatch):
    content = '{"assertions": [{"evidence": "a \\ud800 b"}]}'  # the model escaped half an emoji
    reply = json.dumps({"choices": [{"message": {"content": content + " \ud83d"}}]})  # and cut another
    monkeypatch.setattr(llm.httpx, "post", lambda url, json, headers, timeout: httpx.Response(200, content=reply))
    parsed, text = llm.ChatModel("http://fake-llm/v1", "fake").complete_json("s", "u")
    assert parsed == {"assertions": [{"evidence": "a � b"}]}
    assert text == content + " �"
