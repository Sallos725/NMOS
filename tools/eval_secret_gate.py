"""The Phase 12 secret gate (docs/phases/PHASE-12.md, acceptance): no summary tells a secret to the one it is kept from.

Each case (outside the repository, confirmed with the owner) is a probe at a recorded request, addressed to a character
a secret is kept from, with the words that would tell it. The request is compiled again (ADR 0027 replay, as of now,
with the given extractor and summarize generations) under `packet-v8`, and the gate fails when any of the words is in
its `<Story>`. For comparison the tool also reports where the words already stood outside `<Private>` in the rest of
that packet and in the `packet-v6` packet of the same request (facts and excerpts, before any summary). Read-only;
point it at a restored backup (PHASE-11 Q1).

    cd apps/sidecar && uv run python ../../tools/eval_secret_gate.py DIR --db postgresql://…/copy \\
        --extractor KEY --summarizer KEY [--budget 2000] [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from nmos_sidecar import audit
from nmos_sidecar.retrieval import RecallOptions

STORY = re.compile(r"<Story>.*?</Story>", re.S)
PRIVATE = re.compile(r"<Private>.*?</Private>", re.S)


def hits(text: str, words: list[str]) -> list[str]:
    folded = " ".join(text.casefold().split())
    return [w for w in words if " ".join(w.casefold().split()) in folded]


def check(conn: psycopg.Connection, case: dict[str, Any], extractor: str, summarizer: str,
          budget: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    common = {"known_at": now, "query": case["query"], "budget": budget, "extractor_key": extractor}
    v8 = audit.replay(conn, UUID(case["trace"]), RecallOptions(), "packet-v8", summarize_key=summarizer, **common)
    v6 = audit.replay(conn, UUID(case["trace"]), RecallOptions(), "packet-v6", **common)
    if not v8 or v8["status"] != "ok" or not v6 or v6["status"] != "ok":
        return {"name": case["name"], "status": (v8 or {}).get("status", "missing")}
    story = "".join(STORY.findall(v8["text"]))
    rest = PRIVATE.sub("", STORY.sub("", v8["text"]))
    return {"name": case["name"], "status": "ok", "kept_from": case.get("kept_from"), "story_present": bool(story),
            "in_story": hits(story, case["forbidden"]), "in_rest_v8": hits(rest, case["forbidden"]),
            "in_v6": hits(PRIVATE.sub("", v6["text"]), case["forbidden"]),
            "passed": not hits(story, case["forbidden"])}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("dir", type=Path)
    ap.add_argument("--db", required=True)
    ap.add_argument("--extractor", required=True)
    ap.add_argument("--summarizer", required=True)
    ap.add_argument("--budget", type=int, default=2000)
    ap.add_argument("--json", action="store_true", help="per-case results (names and matched words only)")
    args = ap.parse_args()
    cases = json.loads((args.dir / "cases.json").read_text(encoding="utf-8"))
    with psycopg.connect(args.db, row_factory=dict_row, autocommit=True,
                         options="-c default_transaction_read_only=on") as conn:
        results = [check(conn, c, args.extractor, args.summarizer, args.budget) for c in cases]
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print("| case | kept from | <Story> | words in <Story> | elsewhere, packet-v8 | outside Private, packet-v6 |")
        print("|---|---|---|---|---|---|")
        for r in results:
            if r["status"] != "ok":
                print(f"| {r['name']} | — | {r['status']} | | | |")
                continue
            print(f"| {r['name']} | {r['kept_from']} | {'yes' if r['story_present'] else 'no'} | "
                  f"{', '.join(r['in_story']) or '—'} | {', '.join(r['in_rest_v8']) or '—'} | {', '.join(r['in_v6']) or '—'} |")
        passed = sum(1 for r in results if r.get("passed"))
        print(f"\ngate: {passed} of {len(results)} cases with no forbidden word in <Story>")
    sys.exit(0 if all(r.get("passed") for r in results) else 1)


if __name__ == "__main__":
    main()
