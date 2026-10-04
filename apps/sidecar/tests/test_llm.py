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


# S1 turn 62 (2026-10-04): the same trailing comma after an assertion's last field broke the reply in every run that
# reached that state, a same-input retry included, so the job could never succeed. A comma before `}` or `]` is
# dropped, outside strings only, and only after the strict parse failed.
TURN_62_SHAPE = """```json
{
  "assertions": [
    {
      "subject": "A",
      "predicate": "trusts",
      "known_by": [
        "A",
        "B"
      ],
      "hidden_from": [],
    },
    {"subject": "B", "predicate": "trusts", "hidden_from": []}
  ],
  "roles_ended": [],
  "same_names": []
}
```"""


def test_a_trailing_comma_is_dropped(monkeypatch):
    reply = {"choices": [{"message": {"content": TURN_62_SHAPE}}]}
    monkeypatch.setattr(llm.httpx, "post", lambda url, json, headers, timeout: httpx.Response(200, json=reply))
    parsed, text = llm.ChatModel("http://fake-llm/v1", "fake").complete_json("s", "u")
    assert parsed == {"assertions": [{"subject": "A", "predicate": "trusts", "known_by": ["A", "B"], "hidden_from": []},
                                     {"subject": "B", "predicate": "trusts", "hidden_from": []}],
                      "roles_ended": [], "same_names": []}
    assert text == TURN_62_SHAPE  # the raw reply is kept as it came


@pytest.mark.parametrize("text, expected", [
    ('{"a": [1, 2,], "b": {"c": 3,},}', {"a": [1, 2], "b": {"c": 3}}),
    ('{"a": "x,}", "b": "y, ]",}', {"a": "x,}", "b": "y, ]"}),  # inside a string the comma stays
    ('{"a": "say \\",}\\" then", "b": 1 ,\n }', {"a": 'say ",}" then', "b": 1}),
    ('prose first {"a": 1,} and after', {"a": 1}),
])
def test_trailing_commas_outside_strings(text, expected):
    assert llm.parse_json_object(text) == expected


@pytest.mark.parametrize("text", [
    '{"a": 1 "b": 2}',  # a missing comma is not repaired
    '{"a": [1,, 2]}',
    '{"a": ,}',
    '{,}',
])
def test_other_broken_json_is_still_an_error(text):
    with pytest.raises(llm.LLMError, match="invalid JSON in model reply"):
        llm.parse_json_object(text)


def test_valid_json_parses_as_before():
    text = '{"a": "a,} b", "b": [{"c": ",]"}], "d": null}'
    assert llm.parse_json_object(text) == json.loads(text)
