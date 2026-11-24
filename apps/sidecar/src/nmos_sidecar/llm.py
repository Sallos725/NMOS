"""OpenAI-compatible clients (Ollama, OpenRouter, vLLM, LM Studio, …). Worker/off-request use only,
except `Embedder.embed` which the request path calls with its own short timeout."""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import re
import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from . import vertex
from .canonical import storable
from .config import RESERVED_BODY_KEYS


log = logging.getLogger("nmos.llm")


class LLMError(RuntimeError):
    """A model call that failed, or a reply that could not be used. How a call ended is data (PHASE-61 S6, ADR 0089),
    never parsed from the message: `fault` is `http`, `timeout`, `transport` or `bad_reply` when a call was made
    (None otherwise, e.g. a key that gave no token), `status` the HTTP status of an `http` fault, and `detail` the
    provider's error body (`http`), the exception's class (`timeout`, `transport`) or the kind of fault of a reply
    that could not be read (`bad_reply`: never its text). The message is what it always was."""

    def __init__(self, *args: Any, fault: str | None = None, status: int | None = None, detail: str | None = None):
        super().__init__(*args)
        self.fault = fault
        self.status = status
        self.detail = detail


class ReplyError(LLMError):
    """A call that was made but gave nothing usable: no response (`raw` empty), an error status, or a reply that is
    not the JSON object asked for. It keeps what came back (`raw`, the whole text) and the call's usage (`usage_of`:
    the call counted, tokens only as the provider reported them), so a caller can keep both (ADR 0064 item 4)."""

    def __init__(self, message: str, raw: str, usage: dict[str, Any], *, fault: str | None = None,
                 status: int | None = None, detail: str | None = None):
        super().__init__(message, fault=fault, status=status, detail=detail)
        self.raw = raw
        self.usage = usage


# What a call observer is given when a call ends (PHASE-61 S6): `started` (time.monotonic), `outcome`, `http_status`,
# `usage`, `error` (see `call_outcome`), `model`, `url`, and `api_key` only so the observer can keep it out of a row.
Observer = Callable[[dict[str, Any]], None]


def _fault(exc: httpx.HTTPError) -> str:
    return "timeout" if isinstance(exc, httpx.TimeoutException) else "transport"


def call_outcome(exc: BaseException | None) -> tuple[str, int | None, str | None] | None:
    """How a model call ended, as `(outcome, http_status, error)`: `ok`; `http` with the status and the provider's
    error (`HTTP <status>: <body>`, uncut: a log cuts it after taking any key out); `timeout` or `transport` with the
    exception's class name only; `bad_reply` with the kind of fault only, never any text of the reply. None for an
    error that made no call (it carries no `fault`)."""
    if exc is None:
        return "ok", None, None
    fault = getattr(exc, "fault", None)
    if not isinstance(exc, LLMError) or fault not in ("http", "timeout", "transport", "bad_reply"):
        return None
    if fault == "http":
        return "http", exc.status, f"HTTP {exc.status}: {exc.detail}" if exc.detail is not None else str(exc)
    return fault, None, exc.detail


def tell(observer: Observer | None, started: float, model: str, url: str, api_key: str, exc: BaseException | None,
         usage: dict[str, Any] | None) -> None:
    """Give `observer` the facts of a call that ended. Never raises: an observer's own failure is one warning, and
    the call goes on as if there were none."""
    if observer is None:
        return
    try:
        ended = call_outcome(exc)
        if ended is None:
            return
        outcome, status, error = ended
        observer({"started": started, "outcome": outcome, "http_status": status, "usage": usage, "error": error,
                  "model": model, "url": url, "api_key": api_key})
    except Exception as failure:  # noqa: BLE001 - the log never breaks the call
        log.warning("model call observer failed: %s", type(failure).__name__)


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def chat_headers(api_key: str) -> dict[str, str]:
    """Headers for the extraction LLM: a service-account JSON key becomes a Vertex access token (ADR 0022)."""
    try:
        info = vertex.service_account_info(api_key)
        return _headers(vertex.access_token(info) if info is not None else api_key)
    except vertex.VertexAuthError as exc:
        raise LLMError(str(exc)) from None


_CLOSING = re.compile(r"\s*[\]}]")


