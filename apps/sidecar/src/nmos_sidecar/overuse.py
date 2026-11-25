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

from . import normtext, spans
from .reconcile import apply_ops

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


def reply_text(conn: psycopg.Connection, head: UUID, upto_position: int | None,
               before: datetime | None = None) -> str | None:
    """The character's message right after a request's last position on the head, if there is one. With `before` (a
    replay), as it stood then: the membership rebuilt from the ops recorded before it (a review and its follow-ups: a
    reply written later must not count, a reply edited and edited back is the one it was then, and a reorder moves
    the message at that position)."""
    if upto_position is None:
        return None
    if before is None:
        row = conn.execute(
            "SELECT sr.metadata->>'role' AS role, rt.clean_content FROM active_membership am"
            " JOIN source_revision sr ON sr.id = am.source_revision_id"
            " LEFT JOIN revision_text rt ON rt.source_revision_id = sr.id"
            " WHERE am.commit_id = %s AND am.position = %s AND am.turn IS NOT NULL"
            " ORDER BY rt.normalizer = %s DESC, rt.normalizer DESC LIMIT 1",
            (head, upto_position + 1, normtext.active())).fetchone()  # the active normalizer's text first
        return (row["clean_content"] or "") if row and row["role"] == "char" else None
    # The membership as it stood then, rebuilt from the commits' and appends' ops recorded before it, in the order
    # `ledger.rebuild_membership` replays them: a reorder records no change, only a `set` (the third review).
    conversation = conn.execute("SELECT conversation_id FROM worldline_commit WHERE id = %s", (head,)).fetchone()
    if conversation is None:
        return None
    conv = conversation["conversation_id"]
    commits = conn.execute("SELECT id, delta FROM worldline_commit WHERE conversation_id = %s AND created_at < %s"
                           " ORDER BY seq", (conv, before)).fetchall()
    appends: dict[Any, list[list[dict]]] = {}
    for a in conn.execute("SELECT commit_id, ops FROM worldline_append WHERE commit_id = ANY(%s) AND created_at < %s"
                          " ORDER BY seq", ([c["id"] for c in commits], before)).fetchall():
        appends.setdefault(a["commit_id"], []).append(a["ops"])
    members: list[tuple] = []
    for c in commits:
        members = apply_ops(members, c["delta"]["ops"])
        for ops in appends.get(c["id"], []):
            members = apply_ops(members, ops)
    if upto_position + 1 >= len(members):
        return None
    row = conn.execute(
        "WITH m AS (SELECT x.position - 1 AS position, sr.id, sr.metadata FROM"
        " unnest(%s::text[], %s::text[]) WITH ORDINALITY AS x(logical, hash, position)"
        " JOIN source_object so ON so.host_logical_id = x.logical AND so.conversation_id = %s"
        " JOIN source_revision sr ON sr.source_object_id = so.id AND sr.revision_hash = x.hash)"
        " SELECT m.metadata->>'role' AS role, rt.clean_content FROM m"
        " LEFT JOIN revision_text rt ON rt.source_revision_id = m.id"
        " WHERE m.position = %s AND coalesce(m.metadata->>'disabled', '') NOT IN ('true', 'allBefore')"
        " AND coalesce(m.metadata->>'isComment', '') <> 'true'"
        " AND m.position > (SELECT coalesce(max(position), -1) FROM m WHERE metadata->>'disabled' = 'allBefore')"
        " ORDER BY rt.normalizer = %s DESC, rt.normalizer DESC LIMIT 1",
        ([logical for logical, _ in members], [hashed for _, hashed in members], conv, upto_position + 1,
         normtext.active()),
    ).fetchone()
    return (row["clean_content"] or "") if row and row["role"] == "char" else None


def of_ledger(lines: list[dict[str, Any]], reply: str | None, request: tuple[str, str]) -> Recent:
    """One request as the rest reads it, from its ledger and the reply that followed."""
    placed = [e for e in lines if e.get("placed")]
    echoed = frozenset(key(e["kind"], e.get("ref")) for e in placed
                       if reply and spans.reuse(e.get("content") or e.get("text") or "", reply, request) > 0)
    return Recent(frozenset(key(e["kind"], e.get("ref")) for e in placed), echoed)


