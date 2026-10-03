"""OpenAI-compatible clients (Ollama, OpenRouter, vLLM, LM Studio, …). Worker/off-request use only,
except `Embedder.embed` which the request path calls with its own short timeout."""

from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from . import vertex
from .canonical import storable


class LLMError(RuntimeError):
    pass


class ReplyError(LLMError):
    """A call that was made but gave nothing usable: no response (`raw` empty), an error status, or a reply that is
    not the JSON object asked for. It keeps what came back (`raw`, the whole text) and the call's usage (`usage_of`:
    the call counted, tokens only as the provider reported them), so a caller can keep both (ADR 0064 item 4)."""

    def __init__(self, message: str, raw: str, usage: dict[str, Any]):
        super().__init__(message)
        self.raw = raw
        self.usage = usage


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def chat_headers(api_key: str) -> dict[str, str]:
    """Headers for the extraction LLM: a service-account JSON key becomes a Vertex access token (ADR 0022)."""
    try:
        info = vertex.service_account_info(api_key)
        return _headers(vertex.access_token(info) if info is not None else api_key)
    except vertex.VertexAuthError as exc:
        raise LLMError(str(exc)) from None


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


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def usage_of(body: Any, started: float) -> dict[str, Any]:
    """One model call's usage as the provider reported it (ADR 0051, D61): never estimated. `input`, `output`,
    `cached` and `reasoning` appear only when the response's `usage` carries them; without them the call is
    "not reported". `calls`, `ms` and the model the provider answered with are always kept."""
    out: dict[str, Any] = {"calls": 1, "ms": round((time.monotonic() - started) * 1000)}
    if not isinstance(body, dict):
        return out
    if isinstance(body.get("model"), str):
        out["model"] = storable(body["model"])[:200]
    usage = body.get("usage")
    if not isinstance(usage, dict):
        return out
    details = {"cached": (usage.get("prompt_tokens_details"), "cached_tokens"),
               "reasoning": (usage.get("completion_tokens_details"), "reasoning_tokens")}
    for key, value in (("input", usage.get("prompt_tokens")), ("output", usage.get("completion_tokens")),
                       *((k, d.get(f) if isinstance(d, dict) else None) for k, (d, f) in details.items())):
        if (n := _count(value)) is not None:
            out[key] = n
    return out


NO_CALL: dict[str, Any] = {"calls": 0}  # a row written without asking the model (too little text)


def metered(complete: Any, system: str, user: str) -> tuple[dict[str, Any], str, dict[str, Any] | None]:
    """Call `complete` (a `ChatModel.complete_metered`, or a test's two-value stand-in whose usage is unknown)."""
    parsed, raw, *usage = complete(system, user)
    return parsed, raw, usage[0] if usage else None


def embedded(embedder: Any, text: str) -> tuple[list[float], dict[str, Any] | None]:
    """Embed one chunk with `Embedder.embed_metered`, or a test's `embed`-only stand-in whose usage is unknown."""
    if hasattr(embedder, "embed_metered"):
        vectors, usage = embedder.embed_metered([text], timeout_s=60)
        return vectors[0], usage
    return embedder.embed([text], timeout_s=60)[0], None


TOKEN_FIELDS = ("input", "output", "cached", "reasoning")


def reported(usage: dict[str, Any] | None) -> bool:
    """The provider reported some token count for the call (any of them: one may come without the others)."""
    return bool(usage) and any(k in usage for k in TOKEN_FIELDS)


class ChatModel:
    def __init__(self, url: str, model: str, api_key: str = "", timeout_s: float = 120.0, json_mode: bool = True):
        self.url = url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.json_mode = json_mode

    def complete_json(self, system: str, user: str) -> tuple[dict[str, Any], str]:
        parsed, text, _ = self.complete_metered(system, user)
        return parsed, text

    def complete_metered(self, system: str, user: str) -> tuple[dict[str, Any], str, dict[str, Any]]:
        """`complete_json` and the call's usage (`usage_of`). The worker's handlers pass this one."""
        body: dict[str, Any] = {
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if self.json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = chat_headers(self.api_key)
        started = time.monotonic()
        try:
            res = httpx.post(f"{self.url}/chat/completions", json=body, headers=headers, timeout=self.timeout_s)
        except httpx.HTTPError as exc:
            raise ReplyError(f"request failed: {exc}", "", usage_of(None, started)) from exc
        if res.status_code >= 400:
            raise ReplyError(f"HTTP {res.status_code}: {res.text[:300]}", storable(res.text), usage_of(None, started))
        reply: Any = None
        try:
            reply = res.json()
            text = reply["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError, ValueError) as exc:  # TypeError: a null message or choices
            raise ReplyError(f"unexpected response shape: {exc}", storable(res.text), usage_of(reply, started)) from exc
        if not isinstance(text, str):
            raise ReplyError(f"unexpected response shape: content is {type(text).__name__}, not text",
                             storable(res.text), usage_of(reply, started))
        text = storable(text)
        # a model can escape half an emoji (ADR 0029)
        try:
            parsed = parse_json_object(text)
        except LLMError as exc:
            raise ReplyError(str(exc), text, usage_of(reply, started)) from None
        return storable(parsed), text, usage_of(reply, started)


class Embedder:
    def __init__(self, url: str, model: str, api_key: str = ""):
        self.url = url.rstrip("/")
        self.model = model
        self.api_key = api_key

    def embed(self, texts: list[str], timeout_s: float) -> list[list[float]]:
        return self.embed_metered(texts, timeout_s)[0]

    def embed_metered(self, texts: list[str], timeout_s: float) -> tuple[list[list[float]], dict[str, Any]]:
        """`embed` and the call's usage (`usage_of`; an embedding reports input tokens only)."""
        started = time.monotonic()
        try:
            res = httpx.post(f"{self.url}/embeddings", json={"model": self.model, "input": texts},
                             headers=_headers(self.api_key), timeout=timeout_s)
        except httpx.HTTPError as exc:
            raise LLMError(f"embedding request failed: {exc}") from exc
        if res.status_code >= 400:
            raise LLMError(f"embedding HTTP {res.status_code}: {res.text[:300]}")
        try:
            reply = res.json()
            data = sorted(reply["data"], key=lambda d: d.get("index", 0))
            return [list(map(float, d["embedding"])) for d in data], usage_of(reply, started)
        except (KeyError, ValueError, TypeError) as exc:
            raise LLMError(f"unexpected embedding response: {exc}") from exc
