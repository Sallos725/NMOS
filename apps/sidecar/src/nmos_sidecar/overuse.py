"""Memory that stops repeating itself (PHASE-34 Q2, Q3): which supportive lines rest in a request.

A line is its kind and the id it came from (`key`). It is tired when it was placed in each of the last `rest_after`
requests of the chat (`RecallOptions.rest_after`, 2 by default), or in each of the `rest_after` before the last one and
left out of the last one (it rests for two requests), and none of the replies after those requests echoed it
(`spans.reuse`, ADR 0027).
Nothing is stored: the requests are the chat's recorded traces (their ledgers, ADR 0027) and the replies the messages
after them, so a replay reads what the request read (ADR 0027), and a sequential replay passes its own packets instead
(`Recent`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg

from . import spans

REST_AFTER = 2  # the default: placed in this many requests in a row, echoed by none of their replies (owner, 2026-10-07)


@dataclass(frozen=True)
class Recent:
    """One earlier request: the keys of the lines it placed, and those the reply after it echoed."""
    placed: frozenset[tuple[str, str]]
    echoed: frozenset[tuple[str, str]]


def key(kind: str, ref: dict[str, Any] | None) -> tuple[str, str]:
    """A line's identity across requests: its kind and the assertion, message or item it came from."""
    ref = ref or {}
    for k in ("assertion", "revision", "summary", "key"):
        if ref.get(k) is not None:
            return kind, str(ref[k])
    return kind, str(sorted(ref.items()))


def reply_text(conn: psycopg.Connection, head: UUID, upto_position: int | None) -> str | None:
    """The character's message right after a request's last position on the head, if there is one."""
    if upto_position is None:
        return None
    row = conn.execute(
        "SELECT sr.metadata->>'role' AS role, rt.clean_content FROM active_membership am"
        " JOIN source_revision sr ON sr.id = am.source_revision_id"
        " LEFT JOIN revision_text rt ON rt.source_revision_id = sr.id"
        " WHERE am.commit_id = %s AND am.position = %s ORDER BY rt.normalizer DESC LIMIT 1",
        (head, upto_position + 1)).fetchone()
    return (row["clean_content"] or "") if row and row["role"] == "char" else None


def of_ledger(lines: list[dict[str, Any]], reply: str | None, request: tuple[str, str]) -> Recent:
    """One request as the rest reads it, from its ledger and the reply that followed."""
    placed = [e for e in lines if e.get("placed")]
    echoed = frozenset(key(e["kind"], e.get("ref")) for e in placed
                       if reply and spans.reuse(e.get("content") or e.get("text") or "", reply, request) > 0)
    return Recent(frozenset(key(e["kind"], e.get("ref")) for e in placed), echoed)


def recent(conn: psycopg.Connection, conversation: UUID, head: UUID, before: datetime | None = None,
           n: int = REST_AFTER + 1) -> list[Recent]:
    """The chat's last `n` recorded requests before `before` (all, when None), newest first."""
    rows = conn.execute(
        "SELECT upto_position, query, previous_ai, lines FROM retrieval_trace WHERE conversation_id = %s"
        " AND lines IS NOT NULL AND (%s::timestamptz IS NULL OR created_at < %s) ORDER BY created_at DESC LIMIT %s",
        (conversation, before, before, n)).fetchall()
    return [of_ledger(r["lines"] or [], reply_text(conn, head, r["upto_position"]),
                      (r["query"] or "", r["previous_ai"] or "")) for r in rows]


def tired(history: list[Recent], rest_after: int = REST_AFTER) -> frozenset[tuple[str, str]]:
    """The keys that rest now, from the requests before this one (newest first)."""
    def run(start: int) -> frozenset[tuple[str, str]]:
        window = history[start:start + rest_after]
        if len(window) < rest_after:
            return frozenset()
        keys = frozenset.intersection(*(r.placed for r in window))
        return frozenset(k for k in keys if not any(k in r.echoed for r in window))

    now = run(0)
    if not history:
        return now
    resting_still = frozenset(k for k in run(1) if k not in history[0].placed)  # left out once: still resting
    return now | resting_still
