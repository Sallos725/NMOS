"""Projection generations (#6, #7): the immutable identity of a derived projection.

A generation key hashes everything that changes derived output — compiler, prompt and registry
versions, normalizer and chunker versions, endpoint, model and output-affecting settings — and never
credentials. Jobs and derived rows carry the key; a worker only runs jobs for the generation its
handler implements, and readers only use rows of the active generation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import psycopg
from psycopg.types.json import Jsonb


@dataclass(frozen=True)
class Generation:
    kind: str  # 'extract' | 'embed'
    model: str
    endpoint: str
    spec: dict[str, Any] = field(hash=False)
    key: str = ""

    @property
    def short(self) -> str:
        return self.key[:12]


def endpoint_identity(url: str) -> str:
    """Scheme, host, port and path of an OpenAI-compatible base URL; case and trailing '/' ignored."""
    parts = urlsplit(url.strip())
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}{parts.path.rstrip('/')}"


def make(kind: str, url: str, model: str, **spec: Any) -> Generation:
    endpoint = endpoint_identity(url)
    full = {"kind": kind, "endpoint": endpoint, "model": model, **spec}
    key = hashlib.sha256(json.dumps(full, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32]
    return Generation(kind=kind, model=model, endpoint=endpoint, spec=full, key=f"{kind}-{key}")


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def ensure(conn: psycopg.Connection, gen: Generation) -> None:
    conn.execute(
        "INSERT INTO projection_generation (key, kind, model, endpoint, spec) VALUES (%s, %s, %s, %s, %s)"
        " ON CONFLICT (key) DO NOTHING",
        (gen.key, gen.kind, gen.model, gen.endpoint, Jsonb(gen.spec)),
    )


def active(conn: psycopg.Connection, kind: str) -> str | None:
    """The most recently activated generation of `kind` (it stays active while the provider is off)."""
    row = conn.execute("SELECT key FROM projection_generation WHERE kind = %s ORDER BY activated_at DESC, key LIMIT 1",
                       (kind,)).fetchone()
    return row["key"] if row else None


def activate(conn: psycopg.Connection, gen: Generation) -> str | None:
    """Make `gen` the active generation of its kind. Returns the previously active key."""
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(727002)")
        previous = active(conn, gen.kind)
        ensure(conn, gen)
        if previous != gen.key:
            conn.execute("UPDATE projection_generation SET activated_at = clock_timestamp() WHERE key = %s", (gen.key,))
    return previous


def describe(conn: psycopg.Connection, key: str | None) -> dict[str, Any] | None:
    if key is None:
        return None
    row = conn.execute("SELECT key, kind, model, endpoint, spec, created_at, activated_at FROM projection_generation"
                       " WHERE key = %s", (key,)).fetchone()
    return dict(row) if row else None
