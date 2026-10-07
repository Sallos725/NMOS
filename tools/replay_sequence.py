"""A chat's recorded requests compiled again in the order they were made (PHASE-34 Q8 b): how often the same memory
holds the packet request after request, under a policy, without a model call. Read-only; numbers only.

    cd apps/sidecar
    uv run python ../../tools/replay_sequence.py --db postgresql://…/copy --policy packet-v14 [--conversation ID]
        [--no-vectors] [--json]

Every request of the chat with a ledger is replayed (`audit.replay`, ADR 0027) under `--policy`, oldest first; the
overuse report's numbers (`tools/overuse_report.py`: repeat share, streaks, stale token share) are computed on the
replayed packets, so two policies are compared on the same requests. Echo is not computed: the replies were written
for the recorded packets. Under `packet-v14` the share of placed lines and tokens by label (PHASE-34 Q1) is reported
too. A request that cannot be replayed (the story before it changed) is skipped and counted.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_rp import options as recall_options, warm  # noqa: E402
from overuse_report import line_key, pct  # noqa: E402

from nmos_sidecar import audit  # noqa: E402


def overuse(packets: list[dict[tuple[str, str], int]]) -> dict[str, Any]:
    """The overuse report's placement numbers on a sequence of packets (line key → tokens placed)."""
    sets = [set(p) for p in packets]
    repeats = [len(s & sets[i - 1]) / len(s) for i, s in enumerate(sets) if i and s]
    streaks: list[int] = []
    run: dict[tuple[str, str], int] = defaultdict(int)
    for s in sets:
        for k in list(run):
            if k not in s:
                streaks.append(run.pop(k))
        for k in s:
            run[k] += 1
    streaks.extend(run.values())
    stale = []
    for i in range(3, len(packets)):
        total = sum(packets[i].values())
        if total:
            kept = sum(v for k, v in packets[i].items() if all(k in sets[j] for j in (i - 1, i - 2, i - 3)))
            stale.append(kept / total)
    return {"requests": len(packets),
            "repeat_share": round(statistics.mean(repeats), 3) if repeats else None,
            "streak_p50": pct(streaks, 0.5), "streak_p90": pct(streaks, 0.9), "streak_max": max(streaks, default=None),
            "stale_token_share": round(statistics.mean(stale), 3) if stale else None,
            "mean_tokens": round(statistics.mean(sum(p.values()) for p in packets), 1) if packets else None}


def sequence(conn: psycopg.Connection, conv: UUID, policy: str, opts: Any) -> dict[str, Any]:
    traces = conn.execute("SELECT id FROM retrieval_trace WHERE conversation_id = %s AND lines IS NOT NULL"
                          " ORDER BY created_at", (conv,)).fetchall()
    packets: list[dict[tuple[str, str], int]] = []
    labels: Counter = Counter()
    label_tokens: Counter = Counter()
    repeated: Counter = Counter()  # lines placed again from the request before, by label
    stale_tokens: Counter = Counter()  # tokens on lines placed in each of the three requests before, by label
    label_of: list[dict[tuple[str, str], str]] = []
    skipped = 0
    for t in traces:
        out = audit.replay(conn, t["id"], opts, policy)
        if out is None or out.get("status") != "ok":
            skipped += 1
            continue
        placed = [e for e in out["lines"] if e.get("placed")]
        packets.append({line_key(e): int(e.get("tok") or 0) for e in placed})
        label_of.append({line_key(e): e.get("label") or "" for e in placed})
        for e in placed:
            if e.get("label"):
                labels[e["label"]] += 1
                label_tokens[e["label"]] += int(e.get("tok") or 0)
        i = len(packets) - 1
        for k, tok in packets[i].items():
            if i and k in packets[i - 1]:
                repeated[label_of[i][k]] += 1
            if i >= 3 and all(k in packets[j] for j in (i - 1, i - 2, i - 3)):
                stale_tokens[label_of[i][k]] += tok
    report = overuse(packets) | {"skipped": skipped, "policy": policy}
    if labels:
        n, tok = sum(labels.values()), sum(label_tokens.values()) or 1
        rep, st = sum(repeated.values()) or 1, sum(stale_tokens.values()) or 1
        report["labels"] = {k: {"lines": round(v / n, 3), "tokens": round(label_tokens[k] / tok, 3),
                                "of_repeats": round(repeated[k] / rep, 3), "of_stale_tokens": round(stale_tokens[k] / st, 3)}
                            for k, v in sorted(labels.items())}
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", required=True)
    ap.add_argument("--policy", required=True)
    ap.add_argument("--conversation", help="one conversation's id (default: the one with the most recorded requests)")
    ap.add_argument("--no-vectors", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    with psycopg.connect(a.db, row_factory=dict_row) as conn:
        conn.execute("SET default_transaction_read_only = on")
        conv = UUID(a.conversation) if a.conversation else conn.execute(
            "SELECT conversation_id FROM retrieval_trace WHERE lines IS NOT NULL GROUP BY 1 ORDER BY count(*) DESC"
            " LIMIT 1").fetchone()["conversation_id"]
        opts = recall_options(conn, not a.no_vectors)
        warm(opts)
        report = {"conversation": str(conv)[-8:]} | sequence(conn, conv, a.policy, opts)
    if a.json:
        json.dump(report, sys.stdout, indent=1)
        return
    for k, v in report.items():
        print(f"{k:>18}: {v}")


if __name__ == "__main__":
    main()