def recent(conn: psycopg.Connection, conversation: UUID, head: UUID, before: datetime | None = None,
           n: int = REST_AFTER + 1, *, dedupe_positions: bool = False,
           exclude_position: int | None = None) -> list[Recent]:
    """The chat's last `n` recorded requests before `before` (all, when None), newest first, each with the reply
    after it as it stood at `before` (a replay reads no reply written since).

    `dedupe_positions` (packet-v21; off by default, so packet-v20 reads as it did): rerolls are one request, not
    several. Consecutive traces at the same `upto_position` collapse into the newest of them, and the `n` are counted
    after collapsing, so a reroll neither fills the window nor pushes an earlier turn out of it. `exclude_position`
    (with `dedupe_positions`): the position of the request being answered; traces at it are earlier attempts of this
    very request and are left out, so attempt 3 of a turn rests exactly what attempt 1 rested."""
    if not dedupe_positions:
        rows = conn.execute(
            "SELECT upto_position, query, previous_ai, lines FROM retrieval_trace WHERE conversation_id = %s"
            " AND lines IS NOT NULL AND (%s::timestamptz IS NULL OR created_at < %s) ORDER BY created_at DESC LIMIT %s",
            (conversation, before, before, n)).fetchall()
    else:
        rows = _distinct_positions(conn, conversation, before, n, exclude_position)
    return [of_ledger(r["lines"] or [], reply_text(conn, head, r["upto_position"], before),
                      (r["query"] or "", r["previous_ai"] or "")) for r in rows]


_PAGE = 32  # traces read per step while collapsing rerolls: the ids first, the ledgers only of those kept
_NO_RUN = object()


def _distinct_positions(conn: psycopg.Connection, conversation: UUID, before: datetime | None, n: int,
                        exclude_position: int | None) -> list[dict[str, Any]]:
    """The newest trace of each run of consecutive traces at one `upto_position`, newest first, up to `n`; none at
    `exclude_position`. Pages through the trace ids (cheap columns), then reads the kept rows' ledgers."""
    kept: list[Any] = []
    run: object = _NO_RUN  # the position of the run of traces being read
    after: tuple[datetime, Any] | None = None  # the last trace read (keyset: a trace written meanwhile shifts nothing)
    while len(kept) < n:
        page = conn.execute(
            "SELECT id, upto_position, created_at FROM retrieval_trace WHERE conversation_id = %s AND lines IS NOT NULL"
            " AND (%s::timestamptz IS NULL OR created_at < %s)"
            " AND (%s::timestamptz IS NULL OR (created_at, id) < (%s, %s))"
            " ORDER BY created_at DESC, id DESC LIMIT %s",
            (conversation, before, before, after and after[0], after and after[0], after and after[1], _PAGE)).fetchall()
        for r in page:
            pos = r["upto_position"]
            if pos == run:
                continue  # an older attempt of the run already kept (or left out)
            run = pos
            if exclude_position is not None and pos == exclude_position:
                continue
            kept.append(r["id"])
            if len(kept) == n:
                break
        if len(page) < _PAGE:
            break
        after = (page[-1]["created_at"], page[-1]["id"])
    if not kept:
        return []
    rows = conn.execute("SELECT id, upto_position, query, previous_ai, lines FROM retrieval_trace WHERE id = ANY(%s)",
                        (kept,)).fetchall()
    by = {r["id"]: r for r in rows}
    return [by[i] for i in kept if i in by]


def exempt_from_rest(kind: str, predicate: str | None = None, settled: bool = False) -> bool:
    """Whether a line never rests (packet-v21, for the read side to apply): a thread that has just settled, or a fact
    of standing between two characters (how one addresses, feels toward, is related to or stands toward the other),
    which holds for every reply whether or not the reply echoed it. `kind` is the line's kind, kept for the caller's
    rules; it does not decide alone."""
    return settled or predicate in REST_EXEMPT_PREDICATES


REST_EXEMPT_PREDICATES = frozenset({"addresses", "feels_toward", "relationship", "role_toward"})


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


def placement(ledgers: list[list[dict[str, Any]]]) -> dict[str, Any]:
    """How much of a chat's packets came back request after request (PHASE-34 Q7, the Inspector; the overuse report's
    numbers): of a request's placed lines, the share placed in the request before too; of its placed tokens, the share
    on lines placed in each of the three before; the same on supportive lines when the ledgers carry labels. Oldest
    first."""
    placed = [{key(e["kind"], e.get("ref")): (int(e.get("tok") or 0), e.get("label")) for e in lines if e.get("placed")}
              for lines in ledgers]

    def shares(only: str | None) -> tuple[float | None, float | None]:
        rows = [{k: tok for k, (tok, label) in p.items() if only is None or label == only} for p in placed]
        sets = [set(p) for p in placed]
        repeat = [len(set(r) & sets[i - 1]) / len(r) for i, r in enumerate(rows) if i and r]
        stale = [sum(t for k, t in r.items() if all(k in sets[j] for j in (i - 1, i - 2, i - 3))) / (sum(r.values()) or 1)
                 for i, r in enumerate(rows) if i >= 3 and r]
        mean = lambda xs: round(sum(xs) / len(xs), 3) if xs else None
        return mean(repeat), mean(stale)

    whole = shares(None)
    out: dict[str, Any] = {"requests": len(placed), "repeat_share": whole[0], "stale_token_share": whole[1]}
    if any(label for p in placed for _, label in p.values()):
        sup = shares("supportive")
        out.update(supportive_repeat_share=sup[0], supportive_stale_token_share=sup[1])
    return out
