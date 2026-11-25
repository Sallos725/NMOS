"""PHASE-61 step 2 (A1): permanent pins for what Phase 61 must not move with its settings at their defaults.

The generation keys of every builder that reads the model settings, and the exact request `ChatModel` sends, as
literals computed at 006be90 (before any Phase 61 code). No later change may edit these literals.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from base_rules import base_rules  # noqa: F401 -- autouse: the base's keys, without the revision marker (PHASE-66 part 5)
from nmos_sidecar import canonfacts, extraction, llm, reveals, summaries
from nmos_sidecar.config import Settings

BASE: dict[str, Any] = dict(
    database_url="postgresql://x",
    llm_url="http://llm.test/v1",
    llm_model="model-a",
    embed_url="http://embed.test/v1",
    embed_model="embed-a",
    llm_json_mode=True,
    extract_turns=3,
    extract_hints=40,
    embed_max_chunks=8,
    summaries=True,
    canon_facts=True,
)

# Computed at 006be90 for BASE (JSON mode on) and BASE with JSON mode off. Literal strings, never recomputed.
PINNED: dict[tuple[str, bool], str] = {
    ("extract-v15", True): "extract-8ed39e6a2cf25ffae903b29d7ac9acd9",
    ("extract-v16", True): "extract-029fac9f22f705a5130c70505c98ba49",
    ("extract-v17", True): "extract-c98f66fc178127c0e3126c8503e4b8e9",
    ("extract-v18", True): "extract-15d6e23accadb12ba64df5040859fc22",
    ("extract-v19", True): "extract-aa30ae15592772fe3e31d5aa5a571dc5",
    ("", True): "extract-029fac9f22f705a5130c70505c98ba49",  # the default compiler is extract-v16
    ("canon", True): "canon-5fb6b7fb622106e4949b20ab6e422366",
    ("summarize", True): "summarize-9ff98c40c22744e5ec947542b77f9125",
    ("reveal", True): "reveal-9b682161681128f8a06f7db566d54899",
    ("", False): "extract-e42a0da450f8271528f608a2f77d8a90",
    ("canon", False): "canon-baac9a51c885d5962c3a57174b763105",
    ("summarize", False): "summarize-2bb253dffc8b3c9dbdddc984947bed43",
    ("reveal", False): "reveal-b85774355aae26839af91c0bc42be6f4",
}


def _key(name: str, json_mode: bool) -> str:
    settings = Settings(**(BASE | {"llm_json_mode": json_mode}))
    if name == "canon":
        return canonfacts.generation(settings).key
    if name == "summarize":
        return summaries.summarizer(settings).key
    if name == "reveal":
        return reveals.generation(settings).key
    return extraction.extractor(Settings(**(BASE | {"llm_json_mode": json_mode, "extract_compiler": name}))).key


@pytest.mark.parametrize(("name", "json_mode"), sorted(PINNED))
def test_pinned_generation_keys(name, json_mode):
    """A1: every key of every generation built from the model settings, with the Phase 61 settings at defaults."""
    assert _key(name, json_mode) == PINNED[(name, json_mode)]


def test_default_specs_hold_temperature_zero_and_no_request():
    for gen in (extraction.extractor(Settings(**BASE)), canonfacts.generation(Settings(**BASE)),
                summaries.summarizer(Settings(**BASE)), reveals.generation(Settings(**BASE))):
        assert gen.spec["temperature"] == 0 and "request" not in gen.spec, gen.kind


REPLY = {"choices": [{"message": {"content": '{"ok": true}'}}]}

# The bytes httpx puts on the wire for `complete_metered("SYS", "사용자")`, captured at 006be90.
PINNED_BODY_JSON = (
    b'{"model":"model-a","temperature":0,"messages":[{"role":"system","content":"SYS"},'
    b'{"role":"user","content":"\xec\x82\xac\xec\x9a\xa9\xec\x9e\x90"}],"response_format":{"type":"json_object"}}'
)
PINNED_BODY_PLAIN = (
    b'{"model":"model-a","temperature":0,"messages":[{"role":"system","content":"SYS"},'
    b'{"role":"user","content":"\xec\x82\xac\xec\x9a\xa9\xec\x9e\x90"}]}'
)


def capture(monkeypatch) -> list[dict[str, Any]]:
    """Stub `httpx.post` as `ChatModel` calls it; record the URL, the dict, the wire bytes, headers and timeout."""
    sent: list[dict[str, Any]] = []

    def post(url, json, headers, timeout):
        request = httpx.Request("POST", url, json=json, headers=headers)
        sent.append({"url": url, "json": json, "content": request.content, "headers": headers, "timeout": timeout})
        return httpx.Response(200, json=REPLY)

    monkeypatch.setattr(llm.httpx, "post", post)
    return sent


@pytest.mark.parametrize(("json_mode", "wire"), [(True, PINNED_BODY_JSON), (False, PINNED_BODY_PLAIN)])
def test_pinned_request_body(monkeypatch, json_mode, wire):
    """A1: the request `ChatModel` sends today, byte for byte, with JSON mode on and off."""
    sent = capture(monkeypatch)
    parsed, text, usage = llm.ChatModel("http://llm.test/v1/", "model-a", "sk-test", 42.0,
                                        json_mode).complete_metered("SYS", "사용자")
    assert parsed == {"ok": True} and text == '{"ok": true}' and usage["calls"] == 1
    (call,) = sent
    assert call["url"] == "http://llm.test/v1/chat/completions"
    assert call["content"] == wire
    assert list(call["json"]) == (["model", "temperature", "messages", "response_format"] if json_mode
                                  else ["model", "temperature", "messages"])
    assert call["headers"] == {"Authorization": "Bearer sk-test"}
    assert call["timeout"] == 42.0


def test_pinned_request_body_with_positional_defaults(monkeypatch):
    """The constructor's defaults (no key, 120 s, JSON mode on) send the same body without a header."""
    sent = capture(monkeypatch)
    llm.ChatModel("http://llm.test/v1", "model-a").complete_metered("SYS", "사용자")
    (call,) = sent
    assert call["content"] == PINNED_BODY_JSON and call["headers"] == {} and call["timeout"] == 120.0
