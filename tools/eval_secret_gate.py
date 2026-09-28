"""The Phase 12 secret gate (docs/phases/PHASE-12.md, acceptance): no summary tells a secret to the one it is kept from.

Each case (outside the repository, confirmed with the owner) is a probe at a recorded request, addressed to a character
a secret is kept from, with the words that would tell it. The request is compiled again (ADR 0027 replay, as of now,
with the given extractor and summarize generations) under `packet-v8`, and the gate fails when any of the words is in
its `<Story>`. A case can split its words by secret (`groups`: the secret turns and their words); the words of a
group whose secrets the character has found out by the scene's turn — in the story or by the owner's repairs
(ADR 0044) — are told, not forbidden, and are reported apart. For comparison the tool also reports where the words already stood outside `<Private>` in the rest of
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
from nmos_sidecar.facts import memory_view
from nmos_sidecar.retrieval import RecallOptions

STORY = re.compile(r"<Story>.*?</Story>", re.S)
PRIVATE = re.compile(r"<Private>.*?</Private>", re.S)


def hits(text: str, words: list[str]) -> list[str]:
    folded = " ".join(text.casefold().split())
    return [w for w in words if " ".join(w.casefold().split()) in folded]


def groups(case: dict[str, Any]) -> list[dict[str, Any]]:
    """A case's words by secret: its `groups`, or all its `forbidden` words as one group that is never told."""
    return case.get("groups") or [{"turns": [], "forbidden": case["forbidden"]}]


def words(case: dict[str, Any], told: list[bool]) -> tuple[list[str], list[str]]:
    """(the words still forbidden, the words of secrets the character knows by the scene)."""
    live: list[str] = []
    known: list[str] = []
    for g, t in zip(groups(case), told):
        (known if t else live).extend(g["forbidden"])
    return live, known


def told_group(turns: list[int], secrets: list[dict[str, Any]], who: str, key: Any, scene: int | None) -> bool:
    """Whether the character has found out every secret of these turns kept from them by the scene's turn. Each listed
    turn must hold such a secret: a group NMOS cannot account for fully stays forbidden."""
    mine = [s for s in secrets if s["turn"] in turns and who in {key(n) for n in s["kept_from"]}]
    if not turns or not set(turns) <= {s["turn"] for s in mine} or scene is None:
        return False
    return all(any(key(n) == who and e.get("turn") is not None and e["turn"] <= scene for n, e in s["ended"].items())
               for s in mine)


def told(conn: psycopg.Connection, case: dict[str, Any], extractor: str) -> list[bool]:
    """For each group: whether the case's character has found out its secrets by the scene's turn (the request's last
    message), as memory reads now up to that message (the replay's prefix, which it checks is unchanged)."""
    t = conn.execute("SELECT t.upto_position, c.head_commit_id FROM retrieval_trace t"
                     " JOIN conversation c ON c.id = t.conversation_id WHERE t.id = %s", (UUID(case["trace"]),)).fetchone()
    scene = conn.execute("SELECT max(turn) AS t FROM active_membership WHERE commit_id = %s AND position <= %s",
                         (t["head_commit_id"], t["upto_position"])).fetchone()["t"]
    view = memory_view(conn, t["head_commit_id"], extractor, upto=t["upto_position"])
    r = view["resolution"]
    key = (lambda n: r.key("character", n)) if r else (lambda n: n)
    return [told_group(g["turns"], view["secrets"], key(case["kept_from"]), key, scene) for g in groups(case)]


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
    live, known = words(case, told(conn, case, extractor))
    return {"name": case["name"], "status": "ok", "kept_from": case.get("kept_from"), "story_present": bool(story),
            "in_story": hits(story, live), "told_in_story": hits(story, known), "in_rest_v8": hits(rest, live),
            "in_v6": hits(PRIVATE.sub("", v6["text"]), live), "passed": not hits(story, live)}


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
        print("| case | kept from | <Story> | words in <Story> | found out by the scene, in <Story> | elsewhere, packet-v8 |"
              " outside Private, packet-v6 |")
        print("|---|---|---|---|---|---|---|")
        for r in results:
            if r["status"] != "ok":
                print(f"| {r['name']} | — | {r['status']} | | | | |")
                continue
            print(f"| {r['name']} | {r['kept_from']} | {'yes' if r['story_present'] else 'no'} | "
                  f"{', '.join(r['in_story']) or '—'} | {', '.join(r['told_in_story']) or '—'} | "
                  f"{', '.join(r['in_rest_v8']) or '—'} | {', '.join(r['in_v6']) or '—'} |")
        passed = sum(1 for r in results if r.get("passed"))
        print(f"\ngate: {passed} of {len(results)} cases with no forbidden word in <Story>")
    sys.exit(0 if all(r.get("passed") for r in results) else 1)


if __name__ == "__main__":
    main()
