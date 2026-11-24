"""A log of model calls (PHASE-61 S6, ADR 0089): one `model_call` row per call the worker or the sidecar makes to a
model outside the request path.

Metadata only: never a prompt, a reply, chat text or a key. A row is written in a connection of its own, never the
job's, so it survives the job's rollback; writing it is bounded and its failure is one warning, so a call, a job and a
request go on without the log. `/v1/retrieve` writes none: its embedding and rerank are not observed."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .canonical import storable
from .generations import endpoint_identity
from .ids import uuid7
from .llm import Observer

log = logging.getLogger("nmos.calls")

KINDS = ("extract", "reveal", "summarize", "canon", "embed", "note", "test")
OUTCOMES = ("ok", "http", "timeout", "transport", "bad_reply")
ERROR_CHARS = 300  # the column's check
MODEL_CHARS = 200
# The kinds of fault a reply that could not be read is logged by (`llm`'s `detail` of a `bad_reply`). Anything else in
# their place becomes UNREADABLE: a reply is the model's text and may hold chat text, so none of it is ever kept.
BAD_REPLY = frozenset({"no JSON object", "invalid JSON", "not a JSON object", "not JSON", "unexpected response shape",
                       "content is not text"})
UNREADABLE = "unreadable reply"
_CLASS_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,99}\Z")  # a timeout's or a transport fault's exception class
USAGE_KEYS = ("calls", "ms", "model", "input", "output", "cached", "reasoning")  # `llm.usage_of`'s keys
REDACTED = "[redacted]"
MIN_SECRET = 4  # as `archive.MIN_SECRET`: a key of one to three characters is not looked for
TIMEOUT_S = 2  # connecting and writing a row, each (libpq counts a connect timeout in whole seconds, at least 2)
COLUMNS = ("id", "kind", "conversation_id", "job_id", "generation", "model", "endpoint", "outcome", "http_status", "ms",
           "usage", "error")


def endpoint_of(url: str) -> str:
    """The endpoint a row names: scheme, host, port and path (`generations.endpoint_identity`), never a user, a
    password, a query or a fragment."""
    parts = urlsplit(url.strip())
    return endpoint_identity(urlunsplit((parts.scheme, parts.netloc.rpartition("@")[2], parts.path, "", "")))


def collapsed(text: str, limit: int = ERROR_CHARS) -> str:
    """`text` on one line (every run of whitespace one space), at most `limit` characters."""
    return " ".join(text.split())[:limit]


def _error(outcome: str, error: Any) -> str | None:
    """What a row keeps of a call's error: nothing for `ok`; the kind of fault alone for `bad_reply` (one of
    BAD_REPLY, else UNREADABLE); the exception's class alone for `timeout` and `transport`; the provider's error, on
    one line and cut, for `http`."""
    if outcome == "ok":
        return None
    text = None if error is None else storable(str(error))
    if outcome == "bad_reply":
        return text if text in BAD_REPLY else UNREADABLE
    if outcome in ("timeout", "transport"):
        return text if text is not None and _CLASS_NAME.match(text) else outcome
    return collapsed(text) if text else None


def _usage(usage: Any) -> dict[str, Any] | None:
    """The provider's reported usage (`llm.usage_of`) and nothing else."""
    if not isinstance(usage, dict):
        return None
    out = {k: usage[k] for k in USAGE_KEYS if isinstance(usage.get(k), int) and not isinstance(usage.get(k), bool)}
    if isinstance(usage.get("model"), str):
        out["model"] = storable(usage["model"])[:MODEL_CHARS]
    return out or None


def record_of(kind: str, model: str, endpoint_url: str, started: float, *, outcome: str,
              http_status: int | None = None, usage: dict[str, Any] | None = None, error: Any = None,
              conversation_id: UUID | str | None = None, job_id: int | None = None,
              generation: str | None = None) -> dict[str, Any]:
    """One row of `model_call` for a call that ended now, `started` being its `time.monotonic()` start."""
    if kind not in KINDS:
        raise ValueError(f"unknown model call kind {kind!r}")
    if outcome not in OUTCOMES:
        raise ValueError(f"unknown model call outcome {outcome!r}")
    return {
        "id": uuid7(),
        "kind": kind,
        "conversation_id": None if conversation_id is None else UUID(str(conversation_id)),
        "job_id": job_id,
        "generation": generation,
        "model": storable(str(model))[:MODEL_CHARS],
        "endpoint": endpoint_of(endpoint_url),
        "outcome": outcome,
        "http_status": http_status if outcome == "http" else None,
        "ms": max(0, round((time.monotonic() - started) * 1000)),
        "usage": _usage(usage),
        "error": _error(outcome, error),
    }


def _secrets(secrets: Iterable[str | None]) -> list[str]:
    return sorted({s for s in secrets if isinstance(s, str) and len(s) >= MIN_SECRET}, key=len, reverse=True)


def scrub(text: str, secrets: Iterable[str | None]) -> str:
    """`text` with every key in `secrets` replaced by REDACTED."""
    for secret in _secrets(secrets):
        text = text.replace(secret, REDACTED)
    return text


def redact(row: dict[str, Any], secrets: Iterable[str | None]) -> dict[str, Any]:
    """The guard before a row is written: a key found in its model, endpoint, generation, error or reported model is
    replaced by REDACTED (and the error cut again to the column's length)."""
    keys = _secrets(secrets)
    if not keys:
        return row
    out = dict(row)
    for col in ("model", "endpoint", "generation", "error"):
        if isinstance(out.get(col), str):
            out[col] = scrub(out[col], keys)
    if isinstance(out.get("error"), str):
        out["error"] = out["error"][:ERROR_CHARS]
    if isinstance(out.get("usage"), dict) and isinstance(out["usage"].get("model"), str):
        out["usage"] = {**out["usage"], "model": scrub(out["usage"]["model"], keys)}
    return out


