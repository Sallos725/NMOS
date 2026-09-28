"""Canon sources (Phase 14, ADR 0045): the character card, the chat's author's note, its persona and the lorebook
entries the host shows the chat, kept as immutable source revisions of the conversation.

A canon text is a revision of the source object `canon:<key>` (kind `canon`) under the hash of its normalized text.
A manifest is the chat's canon at one time, each key with its text's hash and what it is (metadata); its id is the
hash of its canonical JSON, which the plugin computes the same way (`manifest_id`). A sync stores the texts the
sidecar lacks, verified against their hashes, then the manifest, and makes it the conversation's canon unless a newer
observation already did. A request records its manifest id, so it replays with the canon its prompt had even when the
texts arrived after it (ADR 0027). Canon is never a head member: no message pipeline sees it.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from . import normtext
from .canonical import canonical_json, normalize_text, sha256_hex, storable
from .ids import uuid7

# card:<field>, note, persona, lore:<id>[~n]: the plugin's keys (ADR 0045)
KEY_PATTERN = r"^(card:(name|desc|personality|scenario|greeting)|note|persona|lore:[A-Za-z0-9_.:-]{1,120}(~[0-9]{1,4})?)$"
KEY = re.compile(KEY_PATTERN)
PREFIX = "canon:"


class CanonError(ValueError):
    """A manifest the sidecar cannot take (the API answers 422)."""


def kind_of(key: str) -> str:
    return key.split(":", 1)[0]


def content_hash(content: str) -> str:
    """The hash a canon text is sent and kept under: SHA-256 of its normalized text (NFC, LF), a lone surrogate read as
    U+FFFD as the browser's encoder does (ADR 0029)."""
    return hashlib.sha256(storable(normalize_text(content)).encode("utf-8")).hexdigest()


def manifest_id(entries: list[dict[str, Any]]) -> str:
    """The id of a manifest: SHA-256 of the canonical JSON of its entries (key, hash, metadata) in key order. The plugin
    computes the same (`canonManifestId`, fixtures/unit/canon-manifest-v1.json)."""
    rows = [{"key": e["key"], "hash": e["hash"], "metadata": e.get("metadata") or {}} for e in entries]
    return sha256_hex(canonical_json(sorted(rows, key=lambda e: e["key"])))


def sync(conn: psycopg.Connection, conv_id: UUID, entries: list[dict[str, Any]], contents: dict[str, str],
         observed_at: datetime | None = None) -> dict[str, Any]:
    """Store the texts the manifest names that the host sent and match their hashes; once none is missing, store the
    manifest and make it the conversation's canon, unless a newer observation already did. The conversation is
    locked by the caller."""
    keys = [e["key"] for e in entries]
    if len(set(keys)) != len(keys):
        raise CanonError("a manifest names each key once")
    needed: list[str] = []
    stored = 0
    for entry in entries:
        key, digest = entry["key"], entry["hash"]
        hlid = PREFIX + key
        if conn.execute(
                "SELECT 1 FROM source_object so JOIN source_revision sr ON sr.source_object_id = so.id"
                " WHERE so.conversation_id = %s AND so.host_logical_id = %s AND so.source_kind = 'canon'"
                " AND sr.revision_hash = %s", (conv_id, hlid, digest)).fetchone():
            continue
        content = contents.get(digest)
        if content is None or content_hash(content) != digest:
            needed.append(digest)
            continue
        conn.execute("INSERT INTO source_object (id, conversation_id, host_logical_id, source_kind)"
                     " VALUES (%s, %s, %s, 'canon') ON CONFLICT (conversation_id, host_logical_id) DO NOTHING",
                     (uuid7(), conv_id, hlid))
        obj = conn.execute("SELECT id, source_kind FROM source_object WHERE conversation_id = %s AND host_logical_id = %s",
                           (conv_id, hlid)).fetchone()
        if obj["source_kind"] != "canon":  # a message the host happened to give this id: never mix the two
            raise CanonError(f"{hlid} is a message of this chat")
        text = storable(normalize_text(content))
        rid = uuid7()
        conn.execute("INSERT INTO source_revision (id, source_object_id, revision_hash, content, metadata, lifecycle)"
                     " VALUES (%s, %s, %s, %s, %s, 'accepted')",
                     (rid, obj["id"], digest, text, Jsonb({"canon": kind_of(key)})))
        normtext.write(conn, rid, text)
        stored += 1
    if needed:
        if observed_at is not None:  # the newest observation holds from now: an older upload finishing first is stale
            conn.execute("UPDATE conversation SET canon_observed_at = greatest(canon_observed_at, %s) WHERE id = %s",
                         (observed_at, conv_id))
        return {"needed": sorted(set(needed)), "stored": stored, "applied": False, "manifest_id": None}
    mid = manifest_id(entries)  # over the metadata as sent, as the plugin computed it
    rows = sorted(({"key": e["key"], "hash": e["hash"], "metadata": storable(e.get("metadata") or {})}
                   for e in entries), key=lambda e: e["key"])
    conn.execute("INSERT INTO canon_manifest (conversation_id, id, entries) VALUES (%s, %s, %s)"
                 " ON CONFLICT DO NOTHING", (conv_id, mid, Jsonb(rows)))
    conv = conn.execute("SELECT canon_manifest_id, canon_observed_at FROM conversation WHERE id = %s",
                        (conv_id,)).fetchone()
    stale = observed_at is not None and conv["canon_observed_at"] is not None and observed_at < conv["canon_observed_at"]
    applied = not stale and conv["canon_manifest_id"] != mid
    if applied:
        conn.execute("UPDATE conversation SET canon_manifest_id = %s, canon_observed_at = %s WHERE id = %s",
                     (mid, observed_at or datetime.now(timezone.utc), conv_id))
        conn.execute("INSERT INTO canon_applied (conversation_id, manifest_id, observed_at) VALUES (%s, %s, %s)",
                     (conv_id, mid, observed_at))
    elif not stale and observed_at is not None:
        conn.execute("UPDATE conversation SET canon_observed_at = greatest(canon_observed_at, %s) WHERE id = %s",
                     (observed_at, conv_id))
    return {"needed": [], "stored": stored, "applied": applied, "stale": stale, "manifest_id": mid,
            "in_force": len(rows)}


