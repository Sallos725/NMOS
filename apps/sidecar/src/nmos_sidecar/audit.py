"""Packet audit (ADR 0027): what a request's packet held, whether the reply that followed echoed it, and
the same request compiled again as of the moment it was answered (replay).

Every retrieval records a ledger: each line it offered (state, thread, fact, claim, excerpt), with its
provenance, its cost, whether it was placed and why not. Three things follow from the ledger and the
immutable source ledger, without a model call:

- **Echo.** The reply to a request is the message right after the request's last position. A line is
  echoed when the reply reuses a span of its content (the words it adds beyond names) that the request
  itself did not contain. For Korean (or other CJK) content that is a run of 4 characters, spaces
  ignored, whose first or last 3 characters occur in neither the user's message nor the previous reply
  (so a word of the question with another particle does not count); for Latin-script content, a word of
  at least 4 letters, not a common one, that neither of them holds. Replies reuse the key
  phrase, not the line ("보라일곱이야" for an excerpt of two sentences), so a share of the whole line would
  miss them (measured, docs/perf/phase9-packets.md). It is a surface measure of use: a line can matter
  without being echoed (a secret the reply rightly keeps), and a reply can repeat what the prompt held
  anyway. Placed secrets that are echoed are flagged, since that may be a leak (K11). Never used for
  ranking in Phase 9.
- **Replay.** A trace records its inputs: query, previous reply, the ids the prompt already held, budget,
  recall options, generations and the head position. Gathering again with the head cut at that position
  and only what NMOS had derived by the trace's time reproduces the packet, as long as the story before
  that position is unchanged. The same inputs can be compiled by another policy: an offline A/B of
  memory selection on real requests.
- **Report.** Over many traces, how two policies differ: tokens, what they place, how often an excerpt
  gets in, and how many of the lines the real reply echoed each policy keeps.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg

from . import spans
from .packet import POLICIES, compile_lines
from .retrieval import RECORDED, RecallOptions, gather

echo, echoed = spans.reuse, spans.reused


def prefix_intact(conn: psycopg.Connection, conversation: UUID, commit: UUID, head: UUID, upto: int) -> bool:
    """Whether the head still shows the story up to `upto` exactly as `commit` did: it is `commit`, or
    descends from it through commits that changed only later positions (a reroll of the reply, an edit
    after the request). Appends never change earlier positions."""
    if commit == head:
        return True
    rows = {r["id"]: r for r in conn.execute(
        "SELECT id, parent_commit_ids, delta FROM worldline_commit WHERE conversation_id = %s", (conversation,))}
    at = rows.get(head)
    while at is not None and at["id"] != commit:
        if any((c.get("position") if c.get("position") is not None else -1) <= upto
               for c in (at["delta"] or {}).get("changes", [])):
            return False
        at = rows.get(at["parent_commit_ids"][0]) if at["parent_commit_ids"] else None
    return at is not None


def _trace(conn: psycopg.Connection, trace_id: UUID) -> dict[str, Any] | None:
    return conn.execute(
        "SELECT t.*, c.head_commit_id FROM retrieval_trace t JOIN conversation c ON c.id = t.conversation_id"
        " WHERE t.id = %s", (trace_id,)).fetchone()


def reply_after(conn: psycopg.Connection, t: dict[str, Any]) -> tuple[str, str | None]:
    """(status, reply text) for a trace: `ok`, `pending` (no reply on the head yet), `not_a_reply` (the
    next message is not the character's), `changed` (the story up to the request changed since) or
    `not_recorded` (a trace from before migration 0020)."""
    if t.get("upto_position") is None or t.get("commit_id") is None:
        return "not_recorded", None
    head = t["head_commit_id"]
    if head is None or not prefix_intact(conn, t["conversation_id"], t["commit_id"], head, t["upto_position"]):
        return "changed", None
    row = conn.execute(
        "SELECT sr.metadata->>'role' AS role, rt.clean_content FROM active_membership am"
        " JOIN source_revision sr ON sr.id = am.source_revision_id"
        " LEFT JOIN revision_text rt ON rt.source_revision_id = sr.id"
        " WHERE am.commit_id = %s AND am.position = %s ORDER BY rt.normalizer DESC LIMIT 1",
        (head, t["upto_position"] + 1)).fetchone()
    if row is None:
        return "pending", None
    if row["role"] != "char":
        return "not_a_reply", None
    return "ok", row["clean_content"] or ""


def audit(conn: psycopg.Connection, trace_id: UUID) -> dict[str, Any] | None:
    """The trace's ledger with each line's echo in the reply that followed, and a summary."""
    t = _trace(conn, trace_id)
    if t is None:
        return None
    status, reply = reply_after(conn, t)
    lines = [dict(e) for e in t.get("lines") or []]
    summary = {"offered": len(lines), "placed": sum(e["placed"] for e in lines), "reply": status}
    if reply is not None:
        request = (t.get("query"), t.get("previous_ai"))
        for e in lines:
            e["echo"] = round(echo(e.get("content") or e.get("text"), reply, request), 3)
            e["echoed"] = e["echo"] > 0
            if e["echoed"] and e["placed"] and (e.get("marks") or {}).get("hidden_from"):
                e["possible_leak"] = True
        summary.update(
            placed_echoed=sum(1 for e in lines if e["placed"] and e["echoed"]),
            unplaced_echoed=sum(1 for e in lines if not e["placed"] and e["echoed"]),
            possible_leaks=sum(1 for e in lines if e.get("possible_leak")))
    return {"trace": str(t["id"]), "policy": t.get("policy"), "budget_tokens": t.get("budget_tokens"),
            "tokens": t["token_estimate"], "summary": summary, "lines": lines}


def _same(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> bool:
    keys = ("kind", "ref", "turn", "tok", "placed", "why", "text", "form")
    return [{k: x.get(k) for k in keys} for x in a] == [{k: x.get(k) for k in keys} for x in b]


def replay(conn: psycopg.Connection, trace_id: UUID, options: RecallOptions, policy: str | None = None,
           known_at: datetime | None = None, **overrides: Any) -> dict[str, Any] | None:
    """Compile a recorded request again, as of its time, with its own recall options, generations and
    budget; `policy` and `overrides` (RecallOptions fields) change what is being tested. `options` gives
    the embedder: vectors are searched only when it serves the trace's projection. Read-only."""
    t = _trace(conn, trace_id)
    if t is None:
        return None
    if t.get("lines") is None or t.get("upto_position") is None:
        return {"trace": str(t["id"]), "status": "not_recorded"}
    if t["head_commit_id"] is None or not prefix_intact(conn, t["conversation_id"], t["commit_id"],
                                                         t["head_commit_id"], t["upto_position"]):
        return {"trace": str(t["id"]), "status": "changed"}
    policy = policy or t["policy"]
    if policy not in POLICIES:
        raise ValueError(f"unknown packet policy: {policy}")
    notes: list[str] = []
    recorded = {k: v for k, v in (t.get("recall_options") or {}).items() if k in RECORDED}
    opts = dataclasses.replace(options, **recorded, extractor_key=t["extractor_key"],
                               rules_version=t["rules_version"] or "none", policy=policy)
    if t["embed_projection"] and not (options.embedder is not None and options.embed_projection == t["embed_projection"]):
        opts = dataclasses.replace(opts, embedder=None)
        notes.append("vectors of the trace's projection unavailable: lexical only")
    elif not t["embed_projection"]:
        opts = dataclasses.replace(opts, embedder=None)
    if overrides:
        opts = dataclasses.replace(opts, **overrides)
        notes.append("options changed: " + ", ".join(sorted(overrides)))
    g = gather(conn, t["head_commit_id"], t["query"], t["previous_ai"] or "", set(t["in_context"] or []), opts,
               upto=t["upto_position"], known_at=known_at or t["created_at"])
    if opts.embedder is not None and g.vector_note != "on":
        notes.append(f"vectors {g.vector_note}")  # an embedder that failed now cannot reproduce the request
    c = compile_lines(g.ranked, t["budget_tokens"], state=g.state, threads=g.threads, facts=g.facts, policy=policy,
                      lead=g.lead)
    out = {"trace": str(t["id"]), "status": "ok", "policy": policy, "recorded_policy": t["policy"],
           "text": c.text, "tokens": c.tokens, "lines": c.ledger, "notes": notes}
    if policy == t["policy"] and not notes:
        out["reproduced"] = _same(c.ledger, t["lines"])
    return out


def _key(e: dict[str, Any]) -> tuple:
    return (e["kind"], tuple(sorted((e.get("ref") or {}).items())))


def compare(conn: psycopg.Connection, trace_ids: list[UUID], options: RecallOptions,
            policies: tuple[str, ...] = POLICIES) -> dict[str, Any]:
    """Replay each trace under each policy and aggregate (ADR 0027): the offline A/B. Lines are matched
    by provenance. `echo_kept` counts, over traces whose reply is on the head, the lines the recorded
    packet placed and the reply echoed, and how many of them each policy places (a policy cannot be
    credited for lines the real reply never had the chance to use: those are counted as `new_lines`)."""
    per: dict[str, dict[str, Any]] = {p: {"packets": 0, "tokens": 0, "placed": {}, "excerpt_offered": 0,
                                          "excerpt_placed": 0, "echoed_recorded": 0, "echo_kept": 0,
                                          "new_lines": 0, "reproduced": 0, "replayed_same_policy": 0}
                                      for p in policies}
    skipped: dict[str, int] = {}
    for tid in trace_ids:
        a = audit(conn, tid)
        runs = {p: replay(conn, tid, options, p) for p in policies}
        if any(r is None or r["status"] != "ok" for r in runs.values()):
            status = next(r["status"] if r else "missing" for r in runs.values() if r is None or r["status"] != "ok")
            skipped[status] = skipped.get(status, 0) + 1
            continue
        recorded_placed = {_key(e) for e in a["lines"] if e["placed"]} if a else set()
        echoed = {_key(e) for e in a["lines"] if e["placed"] and e.get("echoed")} if a else set()
        for p, r in runs.items():
            s = per[p]
            placed = [e for e in r["lines"] if e["placed"]]
            keys = {_key(e) for e in placed}
            s["packets"] += 1
            s["tokens"] += r["tokens"]
            for e in placed:
                s["placed"][e["kind"]] = s["placed"].get(e["kind"], 0) + 1
            if any(e["kind"] == "excerpt" for e in r["lines"]):
                s["excerpt_offered"] += 1
                s["excerpt_placed"] += any(e["kind"] == "excerpt" for e in placed)
            s["echoed_recorded"] += len(echoed)
            s["echo_kept"] += len(echoed & keys)
            s["new_lines"] += len(keys - recorded_placed)
            if "reproduced" in r:
                s["replayed_same_policy"] += 1
                s["reproduced"] += bool(r["reproduced"])
    for s in per.values():
        s["tokens_mean"] = round(s["tokens"] / s["packets"]) if s["packets"] else 0
    return {"traces": len(trace_ids), "skipped": skipped, "policies": per}
