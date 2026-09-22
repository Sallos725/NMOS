"""OpenAI-compatible clients (Ollama, OpenRouter, vLLM, LM Studio, …). Worker/off-request use only,
except `Embedder.embed` which the request path calls with its own short timeout."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx


class LLMError(RuntimeError):
    pass


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse the first JSON object in a model reply (tolerates code fences and prose)."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise LLMError("no JSON object in model reply") from None
        try:
            value = json.loads(cleaned[start: end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError(f"invalid JSON in model reply: {exc}") from None
    if not isinstance(value, dict):
        raise LLMError("model reply is not a JSON object")
    return value


class ChatModel:
    def __init__(self, url: str, model: str, api_key: str = "", timeout_s: float = 120.0, json_mode: bool = True):
        self.url = url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.json_mode = json_mode

    def complete_json(self, system: str, user: str) -> tuple[dict[str, Any], str]:
        body: dict[str, Any] = {
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if self.json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            res = httpx.post(f"{self.url}/chat/completions", json=body, headers=_headers(self.api_key),
                             timeout=self.timeout_s)
        except httpx.HTTPError as exc:
            raise LLMError(f"request failed: {exc}") from exc
        if res.status_code >= 400:
            raise LLMError(f"HTTP {res.status_code}: {res.text[:300]}")
        try:
            text = res.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"unexpected response shape: {exc}") from exc
        return parse_json_object(text), text


class Embedder:
    def __init__(self, url: str, model: str, api_key: str = ""):
        self.url = url.rstrip("/")
        self.model = model
        self.api_key = api_key

    def embed(self, texts: list[str], timeout_s: float) -> list[list[float]]:
        try:
            res = httpx.post(f"{self.url}/embeddings", json={"model": self.model, "input": texts},
                             headers=_headers(self.api_key), timeout=timeout_s)
        except httpx.HTTPError as exc:
            raise LLMError(f"embedding request failed: {exc}") from exc
        if res.status_code >= 400:
            raise LLMError(f"embedding HTTP {res.status_code}: {res.text[:300]}")
        try:
            data = sorted(res.json()["data"], key=lambda d: d.get("index", 0))
            return [list(map(float, d["embedding"])) for d in data]
        except (KeyError, ValueError, TypeError) as exc:
            raise LLMError(f"unexpected embedding response: {exc}") from exc
