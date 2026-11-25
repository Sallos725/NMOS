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


def request_spec(extra_body: dict[str, Any], no_temperature: bool) -> dict[str, Any]:
    """What a generation built from the model settings says about its request (PHASE-61 S2, ADR 0088 item 2):
    `temperature` 0, or None when none is sent; `request`, the extra body in canonical form (sorted keys at every
    level), only when it is not empty. At the defaults this is `{"temperature": 0}`, the spec field every one of them
    had before, so their keys do not move."""
    out: dict[str, Any] = {"temperature": None if no_temperature else 0}
    if extra_body:
        out["request"] = json.loads(json.dumps(extra_body, sort_keys=True, ensure_ascii=False))
    return out


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


# PHASE-61 S2 (ADR 0088 item 3): the extra request body and the temperature switch are part of how the model is called,
# so a change of either alone is a model change (the owner's choice, carry on by default), never a version change.
MODEL_FIELDS = ("model", "endpoint", "request", "temperature")
# Extractor compilers a switch between re-extracts nothing for (PHASE-58 S3, ADR 0081 item 4): extract-v18 is extract-v16
# with a field on rows both write the same way, so the facts older turns have stay as good as they were. extract-v19
# (PHASE-60 S7, ADR 0086 item 6) is extract-v18 with fields and a predicate on rows the others write the same way;
# extract-v20 (PHASE-64, ADR 0091) adds conditional forms of address on `addresses` with the same spec fields, so a
# switch among the four differs in `compiler` and `prompt` alone. extract-v21 (PHASE-66) is extract-v20 with the typed
# ontology's predicates and marks on rows the others write the same way; its spec keeps the same field names (what else
# it changes is in its `prompt`), so a switch to it from any of the four re-extracts nothing either. extract-v17 stays
# outside: its own `speakers` field makes a switch a version.
ADDS = frozenset({"extract-v16", "extract-v18", "extract-v19", "extract-v20", "extract-v21"})
ADDS_FIELDS = ("compiler", "prompt")
# The cap on each message the model is shown (PHASE-62 S1, S2, ADR 0090): `target_chars` in an extract or a reveal
# generation's spec, `message_chars` in a summarize generation's. A change of it alone re-derives nothing: what was
# read at the earlier cap stays as good as it was, and only what comes due afterwards is read at the new one.
READS_FIELDS = ("target_chars", "message_chars")
# Spec fields a change of re-derives nothing a model wrote, each with the values a switch among carries on (None: any
# value): rows written under the one value stay as good as they were, and what comes due afterwards is written under the
# other. A change of only these fields is "carry"; one with a compiler or a cap change too is "adds" or "reads", one
# with the model "model", one with anything else "version" (the more expensive class wins).
# - `normalizer` (PHASE-66 part 3, `normtext`): between clean-v3 and clean-v4, what was read from the one normalizer's
#   text keeps serving and new work reads the other's. Another normalizer is a version.
# - `revision` (PHASE-66 part 5, owner decision 2026-11-25): the number of the post-processing rules a projection kind
#   writes its rows with under one compiler and prompt (`extraction.REVISION`, `reveals.REVISION`,
#   `summaries.REVISION`, `canonfacts.REVISION`; each lists what its values changed). A bump re-derives nothing (no paid
#   re-work) yet makes the keys tell the rows written under the earlier rules from the later ones (AGENTS §4, D20,
#   ADR 0006). Absent from the spec at 0, the production base (Phase 64), so the first bump moves each key once.
# A further zero-cost field is one more entry here (its name, and the values that carry on or None). Its spec field is
# absent at the value every earlier key was made with, so adding the entry moves no key; giving it a value moves the
# keys of its kind once, on purpose. An embedding projection is never classified (its activation always queues what it
# is missing: re-embedding is local).
CARRY_FIELDS: dict[str, frozenset[Any] | None] = {"normalizer": frozenset({"clean-v3", "clean-v4"}), "revision": None}