def manifest(conn: psycopg.Connection, conv_id: UUID, mid: str | None = None) -> list[dict[str, Any]] | None:
    """A manifest's entries with their texts (None where the text never arrived): the conversation's canon now, or
    the manifest a request recorded (a replay). None when there is no such manifest."""
    if mid is None:
        row = conn.execute("SELECT canon_manifest_id FROM conversation WHERE id = %s", (conv_id,)).fetchone()
        mid = row and row["canon_manifest_id"]
    if not mid:
        return None
    found = conn.execute("SELECT entries FROM canon_manifest WHERE conversation_id = %s AND id = %s",
                         (conv_id, mid)).fetchone()
    if found is None:
        return None
    texts = {(r["host_logical_id"], r["revision_hash"]): r for r in conn.execute(
        "SELECT so.host_logical_id, sr.revision_hash, sr.id, sr.content FROM source_object so"
        " JOIN source_revision sr ON sr.source_object_id = so.id"
        " WHERE so.conversation_id = %s AND so.source_kind = 'canon'", (conv_id,)).fetchall()}
    out = []
    for e in found["entries"]:
        rev = texts.get((PREFIX + e["key"], e["hash"]))
        out.append({**e, "content": rev["content"] if rev else None, "revision_id": rev["id"] if rev else None})
    return out


def history(conn: psycopg.Connection, conv_id: UUID) -> dict[str, dict[str, Any]]:
    """For each key of the canon now: since when its current text and metadata have been in force, and how many
    versions of it the conversation has seen."""
    applied = conn.execute(
        "SELECT a.applied_at, m.entries FROM canon_applied a JOIN canon_manifest m"
        " ON m.conversation_id = a.conversation_id AND m.id = a.manifest_id"
        " WHERE a.conversation_id = %s ORDER BY a.applied_at DESC", (conv_id,)).fetchall()
    if not applied:
        return {}
    now = {e["key"]: e for e in applied[0]["entries"]}
    out = {k: {"since": applied[0]["applied_at"], "versions": set()} for k in now}
    open_keys = set(now)
    for row in applied:
        by_key = {e["key"]: e for e in row["entries"]}
        for k in list(open_keys):
            e = by_key.get(k)
            if e is not None and (e["hash"], e.get("metadata")) == (now[k]["hash"], now[k].get("metadata")):
                out[k]["since"] = row["applied_at"]
            else:
                open_keys.discard(k)
        for k, e in by_key.items():
            if k in out:
                out[k]["versions"].add((e["hash"], canonical_json(e.get("metadata") or {})))
    return {k: {"since": v["since"], "versions": len(v["versions"])} for k, v in out.items()}


def held(conn: psycopg.Connection, conv_id: UUID) -> dict[str, dict[str, Any]]:
    """For each canon key a recorded request's prompt held: how many requests held it, and when first and last."""
    rows = conn.execute(
        "SELECT k.key, count(*) AS requests, min(t.created_at) AS first_at, max(t.created_at) AS last_at"
        " FROM retrieval_trace t CROSS JOIN LATERAL jsonb_array_elements_text(t.canon_held) AS k(key)"
        " WHERE t.conversation_id = %s GROUP BY k.key", (conv_id,)).fetchall()
    return {r["key"]: r for r in rows}


def names(conn: psycopg.Connection, conv_id: UUID, known_at: datetime | None = None,
          mid: str | None = None) -> list[dict[str, Any]]:
    """Each lorebook entry's keys, as names of one thing (PHASE-14 Q6), from the manifest `mid` when the sidecar has it
    (a request's own), else the conversation's canon now, or as applied at `known_at` (a replay)."""
    entries = None
    if mid:
        row = conn.execute("SELECT entries FROM canon_manifest WHERE conversation_id = %s AND id = %s",
                           (conv_id, mid)).fetchone()
        entries = row and row["entries"]
    if entries is None and known_at is not None:
        row = conn.execute(
            "SELECT m.entries FROM canon_applied a JOIN canon_manifest m ON m.conversation_id = a.conversation_id"
            " AND m.id = a.manifest_id WHERE a.conversation_id = %s AND a.applied_at <= %s"
            " ORDER BY a.applied_at DESC LIMIT 1", (conv_id, known_at)).fetchone()
        entries = row and row["entries"]
    if entries is None and known_at is None:
        row = conn.execute("SELECT m.entries FROM conversation c JOIN canon_manifest m ON m.conversation_id = c.id"
                           " AND m.id = c.canon_manifest_id WHERE c.id = %s", (conv_id,)).fetchone()
        entries = row and row["entries"]
    return [{"key": e["key"], "names": list((e.get("metadata") or {}).get("keys") or [])}
            for e in entries or () if e["key"].startswith("lore:") and (e.get("metadata") or {}).get("keys")]
