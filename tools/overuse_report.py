"""The overuse baseline (PHASE-33 Q8): how often the same memory reaches the packet request after request, and whether
the reply echoes it. A report, not a ranking input; Phase 34's penalty is measured against it. Read-only; numbers only.

    cd apps/sidecar
    uv run python ../../tools/overuse_report.py --db postgresql://…/copy [--conversation ID] [--json]

Per conversation, over its recorded requests in the order they were made (the packet ledger, ADR 0027):

- `repeat_share`: of the lines placed in a request, the share also placed in the request before it;
- `streak_p50`, `streak_p90`, `streak_max`: how many requests in a row a line stayed placed (each run counted once);
- `stale_token_share`: of a request's placed tokens, the share spent on lines placed in each of the three requests
  before it, averaged over the requests that have three before them;
- `echo_new`, `echo_repeat`: of the placed lines the next reply could be checked against (`audit.reply_after`), the
  share the reply echoed (`spans.reuse`, ADR 0027), for lines new to the packet and for lines repeated from the
  request before.

A line is its kind and its ledger `ref` (a fact, a repair, an excerpt's revision); a line without one is its kind and
text. Requests whose story changed since cannot be checked for echo and count only toward the other numbers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
from collections import defaultdict
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from nmos_sidecar import audit
from nmos_sidecar.config import Settings


def line_key(e: dict[str, Any]) -> tuple[str, str]:
    ref = e.get("ref")
    if ref is not None:
        return str(e.get("kind")), str(ref)
    text = (e.get("content") or e.get("text") or "").encode()
    return str(e.get("kind")), "t:" + hashlib.sha256(text).hexdigest()[:16]


def pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, int(q * len(s)))]


def conversation_report(conn: psycopg.Connection, conv: UUID) -> dict[str, Any]:
    traces = conn.execute(
        "SELECT id, lines FROM retrieval_trace WHERE conversation_id = %s AND lines IS NOT NULL ORDER BY created_at",
        (conv,)).fetchall()
    placed_sets: list[set[tuple[str, str]]] = []
    tokens: list[dict[tuple[str, str], int]] = []
    for t in traces:
        placed = {line_key(e): int(e.get("tok") or 0) for e in t["lines"] or [] if e.get("placed")}
        placed_sets.append(set(placed))
        tokens.append(placed)

    repeats = [len(s & placed_sets[i - 1]) / len(s) for i, s in enumerate(placed_sets) if i and s]
    streaks: list[int] = []
    run: dict[tuple[str, str], int] = defaultdict(int)
    for s in placed_sets:
        for k in list(run):
            if k not in s:
                streaks.append(run.pop(k))
        for k in s:
            run[k] += 1
    streaks.extend(run.values())
    stale = []
    for i in range(3, len(tokens)):
        total = sum(tokens[i].values())
        if total:
            kept = sum(v for k, v in tokens[i].items() if all(k in placed_sets[j] for j in (i - 1, i - 2, i - 3)))
            stale.append(kept / total)

    echo = {"new": [0, 0], "repeat": [0, 0]}
    checked = 0
    for i, t in enumerate(traces):
        result = audit.audit(conn, t["id"])
        if result is None or result["summary"].get("reply") != "ok":
            continue
        checked += 1
        for e in result["lines"]:
            if not e.get("placed"):
                continue
            kind = "repeat" if i and line_key(e) in placed_sets[i - 1] else "new"
            echo[kind][0] += 1
            echo[kind][1] += bool(e.get("echoed"))

    def share(pair: list[int]) -> float | None:
        return round(pair[1] / pair[0], 3) if pair[0] else None

    return {
        "requests": len(traces), "echo_checked": checked,
        "repeat_share": round(statistics.mean(repeats), 3) if repeats else None,
        "streak_p50": pct(streaks, 0.5), "streak_p90": pct(streaks, 0.9), "streak_max": max(streaks, default=None),
        "stale_token_share": round(statistics.mean(stale), 3) if stale else None,
        "echo_new": share(echo["new"]), "echo_repeat": share(echo["repeat"]),
        "lines_new": echo["new"][0], "lines_repeat": echo["repeat"][0],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=os.environ.get("NMOS_DATABASE_URL", Settings().database_url))
    ap.add_argument("--conversation", help="one conversation's id (default: every one with recorded requests)")
    ap.add_argument("--min-requests", type=int, default=5, help="skip conversations with fewer recorded requests")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    with psycopg.connect(a.db, row_factory=dict_row) as conn:
        conn.execute("SET default_transaction_read_only = on")
        ids = [UUID(a.conversation)] if a.conversation else [r["conversation_id"] for r in conn.execute(
            "SELECT conversation_id FROM retrieval_trace WHERE lines IS NOT NULL GROUP BY 1 HAVING count(*) >= %s",
            (a.min_requests,)).fetchall()]
        out = {str(c)[-8:]: conversation_report(conn, c) for c in ids}
    if a.json:
        json.dump(out, sys.stdout, indent=1)
        return
    cols = ("requests", "repeat_share", "streak_p50", "streak_p90", "streak_max", "stale_token_share", "echo_new",
            "echo_repeat", "echo_checked")
    print("conversation " + " ".join(f"{c:>17}" for c in cols))
    for conv, r in out.items():
        print(f"{conv:<12} " + " ".join(f"{str(r[c]):>17}" for c in cols))


if __name__ == "__main__":
    main()
