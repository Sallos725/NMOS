"""Opt-in standard reranker client (Phase 60 S5, ADR 0084).

Request-path non-generative rerank call over the sidecar's `httpx` client:
one bounded POST to `<url>/rerank`, failing open (`None`) on any timeout,
HTTP error, connection error, or malformed response. Pure parsing and
reordering live alongside the transport so they can be tested without HTTP.
"""

from __future__ import annotations

import asyncio
import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, TypeVar
from urllib.parse import urlsplit, urlunsplit

import httpx

FORMATS = ("standard",)
MAX_CANDIDATES = 30
MAX_DOC_CHARS = 1000
DEFAULT_TIMEOUT_MS = 600

log = logging.getLogger("nmos.rerank")

T = TypeVar("T")

# The whole call (name resolution, connect, request, answer) runs on a small worker pool and the request waits on it
# for at most its timeout plus a small constant: a lookup cannot be cancelled, and `asyncio.run`'s teardown joins the
# default executor where a stuck `getaddrinfo` still runs, so only a bound from outside holds. A worker left behind
# by a timed-out call ends by itself when its lookup returns; while every worker is busy a call fails open at once
# instead of queueing behind them.
_MAX_WORKERS = 4
_GRACE_S = 0.05
_POOL = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="nmos-rerank")
_SLOTS = threading.BoundedSemaphore(_MAX_WORKERS)
_BUSY_LOCK = threading.Lock()
_busy = 0


class _PoolBusy(Exception):
    """Every rerank worker is still running an earlier call."""


def _in_flight() -> int:
    """Rerank calls whose worker has not finished yet (tests)."""
    with _BUSY_LOCK:
        return _busy


def _bounded(fn: Any, timeout_s: float) -> Any:
    """`fn()` on a pool worker, waited on for at most `timeout_s + _GRACE_S`; never joins a worker that overruns."""
    global _busy
    if not _SLOTS.acquire(blocking=False):
        raise _PoolBusy

    def run() -> Any:
        global _busy
        try:
            return fn()
        finally:  # the worker frees its own slot when its call really ends, however late
            with _BUSY_LOCK:
                _busy -= 1
            _SLOTS.release()

    with _BUSY_LOCK:
        _busy += 1
    try:
        future = _POOL.submit(run)
    except BaseException:
        with _BUSY_LOCK:
            _busy -= 1
        _SLOTS.release()
        raise
    return future.result(timeout=timeout_s + _GRACE_S)


def _safe_url(url: str) -> str:
    """`url` without any `user:pass@` userinfo, safe for `__repr__`."""
    try:
        parts = urlsplit(url)
        if parts.username is None and parts.password is None:
            return url
        host = parts.hostname or ""
        if ":" in host:
            host = f"[{host}]"
        netloc = f"{host}:{parts.port}" if parts.port is not None else host
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except ValueError:
        return "<invalid-url>"


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


@dataclass(frozen=True)
class Reranker:
    url: str
    model: str
    api_key: str = ""
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    format: str = "standard"

    def __repr__(self) -> str:
        key = "***" if self.api_key else ""
        return (
            f"Reranker(url={_safe_url(self.url)!r}, model={self.model!r}, "
            f"api_key={key!r}, timeout_ms={self.timeout_ms!r}, format={self.format!r})"
        )


def endpoint(url: str) -> str:
    """Strip trailing `/` and append `/rerank` unless the path already ends with `/rerank`."""
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/")
    if not path.endswith("/rerank"):
        path = f"{path}/rerank"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def parse_scores(body: Any, expected: int) -> list[float] | None:
    """Parse a `standard` rerank response body (`results` or `data`) into scores in input order.

    Every input index `0..expected-1` must appear exactly once with a finite numeric
    `relevance_score`; otherwise returns `None` (fail open).
    """
    if not isinstance(body, dict):
        return None
    items = body.get("results")
    if items is None:
        items = body.get("data")
    if not isinstance(items, list) or len(items) != expected:
        return None

    scores: list[float | None] = [None] * expected
    for item in items:
        if not isinstance(item, dict):
            return None
        idx = item.get("index")
        if not isinstance(idx, int) or isinstance(idx, bool) or idx < 0 or idx >= expected:
            return None
        if scores[idx] is not None:
            return None
        raw_score = item.get("relevance_score")
        if not isinstance(raw_score, (int, float)) or isinstance(raw_score, bool):
            return None
        try:
            val = float(raw_score)
        except (OverflowError, ValueError, TypeError):  # e.g. an integer too large for a float: valid JSON
            return None
        if not math.isfinite(val):
            return None
        scores[idx] = val

    if any(s is None for s in scores):
        return None
    return [s for s in scores if s is not None]


