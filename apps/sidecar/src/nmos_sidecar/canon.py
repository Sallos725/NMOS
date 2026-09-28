"""Canon sources (Phase 14, ADR 0045): the character card, the chat's author's note, its persona and the lorebook
entries the host shows the chat, kept as immutable source revisions of the conversation.

The plugin sends a manifest of canon keys and content hashes; the sidecar asks for the texts it lacks, verifies each
against its hash, stores it as a revision of the source object `canon:<key>` (kind `canon`) and records in
`canon_state` which revision of each key is in force from when (migration 0025). A sync that finds a key changed or
gone closes its row, so a read as of an earlier request sees that request's canon (ADR 0027). Canon is never a head
member: the message pipelines (extraction, embeddings, excerpts, state) do not see it.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from . import normtext
from .canonical import normalize_text, storable
from .ids import uuid7

# card:<field>, note, persona, lore:<id>: the plugin's keys (ADR 0045)
KEY = re.compile(r"^(card:(name|desc|personality|scenario|greeting)|note|persona|lore:[A-Za-z0-9_.:-]{1,120})$")
KINDS = ("card", "note", "persona", "lore")
PREFIX = "canon:"
META_KEYS = ("scope", "mode", "always_active", "keys", "comment", "name", "persona_id", "field")


def kind_of(key: str) -> str:
    return key.split(":", 1)[0]


def content_hash(content: str) -> str:
    """The hash a canon text is sent and kept under: SHA-256 of its normalized text (NFC, LF)."""
    return hashlib.sha256(normalize_text(content).encode("utf-8")).hexdigest()


def _meta(key: str, metadata: dict[str, Any]) -> dict[str, Any]:
    kept = {k: metadata[k] for k in META_KEYS if k in metadata}
    if isinstance(kept.get("keys"), list):
        kept["keys"] = [str(k)[:120] for k in kept["keys"][:64]]
    return storable({"canon": kind_of(key), **kept})


def sync(conn: psycopg.Connection, conv_id: UUID, entries: list[dict[str, Any]],
         contents: dict[str, str]) -> dict[str, Any]:
    """Store what the manifest names and the host sent, then make the manifest the canon in force. Returns the
    hashes still needed (the state is not changed until none is), and what was stored and changed."""
    needed: list[str] = []
    stored = 0
    revisions: dict[str, UUID] = {}
    for entry in entries:
        key, digest = entry["key"], entry["hash"]
        hlid = PREFIX + key
        row = conn.execute(
            "SELECT sr.id FROM source_object so JOIN source_revision sr ON sr.source_object_id = so.id"
            " WHERE so.conversation_id = %s AND so.host_logical_id = %s AND sr.revision_hash = %s",
            (conv_id, hlid, digest)).fetchone()
        if row:
            revisions[key] = row["id"]
            continue
        content = contents.get(digest)
        if content is None or content_hash(content) != digest:
            needed.append(digest)
            continue
        conn.execute("INSERT INTO source_object (id, conversation_id, host_logical_id, source_kind)"
                     " VALUES (%s, %s, %s, 'canon') ON CONFLICT (conversation_id, host_logical_id) DO NOTHING",
                     (uuid7(), conv_id, hlid))
        obj = conn.execute("SELECT id FROM source_object WHERE conversation_id = %s AND host_logical_id = %s",
                           (conv_id, hlid)).fetchone()
        text = storable(normalize_text(content))
        rid = uuid7()
        conn.execute("INSERT INTO source_revision (id, source_object_id, revision_hash, content, metadata, lifecycle)"
                     " VALUES (%s, %s, %s, %s, %s, 'accepted')",
                     (rid, obj["id"], digest, text, Jsonb(_meta(key, entry.get("metadata") or {}))))
        normtext.write(conn, rid, text)
        revisions[key] = rid
        stored += 1
    if needed:
        return {"needed": sorted(set(needed)), "stored": stored, "changed": 0, "in_force": None}
    current = {r["canon_key"]: r for r in conn.execute(
        "SELECT id, canon_key, source_revision_id FROM canon_state WHERE conversation_id = %s AND until IS NULL",
        (conv_id,)).fetchall()}
    changed = 0
    for key, row in current.items():
        if revisions.get(key) != row["source_revision_id"]:
            conn.execute("UPDATE canon_state SET until = now() WHERE id = %s", (row["id"],))
            changed += 1
    for key, rid in revisions.items():
        if key not in current or current[key]["source_revision_id"] != rid:
            conn.execute("INSERT INTO canon_state (id, conversation_id, canon_key, source_revision_id)"
                         " VALUES (%s, %s, %s, %s)", (uuid7(), conv_id, key, rid))
            changed += key not in current
    return {"needed": [], "stored": stored, "changed": changed, "in_force": len(revisions)}


def in_force(conn: psycopg.Connection, conv_id: UUID, at: datetime | None = None) -> list[dict[str, Any]]:
    """The canon of a conversation now, or as it was at `at` (a replay, ADR 0027): each key with its revision."""
    return conn.execute(
        "SELECT cs.canon_key AS key, cs.since, sr.id AS revision_id, sr.revision_hash, sr.content, sr.metadata,"
        " (SELECT count(*) FROM canon_state h WHERE h.conversation_id = cs.conversation_id"
        "  AND h.canon_key = cs.canon_key) AS versions"
        " FROM canon_state cs JOIN source_revision sr ON sr.id = cs.source_revision_id"
        " WHERE cs.conversation_id = %(c)s AND (%(at)s::timestamptz IS NULL AND cs.until IS NULL"
        "  OR cs.since <= %(at)s AND (cs.until IS NULL OR cs.until > %(at)s))"
        " ORDER BY cs.canon_key", {"c": conv_id, "at": at}).fetchall()


def held(conn: psycopg.Connection, conv_id: UUID) -> dict[str, dict[str, Any]]:
    """For each canon key a recorded request's prompt held: how many requests held it, and when first and last."""
    rows = conn.execute(
        "SELECT k.key, count(*) AS requests, min(t.created_at) AS first_at, max(t.created_at) AS last_at"
        " FROM retrieval_trace t CROSS JOIN LATERAL jsonb_array_elements_text(t.canon_held) AS k(key)"
        " WHERE t.conversation_id = %s GROUP BY k.key", (conv_id,)).fetchall()
    return {r["key"]: r for r in rows}
