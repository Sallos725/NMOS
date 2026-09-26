"""Offline A/B of packet compilers over recorded requests (Phase 9, ADR 0027). Read-only.

Every request since migration 0020 records its inputs and a ledger of what its packet offered and held.
This replays the latest traces as of their own time (the head cut at the request's position, only the
extractions, vectors and owner links NMOS had then) under each policy and prints how they differ,
including how many of the lines the real reply echoed each policy keeps. The session is read-only, so
it is safe on a production database; point it at a copy anyway if you can.

    cd apps/sidecar && uv run python ../../tools/replay_packets.py --url postgresql://… [--limit 200]
        [--conversation <uuid>] [--policies packet-v0,packet-v1] [--no-vectors]

Vectors are searched only when the configured embedding projection (environment plus the settings saved
from the panel) is the one a trace used; otherwise that trace is replayed lexical-only and cannot count
as reproduced.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import psycopg
from psycopg.rows import dict_row

from nmos_sidecar import audit, runtime, vectors
from nmos_sidecar.config import Settings
from nmos_sidecar.llm import Embedder
from nmos_sidecar.packet import POLICIES
from nmos_sidecar.retrieval import RecallOptions, query_prefix


def options(conn: psycopg.Connection, use_vectors: bool) -> RecallOptions:
    cur = runtime.effective(Settings(), runtime.stored(conn))
    pj = vectors.projection(cur) if use_vectors else None
    emb = Embedder(cur.embed_url, cur.embed_model, cur.embed_api_key) if pj else None
    return RecallOptions(embedder=emb, embed_projection=pj.key if pj else "",
                         query_prefix=query_prefix(cur.embed_model, cur.embed_query_instruction))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--url", default=os.environ.get("NMOS_DATABASE_URL", Settings().database_url))
    ap.add_argument("--conversation")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--policies", default=",".join(POLICIES))
    ap.add_argument("--no-vectors", action="store_true")
    ap.add_argument("--json", action="store_true", help="print the raw report")
    args = ap.parse_args()
    policies = tuple(p for p in args.policies.split(",") if p)
    if unknown := [p for p in policies if p not in POLICIES]:
        sys.exit(f"unknown policy: {', '.join(unknown)}")
    with psycopg.connect(args.url, row_factory=dict_row, autocommit=True,
                         options="-c default_transaction_read_only=on") as conn:
        where = "lines IS NOT NULL AND freshness = 'fresh'"
        params: list = []
        if args.conversation:
            where += " AND conversation_id = %s"
            params.append(args.conversation)
        ids = [r["id"] for r in conn.execute(f"SELECT id FROM retrieval_trace WHERE {where}"
                                             " ORDER BY created_at DESC LIMIT %s", (*params, args.limit))]
        report = audit.compare(conn, ids, options(conn, not args.no_vectors), policies)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return
    print(f"{report['traces']} recorded requests; skipped: {report['skipped'] or 'none'}\n")
    print("| Policy | packets | mean tokens | placed (by kind) | excerpt in / offered | reply-echoed lines kept"
          " | lines the recorded packet did not hold | reproduced (same policy) |")
    print("|---|---:|---:|---|---:|---:|---:|---:|")
    for p, s in report["policies"].items():
        placed = ", ".join(f"{k} {n}" for k, n in sorted(s["placed"].items()))
        repro = f"{s['reproduced']}/{s['replayed_same_policy']}" if s["replayed_same_policy"] else "—"
        print(f"| {p} | {s['packets']} | {s['tokens_mean']} | {placed} | {s['excerpt_placed']}/{s['excerpt_offered']}"
              f" | {s['echo_kept']}/{s['echoed_recorded']} | {s['new_lines']} | {repro} |")


if __name__ == "__main__":
    main()