def _post(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_s: float,
    client: httpx.Client | None,
) -> httpx.Response:
    if client is not None:
        return client.post(url, json=payload, headers=headers, timeout=timeout_s)

    async def request() -> httpx.Response:
        async with asyncio.timeout(timeout_s):
            async with httpx.AsyncClient(timeout=timeout_s) as async_client:
                return await async_client.post(url, json=payload, headers=headers)

    return asyncio.run(request())


def score(
    reranker: Reranker,
    query: str,
    documents: list[str],
    timeout_s: float | None = None,
    *,
    client: httpx.Client | None = None,
) -> list[float] | None:
    """Score up to `MAX_CANDIDATES` documents against `query`, returning scores in input order.

    Fails open (`None`) on any configuration guard, timeout, transport error, non-2xx status,
    or malformed response. Never logs credentials, URL userinfo, query text, or documents.
    Total: it never raises into the request path, whatever the configuration or the answer.
    """
    try:
        return _score(reranker, query, documents, timeout_s, client)
    except Exception as exc:  # noqa: BLE001  (fail open: the reranker may never fail a request)
        log.debug("rerank status=error error=%s", type(exc).__name__)
        return None


def _score(
    reranker: Reranker,
    query: str,
    documents: list[str],
    timeout_s: float | None,
    client: httpx.Client | None,
) -> list[float] | None:
    if reranker.format not in FORMATS or not reranker.url.strip() or not reranker.model.strip():
        return None
    if not documents:
        return []
    if len(documents) > MAX_CANDIDATES:
        return None

    effective_timeout = reranker.timeout_ms / 1000.0 if timeout_s is None else timeout_s
    if (
        not isinstance(effective_timeout, (int, float))
        or isinstance(effective_timeout, bool)
        or not math.isfinite(effective_timeout)
        or effective_timeout <= 0
    ):
        return None

    docs = [doc[:MAX_DOC_CHARS] for doc in documents]
    payload: dict[str, Any] = {
        "model": reranker.model,
        "query": query,
        "documents": docs,
        "top_n": len(docs),
    }
    headers = _headers(reranker.api_key)
    started = time.monotonic()

    url = endpoint(reranker.url)
    timeout = float(effective_timeout)
    try:
        res = _bounded(lambda: _post(url, payload, headers, timeout, client), timeout)
    except _PoolBusy:
        log.debug("rerank status=busy ms=%d", round((time.monotonic() - started) * 1000))
        return None
    except (TimeoutError, httpx.TimeoutException):
        log.debug("rerank status=timeout ms=%d", round((time.monotonic() - started) * 1000))
        return None
    except Exception:
        log.debug("rerank status=error ms=%d", round((time.monotonic() - started) * 1000))
        return None

    elapsed_ms = round((time.monotonic() - started) * 1000)
    if not (200 <= res.status_code < 300):
        log.debug("rerank status=%d ms=%d", res.status_code, elapsed_ms)
        return None

    try:
        scores = parse_scores(res.json(), len(docs))
    except Exception:
        scores = None
    log.debug("rerank status=%d ms=%d", res.status_code, elapsed_ms)
    return scores


def reorder(candidates: list[T], scores: list[float]) -> list[T]:
    """Stable descending sort of `candidates` by `scores`; ties preserve input order."""
    if len(candidates) != len(scores):
        raise ValueError(f"candidates ({len(candidates)}) and scores ({len(scores)}) must have the same length")
    order = sorted(range(len(candidates)), key=lambda i: (-scores[i], i))
    return [candidates[i] for i in order]
