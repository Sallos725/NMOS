"""M0, the RP evaluation on real chats (PHASE-11 step 2): does the packet a real request gets hold what its scene
needs, and keep out what it must not? Read-only; point it at a restored backup (PHASE-11 Q1).

The cases are the owner's chats and stay outside the repository; the report prints numbers only.

    cd apps/sidecar
    uv run python ../../tools/eval_rp.py DIR --db postgresql://…/copy [--extractor KEY] [--policy P] [--budget N]
        [--no-vectors] [--json]

DIR/cases.json:

    [{"name": "goal-1", "category": "goal", "trace": "<a recorded request of the chat>",
      "query": "<optional: a probe in place of the request's user message>",
      "gold": ["<a phrase the packet must hold>", ["<a phrase>", "<or another wording of it>"]],
      "forbidden": ["<a phrase it must not hold: stale, irrelevant, kept from the one asking>"]}]

A case passes when the packet holds every gold phrase (any wording of it) and no forbidden one; phrases match
case- and space-insensitively. Categories are free text; PHASE-11 uses state, past, promise, goal, question,
threat, debt, relationship, address, secret, why and irrelevant. The request is compiled again as of its own
time (ADR 0027 replay); `--extractor` names a newer extractor generation, and the request is then compiled as
of now with that generation's facts, as `eval_secrets.py build` does; `--policy` and `--budget` replace the
request's own (a request recorded before the default reserve rose to 800 carries 600). A request whose chat was
edited before its position since cannot be replayed and is counted as skipped.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from nmos_sidecar import audit, runtime, vectors
from nmos_sidecar.config import Settings
from nmos_sidecar.llm import Embedder
from nmos_sidecar.retrieval import RecallOptions, query_prefix


def norm(text: str) -> str:
    return " ".join(text.casefold().split())


def score(case: dict[str, Any], text: str) -> dict[str, Any]:
    """How a packet's text answers one case: gold phrases held, forbidden ones placed, pass."""
    held, packet = [], norm(text)
    for phrase in case.get("gold") or []:
        wordings = [phrase] if isinstance(phrase, str) else list(phrase)
        held.append(any(norm(w) in packet for w in wordings if w.strip()))
    placed = [norm(p) in packet for p in case.get("forbidden") or [] if p.strip()]
    return {"gold": len(held), "held": sum(held), "forbidden": len(placed), "placed": sum(placed),
            "passed": all(held) and not any(placed)}


def options(conn: psycopg.Connection, use_vectors: bool) -> RecallOptions:
    cur = runtime.effective(Settings(), runtime.stored(conn))
    pj = vectors.projection(cur) if use_vectors else None
    emb = Embedder(cur.embed_url, cur.embed_model, cur.embed_api_key) if pj else None
    return RecallOptions(embedder=emb, embed_projection=pj.key if pj else "",
                         query_prefix=query_prefix(cur.embed_model, cur.embed_query_instruction))


def evaluate(conn: psycopg.Connection, cases: list[dict[str, Any]], opts: RecallOptions, policy: str | None = None,
             extractor: str | None = None, budget: int | None = None) -> dict[str, Any]:
    """Every case's numbers, and a summary per category and overall. Read-only."""
    results: list[dict[str, Any]] = []
    overrides = {"extractor_key": extractor} if extractor else {}
    known_at = datetime.now(timezone.utc) if extractor else None
    for case in cases:
        out = audit.replay(conn, UUID(case["trace"]), opts, policy, known_at=known_at, query=case.get("query"),
                           budget=budget, **overrides)
        row = {"name": case["name"], "category": case.get("category") or "other"}
        if out is None or out["status"] != "ok":
            results.append({**row, "status": "missing" if out is None else out["status"]})
            continue
        results.append({**row, "status": "ok", "tokens": out["tokens"], "policy": out["policy"], **score(case, out["text"])})
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in results:
        groups[r["category"]].append(r)
        groups["all"].append(r)
    summary = {}
    for name, rows in groups.items():
        ok = [r for r in rows if r["status"] == "ok"]
        summary[name] = {"cases": len(rows), "skipped": len(rows) - len(ok), "passed": sum(r["passed"] for r in ok),
                         "gold": sum(r["gold"] for r in ok), "held": sum(r["held"] for r in ok),
                         "forbidden": sum(r["forbidden"] for r in ok), "placed": sum(r["placed"] for r in ok),
                         "tokens_mean": round(sum(r["tokens"] for r in ok) / len(ok)) if ok else None}
    return {"cases": results, "summary": summary}


def table(report: dict[str, Any]) -> str:
    """The summary as a markdown table: numbers only, no phrase of any case."""
    rows = ["| Category | cases | passed | gold held | forbidden placed | skipped | mean tokens |",
            "|---|---:|---:|---:|---:|---:|---:|"]
    for name, s in sorted(report["summary"].items(), key=lambda kv: (kv[0] == "all", kv[0])):
        rows.append(f"| {name} | {s['cases']} | {s['passed']} | {s['held']}/{s['gold']} | {s['placed']}/{s['forbidden']}"
                    f" | {s['skipped']} | {s['tokens_mean'] if s['tokens_mean'] is not None else '—'} |")
    return "\n".join(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("dir", type=Path, help="the case directory (outside the repository)")
    ap.add_argument("--db", default=os.environ.get("NMOS_DATABASE_URL", Settings().database_url))
    ap.add_argument("--extractor", help="a newer extractor generation's key: compile as of now with its facts")
    ap.add_argument("--policy", help="a packet policy in place of each request's own")
    ap.add_argument("--budget", type=int, help="a memory budget (tokens) in place of each request's own")
    ap.add_argument("--no-vectors", action="store_true")
    ap.add_argument("--json", action="store_true", help="per-case numbers as JSON (names and counts only)")
    args = ap.parse_args()
    cases = json.loads((args.dir / "cases.json").read_text(encoding="utf-8"))
    with psycopg.connect(args.db, row_factory=dict_row, autocommit=True,
                         options="-c default_transaction_read_only=on") as conn:
        report = evaluate(conn, cases, options(conn, not args.no_vectors), args.policy, args.extractor, args.budget)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(table(report))
    sys.exit(0)


if __name__ == "__main__":
    main()