def without_trailing_commas(text: str) -> str:
    """`text` without a comma that ends a list or an object (`[1, 2,]`, `{"a": 1,}`): one right after a value and
    before `]` or `}`, outside strings. Nothing else changes: a missing, leading or doubled comma stays an error."""
    out: list[str] = []
    in_string = escaped = False
    last = ""  # the last character outside whitespace, a string's closing quote included
    for i, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
                last = ch
        elif ch == '"':
            in_string = True
        elif ch == "," and (last in ('"', "]", "}") or last.isalnum()) and _CLOSING.match(text, i + 1):
            continue
        elif not ch.isspace():
            last = ch
        out.append(ch)
    return "".join(out)


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse the first JSON object in a model reply (tolerates code fences, prose and trailing commas)."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise LLMError("no JSON object in model reply", fault="bad_reply", detail="no JSON object") from None
        try:
            value = json.loads(cleaned[start: end + 1])
        except json.JSONDecodeError as exc:
            # S1 turn 62 (2026-10-04): the same trailing comma on every attempt at temperature 0, so a retry never
            # passed it. Tried only after the strict parse failed: a valid reply parses exactly as before.
            try:
                value = json.loads(without_trailing_commas(cleaned[start: end + 1]))
            except json.JSONDecodeError:
                raise LLMError(f"invalid JSON in model reply: {exc}", fault="bad_reply",
                               detail="invalid JSON") from None
    if not isinstance(value, dict):
        raise LLMError("model reply is not a JSON object", fault="bad_reply", detail="not a JSON object")
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
    def __init__(self, url: str, model: str, api_key: str = "", timeout_s: float = 120.0, json_mode: bool = True, *,
                 extra_body: Mapping[str, Any] | None = None, no_temperature: bool = False,
                 observer: Observer | None = None):
        """`extra_body` is merged at the top level into every request (PHASE-61 S3); `no_temperature` sends none
        (S1b). Their defaults send exactly the request sent before them. `observer` is told how each call ended
        (S6); None, the default, tells no one."""
        self.url = url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.json_mode = json_mode
        self.extra_body = dict(extra_body or {})
        # never overwrite the request's own fields: a body naming one is refused before it gets here (`config`)
        if clash := sorted(RESERVED_BODY_KEYS & self.extra_body.keys()):
            raise ValueError(f"the extra request body may not set {', '.join(clash)}")
        self.no_temperature = no_temperature
        self.observer = observer

    def observed(self, observer: Observer | None) -> ChatModel:
        """A copy that tells `observer` how each call ended (PHASE-61 S6); this model is unchanged, so one model shared
        by threads gets one observer per job."""
        twin = copy.copy(self)
        twin.observer = observer
        return twin

    def complete_json(self, system: str, user: str) -> tuple[dict[str, Any], str]:
        parsed, text, _ = self.complete_metered(system, user)
        return parsed, text

    def complete_metered(self, system: str, user: str) -> tuple[dict[str, Any], str, dict[str, Any]]:
        """`complete_json` and the call's usage (`usage_of`). The worker's handlers pass this one."""
        started = time.monotonic()
        try:
            out = self._complete_metered(system, user)
        except LLMError as exc:
            tell(self.observer, started, self.model, self.url, self.api_key, exc, getattr(exc, "usage", None))
            raise
        tell(self.observer, started, self.model, self.url, self.api_key, None, out[2])
        return out

    def _complete_metered(self, system: str, user: str) -> tuple[dict[str, Any], str, dict[str, Any]]:
        body: dict[str, Any] = {
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if self.no_temperature:
            del body["temperature"]
        if self.json_mode:
            body["response_format"] = {"type": "json_object"}
        # The extra body after the own fields; a provider that rejects it fails the call as any error does: it is never
        # sent again without it (PHASE-61 S3, ADR 0088 item 4).
        body = {**body, **self.extra_body}
        headers = chat_headers(self.api_key)
        started = time.monotonic()
        try:
            res = httpx.post(f"{self.url}/chat/completions", json=body, headers=headers, timeout=self.timeout_s)
        except httpx.HTTPError as exc:
            raise ReplyError(f"request failed: {exc}", "", usage_of(None, started), fault=_fault(exc),
                             detail=type(exc).__name__) from exc
        reply: Any = None
        if res.status_code >= 400:
            try:  # an error body can still report usage; one that does not stays "not reported"
                reply = res.json()
            except ValueError:
                pass
            whole = storable(res.text)
            raise ReplyError(f"HTTP {res.status_code}: {res.text[:300]}", whole, usage_of(reply, started),
                             fault="http", status=res.status_code, detail=whole)
        try:
            reply = res.json()
            text = reply["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError, ValueError) as exc:  # TypeError: a null message or choices
            raise ReplyError(f"unexpected response shape: {exc}", storable(res.text), usage_of(reply, started),
                             fault="bad_reply",
                             detail="not JSON" if isinstance(exc, ValueError) else "unexpected response shape") from exc
        if not isinstance(text, str):
            raise ReplyError(f"unexpected response shape: content is {type(text).__name__}, not text",
                             storable(res.text), usage_of(reply, started), fault="bad_reply",
                             detail="content is not text")
        text = storable(text)
        # a model can escape half an emoji (ADR 0029)
        try:
            parsed = parse_json_object(text)
        except LLMError as exc:
            raise ReplyError(str(exc), text, usage_of(reply, started), fault="bad_reply",
                             detail=exc.detail if exc.fault == "bad_reply" else "not a JSON object") from None
        return storable(parsed), text, usage_of(reply, started)


class Embedder:
    def __init__(self, url: str, model: str, api_key: str = "", *, observer: Observer | None = None):
        """`observer` is told how each call ended (PHASE-61 S6); None, the default and the request path's, tells no
        one."""
        self.url = url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.observer = observer

    def observed(self, observer: Observer | None) -> Embedder:
        """A copy that tells `observer` how each call ended; this embedder is unchanged (see `ChatModel.observed`)."""
        twin = copy.copy(self)
        twin.observer = observer
        return twin

    def _told(self, started: float, call: Callable[[], tuple[list[list[float]], dict[str, Any]]]
              ) -> tuple[list[list[float]], dict[str, Any]]:
        try:
            out = call()
        except LLMError as exc:
            tell(self.observer, started, self.model, self.url, self.api_key, exc, None)
            raise
        tell(self.observer, started, self.model, self.url, self.api_key, None, out[1])
        return out

    def embed(self, texts: list[str], timeout_s: float) -> list[list[float]]:
        """Query transport: one deadline covers the entire HTTP exchange, including a trickling body.

        Called on QueryEmbedding's bounded worker thread. Worker batches retain `embed_metered` and its
        separate, longer timeout; neither the payload nor embedding generation changes.
        """
        started = time.monotonic()

        async def request() -> httpx.Response:
            async with asyncio.timeout(timeout_s):
                async with httpx.AsyncClient(timeout=timeout_s) as client:
                    return await client.post(f"{self.url}/embeddings", json={"model": self.model, "input": texts},
                                             headers=_headers(self.api_key))

        def call() -> tuple[list[list[float]], dict[str, Any]]:
            try:
                res = asyncio.run(request())
            except TimeoutError as exc:
                raise LLMError(f"embedding request exceeded {timeout_s:g} s total deadline", fault="timeout",
                               detail=type(exc).__name__) from exc
            except httpx.HTTPError as exc:
                raise LLMError(f"embedding request failed: {exc}", fault=_fault(exc),
                               detail=type(exc).__name__) from exc
            return self._decode(res, started)

        return self._told(started, call)[0]

    def embed_metered(self, texts: list[str], timeout_s: float) -> tuple[list[list[float]], dict[str, Any]]:
        """`embed` and the call's usage (`usage_of`; an embedding reports input tokens only, some as the total)."""
        started = time.monotonic()

        def call() -> tuple[list[list[float]], dict[str, Any]]:
            try:
                res = httpx.post(f"{self.url}/embeddings", json={"model": self.model, "input": texts},
                                 headers=_headers(self.api_key), timeout=timeout_s)
            except httpx.HTTPError as exc:
                raise LLMError(f"embedding request failed: {exc}", fault=_fault(exc),
                               detail=type(exc).__name__) from exc
            return self._decode(res, started)

        return self._told(started, call)

    @staticmethod
    def _decode(res: httpx.Response, started: float) -> tuple[list[list[float]], dict[str, Any]]:
        if res.status_code >= 400:
            raise LLMError(f"embedding HTTP {res.status_code}: {res.text[:300]}", fault="http", status=res.status_code,
                           detail=storable(res.text))
        try:
            reply = res.json()
            data = sorted(reply["data"], key=lambda d: d.get("index", 0))
            usage = usage_of(reply, started)
            # An embedding has no output, so a provider that reports `total_tokens` alone (Voyage) reported its input.
            if "input" not in usage and isinstance(reply.get("usage"), dict):
                if (total := _count(reply["usage"].get("total_tokens"))) is not None:
                    usage["input"] = total
            return [list(map(float, d["embedding"])) for d in data], usage
        except (KeyError, ValueError, TypeError) as exc:
            raise LLMError(f"unexpected embedding response: {exc}", fault="bad_reply",
                           detail="not JSON" if isinstance(exc, json.JSONDecodeError)
                           else "unexpected response shape") from exc