_INSERT = (f"INSERT INTO model_call ({', '.join(COLUMNS)})"
           f" VALUES ({', '.join(f'%({c})s' for c in COLUMNS)})")


def write(dsn: str, row: dict[str, Any]) -> bool:
    """Write one row in a connection of its own (autocommit), never a job's: it survives the job's rollback and takes
    none of its locks. Bounded (TIMEOUT_S to connect, to wait for a lock and to write) and fail open: any failure is
    one warning naming the exception's type, and False."""
    try:
        ms = TIMEOUT_S * 1000
        with psycopg.connect(dsn, autocommit=True, connect_timeout=TIMEOUT_S,
                             options=f"-c statement_timeout={ms} -c lock_timeout={ms}") as conn:
            conn.execute(_INSERT, {**row, "usage": None if row.get("usage") is None else Jsonb(row["usage"])})
        return True
    except Exception as exc:  # noqa: BLE001 - the log never breaks a call, a job or a request
        log.warning("model call not logged: %s", type(exc).__name__)
        return False


def observer(dsn: str, kind: str, *, conversation_id: UUID | str | None = None, job_id: int | None = None,
             generation: str | None = None) -> Observer:
    """A call observer (`llm.ChatModel.observed`, `llm.Embedder.observed`) that writes one row per call to `dsn`. The
    call's key is taken out of the provider's whole error before it is cut, and the row is checked again."""

    def observe(facts: dict[str, Any]) -> None:
        keys = [facts.get("api_key")]
        error = facts.get("error")
        row = record_of(kind, facts["model"], facts["url"], facts["started"], outcome=facts["outcome"],
                        http_status=facts.get("http_status"), usage=facts.get("usage"),
                        error=scrub(str(error), keys) if error is not None else None,
                        conversation_id=conversation_id, job_id=job_id, generation=generation)
        write(dsn, redact(row, keys))

    return observe


def _iso(value: Any) -> str | None:
    if not isinstance(value, datetime):
        return None
    return value.astimezone(timezone.utc).isoformat()


def _shown(row: dict[str, Any]) -> dict[str, Any]:
    return {**row, "id": str(row["id"]), "at": _iso(row["at"]),
            "conversation_id": None if row["conversation_id"] is None else str(row["conversation_id"])}


MAX_LIMIT = 500


def recent(conn: psycopg.Connection, limit: int = 200, conversation_id: UUID | str | None = None
           ) -> list[dict[str, Any]]:
    """The newest calls first, at most `limit` (1 to MAX_LIMIT), of one conversation when one is given. Every column;
    ids as strings, `at` as ISO 8601 in UTC."""
    limit = max(1, min(MAX_LIMIT, int(limit)))
    where = "" if conversation_id is None else " WHERE conversation_id = %(c)s"
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(f"SELECT at, {', '.join(COLUMNS)} FROM model_call{where} ORDER BY at DESC, id DESC"
                           " LIMIT %(n)s", {"c": None if conversation_id is None else UUID(str(conversation_id)),
                                            "n": limit}).fetchall()
    return [_shown(r) for r in rows]


TOP_STATUSES = 5  # HTTP statuses named in a summary; the rest are summed under `http_other`
MAX_MINUTES = 7 * 24 * 60


def summary(conn: psycopg.Connection, minutes: int = 60) -> dict[str, Any]:
    """The last `minutes` (1 to a week) of calls in numbers: how many, how many succeeded and failed, the failures by
    HTTP status (the TOP_STATUSES most frequent, as strings; the others under `http_other`) or by fault, the median
    time of every call in the window, and the time of the last success and the last failure."""
    minutes = max(1, min(MAX_MINUTES, int(minutes)))
    window = "FROM model_call WHERE at >= now() - make_interval(mins => %(m)s)"
    with conn.cursor(row_factory=dict_row) as cur:
        head = cur.execute(
            "SELECT count(*) AS total, count(*) FILTER (WHERE outcome = 'ok') AS ok,"
            " percentile_cont(0.5) WITHIN GROUP (ORDER BY ms) AS median_ms,"
            " max(at) FILTER (WHERE outcome = 'ok') AS last_ok_at,"
            f" max(at) FILTER (WHERE outcome <> 'ok') AS last_failed_at {window}", {"m": minutes}).fetchone()
        faults = cur.execute(f"SELECT outcome, http_status, count(*) AS n {window} AND outcome <> 'ok'"
                             " GROUP BY outcome, http_status", {"m": minutes}).fetchall()
    by_fault: dict[str, int] = {"timeout": 0, "transport": 0, "bad_reply": 0, "http_other": 0}
    statuses = sorted(((r["n"], r["http_status"]) for r in faults if r["outcome"] == "http" and r["http_status"]),
                      key=lambda x: (-x[0], x[1]))
    named = {status for _, status in statuses[:TOP_STATUSES]}
    for r in faults:
        if r["outcome"] != "http":
            by_fault[r["outcome"]] += r["n"]
        elif r["http_status"] in named:
            by_fault[str(r["http_status"])] = r["n"]
        else:
            by_fault["http_other"] += r["n"]
    median = head["median_ms"]
    return {"minutes": minutes, "total": head["total"], "ok": head["ok"], "failed": head["total"] - head["ok"],
            "by_fault": by_fault, "median_ms": None if median is None else round(median),
            "last_ok_at": _iso(head["last_ok_at"]), "last_failed_at": _iso(head["last_failed_at"])}
