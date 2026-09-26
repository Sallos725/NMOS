"""Canonical JSON and revision hashing (hash format v1).

Must stay byte-identical with `adapters/pocketrisu-plugin/src/canonical.ts`: NFC, CRLF→LF,
sorted keys, no trailing-whitespace trimming, `undefined`/absent keys dropped, JSON as produced by
JavaScript's `JSON.stringify` (no spaces, non-ASCII kept literally).
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

HASH_FORMAT_VERSION = 1

# Keys of the v1 revision hash payload besides `v` and `selectedContent`.
PAYLOAD_KEYS = ("chatId", "role", "saying", "name", "otherUser", "isComment", "disabled", "swipeId", "generationId")


def normalize_text(value: str) -> str:
    return unicodedata.normalize("NFC", value).replace("\r\n", "\n")


def canonicalize(value: Any) -> Any:
    if isinstance(value, str):
        return normalize_text(value)
    if isinstance(value, list):
        return [canonicalize(v) for v in value]
    if isinstance(value, dict):
        return {k: canonicalize(value[k]) for k in sorted(value)}
    return value


_LONE_SURROGATE = re.compile("[\ud800-\udfff]")


def canonical_json(value: Any) -> str:
    text = json.dumps(canonicalize(value), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    # Well-formed JSON.stringify escapes lone surrogates as lowercase \udxxx.
    return _LONE_SURROGATE.sub(lambda m: f"\\u{ord(m.group()):04x}", text)


def storable(value: Any) -> Any:
    """`value` with each lone surrogate replaced by U+FFFD, which PostgreSQL text and jsonb can hold (ADR 0029).

    Only for storing: hashes are computed on the text as received."""
    if isinstance(value, str):
        return _LONE_SURROGATE.sub("�", value)
    if isinstance(value, list):
        return [storable(v) for v in value]
    if isinstance(value, dict):
        return {storable(k): storable(v) for k, v in value.items()}
    return value


def storable_json(value: Any) -> str:
    """psycopg's jsonb serializer (set in `nmos_sidecar/__init__.py`): JSON text with lone surrogates as
    U+FFFD. Without `ensure_ascii` a surrogate is a single character in the output, never half of a pair."""
    return _LONE_SURROGATE.sub("�", json.dumps(value, ensure_ascii=False))


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def revision_payload(metadata: dict[str, Any], content: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"v": HASH_FORMAT_VERSION, "selectedContent": content}
    for key in PAYLOAD_KEYS:
        payload[key] = metadata.get(key)
    return payload


def revision_hash(metadata: dict[str, Any], content: str) -> str:
    return sha256_hex(canonical_json(revision_payload(metadata, content)))


def manifest_hash(entries: list[tuple[str, str]]) -> str:
    """Hash of the ordered `(host_logical_id, revision_hash)` list."""
    return sha256_hex(_pairs_json(entries))


def _pairs_json(entries: list[tuple[str, str]]) -> str:
    """`canonical_json` of `[[id, hash], ...]` without the generic recursion (≈3× faster at 10k)."""
    text = json.dumps([[normalize_text(i), normalize_text(h)] for i, h in entries], ensure_ascii=False,
                      separators=(",", ":"))
    return _LONE_SURROGATE.sub(lambda m: f"\\u{ord(m.group()):04x}", text)


def manifest_hashes(entries: list[tuple[str, str]], split: int) -> tuple[str, str]:
    """`(manifest_hash(entries[:split]), manifest_hash(entries))`, serializing each entry once.

    A JSON array is `[` + items joined by `,` + `]`, so the full text is the prefix text without its
    closing bracket, then `,` and the rest. Requires 0 < split < len(entries).
    """
    assert 0 < split < len(entries)
    prefix = _pairs_json(entries[:split])
    rest = _pairs_json(entries[split:])
    digest = hashlib.sha256(prefix[:-1].encode("utf-8"))
    head = digest.copy()
    head.update(b"]")
    digest.update(("," + rest[1:]).encode("utf-8"))
    return head.hexdigest(), digest.hexdigest()