def revision(n: int) -> dict[str, int]:
    """The spec's `revision` field for post-processing rules number `n` (CARRY_FIELDS): none at 0, the production
    base's rules, so every key made before the field existed stays as it was."""
    return {"revision": n} if n else {}


def _carries(k: str, old: dict[str, Any], new: dict[str, Any]) -> bool:
    """Whether a difference of spec field `k` between `old` and `new` is one CARRY_FIELDS carries on."""
    if k not in CARRY_FIELDS:
        return False
    values = CARRY_FIELDS[k]
    return values is None or {old.get(k), new.get(k)} <= values


def carry_only(old: dict[str, Any], new: dict[str, Any]) -> bool:
    """Whether two specs differ, and only in fields CARRY_FIELDS carries on (`classify` would say "carry")."""
    differ = [k for k in old.keys() | new.keys() if old.get(k) != new.get(k)]
    return bool(differ) and all(_carries(k, old, new) for k in differ)


def peers(conn: psycopg.Connection, key: str) -> list[str]:
    """`key` and every generation of its kind whose spec differs from its only in CARRY_FIELDS: their rows are as good
    as its own (a carry-on, `classify`), so a rule asking whether the active generation has done something (a reveal
    check, PHASE-66 part 5) counts theirs too. Only `key` on a database that never had a carry-on."""
    rows = conn.execute("SELECT g.key, g.spec FROM projection_generation g JOIN projection_generation k"
                        " ON k.kind = g.kind AND k.key = %s", (key,)).fetchall()
    mine = next((r["spec"] for r in rows if r["key"] == key), None)
    if mine is None:
        return [key]
    return sorted({key} | {r["key"] for r in rows if carry_only(r["spec"], mine)})


def classify(conn: psycopg.Connection, previous: str | None, gen: Generation) -> str:
    """What making `gen` active is, next to the generation `previous` that was (PHASE-57 A3): "same", "new" (none
    was), "model" (only the model, the endpoint, the extra request body or the temperature switch differs: the owner
    changed the model or how it is called, PHASE-61 S2), "adds" (only the compiler and its prompt differ, between two
    compilers of ADDS: PHASE-58 S3, PHASE-60 S7), "reads" (the cap of READS_FIELDS differs, alone or with such a
    compiler change: PHASE-62 S2; either of the two with the model too is "model"), "carry" (only fields of
    CARRY_FIELDS differ, each between values it carries on: PHASE-66 part 3; with a compiler or a cap change too it
    is "adds" or "reads", with the model "model") or "version" (anything else: a release's version or prompt, or another setting
    the key hashes). Every class but "version" carries on: what was written keeps serving."""
    if previous == gen.key:
        return "same"
    if previous is None:
        return "new"
    row = conn.execute("SELECT spec FROM projection_generation WHERE key = %s", (previous,)).fetchone()
    if row is None:
        return "version"

    def rest(spec: dict[str, Any], skip: tuple[str, ...] = ()) -> dict[str, Any]:
        return {k: v for k, v in spec.items() if k not in MODEL_FIELDS + skip}

    old, new = row["spec"], json.loads(json.dumps(gen.spec))
    if rest(old) == rest(new):
        return "model"
    adds = old.get("compiler") != new.get("compiler") and {old.get("compiler"), new.get("compiler")} <= ADDS
    reads = any(old.get(k) != new.get(k) for k in READS_FIELDS)
    carried = tuple(k for k in CARRY_FIELDS if old.get(k) != new.get(k) and _carries(k, old, new))
    skip = (ADDS_FIELDS if adds else ()) + (READS_FIELDS if reads else ()) + carried
    if skip and rest(old, skip) == rest(new, skip):
        if not all(old.get(k) == new.get(k) for k in MODEL_FIELDS):
            return "model"
        return "reads" if reads else "adds" if adds else "carry"
    return "version"


def describe(conn: psycopg.Connection, key: str | None) -> dict[str, Any] | None:
    if key is None:
        return None
    row = conn.execute("SELECT key, kind, model, endpoint, spec, created_at, activated_at FROM projection_generation"
                       " WHERE key = %s", (key,)).fetchone()
    return dict(row) if row else None
